# Python practices (Lambda, Strands on AgentCore, shared libraries)

Defaults with their sources (quotations read on 2026-10-14; runtimes, testing and the SDK watch item
re-read on 2026-10-16). The project's own rules win where they are stricter or different; a deviation from a default here is a ruling in the ledger, not a silent choice.
The security defaults of section 12 can be chosen among but not replaced by an unsafe form.
Re-read a cited page when a decision depends on it: versions and defaults change. A reviewer, which
opens no page, marks a finding that relies on such a date or list `unsure: verify against the docs`
instead, and the main conversation re-reads the page.

## Contents

1. Runtime and packaging
2. Project layout
3. Handlers, clients and state
4. Models and typing
5. Boto3, and the SDK developer preview
6. DynamoDB conditions and transactions
7. Powertools for AWS Lambda (Python) v3
8. Observability caveats
9. Strands agents on AgentCore
10. Testing
11. Toolchain commands
12. Security defaults

## 1. Runtime and packaging

- Lambda's supported Python runtimes are `python3.14` to `python3.10`: 3.14, 3.13 and 3.12 on Amazon
  Linux 2023 (deprecation 2029-06-30, 2029-06-30 and 2028-10-31), 3.11 and 3.10 on Amazon Linux 2
  (deprecation 2027-06-30 and 2026-10-31). `python3.15` is in public preview: "Preview runtimes are not
  covered by the Lambda SLA or Technical Support, and should not be used for production workloads"
  (https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html). AgentCore direct code deploy
  supports `PYTHON_3_14`, `PYTHON_3_13` and `PYTHON_3_12` beyond 2026 (3.11 and 3.10 were deprecated on
  2026-06-30,
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-code-deploy-supported-runtimes.html).
  The project's pinned version is the one to use; a pinned runtime that is deprecated, in preview, or
  within six months of its deprecation date goes into the plan as a question, never a silent upgrade.
  Re-read the runtimes page when the plan depends on a date
- arm64: "Amazon Bedrock AgentCore requires ARM64 architecture for all deployed agents"
  (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html); on Lambda,
  arm64 "can achieve significantly better price and performance"
  (https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html)
- Bundle every dependency, Boto3 included: "we recommend you add all of your function's dependencies to
  your deployment package, even if versions of them are included in the Lambda runtime. This includes the
  Boto3 SDK" (https://docs.aws.amazon.com/lambda/latest/dg/python-package.html), and use the
  runtime-included SDK "only when you can't include additional packages in your deployment"
  (https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html). This overrides Powertools'
  assumption that the runtime's SDK is used. A project whose rules say the runtime's Boto3 is used (a
  zip with no layer for it) keeps that rule; it is a ruling, not a finding
- Build artifacts from the lock file for the target platform and interpreter, for example
  `uv export --frozen --no-dev --no-editable -o requirements.txt` then
  `uv pip install --no-installer-metadata --no-compile-bytecode --python-platform aarch64-manylinux2014
  --python 3.14 --only-binary=:all: --target packages -r requirements.txt` (uv's flags, per
  https://docs.astral.sh/uv/guides/integration/aws-lambda/ and the AgentCore code-deploy guide; plain pip
  spells it `--platform manylinux2014_aarch64 --python-version 3.14 --implementation cp --only-binary=:all:`;
  use the project's runtime version).
  Then import the handler from that tree to prove it loads. Lambda allows 250 MB unzipped including layers
  (https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- Lock files are the project's choice (`uv.lock`, `poetry.lock`, a `requirements.lock` per component).
  Never edit a lock by hand; regenerate it with the project's tool, and only as a plan task. `uv run`
  and `uv sync` lock and sync automatically; `--locked` makes them "raise an error instead of updating
  the lockfile", and `uv lock --check` is the equivalent check
  (https://docs.astral.sh/uv/concepts/projects/sync/)

## 2. Project layout

- Follow the items' `Target:` paths. For a new package, prefer `src/<package>/` with tests beside the
  package: pytest "strongly suggested to use a src layout" with the default import mode, and recommends
  `importlib` mode for new projects (https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- In a uv workspace "each package defines its own pyproject.toml, but the workspace shares a single
  lockfile" (https://docs.astral.sh/uv/concepts/projects/workspaces/); do not use one when members need
  conflicting requirements
- Shared code depends on nothing service-specific; services import shared modules, never the reverse

## 3. Handlers, clients and state

- "Separate the Lambda handler from your core logic" (https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html):
  the handler parses, calls one function, maps the result; logic is testable without the handler
- Handlers are synchronous: "You can't use the Python async function type for your handler function"
  (same page). Strands tools may be async
- "Initialize SDK clients and database connections outside of the function handler", and "don't use the
  execution environment to store user data, events, or other information with security implications"
  (https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html). Use a lazy client factory so tests can
  install mocks before the first client is built
- "Write idempotent code ... gracefully handle duplicate events" (same page); EventBridge may invoke a
  target more than once for one rule match

## 4. Models and typing

- pydantic v2 only, configured with `model_config`; `extra="forbid"` at every trust boundary ("Providing
  extra data is not permitted"; the default is ignore,
  https://pydantic.dev/docs/validation/latest/concepts/models/)
- An event payload is untrusted like model output: no value from it reaches `subprocess` with
  `shell=True`, `eval` or `exec`, or SQL built by string formatting; pass argument lists and bound
  parameters ("it is the application's responsibility to ensure that all whitespace and metacharacters
  are quoted appropriately to avoid shell injection vulnerabilities",
  https://docs.python.org/3/library/subprocess.html#security-considerations)
- Parse JSON with `model_validate_json`, not `model_validate(json.loads(...))`, and build each
  `TypeAdapter` once ("Each time a TypeAdapter is instantiated, it will construct a new validator",
  https://pydantic.dev/docs/validation/latest/concepts/performance/)
- mypy strict with the `pydantic.mypy` plugin; `--warn-unreachable` is not part of `--strict`
  (https://mypy.readthedocs.io/en/stable/command_line.html). Every `# type: ignore` carries its error code
- Timezone-aware datetimes only; `Decimal`, never float, for values written to DynamoDB

## 5. Boto3, and the SDK developer preview

- Boto3 is the default. Watch item: AWS documents a new "AWS SDK for Python" in Developer Preview,
  "intended for evaluation and testing only. Do not use it for production workloads. For production
  applications, use the AWS SDK for Python (Boto3)". It is async-first with per-service packages (for
  example `aws-sdk-dynamodb`), covers 24 services, and has no paginators, waiters or synchronous client
  yet; both SDKs "coexist in the same project without conflicts"
  (https://docs.aws.amazon.com/sdk-for-python/v1/guide/choosing-sdk.html,
  https://docs.aws.amazon.com/sdk-for-python/v1/guide/working-with-boto3.html). Plan it only when the
  project's rules ask for it, and re-read those pages first: its status will change

- Set the retry mode explicitly: "Legacy mode is the default mode". Standard mode retries 3 attempts with
  circuit-breaking; `max_attempts` in a Config "excludes the initial request", so consider
  `total_max_attempts` (https://docs.aws.amazon.com/boto3/latest/guide/retries.html)
- `connect_timeout` and `read_timeout` default to 60 seconds; set them below the function timeout
  (https://docs.aws.amazon.com/botocore/latest/reference/config.html)
- Branch on `error.response["Error"]["Code"]`, never on the message: messages "are subject to change"
  (https://docs.aws.amazon.com/boto3/latest/guide/error-handling.html). Log the request ID
- Paginate every list or query that can truncate: `get_paginator` where boto3 has one
  (`client.can_paginate(op)`), otherwise loop on the operation's continuation token yourself
- Clients are thread-safe but "cannot be shared across processes"
  (https://docs.aws.amazon.com/boto3/latest/guide/clients.html)

## 6. DynamoDB conditions and transactions

From https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html and the
CancellationReason API reference:

- `TransactWriteItems`: up to 100 actions and 4 MB; one item cannot be the target of two actions in one
  transaction, so a fence `ConditionCheck` is on a different item from any Put or Update
- A cancelled transaction raises `TransactionCanceledException`, which the SDK does not retry;
  `CancellationReasons` are ordered like `TransactItems`, with a `None` code for an item without error.
  Map each reason by index to the domain error the items name
- A client request token is idempotent for 10 minutes; reusing it with different parameters raises
  `IdempotentParameterMismatch`. When retries cross invocations, derive it from the business key *and*
  rebuild exactly the same request on retry (or derive it from a hash of the request), otherwise the retry
  fails with that error
- Stream consumers "shouldn't assume transaction atomicity or ordering guarantees"
- `ReturnValuesOnConditionCheckFailure=ALL_OLD` returns the current item on a failed condition, saving a
  read; a failed condition still consumes write capacity

## 7. Powertools for AWS Lambda (Python) v3

Source: https://docs.aws.amazon.com/powertools/python/latest/ (core and utilities pages). Use the parts the
project adopted:

- Logger: never log raw events (`log_event` is off by default "to prevent sensitive info being logged");
  `clear_state=True` so keys do not persist across invocations; Data Masking `erase()` for PII
- Metrics (EMF): `@metrics.log_metrics` flushes; at most 29 user dimensions; high-cardinality values go in
  `add_metadata`, never in dimensions. The EMF specification allows at most 100 metric definitions per log
  event and 30 keys per dimension set
  (https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html)
- Idempotency: call `@idempotent_function` with keyword arguments and `config.register_lambda_context`;
  `raise_on_no_idempotency_key=True`; records expire after an hour by default; any exception deletes the
  record
- Batch: enable ReportBatchItemFailures and use `process_partial_response` (`@batch_processor` is
  deprecated in v3); an empty or unknown `itemIdentifier` fails the whole batch
  (https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- Parameters are cached for 300 seconds by default; call `parameters.clear_caches()` in tests

## 8. Observability caveats

- The X-Ray SDK has been in maintenance mode since 2026-02-25 ("We recommend that you migrate to
  OpenTelemetry", https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html), and
  Powertools Tracer wraps it. Adopt Tracer only where the project decided to; AgentCore observability uses
  `aws-opentelemetry-distro`
- Tracer captures responses by default (`POWERTOOLS_TRACER_CAPTURE_RESPONSE`): turn it off for handlers
  that return sensitive data

## 9. Strands agents on AgentCore

- Entrypoint: `BedrockAgentCoreApp` with `@app.entrypoint`, or `/invocations` POST and `/ping` GET
  (https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/using-any-agent-framework.html)
- Always pin `model_id`: the default Agent uses a Bedrock model the SDK chooses
  (https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/)
- Tools: `@tool` builds the spec from the docstring and type hints, and "Language models rely heavily on
  tool descriptions" (https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/): every tool has a
  precise docstring. Model output never becomes a shell command, SQL or a file path unchecked
- Hooks (`BeforeToolCallEvent` can cancel or rewrite a call) are the documented seam for controls
  (https://strandsagents.com/docs/user-guide/sdk/agents/hooks/)
- Structured output: `structured_output_model` and `StructuredOutputException`
  (https://strandsagents.com/docs/user-guide/sdk/agents/structured-output/)
- Guardrails: `guardrail_id` and `guardrail_version`; check `stop_reason == "guardrail_intervened"`
- Pin minor versions; `strands.experimental` "may change between minor versions"
  (https://strandsagents.com/docs/user-guide/sdk/versioning-and-support/)

## 10. Testing

The Lambda Python testing guide sets the frame (https://docs.aws.amazon.com/lambda/latest/dg/python-testing.html):
cloud-based tests "provide the **most accurate** measure of quality", and CI "should run tests against a
suite of resources provisioned in the cloud before promoting". It points to Moto, a third-party project
on PyPI ("a Python library for mocking AWS services and resources"), and to the Powertools validation
utility for event and response validation. This skill writes and runs unit tests with mocks or stubs, offline; cloud and
end-to-end tests are the operator's, run against resources the operator provisions, and are listed in
the report, never run by the skill.

- Test first: a test for new behaviour must fail before the code exists, or it does not test that
  behaviour; a characterisation test for preserved behaviour passes before and after, by design
- moto: `@mock_aws` with fake credentials, and "ensure that you have your mocks set up BEFORE your boto3
  client is established" (https://docs.getmoto.org/en/latest/docs/getting_started.html). moto's support for
  `CancellationReasons` is not documented: test cancellation mapping with the botocore Stubber
  (`add_client_error`, `assert_no_pending_responses`,
  https://docs.aws.amazon.com/botocore/latest/reference/stubber.html)
- Fault tests inject each documented error code on the path (throttling, conditional check failure,
  transaction cancellation, timeouts) and assert the outcome the items name
- Hypothesis for invariants over many inputs (normalisers, parsers, serialisation round trips), with
  profiles registered in conftest
- Step Functions definitions: the TestState API, not Step Functions Local ("does not provide feature
  parity and is unsupported", https://docs.aws.amazon.com/step-functions/latest/dg/test-and-debug.html).
  TestState on a Task state calls the integrated service unless the test supplies a mock, so it can change
  real resources: mock every Task in local checks and treat unmocked runs as operator-authorised
  integration tests. EventBridge patterns: TestEventPattern, a pure check. Both are real AWS API calls, so
  they run in integration or conformance tests
- A project without a test toolchain gets one as the plan's first, shared task (runner, layout, the
  versions of any test dependencies); a project that already depends on Boto3 can test with `unittest`,
  `unittest.mock` and the botocore Stubber and add no dependency at all. Prefer the setup that adds no
  dependency when offline unit tests are all the items need: every test dependency is an install and a
  lock change that K22 asks about, and when that prompt is denied every test task is blocked
- Run the tests on the interpreter the project names (its `requires-python`, `.python-version`, CI
  image or rules), not whatever `python3` resolves to: a system `python3` may be older than the
  project's Lambda runtime (Amazon Linux 2023's is 3.9). Current pytest, moto, Boto3, pydantic, mypy
  and Powertools releases require Python 3.10 or later (their `Requires-Python` on PyPI, read
  2026-10-16: pytest 9.1.1, moto 5.2.4, boto3 1.43.114, pydantic 2.14.1, mypy 2.4.0,
  aws-lambda-powertools 3.36.0), so on an older interpreter they do not install. The plugin's own
  scripts need only `python3` 3.9

## 11. Toolchain commands

Use the project's commands. Typical shapes:

    uv lock --check                                # the lock is current
    uv run ruff format --check . && uv run ruff check .
    uv run mypy --strict <packages>
    uv run pytest --import-mode=importlib <tests> --cov=<pkg> --cov-branch
    uv run bandit -r <packages>                    # when the project uses it
    uv run pip-audit -r <exported requirements> --strict   # when the project uses it

`pip-audit` and `uv lock --check` are the project's own gate commands, run when the project uses them.
The review's required dependency audit (`core/scripts/dependency-audit.py`) is separate: it reads the lock
and pin files as data, installs nothing, and needs no environment.

Ruff 0.17.0 (2026-10-09) changed its default rule set: projects pin ruff and list `select` explicitly.

## 12. Security defaults

These defaults are the safe form of what an ordinary Lambda handler, agent, web service or script writes,
so that generated code starts where the review's security reviewer begins: each ends with the rules of
`${CLAUDE_PLUGIN_ROOT}/skills/reviewing-python-changes/references/security-dimensions.md` that check it,
and those rules hold the primary sources, the date they were read and the forms that differ by Python or
library release. The repository's rules, the specification and the approved plan choose among safe forms
but cannot require an unsafe one: an item or plan line that does is raised with the user, never
implemented as written, because only the user can defer a security Blocker or Major.

### Injection and code execution

- Caller values reach a query only as driver parameters (`execute(sql, params)`, bound `text()`
  parameters, Athena `ExecutionParameters`, Redshift `Parameters`); identifiers, sort fields and lookups
  from an allowlist; `LIKE` terms escaped (PY-SEC-04, PY-SEC-20, PY-SEC-21)
- No shell: a Python library where one exists, else an argument list with a full-path executable,
  allowlisted values, `--` before positional values and data on standard input; no `eval`, `exec` or
  dynamic import of caller or model text, a `dict` of allowed callables instead (PY-SEC-01, PY-SEC-02)
- Templates by constant name with caller data as context and autoescaping on; constant format strings;
  `re.escape` for caller text in a pattern and input length bounded; header values without `\r` or
  `\n`; CSV cells that start with a formula character prefixed with `'` (PY-SEC-22 to PY-SEC-27)

### Deserialisation, data binding and XML

- JSON into a pydantic model per entry point, `extra="forbid"`, constrained fields and
  `model_validate_json` on the raw body; never `pickle`, `marshal` or `shelve` on data another party
  wrote; YAML through `safe_load`; model files as safetensors or with `weights_only=True` and no
  allowlisted globals beyond the service's own types (PY-SEC-78, PY-SEC-32, PY-SEC-03, PY-SEC-30,
  PY-SEC-29)
- Owner, tenant and role never bound from a request: taken from the authenticated context (PY-SEC-32,
  PY-SEC-11)
- Untrusted XML through `defusedxml`, or lxml with entities, DTDs and network access off, and size limits
  before parsing (PY-SEC-33, PY-SEC-34, PY-SEC-37)

### Cryptography, randomness, TLS and secrets

- Tokens, reset links and unguessable ids from `secrets` (`token_urlsafe(32)`), never `random`; digests
  SHA-256 or stronger, MACs and tokens compared with `hmac.compare_digest` (PY-SEC-09, PY-SEC-44)
- Passwords hashed with Argon2id (`argon2-cffi` `PasswordHasher`) or the framework's configured hasher at
  the figures PY-SEC-40 lists; encryption through `Fernet` or `AESGCM` with a fresh nonce per message, or
  KMS and the Encryption SDK where the plan names them (PY-SEC-40, PY-SEC-41, PY-SEC-98, PY-SEC-99)
- TLS verification left on (no `verify=False`, no unverified context), HTTPS wherever credentials or data
  travel, and an explicit timeout on every outbound call (PY-SEC-07, PY-SEC-43, PY-SEC-106)
- No secret in source, a default or a fixture meant for a real system: only its name or ARN in the
  environment, the value read at run time through a caching client with no default (PY-SEC-06,
  PY-SEC-95)

### Authentication, authorisation and the web surface

- Login, logout and sessions through the framework, cookies `Secure`, `HttpOnly` and `SameSite=Lax` or
  `Strict`; tokens verified before any claim is read, with the algorithm fixed in code and keys from a
  configured JWKS, `aud`, `iss` and `exp` required; OAuth clients through Authlib with PKCE (PY-SEC-47,
  PY-SEC-49, PY-SEC-50, PY-SEC-51, PY-SEC-97)
- Deny by default: authentication applied to the app or router, every route given its rule; identity from
  the authentication context; every object id a request names limited to the caller by a scoped query,
  with a test that another user's and another tenant's id is refused; a check that guards a write made
  part of the write (a condition expression, `select_for_update`) (PY-SEC-54, PY-SEC-11, PY-SEC-58,
  PY-SEC-57)
- Debug off and a production server outside local settings; CSRF on wherever browsers send credentials;
  CORS from a finite origin list; redirect targets from a server-side map; hosts from a finite list;
  body, form and upload limits finite; uploads stored under server-generated names (PY-SEC-60 to
  PY-SEC-69)

### Files, resources, input and failure

- File names generated by the server, else resolved and checked with `is_relative_to` against the
  resolved base in a directory only this code writes, else descriptor-relative opens (PY-SEC-71); tar
  archives extracted with `filter="data"`; temporary files from `tempfile`, removed in `finally`; reads,
  decompression, page sizes and caches bounded; costly operations limited per caller (PY-SEC-05,
  PY-SEC-70, PY-SEC-73, PY-SEC-76, PY-SEC-77, PY-SEC-103)
- Outbound destinations from configuration, a caller naming at most an id the server maps; a caller URL,
  where unavoidable, `https` only with an allowlisted host, every resolved address checked and the
  connection made to the checked address with TLS host-name verification kept, redirects off (PY-SEC-08)
- Logs carry identifiers, not payloads, secrets or personal data, as structured fields; secrets held as
  `SecretStr`; errors answered with a generic body and a correlation id; security checks fail closed and
  never rest on `assert` (PY-SEC-10, PY-SEC-28, PY-SEC-80, PY-SEC-82)

### Platform, agents and AWS

- Request state in locals and parameters, never module globals, thread-locals or `os.environ`; no
  in-process sandbox for caller or model code (PY-SEC-85, PY-SEC-81)
- Model output treated as an untrusted caller and validated for its destination; tools limited to what the
  content's author may cause, permissions and human approval enforced in tool code or a
  `BeforeToolCallEvent` hook, not in the prompt; no secrets in prompts or memory (PY-SEC-86 to PY-SEC-89)
- AWS clients built with no credential arguments, so the default chain supplies the role; another
  party's role assumed with its external ID; S3 event keys URL-decoded and path-checked, keys built under
  an authorised prefix; presigned URLs only after the authorisation check, short-lived, never logged;
  PartiQL with `?` parameters and expressions with `:v` values; SNS messages verified before use
  (PY-SEC-90 to PY-SEC-96)

### Dependencies and build supply chain

- Every dependency declared, pinned through the project's lock file and on a supported release line; an
  override only upwards, with a comment saying why; indexes over HTTPS, one index per internal name;
  hashes kept; no install step that fetches and runs a remote script; no credentials in installer
  configuration (PY-DEP-02 to PY-DEP-09)
- A new package checked by its exact PyPI name before it is planned, and each new or changed version
  matched against the advisory data at plan time (SKILL.md step 3) and the lock file by the review's
  audit; a match fixed at the version the advisories report, or the library replaced; only the user can
  accept an advisory (PY-DEP-10, PY-DEP-01)
