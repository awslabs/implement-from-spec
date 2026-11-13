# Python

Two skills:

- `implement-from-spec:implementing-python-from-spec` implements Python code (AWS Lambda handlers,
  Strands agents on AgentCore, shared libraries, scripts and their tests) from specification items. It
  ends at a green quality gate, a built artifact and a local smoke check. Deploying stays with you or your
  pipeline
- `implement-from-spec:reviewing-python-changes` reviews any Python change: five read-only Claude lens
  reviewers (specification fidelity, failure handling, types and design, security and AWS runtime,
  tests) and, when you enable it, the external reviewer (off by default), in parallel. It is also the Python skill's review step

## Requirements

- python3 3.9 or later for the plugin itself, and a Python that matches the project's target runtime
- pipx or uv, to install command-line tools without touching the project's environment
- The project's own toolchain: uv, pip or poetry with its lock files, and its linter, type checker and
  test runner. These are project dependencies, never installed by setup
- Optional: the AWS SAM CLI; the AWS CLI v2, for read-only checks of the target account
- The AWS Documentation MCP server, for AWS facts

Check and install with `/implement-from-spec:setup python`. Setup reads each tool's minimum version and
install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every gap
with its exact commands, and installs only what you approve. The skill checks the same tools, read-only,
at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A `CLAUDE.md` or `AGENTS.md` with the project's rules
- The specification items, with the `Interface:` names the code must use exactly. A common layout is a
  `specification/` tree with `functional/` (`SPEC-Fxxx`) and `non-functional/` (`SPEC-NFxxx`) topic files;
  structured `SPEC-<SVC>-n` items under `docs/specifications/` and a feature spec under `ai-planning/`
  work too. [spec-format.md](../spec-format.md) gives the rules for each
- A `.gitignore` that covers `__pycache__/`, virtual environments, `.pytest_cache/` and build output:
  after implementation every changed or untracked file must belong to a task (see "How a run goes",
  step 6)
- `pyproject.toml`, lock files and the CI job that runs the checks. A repository with no code or test
  toolchain yet gets a package skeleton and test setup proposed in the plan

## How a run goes

1. Ingest: the items and every interface they rely on (event envelopes, table items, error codes, shared
   modules), the toolchain and the Lambda runtime it targets, two neighbouring modules, and the
   documentation of every library and AWS API the design calls
2. Plan: `ai-planning/<slug>.plan`, with every module, function and handler described in prose and no
   Python
3. Analysis gate: `spec-trace.py plan`, then a self-review of pattern fit, boundaries (every external
   input parsed into a model, every failure mapped to the item's error code), idempotency, AWS clients,
   observability, testability, dependencies and scope
4. Your `approve`
5. Implementation in waves, test first. After each wave the project's full gate runs, typically
   `uv run --locked ruff format --check .`, `ruff check`, `mypy` and `pytest`, or the project's own
   wrapper or CI command. `--locked` makes a stale lock fail instead of being rewritten
6. Verification of each item, `spec-trace.py code`, the artifact build for each touched Lambda function or
   agent, and an import and entrypoint smoke check with stubbed AWS clients. What only a deployed system
   can show is listed as "needs runtime verification". `spec-trace.py code` also fails every file changed
   against `HEAD` that no task owns and that is not under `ai-planning/` (`unowned-change`): a write
   outside the plan is an amendment you approve, never a ruling the skill makes alone
7. Review through `reviewing-python-changes`, whose lens reviewers apply
   [`reviewing-python-changes/references/review-lenses.md`](../../skills/reviewing-python-changes/references/review-lenses.md)
   and
   [`reviewing-python-changes/references/review-dimensions.md`](../../skills/reviewing-python-changes/references/review-dimensions.md);
   Blockers and Majors are fixed
8. The quality gate again, then a documentation sync
9. The report, with each gate command, the build and the smoke check

## What asks first

The gate asks before each of these, before and after plan approval:

- Package installs: `pip`, `pip3`, `pipx`, `uv`, `poetry`, `pdm`, `conda` and `pipenv` `install`, `add`
  and `inject`, and `--with` options
- Lock file changes: `uv lock`, `uv sync`, `remove` and `update`, `pip-compile`, unless run with
  `--locked`, `--frozen`, `--check` or `--dry-run`
- `sam`, `cdk` and `serverless` deploy, destroy, bootstrap, watch, sync, delete and remove commands
- Every mutating `aws` CLI call

Read-only `aws` calls, `events test-event-pattern` and `route53 test-dns-answer` run without asking. In a
gated session the rules of all five implementing skills apply together.

A package the plan does not name, a lock change it does not describe, or a substitute for a package that
failed to install, is a question for you.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate"). When the gate asks about an install or lock change the approved
plan names, its prompt is the confirmation, and the skill does not ask again in the conversation. A step
you decline (or one a non-interactive session cannot answer) is not retried and gets no substitute: the
tasks that need it are marked `blocked` in the ledger with the command for you to run, the others are
finished, and the report's status is "verification incomplete (<command> denied)" (contract section 12).

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (snapshot,
change digest, review state, findings fixed, rejected, covered by gate and open, fix rounds,
and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For
Python the checks line names each quality-gate command, the artifact build and the smoke check with their
results. The review skill's own report feeds into it; it is not the final reply.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-python-changes . main..HEAD
```

The arguments are the repository and a git range or a file list, optionally `--plan
ai-planning/<slug>.plan`. The skill verifies every finding against the code, sets severity itself, and
returns one Blocker, Major, Minor and Nit report with a concrete fix per finding, opening with the
review state block (snapshot, recommendation, verification, approval required, risk, rollback; see
[external-review.md](external-review.md#the-review-around-it-snapshot-isolation-state-and-fix-rounds)).

## Out of scope

- CloudFormation ([cloudformation.md](cloudformation.md)), CDK apps, also in Python ([cdk.md](cdk.md)),
  and Terraform ([terraform.md](terraform.md))
- Deploying
