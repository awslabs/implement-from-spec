# AWS CDK

`implement-from-spec:implementing-cdk-from-spec` implements AWS CDK v2 apps in Python or Java (stacks,
constructs, assertion tests, cdk-nag rules) from specification items. It ends at a change-set diff that
shows no existing resource replaced. Deploying stays in your hands.

## Requirements

- Node.js 22 or later and the AWS CDK CLI. A CLI pinned in the project (`node_modules/.bin/cdk`) is used
  first
- The AWS CLI v2
- For Python apps: Python 3 with pip. For Java apps: a JDK, and Maven or Gradle unless the project ships
  a wrapper
- Optional: `cfn-lint`, `cfn-guard` and `cloudformation-validate`, for checks on the synthesised templates
- AWS credentials for the target account, for the change-set diff
- The AWS Documentation MCP server, or web access to `docs.aws.amazon.com`

Check and install with `/implement-from-spec:setup cdk`. Setup reads each tool's minimum version and
install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every gap
with its exact commands, and installs only what you approve. The skill checks the same tools, read-only,
at the start of every run, and stops before planning when a required one is missing. For a Python app it
also checks that the project's virtual environment imports `aws_cdk`, `constructs` and `pytest`; when it
does not, it stops and gives you the setup command from the project's rules instead of installing
anything. A TypeScript or other-language app gets the template-level checks on its synthesised templates
only, and the plan says so.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A CDK app: `cdk.json`, the entry point, and `requirements.txt` and `requirements-dev.txt`, or `pom.xml`
- A `CLAUDE.md` or `AGENTS.md` with the AWS profile and account, the stack order, naming and retention
  rules, and how the pipeline synthesises and deploys
- The specification items, or a feature spec under `ai-planning/`, in one of the formats of
  [spec-format.md](../spec-format.md)
- A `.gitignore` that covers `cdk.out/`, the virtual environment and build output: after implementation
  every changed or untracked file must belong to a task (see "How a run goes", step 7)

## How a run goes

1. Ingest: the items, the project rules, `cdk.json` and the dependency files, every stack the items
   touch, and the synthesised templates (`cdk synth --quiet`) for the logical IDs of existing resources.
   Every construct, property, default and CLI flag comes from documentation read in the session
2. Plan: `ai-planning/<slug>.plan`, prose only
3. Analysis gate: `spec-trace.py plan`, then a self-review of stack fit, logical ID stability, data
   protection (`RemovalPolicy.RETAIN` or what the items require, set explicitly and asserted in a test),
   replacement behaviour, IAM (`grant*` methods first), tests, dependencies and scope
4. Your `approve`
5. Implementation in waves, test first with fine-grained assertion tests. After each wave: the app's tests
   (`pytest`, or `mvn test` through the wrapper), `cdk synth --quiet` (which runs cdk-nag when the app
   registers it), and `cfn-lint`, `cfn-guard` and `cloudformation-validate` when installed. cdk-nag
   findings are fixed, or acknowledged on the narrowest construct with a recorded reason
6. Replacement evidence: `cdk diff <stack> --method change-set --exclusively` per changed stack, then
   `cdk diff --method change-set` for the whole app. Required: no existing resource destroyed or replaced,
   no change outside the plan. A `--method template` diff is not evidence. When the change set cannot be
   created, the report says the evidence is missing and why
7. Verification of each item and `spec-trace.py code`. Besides the owned files and their tests, it fails
   every file changed against `HEAD` that no task owns and that is not under `ai-planning/`
   (`unowned-change`). A write outside the plan is an amendment you approve, never a ruling the skill
   makes alone
8. Review: the `code-reviewer` and `iac-security-reviewer` skills (Claude, each loaded by its own
   generic subagent), applying the skill's
   `references/review.md` and the checks of
   [`reviewing-cdk-changes/references/review-dimensions.md`](../../skills/reviewing-cdk-changes/references/review-dimensions.md)
   (and the Python or Java review dimensions for the app code), and, when you enable it, the external
   reviewer (off by default), in parallel
9. Checks and diffs again after the fixes, then a documentation sync
10. The report, with the diff results per stack and for the whole app, and the operator's next steps

**Construct IDs.** A changed construct ID or path is a changed logical ID, and CloudFormation creates a
new resource and deletes the old one. The skill keeps existing IDs. A wanted rename becomes a separate
`cdk refactor` step: the skill shows the mapping with `--dry-run`, and you run the refactor before the
deploy.

## What asks first

The gate asks before each of these, before and after plan approval:

- `cdk diff` with the default or change-set method: it creates a change set with the deploy role
- `cdk deploy`, `destroy`, `bootstrap`, `import`, `watch`, `orphan`, `publish-assets`
- `cdk refactor` without `--dry-run`, and `cdk validate` (a service-side check)
- Every mutating `aws` CLI call
- Package installs and dependency changes: `pip`, `pip3`, `uv`, `poetry` and `pipx` `install`, `add` and
  `inject`; `npm`, `pnpm` and `yarn` `install`, `add`, `ci` and `update`; the Maven goals
  `dependency:get`, `dependency:copy`, `install:install-file`, `versions:set` and the `versions:use-*` and
  `versions:update-*` goals; `brew install`, `reinstall` and `upgrade`

`cdk synth`, `cdk diff --method template` and read-only `aws` calls run without asking. In a gated
session the rules of all five implementing skills apply together.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate").

The change-set diffs of step 6 are reads of live state the approved plan names: the gate's prompt is the
confirmation, and the skill does not ask again in the conversation. If you decline, or the session cannot
answer or has no credentials, the skill records the diff as not run in the ledger with the command for you
to run, goes on to verification and review, and the report says the replacement evidence is missing and
why. It never falls back to a template diff. A dependency install the plan names that you decline is not
retried and gets no substitute: the tasks that need it are marked `blocked`, the others are finished, and
the report's status is "verification incomplete (<command> denied)" (contract section 12).

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (change
digest, findings fixed, rejected and open, and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For the
CDK it adds the change-set diff result per stack and for the whole app; the next steps name any
`cdk refactor` to run first, the deploy command or pipeline run, the change set to inspect before
deploying, and read-only smoke commands. Nothing has been deployed.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-cdk-changes . main..HEAD
```

The arguments are the repository and the change: the working tree, a git range, a PR branch, a file list
or a diff file, optionally `--plan ai-planning/<slug>.plan`. The skill runs the same two stages, plus only
read-only checks (`cdk synth`, the app's tests, cdk-nag, `cfn-lint`, `cfn-guard`), verifies every finding
against the code and the synthesised templates, sets severity itself, and returns one Blocker, Major,
Minor and Nit report with a fix per finding and a verdict. It compares the logical IDs of the base and
the changed synthesised templates to find renamed constructs. The change-set diffs are offered with the
account the project's rules name and run only after you approve; without them the report says
"Replacement evidence: not run" and does not claim that nothing is replaced.

## Out of scope

- Deploying, bootstrapping, importing, running the refactor itself, or drift detection
- Plain CloudFormation templates ([cloudformation.md](cloudformation.md)), Terraform
  ([terraform.md](terraform.md)), Lambda handler code ([python.md](python.md), [java.md](java.md))
- Changing a specification item: the skill asks, and you decide
