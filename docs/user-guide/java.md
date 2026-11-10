# Java

Two skills:

- `implement-from-spec:implementing-java-from-spec` implements Java code (Spring Boot services, AWS
  Lambda functions, shared libraries and their JUnit tests, built with Maven or Gradle) from
  specification items or a feature spec. It ends at a built, tested artifact and a local smoke check.
  Deploying stays with you or your pipeline
- `implement-from-spec:reviewing-java-changes` reviews any Java change, with or without a plan: one Claude
  reviewer covering seven dimensions (correctness, design, patterns, extensibility, security,
  maintainability, readability) and, when you enable it, the external reviewer (off by default), in
  parallel. It is also the Java skill's review
  step

## Requirements

- A JDK at the Java version the project targets. Setup offers Amazon Corretto
- The project's build wrapper (`./mvnw` or `./gradlew`); Maven or Gradle only when the project has none
- Optional: the AWS SAM CLI, for projects that build or test Lambda functions with SAM; the AWS CLI v2,
  for read-only checks of the target account
- The AWS Documentation MCP server, for AWS facts

Check and install with `/implement-from-spec:setup java`. Setup reads each tool's minimum version and
install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every gap
with its exact commands, and installs only what you approve. The skill checks the same tools, read-only,
at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A `CLAUDE.md` or `AGENTS.md`. A project rule, for example "run builds only through `scripts/`",
  overrides every default of the skill
- The specification items. A common layout: `specification/SPECIFICATION.md` as the index,
  `functional/` (`SPEC-Fxxx`) and `non-functional/` (`SPEC-NFxxx`) topic files, `open-questions.md`, and
  `test-cases/TEST_CASES.md` with `TC-xxx` cases and a coverage matrix. A feature spec under
  `ai-planning/<feature>.md` works too. [spec-format.md](../spec-format.md) gives the rules for each
  format, including how a test cites a `TC-xxx`: the ID string itself in a comment or Javadoc, because a
  method name such as `tc003_searchesByStatus` does not count
- A `.gitignore` that covers `target/`, `build/` and `.gradle/`: after implementation every changed or
  untracked file must belong to a task (see "How a run goes", step 6)
- Optional: a design doc (for example `docs/DESIGN.md`) and `scripts/` wrappers for build, test, run and
  request calls, which the skill uses instead of raw commands

## How a run goes

1. Ingest: the input, the specification tree, the build and its static analysis (Checkstyle, SpotBugs,
   PMD, Error Prone, Spotless), the design doc and two neighbouring classes per affected package, and for
   AWS work the SDK for Java 2.x modules and client setup. An open question the feature depends on is a
   blocker, never a default
2. Plan: `ai-planning/<slug>.plan`, with every class described in prose and no Java
3. Analysis gate: `spec-trace.py plan` (with `TC-xxx` IDs checked when the items cite test cases), then a
   self-review of pattern fit, Java idioms, layer fit, AWS client use, concurrency, testability,
   dependencies and scope
4. Your `approve`
5. Implementation in waves, test first with JUnit through the project's own build entry point. The full
   build runs after every wave
6. Verification of each item, `spec-trace.py code`, the full build with the project's static analysis,
   the packaged artifact, and a smoke gate whenever request or output behaviour changed: start the
   application, call the endpoint (or invoke the Lambda handler locally), inspect the result, stop it.
   What only a deployed system can show is listed as "needs runtime verification". `spec-trace.py code`
   also fails every file changed against `HEAD` that no task owns and that is not under `ai-planning/`
   (`unowned-change`): a write outside the plan is an amendment you approve, never a ruling the skill
   makes alone
7. Review through `reviewing-java-changes`, whose Claude reviewer applies
   [`reviewing-java-changes/references/review-dimensions.md`](../../skills/reviewing-java-changes/references/review-dimensions.md);
   Blockers and Majors are fixed
8. The full build again, then a sync of the specification and test-case files
9. The report, with each build command, the static analysis and the smoke call, and the deploy command
   the skill did not run

A test that will not pass is debugged; it is never weakened, skipped or disabled.

## What asks first

The gate asks before each of these, before and after plan approval:

- Maven and Gradle dependency and version goals (`versions:*` other than `display-*` and `help`,
  `dependency:get`, `install:install-file`, `wrapper:wrapper`; Gradle `wrapper`, `useLatestVersions`,
  `dependencyUpdates`, `--write-locks` and `--update-locks`)
- Deploy and publish goals (`deploy`, `release:prepare`, `release:perform`, `jib:build`, Gradle `publish`
  tasks other than `publishToMavenLocal`, `jib`)
- `sam deploy`, `sync`, `delete`, `publish`, `pipeline bootstrap`, `remote invoke` and
  `remote test-event put` and `delete`
- Every mutating `aws` CLI call. Read-only calls, `events test-event-pattern` and `route53
  test-dns-answer` run without asking

In a gated session the rules of all five implementing skills apply together, so a `pip` or `brew` install
asks too. A dependency, plugin or build-tool version the plan does not name is an amendment you approve.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate"). When the gate asks about a dependency step or a live read the
approved plan names, its prompt is the confirmation, and the skill does not ask again in the conversation.
A step you decline is not retried and gets no substitute: the tasks that need it are marked `blocked` in
the ledger with the command for you to run, the others are finished, and the report's status is
"verification incomplete (<command> denied)" (contract section 12).

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (change
digest, findings fixed, rejected and open, and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For Java
the checks line names each build command, the static analysis and the smoke call with their results, and
the next steps give the deploy command the skill did not run.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-java-changes . main..HEAD
```

The arguments are the repository and a git range or a file list, optionally `--plan
ai-planning/<slug>.plan`. A pasted diff works too. The skill runs the project's tests while the reviewers
work, verifies every finding against the code, sets severity itself, and returns one Blocker, Major,
Minor and Nit report with a concrete fix per finding.

## Out of scope

- Infrastructure templates and CDK apps: [cloudformation.md](cloudformation.md), [cdk.md](cdk.md)
- Open-ended design discussion: write a spec first
- Deploying
