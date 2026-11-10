# Implementation and verification, Java specifics (after approval)

The contract (`${CLAUDE_PLUGIN_ROOT}/core/contract.md`, sections 6 to 8) is the workflow: the ledger, the
waves, the brief and its status block, test first, integration after each wave, the fix loop and the
verification. This file adds only what is specific to a Java project.

## Contents

1. Docs and shared files first
2. Waves
3. What the implementing brief adds
4. The build gate after each wave
5. Verification: build, artifact and smoke
6. Report lines

## 1. Docs and shared files first

The first wave's tasks (contract section 3: shared work is a task too) own the files several later tasks
need, so no two agents edit them concurrently:

- every touched `specification/` and `specification/test-cases/` file and the coverage matrix, when the
  project keeps them. The documented behaviour leads the code: new SPECs and TCs land first, with status
  `PLANNED`
- the `@ConfigurationProperties` class and `application.yml` (and its test copy), for the properties the
  later waves read
- the build file (`pom.xml`, `build.gradle(.kts)`, a version catalog), when the approved plan adds a
  dependency or plugin: exactly the coordinates and version the plan names, and the CLAUDE.md tech-stack
  line in the same task
- any other file the plan shows two or more tasks writing: a shared enum, an exception handler, a
  `@Configuration` class

No later task touches these files in the same wave as another.

## 2. Waves

- One task per class where possible: the production class and its unit test
- A task that only creates a new class can run beside others unless something it depends on is being
  written in the same wave; if B's test needs A to compile, A's wave comes first
- Two tasks that modify the same existing class go into different waves, or merge into one task
- A plan of one class, or a couple of strictly dependent classes, runs serially in the main conversation

## 3. What the implementing brief adds

The contract's brief (section 7), plus:

- the house style read in the ingest: records for value types, constructor injection, the package layer
  the class belongs to, the test style (JUnit 5, AssertJ, slice tests over `@SpringBootTest`)
- the scoped test command, through the project's entry point, for example
  `./scripts/test.sh` when the project defines one, `./mvnw -q test -Dtest=<TestClass>` or
  `./gradlew test --tests <TestClass>`
- each test cites its item ID or `TC-xxx` literally in its Javadoc or `@DisplayName` (spec-trace matches
  the literal ID; a method name such as `tc003_rejects_empty` does not count)
- "never weaken, skip or `@Disabled` a test to make it pass; never add a dependency, a plugin or a build
  flag; never run a formatter or fixer (`spotless:apply`, OpenRewrite) over files you do not own"
- no network in unit tests: AWS clients are mocked or replaced through the project's client factory, and
  an SDK client is never built inside the code under test for each call

## 4. The build gate after each wave

After the wave joins (contract section 7, step 5), the main conversation runs the project's full gate
through its own entry point, for example:

    ./mvnw -q verify                 (Maven: compile, tests, and the static analysis bound to verify)
    ./gradlew check                  (Gradle: tests and the static analysis bound to check)

or the project's `scripts/` wrappers, or the CI job's exact command line. Static analysis is the one the
project configures (Checkstyle, SpotBugs, PMD, Error Prone, Spotless check); none is added without an
approved plan. A formatter that rewrites files runs here, never inside a wave, and only when the project
uses one. Red is fixed before the next wave.

## 5. Verification: build, artifact and smoke

After contract section 8's per-item check:

1. **Build.** The project's package command (`./mvnw -q package`, `./gradlew build`, or its script)
   produces the artifact without warnings the project treats as errors. For a Lambda function, check the
   artifact the template or function configuration names (the shaded jar or zip, or the container image
   built locally), and that its handler class and method exist in it
2. **Smoke gate**, whenever request or output behaviour changed:
   1. Start the application in the background through the project's run command or script
   2. Call the endpoint with representative input, through the project's request script when it has one
      (`scripts/curl-<feature>.sh`); for a Lambda function, invoke the handler locally
      (`sam local invoke` with an event from the items or the fixtures, or a test harness calling the
      handler)
   3. Check the status, open any artefact the call produced and confirm it is structurally sane, and
      confirm the behaviour matches the item. Keep the response body for the report
   4. Stop what you started
   5. A visible defect is a blocker: reproduce, fix, re-run from step 1. When the smoke run shows the
      specification itself is wrong or ambiguous, stop and ask
3. **Docs.** Re-read the touched specification and test-case files and the coverage matrix against the
   diff: every new code path has a SPEC, every new test a `TC-xxx` cited in its name or Javadoc and a
   matrix row, statuses current. The frozen `.plan` and the input feature spec are not edited

## 6. Report lines

Contract section 11's report, with these lines filled for Java:

    Checks: <build command> -> <result>; <static analysis> -> <result>; coverage <n %> on changed files (when measured)
    Smoke: <invocation> -> <status>; output at <path>   (or: not applicable, no request or output change)
    Spec: new <SPEC ids>; amended <SPEC ids>. Test cases: new <TC ids>   (when the project keeps them)
