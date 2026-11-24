# Java practices: defaults and their sources

Defaults for a Java project, each with its source. Precedence (contract section 1): the approved plan and
the project's specifications and rules override these defaults; they apply only where the project says
nothing. Safety rules (no deploys, no secrets, no unapproved dependencies) hold either way, and the
security defaults of section 7 can be chosen among but not replaced by an unsafe form. AWS facts were
read on 2026-10-16; re-read the cited page before relying on a date or a list, because they change. A
reviewer, which opens no page, marks a finding that relies on such a date or list `unsure: verify
against the docs` instead, and the main conversation re-reads the page.

## Contents

1. Build, tests and static analysis
2. Design defaults
3. AWS SDK for Java 2.x
4. AWS Lambda functions in Java
5. Lambda SnapStart
6. Dependencies
7. Security defaults

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
  `https://docs.aws.amazon.com/sdk-for-java/v1/developer-guide/basics.html`). An SDK 1.x artifact
  (`com.amazonaws:aws-java-sdk-*`) in new code is a finding; migrating existing v1 code is its own planned
  task. Other libraries share the `com.amazonaws` group and are not SDK 1.x: the Lambda runtime and event
  libraries and the AWS Encryption SDK for Java (the review's JAVA-CTR-03 lists them)
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
- A version comes from the specification or from the project's own dependency management (its parent, a
  BOM, a version catalog). A version the plan proposes beyond those is marked as the plan's own choice:
  one recalled from memory is older than the advisories published since
- The plan-time check: before approval, the coordinates of every new dependency and plugin are matched
  against public advisory data (`core/scripts/dependency-audit.py check`, SKILL.md step 3). A result
  with no match says nothing about whether the version exists, is maintained or is compatible; a match
  is raised with the fix the advisories report, never resolved silently
- The review's audit: the review has the build tool resolve the project's dependencies and matches all
  of them, transitive ones included, against the same data. A vulnerable dependency the change
  introduced is a finding (JAVA-DEP-01) and, at Blocker or Major, fails the review's gate until it is
  fixed or the user accepts the advisory
- The resolved graph is what ships, not the declared one: a managed, forced or excluded version never
  takes a transitive dependency below the release that fixes an advisory
- No dynamic or snapshot versions (a version range, `+`, `latest.release`, `-SNAPSHOT`) outside the
  project's own modules: the same build file must resolve the same artifacts tomorrow
- Repositories over HTTPS only

The last three defaults, and JAVA-DEP-01, have their sources in the JAVA-DEP rules of the review's
security catalogue, `skills/reviewing-java-changes/references/security-dimensions.md`.

## 7. Security defaults

These defaults are the safe form of what an ordinary Spring Boot service or Lambda function writes, so
that generated code starts where the review's security reviewer begins: each ends with the rules of
`${CLAUDE_PLUGIN_ROOT}/skills/reviewing-java-changes/references/security-dimensions.md` it prevents, and
those rules hold the primary sources, the date they were read and the forms that differ by Java release
or Spring Boot generation. The repository's rules, the specification and the approved plan choose among
safe forms but cannot require an unsafe one: an item or plan line that does is raised with the user,
never implemented as written, because only the user can defer a security Blocker or Major.

### Injection

- Caller values reach a query only as bound parameters (`?`, `:name`, `setParameter`), Spring Data
  derived queries or the Criteria API, with sort columns through an allow-list map; LDAP, XPath and
  document-store queries use the interpreter's own parameters, never `$where`; caller text in a `LIKE`
  term with the escape character, `%` and `_` escaped and the escape character named in the query (an
  `ESCAPE` clause, the `escapeChar` argument of `CriteriaBuilder.like`), or through a Spring Data
  `Containing`, `StartingWith` or `EndingWith` method (JAVA-SEC-04, JAVA-SEC-13, JAVA-SEC-28)
- No caller text run as code, a format or a pattern: SpEL, EL, scripts and templates are constants with
  caller data only as variables or model values; an enum or a fixed map where the caller picks an
  operation, a class or a JNDI name; format strings constant (`"%s"`); caller text in a pattern through
  `Pattern.quote`, and input length bounded before any match (JAVA-SEC-14, JAVA-SEC-67, JAVA-SEC-15,
  JAVA-SEC-17, JAVA-SEC-16, JAVA-SEC-19)
- No shell: a Java API where one exists, otherwise a fixed command with allow-listed arguments as
  separate `ProcessBuilder` elements, `--` before caller values, untrusted data on standard input
  (JAVA-SEC-03)
- Caller text in a response encoded for its context: the template engine's auto-escaping (`th:text`),
  JSON responses written by the serialiser, data inside an inline `<script>` through an encoder made for
  both JavaScript and the script element, caller URLs in `href` or `src` limited to `http` and `https`,
  a maintained sanitiser for rich text; a header value containing `\r` or `\n` rejected, a download file
  name encoded as RFC 6266 describes (JAVA-SEC-63, JAVA-SEC-18)
- CSV exports written by a CSV library that quotes fields, never joined by hand, with every text field
  that starts with `=`, `+`, `-`, `@`, tab, carriage return, line feed or NUL prefixed with `'`; in
  Apache POI, caller text only through `setCellValue(String)`, never `setCellFormula`, and such cells
  given a style with `setQuotePrefixed(true)` (JAVA-SEC-27)

### Deserialisation and data binding

- JSON bound to concrete DTO records; polymorphism only as `Id.NAME` with listed `@JsonSubTypes`, never
  default typing or `Id.CLASS`; on Boot 4 (Jackson 3, `tools.jackson`) such settings go on the
  `JsonMapper` that binds requests, through a `JsonMapper` bean or a `JsonMapperBuilderCustomizer`, not on
  a Jackson 2 `ObjectMapper` bean (JAVA-SEC-07, JAVA-SEC-77)
- A message listener binds one fixed type, with type headers off and trusted packages limited to the DTO
  package; no Java serialisation of data from outside the process, or where it cannot be removed an
  allow-list `ObjectInputFilter` that ends in `!*`, sets `maxdepth`, `maxrefs`, `maxbytes` and `maxarray`
  and is also set JVM-wide; SnakeYAML 1.x only through `SafeConstructor`, 2.x with its default tag
  inspector (JAVA-SEC-69, JAVA-SEC-20, JAVA-SEC-78)
- One request record per operation with only the fields the caller may set (no ID, owner, tenant, role or
  price), mapped to the entity explicitly; never an `@Entity` bound from a request; Spring Data REST only
  when the plan names it (JAVA-SEC-66)

### XML

- XML from outside the artefact parsed, on every Java release, with each factory's own controls: DOM and
  SAX with `disallow-doctype-decl` set to `true` and XInclude left off; StAX with `SUPPORT_DTD` and
  `IS_SUPPORTING_EXTERNAL_ENTITIES` set to `false`; `TransformerFactory` with `ACCESS_EXTERNAL_DTD` and
  `ACCESS_EXTERNAL_STYLESHEET` set to `""`; `SchemaFactory` with `ACCESS_EXTERNAL_DTD` and
  `ACCESS_EXTERNAL_SCHEMA` set to `""` (a factory throws on a name it does not support); the JDK's
  limits never raised; stylesheets only from the classpath, with `FEATURE_SECURE_PROCESSING` on where
  extension functions are on by default (Java 17 and 21) (JAVA-SEC-08, JAVA-SEC-21, JAVA-SEC-22)

### Cryptography, randomness, TLS and secrets

- Bearer tokens, reset links and unguessable IDs as 16 or more bytes from one self-seeded
  `new SecureRandom()`, never `Random`, `Math.random()`, `ThreadLocalRandom` or a `UUID` as the only
  secret; a short code a person types from the same source, single use, bound to its account and
  purpose, expiring within minutes and with attempts and resends limited; under Lambda SnapStart,
  generated after restore, not during initialisation (JAVA-SEC-09, JAVA-SEC-46)
- Encryption as `AES/GCM/NoPadding` with a fresh IV from `SecureRandom` per message, stored beside the
  ciphertext; digests SHA-256 or stronger; RSA only as `RSA/ECB/OAEPWithSHA-256AndMGF1Padding` with keys
  of 3072 bits or more; MACs, signatures and token hashes compared with `MessageDigest.isEqual`
  (JAVA-SEC-09, JAVA-SEC-24, JAVA-SEC-26)
- Passwords hashed with Argon2id at m=19456 (19 MiB), 2 iterations and parallelism 1, or another of the
  equivalent configurations JAVA-SEC-23 lists, from configuration (Spring Security's
  `defaultsForSpringSecurity_v5_8()` figures are lower), or with the project's encoder
  where it meets the rule's figures. In Spring Security that is a `DelegatingPasswordEncoder` whose
  `idForEncode` maps to `new Argon2PasswordEncoder(16, 32, 1, 19456, 2)` (salt and hash bytes,
  parallelism, memory in KiB, iterations; it needs Bouncy Castle, a dependency the plan names) and whose
  map keeps `bcrypt` and every other id the stored hashes carry, so older hashes still verify and can be
  upgraded; not `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, which encodes with BCrypt;
  a 72-byte cap that rejects, never truncates, wherever BCrypt is used; `NoOpPasswordEncoder` and
  `{noop}` in tests only (JAVA-SEC-23, JAVA-SEC-55)
- TLS through the platform's default trust manager and protocol list, never a trust-all `TrustManager` or
  `HostnameVerifier`; host-name verification on (`setEndpointIdentificationAlgorithm("HTTPS")`) for raw
  sockets and engines and on Netty 4.1 clients, whose default leaves it off; only `TLSv1.3` and `TLSv1.2`
  where protocols are named (JAVA-SEC-25, JAVA-SEC-84)
- No secret in source, `application.yml`, a `@Value` default or a fixture meant for a real system:
  configuration resolved at run time from Secrets Manager, Parameter Store or the environment, with no
  default value; in a Lambda function only the secret's name or ARN in the environment, as under AWS SDK
  and Lambda below (JAVA-SEC-05, JAVA-SEC-100)

### Authentication, sessions and tokens

- Login through the framework's mechanisms with session-fixation protection at its default, and
  `SessionCreationPolicy.STATELESS` for a bearer-token API; session and token cookies `Secure`, `HttpOnly`
  and `SameSite=Lax` or `Strict`, with the `__Host-` prefix, `Path=/` and no `Domain` (`SameSite=None`
  only with `Secure`, for a cross-site use the plan names, CSRF protection on); remember-me only when the
  plan names it (JAVA-SEC-56, JAVA-SEC-57)
- A token verified before any claim is read, with the algorithm fixed in configuration and keys only from
  a configured JWK set or key store, never from the token's header; a resource server sets both
  `issuer-uri` and `audiences` (a hand-built decoder passes `setJwtValidator` the standard validators,
  `JwtValidators.createDefaultWithIssuer(issuer)`, plus an audience validator, so expiry and not-before
  stay checked) and checks scopes as `hasAuthority("SCOPE_x")`; code-flow clients use PKCE and Spring
  Security's `oauth2Login()` or `oauth2Client()`, never a hand-written callback (JAVA-SEC-58,
  JAVA-SEC-59)

### Authorisation

- An explicit `SecurityFilterChain` bean in the lambda DSL (`authorizeHttpRequests(auth -> ...)`), most
  specific rule first, ending in `anyRequest().denyAll()` or `.authenticated()`; every new route given its
  rule, `permitAll()` rather than `web.ignoring()`, matcher patterns that start with `/`, and a test that
  an anonymous request is refused (JAVA-SEC-60, JAVA-SEC-61, JAVA-SEC-71)
- Identity and tenant from the security context, never from the request; every object ID a request names,
  and every search it runs, limited to the caller in the service layer, by a scoped query
  (`findByIdAndOwnerId`) or an ownership check, with a test that another user's and another tenant's ID
  is refused (JAVA-SEC-11)
- `@EnableMethodSecurity` wherever method annotations are used (`securedEnabled = true` for `@Secured`,
  `jsr250Enabled = true` for `@RolesAllowed`; `@EnableReactiveMethodSecurity` on WebFlux), `@PreAuthorize`
  on a public, non-final method of the concrete bean, never self-invoked; a check that guards a write
  made part of the write (a conditional
  update, a unique constraint, a DynamoDB condition expression, `@Version`) (JAVA-SEC-62, JAVA-SEC-42)

### Web surface and Spring configuration

- CSRF protection on wherever browsers send credentials (`csrf.spa()` for single-page clients on Spring
  Security 7), off only for an API whose only credential is a bearer token, with the reason in a comment;
  no state change on `GET`; CORS as one `CorsConfigurationSource` with a finite origin list from
  configuration (JAVA-SEC-10)
- Actuator exposing `health` and what the plan names, details `when-authorized`; DevTools only as
  `developmentOnly` or optional, the H2 console only in a `local` profile; the default security headers
  kept, plus a Content-Security-Policy where HTML is rendered; error properties at their defaults on both
  Boot generations, errors answered with a generic body and a correlation ID (JAVA-SEC-10, JAVA-SEC-70,
  JAVA-SEC-72)
- Redirect targets and view names from a server-side map; a local target only as a path with no scheme
  or authority (`//host` rejected), an external one parsed once with `java.net.URI` and its host
  allow-listed; the forwarded-headers strategy set explicitly (`server.forward-headers-strategy` through
  Boot 4.1, `server.request.header.forwarded.strategy` from 4.2): to the proxy's when the plan names a
  proxy that overwrites the headers and is the only way in, otherwise to `NONE` (`none` from 4.2), since
  the unset default trusts them on a cloud platform Boot detects; links from a configured base URL
  (JAVA-SEC-64, JAVA-SEC-65)
- Uploads stored under a server-generated name outside the web root, typed by an extension allow-list and
  a content check, served back as attachments with `nosniff`; multipart limits finite (Boot's defaults are
  1MB per file and 10MB per request), raised only to a figure the plan states, and set explicitly where a
  library leaves them off (Commons FileUpload) (JAVA-SEC-68, JAVA-SEC-83)

### Files, resources and denial of service

- File names generated by the server where possible, otherwise `base.resolve(name).normalize()` on an
  absolute base checked with `Path.startsWith(base)`, in a directory tree only the application can write
  (otherwise every step opened relative to it through a `SecureDirectoryStream`), and the same check per
  archive entry, link entries rejected; temporary files from `Files.createTempFile` with `rw-------` and
  directories from `Files.createTempDirectory` with `rwx------`, deleted in `finally`; `CREATE_NEW`
  instead of an existence check (JAVA-SEC-02, JAVA-SEC-35, JAVA-SEC-36)
- Sizes a caller drives capped: reads stop at a configured maximum (`readNBytes(max + 1)`), a declared
  length is checked before allocation, page sizes are capped on the server, size arithmetic uses
  `Math.addExact` and its siblings, unpacking counts inflated bytes and entries against totals, and caches
  keyed by caller values are bounded by size and time (JAVA-SEC-37, JAVA-SEC-39, JAVA-SEC-38, JAVA-SEC-40)
- A costly operation (an export over every matching row, a bulk read to a file or S3, a job start, a
  call to a paid service) capped in the rows or items one call handles and limited per principal in how
  often and how many at once it runs, long work as an asynchronous job; logins, code checks and messages
  sent limited per account, per recipient and per source in a store every instance shares (JAVA-SEC-46)

### Input, outbound requests, logs and failure

- Allow-list `jakarta.validation` constraints on every request DTO field, a `@Size` beside every
  `@Pattern`, `@Valid` on the parameter and on nested DTOs; Lambda handlers and listeners call the same
  `Validator` and reject; input canonicalised first, then validated once (JAVA-SEC-01)
- Outbound destinations from configuration, the caller naming at most an identifier the server maps to
  one; a caller URL, where unavoidable, `https` only with host and port on an allow-list, every resolved
  address checked against the permitted networks and then used for the connection, redirects off or
  checked again (JAVA-SEC-12)
- Logs carry identifiers, not payloads, secrets, tokens or personal data; sensitive record components
  masked in `toString`; caller text encoded by the layout (Boot's `logging.structured.format.console`,
  Log4j 2's `%enc{%m}{CRLF}`) or stripped of `\r` and `\n`; no exception message, stack trace or SQL in a
  response (JAVA-SEC-06)
- An export or bulk read of personal data writes one audit record: the principal, the operation, the
  filter's field names (values only where they are not personal data), opaque record identifiers, the
  count, the time and the outcome, never the data itself (JAVA-SEC-47)
- Security checks fail closed: initialised to deny, granted only on the success path, a denying result or
  a rethrow on any exception, the transaction rolled back (JAVA-SEC-41)

### Platform mechanisms

- Request identity in parameters and locals; a `ThreadLocal` that holds it removed in `finally`;
  asynchronous work given identity as an argument or through a context-propagating executor, never
  `InheritableThreadLocal`; on Java 25, `ScopedValue`, whose binding ends with the call (JAVA-SEC-45)

### AWS SDK and Lambda

- SDK clients built with no `credentialsProvider(...)` call, so the default chain supplies the role's
  temporary credentials; `StsAssumeRoleCredentialsProvider` for another role, and for a customer's role
  the external ID the service generated and stored for that customer (JAVA-SEC-95, JAVA-SEC-101)
- Only a secret's name or ARN in the environment, its value read through a caching client and, under
  SnapStart, in the handler or an `afterRestore` hook (section 5); a KMS encryption context of non-secret
  identifiers, supplied again on decrypt from the server's records (JAVA-SEC-100, JAVA-SEC-104)
- S3 keys built on the server under a prefix the caller is authorised for, and `expectedBucketOwner` on a
  bucket the code does not fix; an event's key read with `getUrlDecodedKey()` and path-checked before any
  file use; a presigned URL only after the authorisation check, for a key the server derived, valid for
  the minutes the client needs, never logged or stored (JAVA-SEC-02, JAVA-SEC-97, JAVA-SEC-96)
- DynamoDB PartiQL with `?` placeholders and `parameters(...)`, expressions with `:name` values, table
  names from an allow-list and the tenant's partition key in every `WHERE` (JAVA-SEC-98)
- A Cognito token verified against the user pool's JWKS, then `exp`, `iss`, `token_use` and the app client
  ID; a Lambda authoriser's policy names every route the principal may call, and its `context` holds only
  verified claims (JAVA-SEC-102)

### Known-vulnerable usage

- `StringSubstitutor` only over a fixed map, never an interpolator with lookups; JDBC URLs from deployment
  configuration only; logging configuration packaged in the artefact, with no JNDI element or Janino
  condition; on the Lambda `java25` runtime, which lacks the Log4Shell patch, log4j-core 2.17.0 or later
  (JAVA-SEC-75, JAVA-SEC-81, JAVA-SEC-89, JAVA-SEC-76)

### Dependencies and build supply chain

- Exact or BOM-managed versions through the project's dependency management, on the newest supported
  release line the plan allows; an override only upwards, an exclusion only with a comment saying why;
  the enforcer rules `banDynamicVersions`, `requirePluginVersions`, `requireUpperBoundDeps` and
  `dependencyConvergence` proposed in the plan where the build lacks them (JAVA-DEP-04, JAVA-DEP-02,
  JAVA-DEP-03, JAVA-DEP-11)
- Repositories over HTTPS with checksums enforced, declared once (Gradle settings with content filters, a
  Maven settings mirror rather than the POM), no `mavenLocal()`; repository credentials from the
  environment or user-level files; no build step that downloads or runs a remote script (JAVA-DEP-05,
  JAVA-DEP-06, JAVA-DEP-09, JAVA-DEP-08)
- New dependencies and plugins checked against the advisory data at plan time and the resolved graph by
  the review's audit (section 6); a match fixed at the version the advisories report, through dependency
  management, or the library replaced; only the user can accept an advisory (JAVA-DEP-01)
