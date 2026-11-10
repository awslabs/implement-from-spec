# Java practices: defaults and their sources

Defaults for a Java project, each with its source. Precedence (contract section 1): the approved plan and
the project's specifications and rules override these defaults; they apply only where the project says
nothing. Safety rules (no deploys, no secrets, no unapproved dependencies) hold either way. AWS facts were
read on 2026-10-16; re-read the cited page before relying on a date or a list, because they change.

## Contents

1. Build, tests and static analysis
2. Design defaults
3. AWS SDK for Java 2.x
4. AWS Lambda functions in Java
5. Lambda SnapStart
6. Dependencies

## 1. Build, tests and static analysis

- Build and test through the project's own entry point: its `scripts/` wrappers when its rules say so,
  else the wrapper it ships (`./mvnw`, `./gradlew`), else `mvn` or `gradle`. The wrapper pins the tool
  version the project tested with
- Tests first with JUnit 5 (and AssertJ when the project uses it): write the test, run it, see it fail
  because the behaviour is missing, then write the code. Each test cites its item ID or `TC-xxx` literally in
  its Javadoc or `@DisplayName` (a method name such as `tc003_rejects_empty` is not matched)
- Slice tests (`@WebMvcTest`, `@JsonTest`, plain JUnit) before `@SpringBootTest`; keep one context-loads
  test so a broken bean graph fails fast
- No network in unit tests: AWS SDK clients are mocked or replaced through the project's client factory;
  integration tests that need AWS are the operator's, in an account they choose
- Static analysis is what the build configures (Checkstyle, SpotBugs, PMD, Error Prone, a Spotless
  check). Run it with the build; never add a tool, a rule set or a suppression without an approved plan

## 2. Design defaults

From the demos kit's CLAUDE.md and review dimensions, where the project has no rule of its own:

- Layered packages: `api` (controllers, DTOs), `service` (logic), an adapter layer for persistence and
  outbound calls, `model` (records), `config` (`@Configuration`, `@ConfigurationProperties`). Controllers
  stay thin; services do no I/O of their own
- Records for value types, no Lombok; constructor injection only
- Tunables on the single `@ConfigurationProperties` bean, mapped to `application.yml` with environment
  overrides; extend it, never add a parallel one
- `jakarta.validation` on every request DTO field; a user-supplied string never reaches a file path, a
  shell command or a query unchecked
- No catch-all handler that hides a logic bug; never swallow `InterruptedException` (restore the interrupt
  flag); resources in try-with-resources

## 3. AWS SDK for Java 2.x

- **Version 2.x only.** "The AWS SDK for Java 1.x reached end-of-support on December 31, 2025. We
  recommend that you migrate to the AWS SDK for Java 2.x" (SDK for Java 1.x Developer Guide,
  `https://docs.aws.amazon.com/sdk-for-java/v1/developer-guide/basics.html`). A `com.amazonaws`
  dependency in new code is a finding; migrating existing v1 code is its own planned task
- **Versions through the BOM.** Declare the `software.amazon.awssdk:bom` in dependency management and
  depend on the individual service modules (`setup-project-maven.html`, "Declare the SDK as a dependency")
- **Explicit API-call timeouts.** "The SDK provides default values for some timeout options, such as
  connection timeout and socket timeouts, but not for API call timeouts or individual API call attempt
  timeouts. It is a good practice to set timeouts for both the individual attempts and the entire
  request." Set `apiCallTimeout` (the whole call, all retries) and `apiCallAttemptTimeout` (one attempt)
  on the client's `ClientOverrideConfiguration`, or per request (Best practices,
  `https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html`)
- **Reuse clients.** "Each service client maintains its own HTTP connection pool ... We recommend sharing a
  single instance of the client ... All service clients are thread safe." A client that is not shared is
  closed when no longer needed (same page)
- **Close response streams.** Read and close a `ResponseInputStream` (for example from
  `S3Client#getObject`) as soon as possible; an unread stream holds its HTTP connection (same page)
- Pagination through the SDK's paginators, not hand-rolled token loops, unless the item needs a bound

## 4. AWS Lambda functions in Java

- **Runtimes** (Lambda runtimes table, `https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html`):
  Java 25 (`java25`), Java 21 (`java21`) and Java 17 (`java17.al2023`) on Amazon Linux 2023, each with a
  projected deprecation date of Jun 30, 2029. Java 11 and Java 8 remain as `java11.al2023` and
  `java8.al2023`, and the Amazon Linux 2 identifiers `java17`, `java11` and `java8.al2` are projected to
  deprecate on Jun 30, 2027. The page recommends upgrading to an Amazon Linux 2023-based runtime as soon as
  possible. New functions use `java25` or `java21` unless the project fixes another
- **Handler and core logic apart**, so the logic is unit-testable; dependencies packaged with the function;
  only the SDK modules used, not the whole SDK; simple dependency injection over heavy frameworks for
  start-up time (Lambda Java handler page, "Code best practices for Java Lambda Event Functions",
  `https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html`)
- **Clients outside the handler method.** Static code and the constructor run during initialization, and
  resources created there are reused across invocations (same page, "Using global state"). Never keep user
  data or event content in that shared state
- **Idempotent handlers**: duplicate events handled the same way (same page)
- **Start-up**: the SDK guide recommends the AWS CRT-based HTTP clients for Lambda and setting the client's
  Region from `AWS_REGION` to shortcut lookups; it warns that `EnvironmentVariableCredentialsProvider`
  stops working once SnapStart is activated, so functions that may use SnapStart keep the default
  credentials chain (`https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/lambda-optimize-starttime.html`)

## 5. Lambda SnapStart

From `https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html`:

- Supported for Java 11 and later managed runtimes, ZIP and container image deployments
- Only on published function versions and aliases that point to them, never on `$LATEST`
- Not with provisioned concurrency, Amazon EFS, Amazon S3 Files, or ephemeral storage above 512 MB
- **Uniqueness**: unique IDs, secrets and entropy generated during initialization are copied into every
  restored environment; generate them after initialization (`snapstart-uniqueness.html`)
- **Network connections** opened during initialization are not guaranteed after restore; connections the
  AWS SDK opens usually resume, others are validated and re-established
- **Temporary data** cached during initialization (credentials, timestamps) is refreshed in the handler
- **Secrets**: the snapshot holds "the memory and disk state of the initialized execution environment"
  (`snapstart.html`), so a secret read during initialization (Secrets Manager, Parameter Store) into a
  static field is in every snapshot copy; read it in the handler or an `afterRestore()` runtime hook
  (`snapstart-runtime-hooks-java.html`)
- With SnapStart the runtime supplies container credentials instead of access-key environment variables
  (`snapstart-activate.html`, "Using SnapStart with AWS SDKs")
- Activation is a template property (CloudFormation `SnapStart`, the AWS SAM function's `SnapStart`, the
  CDK `SnapStartProperty`): an infrastructure change, planned with the template's owner

## 6. Dependencies

- A dependency, plugin or wrapper version the approved plan does not name is an amendment (contract
  section 5). The gate asks on `versions:*` goals, `dependency:get`, `install:install-file`, wrapper
  regeneration and Gradle lock writes
- Every new dependency is pinned (directly or through a BOM), recorded in the project's tech-stack list in
  the same change, and justified in the plan
- A database driver, ORM, broker, cache server or cloud SDK is an architectural decision: never added as
  an implementation detail
- A dependency that fails to resolve is never replaced by a similar-looking one: the name may be wrong or
  squatted. Stop and ask
