# AWS CloudFormation

`implement-from-spec:implementing-cloudformation-from-spec` implements CloudFormation YAML templates,
Guard rules, template tests and parameter files from specification items. It ends at validated templates
and, when a dev change set exists, a replacement check on it. Deploying stays with you or your pipeline.

## Requirements

- `cfn-lint` and CloudFormation Guard (`cfn-guard`), unless the project has its own validate entry point
- The AWS CLI v2, for read-only change-set inspection
- Recommended: `cloudformation-validate` (AWS CloudFormation Validate), which adds offline schema checks
- Optional: Checkov, when the project adopts it; TaskCat, only when you opt in, because it creates real
  stacks
- The AWS Documentation MCP server, or web access to `docs.aws.amazon.com`

Check and install with `/implement-from-spec:setup cloudformation`. Setup reads each tool's minimum
version and install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows
every gap with its exact commands, and installs only what you approve. The skill checks the same tools,
read-only, at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- Templates and parameter files, for example `infra/<stack>.yaml` and `params/`, Guard rules (for example
  under `policies/guard/`) and template tests
- The ownership rules: which specification owns each stack, role and parameter, and the stack order.
  Usually the specifications index and `CLAUDE.md`
- The pipeline's validate stage or a validate script. The skill runs it, since that is what the pipeline
  judges
- The specification items, or a feature spec under `ai-planning/`, in one of the formats of
  [spec-format.md](../spec-format.md)
- A `.gitignore` that covers build and packaging output: after implementation every changed or
  untracked file must belong to a task (see "How a run goes", step 6). The change-set JSON the skill keeps
  as evidence goes under `ai-planning/`, which is exempt

## How a run goes

1. Ingest: the items, the ownership rules, the existing templates, parameter files, Guard rules and
   tests, the validate stage, and the Template Reference page of every resource type the design uses
2. Plan: `ai-planning/<slug>.plan`, prose only
3. Analysis gate: `spec-trace.py plan`, then a self-review of stack fit, quotas after `Fn::ForEach`
   expansion, data protection (both `DeletionPolicy` and `UpdateReplacePolicy` set explicitly, since both
   default to `Delete`), replacement behaviour, IAM, typed and constrained parameters with no secret
   defaults, Guard rules and tests, and scope
4. Your `approve`
5. Implementation in waves. Test first means a Guard rule fixture or a template test that fails before the
   resource exists. After each wave the full validation runs: the project's validate entry point, or
   `cfn-lint`, `cloudformation-validate` when installed, `cfn-guard test` and `cfn-guard validate`, and
   the template tests
6. Verification of each item and `spec-trace.py code`. Besides the owned files and their tests, it fails
   every file changed against `HEAD` that no task owns and that is not under `ai-planning/`
   (`unowned-change`); a write outside the plan is an amendment you approve, never a ruling the skill
   makes alone. When the change updates an existing stack and a dev change set exists, the skill
   inspects it read-only and runs the bundled Guard rule on it. The rule fails on every `Modify` whose
   `Replacement` is `True` or `Conditional`, and on every `Remove` whose `PolicyAction` is not `Retain` or
   `Snapshot`. A failure stops the run unless you agreed to that replacement. When no change set is named,
   or the inspection cannot run, the check is recorded as not run, with the commands for you to run, and
   the run goes on to review; the skill never creates a change set to get one
7. Review: the `iac-security-reviewer` skill (IAM, secrets and exposure) and the `code-reviewer` skill
   (everything else), each loaded by its own generic subagent,
   applying the skill's `references/review.md` and the checks of
   [`reviewing-cloudformation-changes/references/review-dimensions.md`](../../skills/reviewing-cloudformation-changes/references/review-dimensions.md),
   and, when you enable it, the external reviewer (off by default), in parallel
8. Validation again after the fixes, then a documentation sync
9. The report, with the deploy command or pipeline run, the change-set check to run before deploying, and
   read-only smoke commands

Logical IDs, export names and registry keys of existing resources never change: a new logical ID is a new
resource, and the old one is deleted. A change set in a dev account is created only when you ask for one
by name.

## What asks first, and what is refused

The gate asks before each of these, before and after plan approval:

- Mutating `aws cloudformation` calls: `create-stack`, `update-stack`, `delete-stack`, `deploy`,
  `create-change-set`, `execute-change-set` and the rest
- `sam`, `cdk`, `rain` and `taskcat` `deploy`, `test`, `sync`, `destroy`, `delete` and `rm` commands
- Every other mutating `aws` CLI call
- Tool installs through `pip`, `pip3`, `pipx`, `uv`, `brew` or `cargo`, including `python3 -m pip install`

Read-only `aws cloudformation` calls (`describe-*`, `list-*`, `get-*`, `validate-template`,
`estimate-template-cost`, `detect-*`, `wait`) run without asking. In a gated session the rules of all five
implementing skills apply together.

Refused: any `aws cloudformation` call with `--use-previous-template`. With `AWS::LanguageExtensions`, it
reuses the processed template with the old literal parameter values, so new values are silently not
applied.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate"). When the gate asks about a live read the approved plan names,
its prompt is the confirmation, and the skill does not ask again in the conversation; declined or unable
to run, the check is recorded as not run with the command for you to run. A tool install the plan names
that you decline is not retried and gets no substitute: the tasks that need it are marked `blocked`, the
others are finished, and the report's status is "verification incomplete (<command> denied)" (contract
section 12).

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (snapshot,
change digest, review state, findings fixed, rejected, covered by gate and open, fix rounds,
and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator: the
pipeline run or the exact deploy command, the change set to inspect for `Replacement` and `PolicyAction`
before deploying, and read-only smoke commands. Nothing has been deployed.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-cloudformation-changes . main..HEAD
```

The arguments are the repository and the change: the working tree, a git range, a PR branch, a file list
or a diff file, optionally `--plan ai-planning/<slug>.plan` and `--change-set <file>`, a
`describe-change-set --output json` file you created. The skill runs the same two stages, plus only
read-only checks (`cfn-lint`, `cfn-validate`, `cfn-guard`, and the change-set replacement rule on the
change set you supplied), verifies every finding against the templates, sets severity itself, and returns
one Blocker, Major, Minor and Nit report with a fix per finding, opening with the review state block
(snapshot, recommendation, verification, approval required, risk, rollback; see
[external-review.md](external-review.md#the-review-around-it-snapshot-isolation-state-and-fix-rounds)). It never creates a change
set; without one, the report does not claim that nothing is replaced.

## Out of scope

- Deploying, creating or executing change sets, importing resources, drift detection
- Terraform ([terraform.md](terraform.md)), CDK ([cdk.md](cdk.md)), application code
- Changing a specification item: the skill asks, and you decide
