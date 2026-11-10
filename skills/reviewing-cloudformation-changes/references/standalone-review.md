# Standalone CloudFormation review

What a review outside `implementing-cloudformation-from-spec` adds to that skill's `review.md`,
`cloudformation-practices.md`, `review-focus.md` and `rules/change-set-replacement.guard` (read in place
under `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/`; this file does not restate
them).

## Contents

1. What counts as a CloudFormation change
2. Read-only checks
3. Check groups without a plan or specification
4. Severity classes

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

## 2. Read-only checks

Run from the main conversation while the stages work, from the repository root. Each command below
changes nothing in the repository. Run them against the tree the change mode names; for a committed
range whose tip differs from the working tree, extract the tip into a scratch directory
(`scratch="$(mktemp -d)"; git -C <repo> archive <b> | tar -x -C "$scratch"`, which writes nothing in
the repository) and run there.

1. **Binaries**, read-only:

       python3 -I "${CLAUDE_PLUGIN_ROOT}/core/deps/doctor.py" --stack cloudformation --project <repo> --json

   Exit 69 names the gap (cfn-lint or cfn-guard missing or too old). In a review that is not a stop: the
   checks that need the binary are reported as not run with that reason, and the review continues.
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
   - The user supplies the JSON `aws cloudformation describe-change-set --output json` printed: copy it
     to a `mktemp -d` directory outside the repository when it was pasted
   - The user names an existing change set and allows the call: the read-only
     `aws cloudformation describe-change-set --stack-name <stack> --change-set-name <name> --output json`
     under the AWS profile the project's CLAUDE.md prescribes, its output saved to that scratch
     directory. Ask first, naming the command and the profile; never with another profile
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

A missing optional tool is "not run: not installed", never "clean". When a check runs against a scratch
copy, say so in its report line.

## 3. Check groups without a plan or specification

Give the reviewers this rule verbatim when neither a plan nor specification files are in scope:

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
