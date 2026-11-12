#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
review-risk.py — classifies a review snapshot's change by risk: the tier, why, what a human must approve,
which security reviewers must be handed the change, and which model the review lenses run on.

Owns one thing: the mechanical risk rules of the review model (docs/design-notes.md, "Review model",
section 2). It only adds scrutiny: it never lowers lens coverage, never reads author labels or commit
messages, and never reads or changes an external-review setting. It reads the snapshot that
core/scripts/review-snapshot.py wrote and the repository's git objects; it writes nothing.

    classify DIR [--json]

The snapshot must still verify (the candidate is recomputed first; a changed one exits 3). Each rule is
matched by path and by the added or removed lines between the base and the candidate (whole files for an
added or deleted path; binary files and files over 2 MB are matched by path only):

    policy-file          a policy file changed (the snapshot's policy_changed)          approval, high
    ci-automation        .github/, .gitlab-ci.yml, buildspec*.yml, Jenkinsfile, .claude/, hooks/,
                         *settings*.json, .claude-plugin/                                approval, high
    specification        a specification file changed (docs/specifications/, specification/,
                         ai-planning/<feature>.md) and the snapshot holds no plan        approval
    security             IAM policy documents or statements, Principal, sts:AssumeRole, authentication,
                         tokens, passwords, secrets, cryptography or TLS, network exposure (0.0.0.0/0, ::/0,
                         public access settings)                                         high
    destructive-data     migrations; DeletionPolicy or UpdateReplacePolicy (and other deletion safeguards)
                         changed; a removed or replaced stateful resource (tables, buckets, databases,
                         queues, file systems, streams, keys); destructive SQL           high
    weakened-tests       a deleted test file, a removed assertion or test case, an added skip, xfail,
                         @Disabled, pytest.mark.skip or .only                            high
    infrastructure       CloudFormation or CDK templates and constructs: security_handoff
                         implement-from-spec:iac-security-reviewer; Terraform files: security_handoff
                         implement-from-spec:reviewing-terraform-security
    unrecognised         a path no rule and no known file type recognises (and every symlink or directory
                         entry): listed under reasons as "unrecognised file type", never lowers the tier

Output: tier standard|high, reasons (one per matched rule and path), approval_required (reasons a human must
approve this snapshot), security_handoff (reviewer skills to dispatch, each with its reason) and lens_model
(sonnet, or opus on high). With --json, schema ifs-review-risk/1.

Usage:
    python3 -I <plugin-root>/core/scripts/review-risk.py classify <snapshot DIR>
    python3 -I <plugin-root>/core/scripts/review-risk.py classify <snapshot DIR> --json

Exit status: 0 classified, 1 error, 3 the snapshot no longer verifies, 64 usage.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import sys

SCHEMA = "ifs-review-risk/1"
MAX_SCAN_BYTES = 2_000_000
IAC_REVIEWER = "implement-from-spec:iac-security-reviewer"
TF_REVIEWER = "implement-from-spec:reviewing-terraform-security"
EXIT_OK, EXIT_ERROR, EXIT_CHANGED, EXIT_USAGE = 0, 1, 3, 64


def load_snapshot_module():
    """review-snapshot.py, the sibling that owns the candidate, loaded by its path (works under python3 -I)."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "review-snapshot.py")
    spec = importlib.util.spec_from_file_location("ifs_review_snapshot", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # No __pycache__ in the plugin's directory: an installed plugin is read-only content.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


# ---------------------------------------------------------------- path rules
CI_RE = re.compile(r"(^|/)(\.github|\.claude|hooks|\.claude-plugin)/|(^|/)(\.gitlab-ci\.ya?ml|Jenkinsfile|"
                   r"buildspec[^/]*\.ya?ml|[^/]*settings[^/]*\.json)$", re.I)
SPEC_RE = re.compile(r"^(docs/specifications/|specification/)|^ai-planning/[^/]+\.md$")
MIGRATION_RE = re.compile(r"(^|/)(migrations?|migrate|alembic|flyway|liquibase|changelogs?)/|(^|/)V\d+[^/]*__[^/]*\.sql$",
                          re.I)
SECURITY_PATH_RE = re.compile(r"(^|/|[_.-])(iam|auth(n|z|entication|orization|orisation)?|crypto\w*|security|secrets?|credentials?|tls|ssl|"
                              r"certs?|kms|permissions?|polic(y|ies))([_./-]|$)", re.I)
TERRAFORM_RE = re.compile(r"\.(tf|tf\.json|tfvars|tfvars\.json|hcl)$", re.I)
CFN_PATH_RE = re.compile(r"(^|/)(cdk\.json|cdk\.context\.json)$|\.(template|cfn)(\.(json|ya?ml))?$|"
                         r"(^|/)(template|cloudformation)[^/]*\.(json|ya?ml)$|(^|/)(cloudformation|cfn)/", re.I)
CFN_CONTENT_RE = re.compile(r"AWSTemplateFormatVersion|AWS::Serverless|[\"']?Type[\"']?\s*:\s*[\"']?AWS::\w+::")
CDK_CONTENT_RE = re.compile(r"aws-cdk-lib|@aws-cdk/|\bfrom aws_cdk\b|\bimport aws_cdk\b|software\.amazon\.awscdk|"
                            r"github\.com/aws/aws-cdk-go|Amazon\.CDK")
TEST_CONFIG_RE = re.compile(r"(^|/)(pytest\.ini|pyproject\.toml|setup\.cfg|tox\.ini|conftest\.py|"
                            r"jest\.config\.[cm]?[jt]s|vitest\.config\.[cm]?[jt]s|package\.json|karma\.conf\.js|"
                            r"build\.gradle(\.kts)?|pom\.xml)$")

KNOWN_EXT = set("""py pyi pyx js mjs cjs jsx ts tsx mts cts vue svelte java kt kts groovy gradle scala go rs rb
php cs fs vb swift m mm c h cc cpp cxx hpp hh dart lua pl pm r jl ex exs erl hs clj sh bash zsh fish ps1 psm1
bat cmd sql md markdown rst txt adoc org tex json jsonc json5 yaml yml toml ini cfg conf properties env xml
xsd xsl html htm css scss sass less svg csv tsv tf tfvars hcl lock mod sum proto graphql gql j2 jinja
jinja2 tpl mustache hbs ipynb dockerfile editorconfig gitignore gitattributes gitmodules dockerignore
npmignore prettierrc eslintrc babelrc nvmrc mdx""".split())
KNOWN_NAMES = {"Dockerfile", "Containerfile", "Makefile", "GNUmakefile", "Jenkinsfile", "Procfile", "Gemfile",
               "Pipfile", "Rakefile", "Vagrantfile", "Brewfile", "LICENSE", "NOTICE", "COPYING", "AUTHORS",
               "CODEOWNERS", "OWNERS", "README", "CHANGELOG", "VERSION", ".python-version", ".tool-versions",
               ".node-version", "go.mod", "go.sum", "mvnw", "gradlew"}

# ---------------------------------------------------------------- content rules (added or removed lines)
SECURITY_CONTENT = (
    ("IAM policy document or statement", re.compile(
        r"PolicyDocument|ManagedPolicyArns|AWS::IAM::|aws_iam_|\biam\.(PolicyStatement|PolicyDocument|Role|Policy|"
        r"ManagedPolicy|Grant)\b|[\"']?\bStatement[\"']?\s*[:=]|[\"']?\bEffect[\"']?\s*[:=]\s*[\"']?(Allow|Deny)|"
        r"[\"']?\b(Not)?Action[\"']?\s*[:=]\s*\[?\s*[\"'][\w*-]+:|\bgrant(Read|Write|ReadWrite|Invoke|"
        r"PutRecords?|Consume|Send|Encrypt|Decrypt)\w*\(")),
    ("Principal", re.compile(r"\bPrincipals?\b|\bprincipals?\s*[{=(]|(Service|Arn|Account|Any|Federated|Organization)"
                             r"Principal\b")),
    ("sts:AssumeRole", re.compile(r"sts:AssumeRole\w*|\bAssumeRole\w*|\bassume_role\w*", re.I)),
    ("authentication or authorisation", re.compile(
        r"\b(auth|authn|authz|authenticat\w*|authori[sz]\w*|oauth\w*|oidc|saml\w*|sso|login|logout|session_?id|"
        r"cognito\w*|jwt\w*|bearer)\b", re.I)),
    ("token, password or secret handling", re.compile(
        r"token|passw(or)?d|passwd|secret|api[_-]?key|private[_-]?key|credential", re.I)),
    ("cryptography or TLS", re.compile(
        r"\b(\w*crypt\w*|cipher\w*|kms|hashlib|hmac|bcrypt|scrypt|argon2|pbkdf2\w*|rsa|aes|sha1|md5|tls\w*|ssl\w*|"
        r"x509|certificates?|cert_?reqs|verify\s*=\s*False|InsecureSkipVerify|rejectUnauthorized|"
        r"check_hostname|CERT_NONE|secure_?random|secrets\.token\w*)\b", re.I)),
    ("network exposure", re.compile(
        r"0\.0\.0\.0/0|::/0|\bpublic[_-]?access\w*|PubliclyAccessible|publicly_accessible|BlockPublic\w*|"
        r"block_public_\w+|RestrictPublicBuckets|restrict_public_buckets|IgnorePublicAcls|ignore_public_acls|"
        r"public-read(-write)?|\bAllUsers\b|MapPublicIpOnLaunch|map_public_ip_on_launch|internet-facing|"
        r"associate_public_ip_address|AssociatePublicIpAddress|SecurityGroupIngress|\bingress\b|CidrIp|"
        r"cidr_blocks|allowAllOutbound|Peer\.anyIpv[46]|FunctionUrl|function_url|AuthType\s*[:=]\s*[\"']?NONE",
        re.I)),
)
SAFEGUARD_RE = re.compile(
    r"DeletionPolicy|UpdateReplacePolicy|deletion_policy|update_replace_policy|RemovalPolicy|removal_?policy|"
    r"prevent_destroy|force_destroy|forceDestroy|autoDeleteObjects|auto_delete_objects|DeletionProtection\w*|"
    r"deletion_protection|deletionProtection|skip_final_snapshot|SkipFinalSnapshot|EnableTerminationProtection|"
    r"termination_protection|retain_on_delete|PointInTimeRecovery\w*|point_in_time_recovery|BackupRetentionPeriod|"
    r"backup_retention_period")
STATEFUL_RE = re.compile(
    r"AWS::(DynamoDB::(Global)?Table|S3::Bucket|S3Express::DirectoryBucket|RDS::DB(Instance|Cluster)|"
    r"SQS::Queue|EFS::FileSystem|FSx::FileSystem|Kinesis::Stream|ElastiCache::\w+|DocDB::DBCluster|"
    r"Neptune::DBCluster|OpenSearchService::Domain|Elasticsearch::Domain|Redshift::Cluster|KMS::Key|"
    r"Backup::BackupVault|SecretsManager::Secret|Logs::LogGroup|Timestream::\w+|QLDB::Ledger|Cassandra::Table|"
    r"MemoryDB::Cluster|EC2::Volume|ECR::Repository|Cognito::UserPool)\b|"
    r"resource\s+\"(aws_dynamodb_table|aws_s3_bucket|aws_db_instance|aws_rds_cluster\w*|aws_sqs_queue|"
    r"aws_efs_file_system|aws_fsx_\w+|aws_kinesis_stream|aws_elasticache_\w+|aws_docdb_cluster\w*|"
    r"aws_neptune_cluster\w*|aws_opensearch_domain|aws_elasticsearch_domain|aws_redshift_cluster|aws_kms_key|"
    r"aws_backup_vault|aws_secretsmanager_secret|aws_cloudwatch_log_group|aws_memorydb_cluster|"
    r"aws_keyspaces_table|aws_ebs_volume|aws_ecr_repository|aws_cognito_user_pool)\"|"
    r"\b(dynamodb\.(Table|TableV2)|s3\.Bucket|rds\.(DatabaseInstance|DatabaseCluster|ServerlessCluster)\w*|"
    r"sqs\.Queue|efs\.FileSystem|kms\.Key|kinesis\.Stream|logs\.LogGroup|opensearch\.Domain|"
    r"secretsmanager\.Secret|ecr\.Repository|cognito\.UserPool)\s*\(")
REPLACEMENT_RE = re.compile(r"\b(TableName|BucketName|DBInstanceIdentifier|DBClusterIdentifier|QueueName|"
                            r"FileSystemName|KeySchema|StreamName|DomainName|ClusterName|table_name|bucket_name|"
                            r"queue_name|tableName|bucketName|queueName)\b")
DESTRUCTIVE_SQL_RE = re.compile(r"\b(drop\s+(table|column|database|schema|index|view)|truncate\s+(table\s+)?\w|"
                                r"delete\s+from|alter\s+table\s+\S+\s+drop)\b", re.I)
ASSERT_RE = re.compile(r"\bassert\w*\b|\bexpect\s*\(|\.should\b|\bverify\s*\(|\b[tb]\.(Error|Errorf|Fatal|Fatalf|"
                       r"Fail\w*)\b|\brequire\.\w+\(|\bpytest\.raises\b|\bassertThrows\b|\bassertThat\b|\.to(Be|Equal|"
                       r"Have|Throw|Match|Contain)\w*\(")
TEST_CASE_RE = re.compile(r"^\s*(async\s+)?def\s+test\w*|@Test\b|@ParameterizedTest\b|^\s*(it|test)\s*\(|"
                          r"\bfunc\s+Test\w+\s*\(")
SKIP_RE = re.compile(r"\b(skip\w*|xfail|xit|xdescribe|xtest)\b|@Disabled\b|@Ignore\b|pytest\.mark\.skip|"
                     r"\b[tb]\.Skip\w*\(|\b(it|describe|test|context)\.only\s*\(|\bfit\s*\(|\bfdescribe\s*\(")
TEST_CONFIG_SKIP_RE = re.compile(r"--deselect|--ignore(-glob)?\b|testPathIgnorePatterns|modulePathIgnorePatterns|"
                                 r"collect_ignore\w*|\bskip\w*\b|\bxfail\b|exclude\s*=|<exclude>", re.I)


def is_test(rel: str) -> bool:
    """The same test-file definition as core/scripts/spec-trace.py."""
    name = os.path.basename(rel)
    return rel.startswith(("tests/", "test/", "src/test/")) or any(
        part in rel for part in ("/tests/", "/__tests__/", "/src/test/")) or name.startswith("test_") \
        or name.endswith(("_test.py", "_test.go")) or ".test." in name or ".spec." in name or name == "conftest.py" \
        or re.search(r"(Test|Tests|IT|TestCase)\.(java|kt|groovy|scala)$", name) is not None


def known_type(rel: str) -> bool:
    name = os.path.basename(rel)
    if name in KNOWN_NAMES or name.startswith(("Dockerfile", "Makefile", "requirements", "README", "LICENSE")):
        return True
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in KNOWN_EXT


def text_of(data) -> str | None:
    """Text for the content rules; None when absent, binary or too large to scan."""
    if data is None or len(data) > MAX_SCAN_BYTES or b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def line_changes(old: str | None, new: str | None) -> tuple:
    """(added, removed) lines between two texts; a missing side contributes nothing."""
    a = old.splitlines() if old else []
    b = new.splitlines() if new else []
    added, removed = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(a[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(b[j1:j2])
    return added, removed


# ---------------------------------------------------------------- classification
class Result:
    def __init__(self) -> None:
        self.high = False
        self.reasons: list = []
        self.approval: list = []
        self.handoff: dict = {}
        self._seen: set = set()

    def reason(self, rule: str, path: str, detail: str, high: bool = False, approval: str = "") -> None:
        key = (rule, path)
        if key not in self._seen:
            self._seen.add(key)
            self.reasons.append({"rule": rule, "path": path, "detail": detail})
        self.high = self.high or high
        if approval and approval not in self.approval:
            self.approval.append(approval)

    def hand_off(self, skill: str, what: str, path: str) -> None:
        self.handoff.setdefault(skill, (what, []))[1].append(path)
        self.reason("infrastructure", path, f"{what}: hand-off to {skill}")

    def as_json(self, sid: str) -> dict:
        tier = "high" if self.high else "standard"
        handoff = [{"skill": skill, "reason": f"{what} changed: {', '.join(paths)}"}
                   for skill, (what, paths) in sorted(self.handoff.items())]
        return {"schema": SCHEMA, "snapshot": sid[:12], "tier": tier, "reasons": self.reasons,
                "approval_required": self.approval, "security_handoff": handoff,
                "lens_model": "opus" if self.high else "sonnet"}


def matched_kinds(lines: list, table) -> list:
    return [kind for kind, pattern in table if any(pattern.search(line) for line in lines)]


def classify_entry(res: Result, entry: dict, old_text, new_text, scanned: bool, has_plan: bool) -> None:
    rel, status = entry["path"], entry["status"]
    recognised = False
    if CI_RE.search(rel):
        res.reason("ci-automation", rel, "CI or automation file changed", high=True,
                   approval=f"CI or automation file changed: {rel}")
        recognised = True
    if SPEC_RE.search(rel):
        recognised = True
        if not has_plan:
            res.reason("specification", rel, "specification changed without an approved plan in the snapshot",
                       approval=f"specification changed without an approved plan: {rel}")
    added, removed = line_changes(old_text, new_text) if scanned else ([], [])
    changed_lines = added + removed

    # security
    kinds = matched_kinds(changed_lines, SECURITY_CONTENT)
    if SECURITY_PATH_RE.search(rel):
        kinds.insert(0, "security-relevant path")
    if kinds:
        res.reason("security", rel, "security-relevant change: " + ", ".join(kinds), high=True)
        recognised = True

    # destructive data
    destructive = []
    if MIGRATION_RE.search(rel):
        destructive.append("migration")
    if any(SAFEGUARD_RE.search(line) for line in changed_lines):
        destructive.append("deletion policy or safeguard changed")
    added_set = {line.strip() for line in added}
    whole = (new_text or "") + "\n" + (old_text or "")
    is_terraform = bool(TERRAFORM_RE.search(rel))
    is_cfn_or_cdk = not is_terraform and bool(
        CFN_PATH_RE.search(rel) or (scanned and (CFN_CONTENT_RE.search(whole) or CDK_CONTENT_RE.search(whole))))
    if any(STATEFUL_RE.search(line) for line in removed if line.strip() not in added_set):
        destructive.append("stateful resource removed or replaced")
    elif (is_terraform or is_cfn_or_cdk) and any(REPLACEMENT_RE.search(line) for line in removed
                                                 if line.strip() not in added_set):
        # A resource's naming property, in infrastructure code only: in application code TableName= is an
        # API parameter (a boto3 call), not a stateful resource being replaced.
        destructive.append("replacement-triggering property of a stateful resource changed")
    if any(DESTRUCTIVE_SQL_RE.search(line) for line in added):
        destructive.append("destructive SQL")
    if destructive:
        res.reason("destructive-data", rel, ", ".join(destructive), high=True)
        recognised = True

    # weakened tests
    weakened = []
    if is_test(rel):
        if status == "deleted":
            weakened.append("test file deleted")
        moved = {line.strip() for line in added}
        if status != "deleted" and any(ASSERT_RE.search(line) for line in removed if line.strip() not in moved):
            weakened.append("assertion removed")
        if status != "deleted" and any(TEST_CASE_RE.search(line) for line in removed if line.strip() not in moved):
            weakened.append("test case removed")
        if any(SKIP_RE.search(line) for line in added):
            weakened.append("skip, xfail, @Disabled or .only added")
    elif TEST_CONFIG_RE.search(rel) and any(TEST_CONFIG_SKIP_RE.search(line) for line in added):
        weakened.append("test selection narrowed in the test configuration")
    if weakened:
        res.reason("weakened-tests", rel, ", ".join(weakened), high=True)
        recognised = True

    # infrastructure hand-off
    if is_terraform:
        res.hand_off(TF_REVIEWER, "Terraform files", rel)
        recognised = True
    elif is_cfn_or_cdk:
        res.hand_off(IAC_REVIEWER, "CloudFormation or CDK files", rel)
        recognised = True

    mode = entry["mode"]
    if mode in ("120000", "160000"):
        res.reason("unrecognised", rel, "unrecognised file type (" + ("symlink" if mode == "120000" else
                                                                       "directory or submodule") + ")")
    elif not recognised and not known_type(rel):
        res.reason("unrecognised", rel, "unrecognised file type")
    elif not scanned and not recognised:
        res.reason("not-scanned", rel, "content not scanned (binary or over 2 MB): matched by path only")


def classify(snap, directory: str) -> dict:
    _d, manifest = snap.load_manifest(directory)
    changed = snap.verify_manifest(manifest)
    if changed:
        raise snap.Failure(EXIT_CHANGED, "the snapshot no longer verifies (" + "; ".join(changed) +
                           "): take a new snapshot")
    res = Result()
    for rel in manifest.get("policy_changed", []):
        res.reason("policy-file", rel, "policy file changed", high=True, approval=f"policy file changed: {rel}")
    root, base = manifest["repo"], manifest["base"]
    with snap.open_candidate(manifest) as cand:
        base_tree = snap.ls_tree(root, base, [e["path"] for e in manifest["candidate"]])
        for entry in manifest["candidate"]:
            rel = entry["path"]
            new = cand.read(rel) if entry["status"] != "deleted" and entry["mode"] in snap.FILE_MODES else None
            if new is not None and snap.sha256(new) != entry["sha256"]:
                raise snap.Failure(EXIT_CHANGED, f"the snapshot no longer verifies ({rel} changed while reading)")
            old = None
            if rel in base_tree and base_tree[rel][0] in snap.FILE_MODES:
                old = snap.object_bytes(root, *base_tree[rel])
            old_text, new_text = text_of(old), text_of(new)
            scanned = entry["mode"] in snap.FILE_MODES + (None,) and \
                (old is None or old_text is not None) and (new is None or new_text is not None)
            classify_entry(res, entry, old_text, new_text, scanned, manifest.get("plan") is not None)
    return res.as_json(manifest["id"])


def print_text(result: dict) -> None:
    print(f"Snapshot: {result['snapshot']}")
    print(f"Risk: {result['tier']}")
    print("Reasons:" if result["reasons"] else "Reasons: none")
    for r in result["reasons"]:
        print(f"- {r['rule']}: {r['path']} ({r['detail']})")
    approval = result["approval_required"]
    print("Approval required: " + (f"human ({'; '.join(approval)})" if approval else "none"))
    handoff = result["security_handoff"]
    print("Security hand-off: " + ("; ".join(f"{h['skill']} ({h['reason']})" for h in handoff) if handoff
                                   else "none"))
    print(f"Lens model: {result['lens_model']}")


class Parser(argparse.ArgumentParser):
    """argparse with the documented usage exit status, 64."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def main(argv=None) -> int:
    parser = Parser(prog="review-risk.py", description="Classify a review snapshot's change by risk "
                    "(escalation only).", formatter_class=argparse.RawDescriptionHelpFormatter,
                    epilog="The snapshot must still verify" + __doc__.split("The snapshot must still verify", 1)[1]
                    .split("Usage:", 1)[0].rstrip())
    sub = parser.add_subparsers(dest="command_name", metavar="{classify}")
    sub.required = True
    cls = sub.add_parser("classify", help="print the tier and why")
    cls.add_argument("dir", help="the snapshot directory review-snapshot.py create wrote")
    cls.add_argument("--json", action="store_true", help="print JSON (schema ifs-review-risk/1)")
    args = parser.parse_args(argv)
    try:
        snap = load_snapshot_module()
    except (ImportError, OSError, SyntaxError) as exc:
        print(f"review-risk: cannot load review-snapshot.py: {exc}", file=sys.stderr)
        return EXIT_ERROR
    try:
        result = classify(snap, args.dir)
    except snap.Failure as exc:
        print(f"review-risk: {exc.message}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"review-risk: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_text(result)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
