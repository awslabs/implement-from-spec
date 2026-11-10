# Python practices (Lambda, Strands on AgentCore, shared libraries)

Defaults with their sources (quotations read on 2026-10-14; runtimes, testing and the SDK watch item
re-read on 2026-10-16). The project's own rules win where they are stricter or different; a deviation from a default here is a ruling in the ledger, not a silent choice.
Re-read a cited page when a decision depends on it: versions and defaults change.

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

Ruff 0.17.0 (2026-10-09) changed its default rule set: projects pin ruff and list `select` explicitly.
