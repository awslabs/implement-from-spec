# Terraform

`implement-from-spec:implementing-terraform-from-spec` implements Terraform infrastructure (modules,
environment wiring, variables, outputs, IAM policy documents) from specification items or a feature spec.
It ends at a targeted plan with zero destroys. Applying stays in your hands.

## Requirements

- terraform 1.6.0 or later on PATH (setup's minimum)
- Optional: TFLint (when the project configures `.tflint.hcl`) and Checkov (when the project's CI runs
  it)
- Optional: the AWS CLI v2, for read-only checks of the target account; required only for the external
  reviewer in `aws-profile` mode
- The AWS Documentation MCP server; the Terraform MCP server when you have it, otherwise the skill reads
  the Terraform Registry documentation online

Check and install with `/implement-from-spec:setup terraform`. Setup reads each tool's minimum version
and install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every
gap with its exact commands, and installs only what you approve. The skill checks the same tools,
read-only, at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A `CLAUDE.md` that names the AWS profile every Terraform command runs under. Without one, the skill asks
  before the first plan, because the default profile may be another account
- The project's **architecture invariants** in `CLAUDE.md`: rules that silently break the stack when
  "tidied up". The skill treats them as blocking. A design that needs to break one stops for you
- A layout the skill can follow. With nothing documented it assumes the default: a `bootstrap/` root for
  remote state, an `environment/` root that wires modules, `envs/` for backend and variable files, and
  `modules/`. Resource modules export IAM policy JSON; only the compute module (or the project's
  documented attachment point) creates roles and attachments
- The specification items: a `specification/` tree with `functional/` (`SPEC-Fxxx`) and `non-functional/`
  (`SPEC-NFxxx`) topic files, structured `SPEC-<SVC>-n` items under `docs/specifications/`, or a feature
  spec under `ai-planning/`. [spec-format.md](../spec-format.md) gives the rules for each
- A `.gitignore` that covers `.terraform/`, plan files and local state: after implementation every
  changed or untracked file must belong to a task (see "How a run goes", step 7)
- Optional: a cost baseline, for example `ai-planning/costs.md`. The report gives the cost delta against it

## How a run goes

1. Ingest: the spec, the invariants, the pattern module, `versions.tf` in every root, the environment
   wiring, the example tfvars and the provider documentation of every resource type. Open questions about
   live account state become pre-apply manual checks in the plan; the skill does not query AWS while
   planning. It posts a short "what I read"
2. Plan: `ai-planning/<slug>.plan`, with no HCL, policy JSON or pseudocode
3. Analysis gate: `spec-trace.py plan`, then a self-review of the module pattern, naming, IAM least
   privilege, safety invariants (public access blocks, `prevent_destroy` where data lives, no existing
   `lifecycle` block touched) and scope
4. Your `approve`
5. Implementation in waves. Test first means a `terraform test` run with `command = plan` or mock
   providers, or a `check` or `validation` block, that fails before the resource exists. `terraform fmt`
   and `validate` run after each module and on the root after each wave
6. A targeted plan of the new modules. Required: zero destroys, zero changes to existing resources apart
   from the documented IAM attachment point, and additions that match the plan. Anything unexpected stops
   the run. A full plan of the root is run before the report claims the change destroys nothing anywhere;
   without one, the report says global effects are unverified
7. Verification of each item and `spec-trace.py code`. Besides the owned files and their tests, it fails
   every file changed against `HEAD` that no task owns and that is not under `ai-planning/`
   (`unowned-change`). A write outside the plan is an amendment you approve, never a ruling the skill
   makes alone
8. Review: the `reviewing-terraform-code` (Code Reviewer for HashiCorp Terraform) and
   `reviewing-terraform-security` (Security Reviewer for HashiCorp Terraform) skills (Claude, each loaded by
   its own generic subagent), applying the skill's
   `references/review.md` and the checks of
   [`reviewing-terraform-changes/references/review-dimensions.md`](../../skills/reviewing-terraform-changes/references/review-dimensions.md),
   and, when you enable it, the external reviewer (off by default), in parallel
9. Re-validation after the fixes, then a sync of the specification, the cost file and `CLAUDE.md`
10. The report, with the plan counts, the cost delta and the apply command for the operator

A provider version a new resource needs is said prominently in the plan, because you must run
`terraform init -upgrade`.

## What asks first

The gate asks before each of these, before and after plan approval:

- `terraform` or `tofu` `apply`, `destroy`, `import`, `taint`, `untaint`, `force-unlock`, `refresh`,
  `state rm`, `state mv`, `state push`, `state replace-provider`, `workspace delete`
- `plan` and `test`: a plan reads live state under whatever AWS profile is active, so you confirm the
  account; `terraform test` applies by default unless its run blocks use `command = plan` or mocks
- `init -migrate-state`
- Every mutating `aws` CLI call. Read-only calls (`describe`, `list`, `get` and similar) and
  `aws sts get-caller-identity` run without asking

`fmt`, `validate` and `state list` run without asking. In a gated session the rules of all five
implementing skills apply together, so for example a package install also asks.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate").

When a prompt comes up for a live read the approved plan names (the targeted plan, the full plan of the
root), that prompt is the confirmation: the skill does not ask again in the conversation. If you decline,
or the session cannot answer (no credentials, a non-interactive run), the skill records the plan as not
run in the ledger with the command for you to run, goes on to verification and review, and the report
says so. A dependency install the plan names that you decline is not retried and gets no substitute: the
tasks that need it are marked `blocked`, the others are finished, and
the report's status is "verification incomplete (<command> denied)" (contract section 12).

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (change
digest, findings fixed, rejected and open, and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For
Terraform it adds the counts of the targeted plan and, when it ran, of the full plan, the cost delta
against the baseline, and the exact apply command. Nothing has been applied.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-terraform-changes . main..HEAD
```

The arguments are the repository and the change: the working tree, a git range, a PR branch, a file list
or a diff file, optionally `--plan ai-planning/<slug>.plan`. The skill runs the same two stages, plus only
read-only checks (`fmt -check`, `validate`, TFLint and Checkov when present; never `plan` or `apply`),
verifies every finding against the code, sets severity itself, and returns one Blocker, Major, Minor and
Nit report with a fix per finding and a verdict. Without a plan, its destroy and replacement analysis
comes from the code, and the report says so.

## Out of scope

- Applying, importing or editing state: the operator does
- Live AWS inspection during planning
- CloudFormation projects ([cloudformation.md](cloudformation.md)) and CDK apps ([cdk.md](cdk.md))

A project whose `CLAUDE.md` pins another infrastructure tool stops the skill at ingest, with the name of
the matching skill.
