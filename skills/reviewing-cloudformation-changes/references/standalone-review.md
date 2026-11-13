# Standalone CloudFormation review

What the review skill adds to `implementing-cloudformation-from-spec`'s `review.md`,
`cloudformation-practices.md`, `review-focus.md` and `rules/change-set-replacement.guard` (read in place
under `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/`; this file does not restate
them). It applies standalone and when the implementing skill calls the review. The snapshot, the review
state and the fix rounds are contract section 9 and SKILL.md steps 1, 5 and 6.

## Contents

1. What counts as a CloudFormation change
2. Read-only checks (the quality gate)
3. Check groups without a plan or specification
4. Severity classes
5. Rollback evidence

## 1. What counts as a CloudFormation change

- In scope: templates (`*.yaml`, `*.yml`, `*.json`, `*.template`) that carry `AWSTemplateFormatVersion`
  or a `Resources` section of `AWS::` types, including templates with the `AWS::LanguageExtensions` or
  the SAM transform (cfn-lint applies the SAM transform before checking; this skill never runs `sam`);
  parameter files (a `ParameterKey`/`ParameterValue` list or a `Parameters` map) and the project's
  parameter registry; `.cfnlintrc*`; Guard rules (`*.guard`) and their `*_tests.yaml`; template tests;
  the validate script and the pipeline file that deploys the stacks, for group 8
- Templates directory: the one the project's CLAUDE.md, `.cfnlintrc*` (`templates:`) or validate script
  names; otherwise every file that matches the first bullet
- Not in scope: a CDK app (`cdk.json` present; use `reviewing-cdk-changes`) and its `cdk.out/`, Terraform
- Change modes map to the external script's arguments exactly as SKILL.md step 1 lists them. For a pull
  request: the user checks out the branch; the range is `$(git -C <repo> merge-base <target> HEAD)..HEAD`
  with `<target>` the branch the PR merges into. Never fetch, pull or check out a branch yourself

## 2. Read-only checks (the quality gate)

Run from the main conversation while the stages work, from the repository root; the reviewers never run
them. Each command below changes nothing in the repository: a check that wrote there would change the
candidate, and `record-gate` would then refuse its result. Run them against the tree the change mode
names; for a committed range whose tip differs from the working tree, extract the tip into a scratch
directory (`scratch="$(mktemp -d)"; git -C <repo> archive <b> | tar -x -C "$scratch"`, which writes
nothing in the repository) and run there. Write each output to `<work>/<name>.txt` (SKILL.md step 1, the
review's scratch directory) and attach it as `<DIR>/gates/<name>.txt`, where the reviewers of a fix round
can read it (never redirect into `<DIR>`: in the implementing skill's gated session the approval gate
denies every write there), and record checks 2 to 5 with `record-gate` (SKILL.md step 3) under
the names `validate-entry-point`, `cfn-lint`, `cfn-validate`, `cfn-guard-test:<rule>` and
`cfn-guard-validate`: `pass` when the check is green as defined below, `fail` when it is red, and
`not-run` with `--reason` when a required check could not run to a result (below), never `fail`. Checks 2
to 5 are the quality gate; check 6 is evidence for the triage, outside it.

1. **Binaries**, read-only:

       python3 -I "${CLAUDE_PLUGIN_ROOT}/core/deps/doctor.py" --stack cloudformation --project <repo> --json

   Exit 69 names the gap (cfn-lint or cfn-guard missing or too old). In a review that is not a stop: the
   required checks that need the binary are recorded as `not-run` with that reason (below), and the
   review continues.
   Point the user to `/implement-from-spec:setup`; never install anything

2. **The project's validate entry point** (for example `scripts/validate.sh`, a Makefile target), when
   it exists: read it first. Run it only when every command in it is one of the read-only checks below
   and it writes nothing inside the repository; it is what the pipeline will judge, so its pass or fail
   is the validation result. Otherwise run checks 3 to 6 yourself with the invocations it uses

3. **cfn-lint**, with the project's configuration: `cfn-lint` (it reads `.cfnlintrc*` for templates,
   regions and checks), or `cfn-lint -t '<templates>' --regions <region>` plus
   `--parameter-files <file>` per template when the project keeps parameter files. The exit code is a
   bitmask (practices section 11): an error bit (2) is red; warnings (4) and informational results (8)
   are *(tool)* findings for the triage, unless the project's validate stage fails on them

4. **cfn-validate** (AWS CloudFormation Validate), when installed: `cfn-validate <templates dir> --region
   <region>`, with `--parameter Key=Value` for parameter-dependent checks and `--strict` when the project
   asks. Exit 1 is red. Not installed: "not run: not installed (recommended)"

5. **cfn-guard with the project's rules**:
   - `cfn-guard test --rules-file <rule>.guard --test-data <rule>_tests.yaml` for every rule file; a
     failing test is red, and a rule without a tests file is a group 7 finding
   - `cfn-guard validate --rules <rule dir> --data <templates dir> --type CFNTemplate --show-summary fail`;
     a FAIL is red
   - Guard sees the raw template: it does not resolve parameters or transforms, so resources a
     `Fn::ForEach` loop generates are invisible to it (practices section 11). Say so in the report line
     when the change touches a loop; a processed template the user supplies
     (`get-template --template-stage Processed`) can be validated the same way
   - **AWS Guard Rules Registry**: rules the project vendored into its rule directory run with the
     project's rules above. When the project keeps a pinned copy elsewhere in the repository and its
     docs or validate stage name it, run `cfn-guard validate --rules <that dir> --data <templates dir>
     --type CFNTemplate --show-summary fail` as well; each failure is a *(tool)* finding, confirmed
     against the project's rules (a registry rule the project did not adopt is advisory). Never download
     the registry (practices section 12)

6. **The change-set rule**, only on a CloudFormation change set that already exists:
   - The user supplies the JSON `aws cloudformation describe-change-set --output json` printed: attach
     it as `<DIR>/input/change-set.json` (from its file, or `--from -` with the pasted text in a quoted
     heredoc), outside the repository, so the reviewers can read it
   - The user names an existing change set and allows the call: the read-only
     `aws cloudformation describe-change-set --stack-name <stack> --change-set-name <name> --output json`
     under the AWS profile the project's CLAUDE.md prescribes, its output written to
     `<work>/change-set.json` and attached as `<DIR>/input/change-set.json`. Ask
     first, naming the command and the profile; never with another profile
   - Run:

         cfn-guard validate --rules "${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/rules/change-set-replacement.guard" \
             --data <change set JSON> --show-summary none --structured --output-format json

     Exit 0 passes; 19 is a FAIL that names each offending change by its `/Changes/<n>` path; 5 means the
     rule or the data was unreadable (report "not run" with the message). For each failing change,
     report its `LogicalResourceId`, the property that forces replacement (`Details[].Target.Name` and
     `RequiresRecreation`) and that property's update behaviour from the Template Reference
   - Check that the document describes this change: `StackName` is the stack the changed template
     deploys, `Status` is `CREATE_COMPLETE`, and `ExecutionStatus` is not `OBSOLETE` ("the stack was
     already updated", DescribeChangeSet API reference). A `NextToken` in the document means more than
     1 MB of changes and only the first page is present: report the check as partial. A change set
     created from a template other than the one under review proves nothing about it; when the user
     cannot say which template it came from, say so
   - No change set: "not run: no change set supplied". The *Read-only checks* line names the operator's
     two steps, creating the change set in the pipeline or a dev account and running this rule on its
     describe output

7. **Never in this skill**: `create-stack`, `update-stack`, `delete-stack`, `deploy`, `package` (it
   uploads to S3), `create-change-set`, `execute-change-set`, `delete-change-set`, `detect-stack-drift`,
   `validate-template` (a service call; cfn-lint and cfn-validate cover it offline), `sam` commands,
   TaskCat, `cfn-lint --output-file` pointed into the repository, or any other mutating `aws` call

A required check that could not run (cfn-lint or cfn-guard missing, a sandbox that blocks it) is
reported as not run with its reason, never as clean and never as `fail`, and recorded so:

    python3 -I "${CLAUDE_PLUGIN_ROOT}/core/scripts/review-snapshot.py" record-gate <DIR> --name cfn-lint \
        --status not-run --command "<the command that could not run>" --reason "<why, one line>"

`state` then reports verification incomplete with `<name> not run: <reason>`, never Blocked by itself. A
result recorded by mistake stays in `gates.json`: record the right one after it (`state` reads each
name's latest result), never edit, rewrite or delete the file. An optional one (cfn-validate, a change
set not supplied) is reported as not run and not recorded: a missing optional tool is "not run: not
installed", never "clean".
Advisory results (cfn-lint warnings and informational results, a change-set rule FAIL, registry rules the
project did not adopt) go into the triage like a reviewer's, tagged *(tool)*. When a check runs against a
scratch copy, say so in its report line.

## 3. Check groups without a plan or specification

When neither a plan nor specification files are in scope, this rule holds verbatim
(`references/dispatch.json` copies this section into every reviewer's brief):

    No plan and no specification are in scope. Group 1 (Specification fidelity): review the change
    against what it claims to do (commit messages, PR description, template Description and comments,
    read after the code) and against the project's documented contracts when they exist (CLAUDE.md,
    README, docs/); report anything added that nothing asks for and anything that silently changes an
    existing logical ID, parameter, output or export; write "not applicable: no plan or specification"
    only when nothing states an intent. Group 2 (Data safety): with no ledger, a replacement, a deleting
    removal or a changed logical ID is covered only by a decision recorded in the project's documents;
    otherwise it is a finding. Group 3 (Cross-stack contract): the owner is the template that declares
    the export or parameter; an export removed or renamed while any template in the repository imports
    it (Fn::ImportValue) is a finding, and an export changed with no importer in the repository needs
    runtime verification (`aws cloudformation list-imports --export-name <name>`, run by the operator).
    The project's architecture invariants are the CLAUDE.md ones when the file exists; otherwise the
    defaults in cloudformation-practices.md, and write "no project invariants documented". All other
    groups apply unchanged.

With a plan or specification, `review.md` applies unchanged.

## 4. Severity classes

The main conversation sets severity from the code, never from a reviewer or a tool.

- **Blocker**: every Blocker class in `review.md`; a contradiction of a project invariant or a
  specification item (CLAUDE.md, the specification, the plan); a trust policy or resource policy whose
  `Principal` is `"*"` or `AWS: "*"` with no condition that narrows it to the intended callers, unless
  the items require public access; a public access path the items do not allow (a public access block
  flag set false, a bucket policy open to `"*"`, `0.0.0.0/0` ingress to a non-public port); a secret as
  a parameter default, a literal or an output; a stateful resource (table, bucket, key, user pool, log
  group holding audit data, database) without `DeletionPolicy` or `UpdateReplacePolicy` where the
  project's rules require them; a change-set rule FAIL with no recorded decision; red validation;
  custom-named IAM resources while the pipeline's change-set call omits `CAPABILITY_NAMED_IAM` (the
  change cannot deploy)
- **Major**: a stateful resource without both policies where no project rule requires them (a later
  removal or replacement deletes its data: `UpdateReplacePolicy` defaults to `Delete`, and so does
  `DeletionPolicy` except on RDS clusters and RDS instances outside a cluster, where it defaults to
  `Snapshot`); deletion protection missing where the resource has it; an IAM action or resource wildcard
  with no stated reason where no Blocker rule applies; an unconstrained string parameter; hard-coded partition, Region or account; a
  Guard rule without PASS and FAIL fixtures; a test that would pass with the resource removed; a resource
  no item asks for, when a specification is in scope; a property or action name that may not exist
- **Minor**: worth fixing in this change if quick (an unused parameter or condition, a missing
  description, a cfn-lint informational result the project does not require)
- **Nit**: optional polish
- A finding attributed to the base keeps its class under *Pre-existing* (SKILL.md step 4); it is outside
  the recommendation, and a pre-existing Blocker carries an escalation note

## 5. Rollback evidence

The report's `Rollback:` line rests on the templates and the change set, never on the author's word, and
states code rollback and data recovery separately: reverting the template restores configuration, not
data a replacement or a deleting removal destroyed. A report never says the change replaces or deletes
nothing unless a supplied change set passed the change-set rule: without one, the replacement analysis
is from the Template Reference's update behaviour, and the report says so.

- **Evidence that counts**: a supplied change set and its change-set rule result (`Replacement` and
  `PolicyAction` per logical ID); for every modified property of an existing resource, its update
  behaviour in the Template Reference (No interruption, Some interruptions, Replacement); `DeletionPolicy`
  and `UpdateReplacePolicy` on every stateful resource the change touches, before and after (both default
  to `Delete`, `DeletionPolicy` to `Snapshot` on RDS clusters and instances outside a cluster); deletion
  protection and point-in-time recovery or backup settings; changed logical IDs, including `Fn::ForEach`
  tokens
- **not applicable**: the change deploys nothing (Guard rules and their fixtures, template tests,
  documentation, a parameter registry no stack reads yet)
- **supported (<evidence>)**: code: redeploy the previous template through the pipeline (a failed update
  rolls back on its own); data: no stateful resource is replaced or removed, shown by a passing
  change-set rule or by the update behaviour of every changed property, and each touched stateful resource
  keeps `Retain` or `Snapshot` in both policies. Name the evidence, for example `supported (code: previous
  template via the pipeline; data: change-set rule PASS on dev-orders, OrdersTable Retain/Retain)`. A
  change that only adds resources and changes no existing one is supported: a rollback removes the new
  resources, deleted with what was written to them after the deploy or retained as their
  `DeletionPolicy` says, which is the inverse of the change, not stranded writes; say so in the evidence
  (`data: change-set rule PASS, 2 Add, 0 Remove; a rollback deletes the new queue and its messages`).
  That revert is not a finding when the plan's rollback says how the new resources are removed, Minor at
  most when it is silent, and Major only when the items, the plan or the project's rules require that
  data to survive a rollback. A change that alters the shape of persisted data or a contract the previous
  template reads (a key, attribute or field moved, renamed, nested or retyped; an item, message, export or
  output format) is never additive, even when it also adds resources: it is judged under unsafe below
- **unsafe (<finding>)**: a finding shows a stateful resource replaced or removed whose policy deletes
  it, or a change whose revert strands writes made after it (the previous template cannot read, or no
  longer grants access to, data in a resource that survives the revert, or a revert deletes data that
  the items, the plan or the project's rules require to survive a rollback); name the F-number and the
  data recovery it needs (a snapshot or PITR restore, a backup), or "no recovery path" when none exists
- **unknown (<what settles it>)**: a modified property's update behaviour is Replacement or Conditional and
  no change set was supplied, or the behaviour is not documented: name the operator's change set and the
  change-set rule command
