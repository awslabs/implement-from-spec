# Python review dimensions

Concrete, diff-level checks for Python changes (Lambda handlers, Strands agents, shared libraries,
scripts, tests) on Python 3.9 to 3.14 with mypy, pydantic v2, boto3 and Powertools for AWS Lambda. The
lens subagents of `reviewing-python-changes` apply the groups their lens owns; the orchestrator uses the
same checks when it reviews a lens itself. Precedence: the repository's rules (CLAUDE.md, AGENTS.md),
its specification items and the approved plan override every default here, and a deviation the project
prescribes is not a finding. Facts with versions or defaults were read on 2026-10-16.

## Contents

- How to apply
- 1. Contract and interface fidelity (PY-CTR)
- 2. Design and architecture smells (PY-ARC)
- 3. Language pitfalls (PY-IDM)
- 4. Types and data modelling (PY-TYP)
- 5. Error handling (PY-ERR)
- 6. Concurrency and resources (PY-CON)
- 7. AWS runtime: Lambda, boto3, DynamoDB, Powertools (PY-AWS)
- 8. Security (PY-SEC)
- 9. Logging and observability (PY-LOG)
- 10. Performance (PY-PRF)
- 11. Tests (PY-TST)
- 12. Style and readability (PY-STY)
- 13. Out of scope / handled elsewhere
- Sources

## How to apply

**Groups per lens.** Each of the five lens subagents loads `implement-from-spec:code-reviewer` and receives
its brief from `references/review-lenses.md` verbatim plus the groups below. The lens brief stays the
contract; these groups are the depth inside it.

- Specification fidelity: group 1, and every check whose *Look for* names an item's `Interface:` or
  `Acceptance:`, plus temporal compatibility of the interfaces and stored formats the change alters
- Failure handling: groups 5 and 6, plus PY-AWS-02, PY-AWS-07 and PY-AWS-08, plus temporal
  compatibility at run time (mixed versions, migration order, replay, rollback after new writes,
  partial deployment)
- Types and design: groups 2, 3, 4, 10 and 12
- Security and AWS runtime: groups 7, 8 and 9, plus PY-ARC-03. There is no separate Python
  application-security reviewer: this lens is the security reviewer for Python. The plugin's
  `iac-security-reviewer` reviews infrastructure (CloudFormation, and CDK apps written in Python through
  `reviewing-cdk-changes`), not application code
- Tests: group 11

A finding that belongs to another lens is still reported, as one out-of-lens head line naming the owning
lens (`references/review-lenses.md` section 6), with no Why, Evidence or Fix.
Shared principles and smells (PRN, ARC and SML IDs) are defined once in
`${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`; the checks here give the
Python form. As that file asks, name the concrete cost, not the principle, and report a tension the
rules and the plan do not settle as Minor `unsure`.

**Evidence.** A size, count or shape in a *Look for* line prompts a closer look; it is not a finding by
itself. A finding that needs evidence outside the diff (callers, the event source mapping, the
effective AWS configuration, the deployed runtime) names it or is `unsure`, saying what is missing.
Every Blocker and Major carries the `Evidence:` clause of `references/review-lenses.md` section 6
(trigger, at most three file:line steps from source to sink with a `+<n> steps:` tail for the rest,
wrong result) and `(pre-existing)` only when the defect and its exposure both exist
on the base independent of the change.

**Linters and the gate.** The quality gate runs the project's Ruff, mypy, pytest and (when present)
Bandit, in the main conversation; reviewers read code and never run it. A red gate makes the
recommendation Blocked whatever the findings. Rule codes are cited so a finding can say "enable Ruff
`B006`"; report a linter-detectable defect only when the rule is unselected or suppressed, or the file is
outside the gate's configuration (the orchestrator files a defect the green gate settles under *Covered
by gate*).
Ruff 0.17.0 (2026-10-09) changed its default rule set and, with no `target-version` or
`requires-python`, assumes Python 3.11: read the project's `select` list and target.
Rules marked *preview* in Ruff are opt-in.

**Severity classes** (the classes of `references/review-lenses.md` section 7; each check gives its
default and when it escalates; the orchestrator sets the final class from the code):

- **Blocker**: an item's interface missing, renamed or stubbed; a write that can duplicate or lose
  data; a swallowed failure on a documented error path; unchecked untrusted input controlling a shell
  command, `eval`, SQL text, a file path, a fetched URL or a deserialiser; a secret or sensitive data
  exposed; code that cannot run on the declared runtime (syntax, an API or a pinned dependency newer
  than the floor, an `async` handler, a return the runtime cannot serialise on the main path); a test
  suite that would pass with the feature broken, or a unit or default-selected test that can reach real
  AWS; a red quality gate; an undeclared dependency
- **Major**: wrong behaviour on a realistic but non-documented path; a type hole that hides a real
  path; a trust boundary without a strict model; logic in the handler; a client per invocation;
  implicit retry mode or default timeouts; missing pagination; high-cardinality dimensions; a missing
  fault test for a documented error code; a test that is order- or clock-dependent
- **Minor**: maintainability or local-correctness issue worth fixing in this change if quick
- **Nit**: style and polish; optional

Findings use the format in `references/review-lenses.md` section 6 (contract section 9), with the check
ID in brackets after the lens and, where the check names one, the shared ID beside it, for example
`[Major] src/orders/repo.py:41 - Types and design (PY-ARC-01, ARC-01) - ...`. This file's severity wins
over the shared file for Python, and `references/review-lenses.md` section 7 wins over both. A retired
ID names the check that absorbed it; cite that one.

## 1. Contract and interface fidelity (PY-CTR)

### PY-CTR-01 Public interface removed, renamed or re-signed

- **Look for:** a function, class, constant or module named in an item's `Interface:` line, listed in
  `__all__` or imported by another package that is deleted, renamed or moved; a new positional
  parameter inserted before existing ones; a parameter renamed or its default changed while callers
  pass it by keyword or position; a module path changed without a re-export
- **Why it matters:** other components and the specification bind to the name and signature, and
  Python finds the break only at import or call time, often in production
- **Instead:** keep the interface exactly as the item states; add new parameters keyword-only after
  `*`; for a planned rename keep the old name as an alias that calls
  `warnings.warn(..., DeprecationWarning, stacklevel=2)`, or update every caller in the same change
- **Severity:** Blocker when an item's `Interface:` names it; Major for any other public name
- **Source:** https://peps.python.org/pep-0008/#public-and-internal-interfaces — "Any backwards
  compatibility guarantees apply only to public interfaces."

### PY-CTR-02 Wire-format drift in pydantic serialisation

- **Look for:** a model field renamed without `alias`/`serialization_alias`; an alias changed;
  `model_dump()` or `model_dump_json()` where the contract uses the aliased names (`by_alias=True`
  missing, or `serialize_by_alias` changed in `model_config`); `exclude_none`/`exclude_unset` toggled;
  `mode="json"` dropped so `datetime` or `Decimal` change form
- **Why it matters:** the field names and formats on the wire are the contract another service, a
  stored item or the specification reads; the Python code still type-checks after the drift
- **Instead:** pin the wire name with `Field(alias=...)` and serialise with the options the contract
  needs, covered by a round-trip test against a fixture of the documented payload
- **Severity:** Blocker when the payload, event or stored item is named in an item; Major otherwise
- **Source:** https://pydantic.dev/docs/validation/latest/concepts/alias/ — "you can enable
  serialization by alias, which is disabled by default"

### PY-CTR-03 Error contract drift

- **Look for:** a different exception type raised than the one callers catch or the item names; an
  error-code literal that differs from the item's; `str(exc)` used as the error code; a domain
  exception now wrapped in `RuntimeError`; an HTTP status or `errorType` mapping changed in the handler
- **Why it matters:** callers branch on exception types and codes; a drift turns a documented,
  handled error into an unhandled one or the wrong response
- **Instead:** raise the item's exception or code exactly; keep the hierarchy designed for the
  catching side; map codes in one place
- **Severity:** Blocker when the item documents the error; Major otherwise
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "Design exception
  hierarchies based on the distinctions that code *catching* the exceptions is likely to need"

## 2. Design and architecture smells (PY-ARC)

### PY-ARC-01 boto3 shapes leaking past the adapter

- **Look for:** service or domain functions that take or return raw SDK responses (`resp["Item"]`,
  `["ResponseMetadata"]`, `{"S": ...}` attribute-value maps, `LastEvaluatedKey`), `mypy_boto3_*`
  `TypeDef` types in domain signatures, `ClientError` caught outside the adapter module, and deep
  chains such as `event["detail"]["requestParameters"]["bucketName"]` repeated across modules
- **Why it matters:** every caller couples to the SDK's shape and error model, so a change of store,
  of client versus resource, or of SDK ripples through the code base and the tests (stack form of
  ARC-01; feature envy and message chains, ARC-08, PRN-10, SML-09)
- **Instead:** one adapter (gateway) module per external system that translates responses into
  domain models and `ClientError` codes into domain exceptions; parse the event once at the edge
- **Severity:** Major when the shape crosses a package boundary or reaches the shared library; Minor
  inside one module
- **Source:** https://martinfowler.com/articles/gateway-pattern.html — "An object that encapsulates
  access to an external system or resource"

### PY-ARC-02 Business logic in the handler

- **Look for:** a `lambda_handler` or `@app.entrypoint` function that branches on business rules,
  calls boto3 directly or loops over records with logic inline. Length alone is not the finding:
  parsing, logging, dispatch and error mapping belong in the handler
- **Why it matters:** the logic cannot be unit-tested without events and contexts, nor reused by
  another trigger (stack form of ARC-13)
- **Instead:** the handler parses the event into a model, calls one function, maps the result or
  domain error to the response
- **Severity:** Major (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html — "Separate the Lambda
  handler from your core logic."

### PY-ARC-03 Import-time side effects and init-phase work

- **Look for:** module top level that writes, downloads or fetches a parameter once and never refreshes
  it after rotation; `os.environ["X"]` read at import in a shared library; `logging.basicConfig`,
  threads or `sys.path` edits at import; heavy imports for a rarely used path; secrets fetched every
  invocation with no cache (merged from PY-AWS-10). Clients and reusable connections at module scope in
  an entry module are the documented pattern, not this finding
- **Why it matters:** importing the module for a test needs credentials, network and configuration;
  on-demand Init is limited to 10 seconds, then retried inside the first invocation (provisioned
  concurrency and SnapStart allow longer); a never-refreshed secret breaks at rotation
- **Instead:** pure library imports; configuration in a settings object or a lazy factory
  (`functools.cache`) called from the handler; lazy imports for rare paths; Powertools parameters with a
  TTL matching rotation (5 minutes by default). Lazy initialisation moves the cost into the first
  invocation; it does not remove it
- **Severity:** Major for AWS or network side effects at import in a shared library, or a rotated
  secret never picked up; Minor for configuration reads, logging setup and heavy imports in an entry
  module
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html — "Lambda
  retries the `Init` phase at the time of the first function invocation"; Powertools parameters page
  ("defaults to 5 minutes"); Google Python Style Guide 3.17

### PY-ARC-04 Import cycles and inverted dependency direction

- **Look for:** a function-local `import` or a new `if TYPE_CHECKING:` import added to break a cycle
  the module structure still has; two modules that `from a import x` each other at module level; a
  shared library importing a service package (`from services.orders import ...` inside `shared/`)
- **Why it matters:** runtime cycles make import order load-bearing and fail with partially
  initialised modules; a shared module depending on a service inverts the dependency direction (stack
  form of ARC-03 and ARC-06). `TYPE_CHECKING` is `False` at runtime, so a type-only cycle does not fail
- **Instead:** move the shared concept down into the shared layer, or invert with a `Protocol` the
  shared side owns; services import shared code, never the reverse
- **Severity:** Major for a runtime cycle or an inverted dependency; Minor for a type-only cycle;
  Blocker when the project's rules forbid the dependency
- **Source:** https://docs.python.org/3/faq/programming.html#what-are-the-best-practices-for-using-import-in-a-module
  — "They fail when the 2nd module wants to grab a name out of the first"; pylint `R0401`;
  `python-practices.md` section 2

### PY-ARC-05 God modules and grab-bag utilities

- **Look for:** unrelated code added to `utils.py`, `helpers.py` or `common.py`; a module past about
  1,000 lines (pylint's `max-module-lines` default) or mixing parsing, business rules, AWS calls and
  formatting; a module that the repository's imports show most modules use and that imports service
  code (hub-like; `unsure` without that evidence)
- **Why it matters:** low cohesion makes every change touch the same file, and a hub makes any edit a
  change for every consumer (stack form of ARC-04, ARC-05, SML-02)
- **Instead:** split by responsibility (`parsing.py`, `repository.py`, `pricing.py`); keep shared
  modules small and dependency-free
- **Severity:** Minor; Major when the change grows a shared module into a god component or a hub that
  imports service code
- **Source:** pylint `C0302`; the size threshold is community consensus, not a style-guide rule

### PY-ARC-06 Mutable global state and runtime singletons

- **Look for:** `global` statements, module-level dicts or lists mutated by functions, singletons
  configured at runtime (`CONFIG.update(...)`), class attributes holding mutable defaults (Ruff
  `RUF012`), lists or dicts annotated `Final` and treated as constants
- **Why it matters:** behaviour depends on call order, tests leak into each other, and in Lambda the
  state survives into the next invocation (stack form of ARC-11; invocation data is PY-AWS-04).
  `Final` only stops rebinding, in the type checker
- **Instead:** pass state explicitly, or hold it in an object the caller owns; constants as tuples of
  immutable values, `frozenset`, or `MappingProxyType` over a private dict nobody mutates (it is a
  live, shallow view)
- **Severity:** Minor; Major when correctness depends on the mutation order
- **Source:** https://docs.python.org/3/library/typing.html#typing.Final — "There is no runtime
  checking of these properties."; https://docs.python.org/3/library/types.html#types.MappingProxyType —
  "when the mapping changes, the view reflects these changes"; Ruff `PLW0603`

### PY-ARC-07 Abstractions: Protocol ports, speculative ABCs, overrides that break substitution

- **Look for:** an `abc.ABC` or `Protocol` with one implementation and no declared boundary or test
  seam (`unsure` unless the plan rules out a second variant); a concrete adapter imported where the
  rules name a port; a `Protocol` with methods most consumers never call; `isinstance` dispatch on
  concrete classes; an override that narrows parameters, adds required ones, returns a non-subtype or
  raises `NotImplementedError`, often with `# type: ignore[override]`; stateful mixins that depend on
  MRO order; many ancestors (pylint `R0901`)
- **Why it matters:** speculative layers add indirection, a fat interface couples consumers to unused
  capabilities, and a broken override fails only where the subclass is substituted
  (shared PRN-05, PRN-06, PRN-09, PRN-11, SML-07, SML-13)
- **Instead:** a small `typing.Protocol` in the consuming module, split by consumer capability
  (`OrderReader`, `OrderWriter`), or a plain callable; composition over mixins; an ABC when the project
  wants runtime enforcement or shared code
- **Severity:** Minor; Major for an override that violates the base signature on a real path
- **Source:** https://peps.python.org/pep-0544/ — "Structural subtyping is natural for Python
  programmers"; mypy `[override]` (https://mypy.readthedocs.io/en/stable/error_code_list.html)

### PY-ARC-08 Complexity and parameter sprawl

- **Look for:** functions over about 50 lines (the lens brief's threshold), nesting deeper than three
  levels, many branches or returns, more than five parameters, and positional boolean flags at call
  sites (`process(event, True, False)`)
- **Why it matters:** complex functions hide untested paths, and boolean traps make call sites
  unreadable and easy to swap (shared SML-01, SML-03)
- **Instead:** guard clauses and early returns; extract named helpers; a dataclass or pydantic
  parameter object; keyword-only arguments or an `Enum` instead of flags
- **Severity:** Minor; Major when the function mixes I/O and logic on an item's critical path
- **Source:** https://google.github.io/styleguide/pyguide.html (3.18) — "If a function exceeds about 40
  lines, think about whether it can be broken up"; Ruff `C901`, `PLR0912`, `PLR0913`, `FBT001`
  (positional `bool` parameters), `FBT003` (positional `bool` values in calls)

### PY-ARC-09 Duplicated knowledge, scattered functionality and forced reuse

- **Look for:** a second copy of a retry loop, pagination loop, key builder, validation or error
  mapping a shared module or Powertools already provides; one concern implemented in several handlers;
  table names or a configurable tunable written as literals in several modules (merged from PY-STY-04).
  The opposite: a shared helper needing flags to fit unrelated callers, one model shared by separately
  owned services because the fields match, a wrapper that forwards and enforces nothing
- **Why it matters:** copies diverge and a fix lands in one of them, while a forced abstraction couples
  callers that change for different reasons (shared PRN-01, PRN-02, ARC-07, SML-10)
- **Instead:** call the existing helper; move the concern to one module; settings fields for tunables;
  separate models where meanings differ; inline empty wrappers unless they enforce a required seam
- **Severity:** Major when the copy is retry, idempotency, validation or error mapping, or the forced
  abstraction couples modules the project keeps apart; Minor otherwise (`unsure` when intent is unclear)
- **Source:** shared principles file (PRN-01, PRN-02, ARC-07, SML-10); Ruff `PLR2004`

### PY-ARC-10 Layer or module API bypass

- **Look for:** a service module importing a handler or framework request type; domain code building
  HTTP or database clients; imports of another package's `_`-prefixed modules or names; writes to a
  table, bucket or queue another module owns, bypassing its published operation
- **Why it matters:** the call skips the owner's validation, authorisation or concurrency rules and
  couples to its internals (stack form of ARC-02, ARC-12 and ARC-17)
- **Instead:** call the owner's public operation, adding a narrow one there when needed; compose
  concrete adapters at the application edge
- **Severity:** Major; Blocker when it breaks a stated layering or data-ownership rule or lets a write
  skip a required guard; `unsure` when ownership is not established
- **Source:** https://peps.python.org/pep-0008/#descriptive-naming-styles — "`_single_leading_underscore`:
  weak “internal use” indicator"

## 3. Language pitfalls (PY-IDM)

### PY-IDM-01 Defaults evaluated once

- **Look for:** `def f(items=[])`, `def f(opts={})`, `def f(ts=datetime.now(timezone.utc))`,
  `def f(request_id=uuid4())`, `def f(client=boto3.client("s3"))`; dataclass or pydantic fields whose
  default is computed at class creation (`created: datetime = datetime.now(timezone.utc)`)
- **Why it matters:** a function default is built once and shared by every call, so lists accumulate
  across calls (and Lambda invocations) and timestamps or IDs never change. Dataclasses reject
  unhashable defaults and pydantic deep-copies them, but a computed default is still computed once
- **Instead:** `def f(items: Optional[list[str]] = None)` (3.9-safe), then
  `items = [] if items is None else items`; `field(default_factory=...)` or
  `Field(default_factory=...)` for values computed per instance
- **Severity:** Major; Blocker when the shared default carries invocation or user data
- **Source:** https://docs.python.org/3/tutorial/controlflow.html#default-argument-values — "The
  default value is evaluated only once."; https://pydantic.dev/docs/validation/latest/concepts/fields/ —
  "Pydantic will create a deep copy of the default value"; Ruff `B006`, `B008`, `RUF008`, `RUF009`

### PY-IDM-02 Late-binding closures in loops

- **Look for:** `lambda` or nested `def` created inside a loop that reads the loop variable
  (callbacks, `executor.submit(lambda: f(x))`, handlers registered in a loop)
- **Why it matters:** a closure reads the variable when called, so callbacks run after the loop all
  act on the last item
- **Instead:** bind the value: `lambda x=x: f(x)`, `functools.partial(f, x)`, or pass it as an argument
- **Severity:** Major
- **Source:** https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result
  — "it is accessed when the lambda is called"; Ruff `B023`

### PY-IDM-03 Mutating a collection while iterating it

- **Look for:** `for k in d: del d[k]`, `for x in items: items.remove(x)`, appending to the list being
  iterated
- **Why it matters:** elements are skipped or the loop raises `RuntimeError` for dicts
- **Instead:** iterate over a copy (`list(d)`) or build a new collection with a comprehension
- **Severity:** Major
- **Source:** https://docs.python.org/3/tutorial/controlflow.html#for-statements — "can be tricky to get
  right"; Ruff `B909` (preview)

### PY-IDM-04 assert used for runtime checks

- **Look for:** `assert` validating input, permissions, configuration or invariants in non-test code
- **Why it matters:** assertions are removed under `-O`, so the check silently disappears
- **Instead:** `if not cond: raise ValueError(...)` or a domain exception; keep `assert` for tests and
  internal sanity checks the code does not rely on
- **Severity:** Major when the assert guards input or authorisation; Minor otherwise
- **Source:** https://google.github.io/styleguide/pyguide.html (2.4) — "Do not use `assert` statements
  in place of conditionals or validating preconditions."; Bandit `B101`, Ruff `S101`

### PY-IDM-05 Closed sets as bare strings

- **Look for:** status, type or mode values compared as string literals in several places
  (`if status == "SUCCEEDED"`), new values added in one branch only, `class Status(StrEnum)` on a
  project whose floor is below 3.11
- **Why it matters:** a typo or a new value compiles and silently takes the wrong branch
- **Instead:** an `Enum` (`class Status(str, Enum)` on 3.9 and 3.10, `StrEnum` from 3.11) or `Literal`
  type, validated at the boundary and matched exhaustively (PY-TYP-08)
- **Severity:** Minor; Major when the set is an item's documented state machine
- **Source:** https://docs.python.org/3/library/enum.html (`StrEnum` added in 3.11); lens brief 3

### PY-IDM-06 Syntax, APIs or dependencies newer than the supported floor

- **Look for:** against `requires-python`, Ruff `target-version` and the Lambda or AgentCore runtime:
  syntax (`match` 3.10, `except*` 3.11, PEP 695 `class C[T]` and `type X = ...` 3.12); APIs
  (`ExceptionGroup`, `asyncio.TaskGroup`, `StrEnum`, `tomllib`, `datetime.UTC` 3.11, `typing.override`
  3.12); `X | Y` evaluated at runtime (annotations without `from __future__ import annotations`,
  `isinstance(x, int | str)`, pydantic fields, which evaluate string annotations; 3.10); a pin whose
  `Requires-Python` excludes the floor (on 2026-10-16 current pydantic, boto3, Powertools, moto,
  pytest, mypy and strands-agents declare `>=3.10`)
- **Why it matters:** the module fails to import, raises `TypeError` or cannot be installed on the
  oldest supported interpreter, which unit tests on a newer one never show
- **Instead:** stay within the floor (`Optional[X]`, `typing_extensions`, `hasattr` checks), pin
  releases that support it, or raise the floor as a planned change. Python 3.9 reached end of life on
  2025-10-31 and 3.10 on 2026-10-01 (https://devguide.python.org/versions/): an end-of-life floor is a
  question for the plan, not a silent upgrade
- **Severity:** Blocker when code or a pinned dependency fails on the declared runtime; Minor for a
  floor that is merely end of life
- **Source:** PEP 604 and PEP 634 (`Python-Version: 3.10`), PEP 654 and PEP 680 (3.11), PEP 695 and
  PEP 698 (3.12); `requires_python` at https://pypi.org/pypi/pydantic/json (same endpoint per package)

### PY-IDM-07 Text I/O without an explicit encoding

- **Look for:** `open(path)`, `Path.read_text()` or `Path.write_text()` in text mode without
  `encoding=`, on files that cross systems (S3 objects, fixtures, exports)
- **Why it matters:** before Python 3.15 the default is the locale's encoding unless UTF-8 Mode is on,
  so the same file can decode differently between a laptop, CI and Lambda
- **Instead:** `encoding="utf-8"` on every text open
- **Severity:** Minor
- **Source:** https://docs.python.org/3/library/functions.html#open — "the default is
  platform-dependent"; PEP 686 (UTF-8 Mode default from 3.15); Ruff `PLW1514` (preview)

## 4. Types and data modelling (PY-TYP)

### PY-TYP-01 Type holes: Any, bare generics, blanket ignores and cast

- **Look for:** untyped `def`s in changed code; `Any` in public signatures (`**kwargs: Any`
  pass-through); bare `list` or `dict` annotations; `# type: ignore` without an error code;
  `typing.cast(...)` or `assert isinstance(...)` applied to data from an event, a response or a file
  instead of validating it
- **Why it matters:** each hole turns off checking downstream; `cast` asserts a type nothing checks
- **Instead:** precise types, `TypedDict` or models (PY-TYP-03); `# type: ignore[<code>]` with a
  comment; validate external data (PY-TYP-04) instead of casting it
- **Severity:** Minor; Major when the hole hides a real path (a field that can be `None`, a union
  member that lacks an attribute)
- **Source:** https://docs.python.org/3/library/typing.html#typing.cast — "at runtime we
  intentionally don't check anything"; mypy `--strict`, `[ignore-without-code]`; Ruff `ANN401`,
  `PGH003`

### PY-TYP-02 Implicit Optional and unchecked None

- **Look for:** `def f(x: str = None)`; the result of `dict.get`, `re.match`, `next(..., None)` or an
  optional model field used without a `None` check; a function annotated `-> Model` that can fall off
  the end and return `None`
- **Why it matters:** `AttributeError` or `TypeError` on the path where the value is missing, usually
  the error path nobody tested
- **Instead:** `x: str | None = None` (or `Optional[str]` below 3.10) and an explicit check; explicit
  return or raise at the end
- **Severity:** Major when the value comes from outside the process; Minor otherwise
- **Source:** https://peps.python.org/pep-0484/ — "Type checkers should move towards requiring the
  optional type to be made explicit."; Ruff `RUF013`, `RET503`; mypy `[union-attr]`

### PY-TYP-03 Dicts standing in for structured data

- **Look for:** `dict[str, Any]` or plain dicts with fixed keys passed between functions or layers,
  string keys repeated at many sites, results returned as tuples of four or more positional values
- **Why it matters:** key typos and missing keys are found at runtime only, and every consumer re-learns
  the shape (stack form of SML-04, SML-05)
- **Instead:** `TypedDict` for external shapes you only read, a dataclass or pydantic model for domain
  data, `NamedTuple` for small immutable records
- **Severity:** Minor; Major when the dict crosses a package boundary
- **Source:** https://peps.python.org/pep-0589/ (TypedDict)

### PY-TYP-04 Trust boundary not parsed into a strict model

- **Look for:** event bodies, API payloads, queue messages, files or model (LLM) output used as dicts
  without a pydantic model; boundary models, or models nested in them, without
  `ConfigDict(extra="forbid")`; `model_construct()` on external data; `model_validate(json.loads(body))`
  where the plugin's policy asks for `model_validate_json` (`python-practices.md` section 4); lax
  coercion where the item needs exact types (an identifier with leading zeros typed `int`)
- **Why it matters:** unknown fields are dropped silently by default, configuration does not reach
  nested models, `model_construct` skips validation, and lax mode turns `"123"` into `123`; a valid
  shape is no permission (PY-SEC-11)
- **Instead:** one model per boundary with `extra="forbid"` on it and every nested model,
  `model_validate_json(raw)`, `strict=True` or `StrictStr`/`StrictInt` where coercion is wrong, field
  constraints for domain rules, and the Powertools parser where the project uses it
- **Severity:** Major (lens brief); Blocker when the unvalidated value controls a command, query, path
  or tool call
- **Source:** https://pydantic.dev/docs/validation/latest/concepts/models/ — "Providing extra data is
  ignored (the default)"; https://pydantic.dev/docs/validation/latest/concepts/config/ — "configuration
  will not be propagated"

### PY-TYP-05 pydantic v1 API in v2 code

- **Look for:** `.dict()`, `.json()`, `.parse_obj()`, `.parse_raw()`, `@validator`, `@root_validator`,
  a nested `class Config`, `from pydantic.v1 import ...` mixed with v2 models
- **Why it matters:** the old names emit `DeprecationWarning` and some behave differently from their v2
  replacements
- **Instead:** `model_dump`, `model_dump_json`, `model_validate`, `model_validate_json`,
  `@field_validator`, `@model_validator`, `model_config = ConfigDict(...)`
- **Severity:** Minor; Major when v1 and v2 models are nested. When warnings are errors and the gate
  goes red, the red gate is the Blocker (How to apply)
- **Source:** https://pydantic.dev/docs/validation/latest/get-started/migration/ — "calling them will
  emit `DeprecationWarning`s"

### PY-TYP-06 Naive datetimes

- **Look for:** `datetime.utcnow()`, `datetime.utcfromtimestamp()`, `datetime.now()` without `tz`,
  `datetime(...)` without `tzinfo`, `strptime` without `%z`, comparisons between parsed and generated
  times, ISO strings without an offset written to storage
- **Why it matters:** naive values are read as local time, ordering comparisons between naive and aware
  values raise `TypeError`, and `utcnow()` is deprecated since 3.12
- **Instead:** `datetime.now(timezone.utc)`, `zoneinfo.ZoneInfo`, aware values end to end, ISO 8601
  with offset at the boundary
- **Severity:** Major when the value is persisted, compared or used for expiry; Minor in logs
- **Source:** https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow — "Order
  comparison between naive and aware `datetime` objects raises `TypeError`."; Ruff `DTZ001`, `DTZ003`,
  `DTZ005`, `DTZ007`

### PY-TYP-07 float where Decimal or int is required

- **Look for:** `float` values written through the boto3 DynamoDB resource or `TypeSerializer`;
  `Decimal(0.1)` built from a float; money or quantities typed `float`; `json.loads` of a payload bound
  for DynamoDB without `parse_float=Decimal`; `Decimal` passed to `json.dumps` without `default=`
  (PY-AWS-05)
- **Why it matters:** the resource layer rejects `float`, a `Decimal` built from a float carries the
  binary error into the stored value, and float arithmetic on amounts drifts
- **Instead:** `Decimal(str(x))` or `Decimal("0.1")`, `int` minor units for money,
  `json.loads(s, parse_float=Decimal)`, convert back at the serialisation edge
- **Severity:** Major; Blocker when stored amounts or keys can be wrong
- **Source:** https://docs.aws.amazon.com/boto3/latest/reference/customizations/dynamodb.html (Number
  maps to `integer` and `decimal.Decimal`, no `float`); https://docs.python.org/3/library/decimal.html

### PY-TYP-08 Non-exhaustive or repeated branching over enums and literals

- **Look for:** `if/elif` chains or `match` over an `Enum` or `Literal` with no final branch that fails,
  or with `else: pass`; a new member added without updating every branch; the same set dispatched by
  separate `if` chains, dicts or `isinstance` branches in several modules
- **Why it matters:** the new value falls through silently to the default behaviour, and each copy of
  the dispatch is one more place to miss (stack form of SML-06, PRN-04)
- **Instead:** end the chain with `assert_never(x)` (`typing` from 3.11, `typing_extensions` before);
  one owning dispatch table or strategy when several modules branch on the same set
- **Severity:** Minor; Major when the set is an item's state machine or the change edits three or more
  copies of one dispatch
- **Source:** https://mypy.readthedocs.io/en/stable/literal_types.html#exhaustiveness-checking

### PY-TYP-09 pydantic validation that does not run

- **Look for:** an `Optional[T]` or `T | None` field without a default where the input may omit it; a
  default or `default_factory` outside the field's constraints without `validate_default=True`;
  untrusted values passed to `model_copy(update=...)`; fields assigned after construction without
  `validate_assignment=True`; tests that always supply every field
- **Why it matters:** in pydantic v2 a nullable field without a default is required, defaults are not
  validated and copy updates are not validated, so valid input is rejected or a forbidden value
  reaches business logic
- **Instead:** `= None` only where omission is allowed; `validate_default=True` where the default must
  meet the constraints; re-validate (`Model.model_validate({**m.model_dump(), **update})`) instead of
  `model_copy(update=...)` on untrusted data; `validate_assignment=True` or `frozen=True`; tests for
  omitted, null and supplied values
- **Severity:** Major; Blocker when an item's interface or a write depends on it
- **Source:** https://pydantic.dev/docs/validation/latest/concepts/fields/ — "By default, Pydantic will
  not validate default values." and (implicit `None` for `Optional`) "This is no longer the case in
  Pydantic V2."; https://pydantic.dev/docs/validation/latest/concepts/models/ — "optional updates that
  aren’t validated"

## 5. Error handling (PY-ERR)

### PY-ERR-01 Bare, broad and silenced except

- **Look for:** `except:` or `except BaseException:` without a bare `raise`; `except Exception:` that
  logs and returns success, a default or `None`, or continues; `except ...: pass`,
  `contextlib.suppress(Exception)`; an exception built but never raised (`ValueError("bad id")` alone
  on a line) (merged from PY-ERR-02)
- **Why it matters:** a broad handler turns programming errors and documented failures into silent
  wrong results, and a missing `raise` is a validation that never fires (stack form of PRN-14)
- **Instead:** catch the specific exceptions the call raises; a broad catch only at an isolation point
  (one batch record, the outermost handler) that records the failure and re-raises or reports it as the
  item documents; suppress only a named, expected exception, with a comment
- **Severity:** Major; Blocker when a documented error path or a write path ends in a success response
  (the lens brief's class)
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "A bare `except:` clause
  will catch SystemExit and KeyboardInterrupt exceptions"; https://peps.python.org/pep-0020/ — "Errors
  should never pass silently."; Ruff `E722`, `BLE001`, `S110`, `S112`; Bandit `B110`, `B112`; pylint
  `W0718`

### PY-ERR-02 Silenced failures

Retired 2026-10-16: merged into PY-ERR-01

### PY-ERR-03 Exception translation that hides the cause

- **Look for:** `raise DomainError(...)` inside an `except` block without `from err`; `raise err`
  instead of a bare `raise`; `from None` below the public boundary, or at it without copying the
  `ClientError` code and request ID into the new exception
- **Why it matters:** without `from`, the original survives only as implicit context and the
  traceback reads as a second failure during handling, not a translation; `raise err` adds a frame;
  `from None` hides the cause from the default traceback (it stays on `__context__`)
- **Instead:** `raise OrderWriteFailed(order_id) from err`; bare `raise` to re-raise; `from None` only
  at a public boundary, with the relevant details copied
- **Severity:** Minor; Major when the code or request ID of an AWS failure no longer reaches the logs
- **Source:** https://docs.python.org/3/library/exceptions.html#exception-context — "the new
  exception's `__context__` attribute is automatically set to the handled exception"; Ruff `B904`,
  `TRY201`; pylint `W0707`

### PY-ERR-04 Generic exceptions instead of a domain hierarchy

- **Look for:** `raise Exception(...)` or `raise RuntimeError(...)` for domain failures; callers
  branching on `str(e)` or `e.args[0]`; custom exceptions deriving from `BaseException`
- **Why it matters:** callers cannot catch one failure without catching all of them, so documented
  errors cannot be mapped to their codes
- **Instead:** a small hierarchy (`class OrdersError(Exception)`, `class OrderNotFound(OrdersError)`)
  carrying the data callers need as attributes
- **Severity:** Minor; Major when callers must distinguish documented error codes
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "Derive exceptions from
  `Exception` rather than `BaseException`."; Ruff `TRY002`

### PY-ERR-05 try body larger than the failing call

- **Look for:** a `try` wrapping parsing, the AWS call and post-processing together, with an `except
  KeyError` or `except ClientError` that more than the intended line can trigger
- **Why it matters:** an unrelated bug is caught and mapped to the wrong domain error (a `KeyError` in
  parsing reported as "not found")
- **Instead:** wrap only the call that raises; move the rest to `else:` or after the block
- **Severity:** Minor; Major when the over-wide catch maps a bug to a documented error
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "limit the `try` clause to
  the absolute minimum amount of code necessary"; Ruff `TRY300` (a `return` that belongs in `else`)

### PY-ERR-06 Sentinel returns instead of raising

- **Look for:** functions that return `None`, `False`, `{}` or `-1` on failure while other paths return
  data; callers that do not check; a mix of `return value` and bare `return`
- **Why it matters:** the failure becomes a value that flows on as if valid, typically into a success
  response (stack form of PRN-14)
- **Instead:** raise a domain exception; reserve `None` for "absent" when absence is a normal result,
  and type it `T | None`
- **Severity:** Blocker when a documented error becomes a success (`references/review-lenses.md`
  section 7); Major when callers on a write path do not check; Minor otherwise
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "Be consistent in return
  statements."; Ruff `RET503`

### PY-ERR-07 Control flow in finally

- **Look for:** `return`, `break` or `continue` inside a `finally` block
- **Why it matters:** it discards the exception in flight; Python 3.14 emits `SyntaxWarning` for it
- **Instead:** move the `return` after the `try` statement; keep `finally` for cleanup only
- **Severity:** Major
- **Source:** https://peps.python.org/pep-0765/ (Python 3.14 What's New: "The compiler now emits a
  `SyntaxWarning`"); Ruff `B012`

### PY-ERR-08 boto3 errors mapped by message or too broadly

- **Look for:** `except Exception` around boto3 calls; `"ConditionalCheckFailed" in str(e)` or other
  message matching; `ClientError` caught without reading `e.response["Error"]["Code"]`; no handling of
  non-`ClientError` botocore exceptions (`EndpointConnectionError`, `ConnectTimeoutError`,
  `ReadTimeoutError`) where the items document a timeout outcome; the request ID not logged
- **Why it matters:** messages change, and connection or timeout failures bypass a handler that only
  expects `ClientError`
- **Instead:** `except ClientError as e: code = e.response["Error"]["Code"]` or
  `client.exceptions.ConditionalCheckFailedException`; `botocore.exceptions.BotoCoreError` for
  transport failures where they are handled; log `e.response["ResponseMetadata"]["RequestId"]`
- **Severity:** Major; Blocker when the mis-mapping swallows a documented error
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/error-handling.html — "These messages are
  subject to change and should not be relied upon in code."

### PY-ERR-09 Partial batch failures misreported

- **Look for:** an SQS, Kinesis or DynamoDB Streams handler that raises after records with
  non-idempotent side effects succeeded; caught per-record errors missing from `batchItemFailures`; an
  empty, `None` or wrong `itemIdentifier` (SQS `record["messageId"]`, Kinesis
  `record["kinesis"]["sequenceNumber"]`, DynamoDB `record["dynamodb"]["SequenceNumber"]`); a mapping
  without `ReportBatchItemFailures` in `FunctionResponseTypes` (`unsure` when not in the change); a FIFO
  or stream batch processed past the first failure
- **Why it matters:** raising replays the whole batch; without the setting Lambda ignores the response,
  so SQS deletes the failed messages; a bad identifier fails the whole batch; on streams Lambda retries
  every record after the lowest reported sequence number
- **Instead:** `process_partial_response` with a Powertools `BatchProcessor`, or a loop returning the
  source's identifier per failed record; on FIFO queues and streams stop at the first failure (FIFO:
  report every unprocessed record too); the mapping setting; idempotent processing, since successful
  records can still be retried
- **Severity:** Blocker when a failed record can be acknowledged (lost) or a non-idempotent side effect
  replayed; Major for a whole-batch retry of idempotent processing
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html — "the
  entire batch is considered a complete failure"; https://docs.aws.amazon.com/lambda/latest/dg/services-kinesis-batchfailurereporting.html
  (and `services-ddb-batchfailurereporting.html`) — "not processed by Lambda unless the
  `ReportBatchItemFailures` feature is explicitly turned on"

### PY-ERR-10 Retries and batch operations that duplicate or drop items

- **Look for:** a hand-rolled `for attempt in range(n)` around `put_item`, `send_message` or a payment
  call without a condition or idempotency token; fixed `time.sleep` backoff without jitter; a retry loop
  on top of the SDK's own retries; `UnprocessedItems` or `UnprocessedKeys` ignored; per-entry failures
  not inspected (`send_message_batch` or `delete_message_batch` `Failed`, Kinesis `put_records`
  `FailedRecordCount`, S3 `delete_objects` `Errors`); a conditional `put_item` or a transaction
  replaced by `batch_writer()` or `batch_write_item`
- **Why it matters:** retries of a non-idempotent write create duplicates, stacked retries multiply the
  attempts, a 200 response can carry failed entries that are silently lost, and `BatchWriteItem` takes
  no conditions, so batching a guarded write drops the guard
- **Instead:** make the write conditional or idempotent before retrying it; retry only failed entries with exponential backoff inside the time budget and surface
  the rest; keep conditional and transactional writes individual
- **Severity:** Blocker when items can be duplicated or dropped; Major otherwise
- **Source:** https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html —
  "you cannot specify conditions on individual put and delete requests";
  https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SendMessageBatch.html —
  "check for batch errors even when the call returns an HTTP status code of `200`"; Kinesis
  `PutRecords` API reference

## 6. Concurrency and resources (PY-CON)

### PY-CON-01 Resources not bound to a with block

- **Look for:** `open()`, `tempfile.NamedTemporaryFile`, sockets, `threading.Lock().acquire()`,
  `ThreadPoolExecutor` or database connections without `with` or `try/finally`; an S3
  `get_object()["Body"]` stream never closed or never fully read
- **Why it matters:** descriptors and pooled connections leak across warm invocations until the
  function hits its file-descriptor quota or the connection pool is exhausted
- **Instead:** `with open(...) as f`, `with lock:`, `with ThreadPoolExecutor() as pool:`,
  `with contextlib.closing(resp["Body"]) as body:`, `contextlib.ExitStack` for several resources
- **Severity:** Minor in scripts; Major in Lambda handlers and long-running services
- **Source:** https://docs.python.org/3/tutorial/inputoutput.html#reading-and-writing-files — "It is
  good practice to use the `with` keyword"; StreamingBody `close()`
  (https://docs.aws.amazon.com/botocore/latest/reference/response.html); Ruff `SIM115`

### PY-CON-02 Lambda /tmp and temporary files

- **Look for:** fixed file names under `/tmp` (`/tmp/report.csv`), files written per invocation and never
  removed, `tempfile.mktemp()`, hard-coded temp paths
- **Why it matters:** `/tmp` persists across invocations and is not cleared when Lambda resets after an
  error, so one invocation reads another's file or the space fills; `mktemp` has a race
- **Instead:** `with tempfile.TemporaryDirectory() as d:` per invocation; `mkstemp` or
  `NamedTemporaryFile`; cache only static assets in `/tmp`, by content hash
- **Severity:** Major; Blocker when one tenant's or request's data can be read by another invocation
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html — "the Lambda
  reset does not clear the `/tmp` directory content"; https://docs.python.org/3/library/tempfile.html
  (`mktemp`: "this is not secure"); Bandit `B306`, `B108`; Ruff `S306`, `S108`

### PY-CON-03 Blocking calls inside coroutines

- **Look for:** boto3 calls, `requests`, `time.sleep`, `open().read()`, `subprocess.run` or CPU-heavy
  loops inside `async def` (Strands async tools, AgentCore entrypoints, asyncio services)
- **Why it matters:** one blocking call stalls every task on the event loop for its whole duration
- **Instead:** `await asyncio.to_thread(client.get_object, ...)` (3.9+; cancellation in PY-CON-05), an
  async client the project approved, `await asyncio.sleep`, `loop.run_in_executor` for CPU work
- **Severity:** Major
- **Source:** https://docs.python.org/3/library/asyncio-dev.html#running-blocking-code; Ruff `ASYNC210`,
  `ASYNC230`, `ASYNC251`

### PY-CON-04 Lost concurrent work: unawaited coroutines, dangling tasks, unread futures

- **Look for:** an `async def` called without `await`; `asyncio.create_task(...)` whose result is not
  stored or awaited; fire-and-forget tasks in request handlers; `executor.submit(...)` futures
  discarded, `executor.map(...)` iterators never consumed, a `wait()` that ignores `future.exception()`
  (merged from PY-CON-07)
- **Why it matters:** an unawaited coroutine never runs, an unreferenced task can be garbage collected
  mid-run, and a worker's exception surfaces only through `result()`, so the work (often a write)
  silently fails or does not happen
- **Instead:** `await` it; keep tasks in a set or use `asyncio.TaskGroup` (3.11+); iterate
  `as_completed(futures)` and call `f.result()`, collecting failures
- **Severity:** Blocker when the lost work is a write or a documented side effect the response claims;
  Major otherwise
- **Source:** https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task — "to avoid a task
  disappearing mid-execution"; https://docs.python.org/3/library/concurrent.futures.html (`result()`);
  mypy `[unused-coroutine]`; Ruff `RUF006`

### PY-CON-05 asyncio fan-out, task lifetime and cancellation

- **Look for:** `gather(..., return_exceptions=True)` whose results are not checked; default `gather`
  whose siblings keep running after the first failure; unbounded fan-out with no `asyncio.Semaphore`;
  `except asyncio.CancelledError` (or `BaseException`) that does not re-raise; a timeout or cancellation
  around `asyncio.to_thread(...)` taken as proof that the boto3 call did not happen
- **Why it matters:** failures are dropped as results, orphaned tasks keep writing, unbounded
  concurrency triggers throttling, and swallowed cancellation breaks timeouts. A running thread cannot
  be cancelled, so its write may commit after the caller reported failure; a `TaskGroup` cancels
  siblings but rolls back nothing
- **Instead:** check each result for `BaseException`; `TaskGroup` (3.11+) for structured lifetime; a
  semaphore; re-raise `CancelledError` after cleanup; idempotent writes and an "outcome unknown" path
- **Severity:** Major; Blocker when work continuing after a timeout or failure can duplicate or corrupt
  data
- **Source:** https://docs.python.org/3/library/asyncio-task.html — `gather`: "won't be cancelled";
  `CancelledError` "should generally be propagated"; https://docs.python.org/3/library/concurrent.futures.html
  — `Future.cancel()` returns `False` "If the call is currently being executed"

### PY-CON-06 Thread safety: boto3 sessions and resources, shared state

- **Look for:** a `boto3.resource` or `boto3.Session` shared across threads; `boto3.client(...)` called
  in worker threads; a client passed to another process, or with custom event hooks used by several
  threads; shared caches mutated without a lock; check-then-act on shared state
- **Why it matters:** resources and sessions are not thread-safe, clients are generally thread-safe
  but not across processes or with custom hooks, and compound operations on built-ins are not atomic
  (free-threaded builds have no GIL)
- **Instead:** create a client before starting the threads and share it, or one session and resource
  per thread; never pass a client to another process; `threading.Lock` or `queue.Queue` for shared state
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/resources.html — "Resource instances are
  **not** thread safe"; https://docs.aws.amazon.com/boto3/latest/guide/clients.html — "they cannot be
  shared across processes"; https://docs.aws.amazon.com/boto3/latest/guide/session.html; Google Python
  Style Guide 2.18

### PY-CON-07 Executor futures whose exceptions are never retrieved

Retired 2026-10-16: merged into PY-CON-04

### PY-CON-08 GIL and multiprocessing assumptions

- **Look for:** CPU-bound work moved into threads to make it faster; `multiprocessing.Pool` or
  `multiprocessing.Queue` in Lambda code
- **Why it matters:** the GIL lets one thread run Python bytecode at a time on standard builds, and an
  AWS blog reports that Lambda has no `/dev/shm`, so `Pool` and `Queue` fail there (written for Python
  2.7: verify against the deployed runtime)
- **Instead:** threads for I/O-bound work; `ProcessPoolExecutor` outside Lambda; in Lambda,
  `multiprocessing.Process` with `Pipe`, or more memory (more vCPU) and fewer processes
- **Severity:** Minor for threads with no gain; Major for `Pool` or `Queue` on a path Lambda runs
- **Source:** https://docs.python.org/3/glossary.html#term-global-interpreter-lock;
  https://aws.amazon.com/blogs/compute/parallel-processing-in-python-with-aws-lambda/ — "you can't use
  multiprocessing.Queue or multiprocessing.Pool"

### PY-CON-09 Background work outliving the invocation

- **Look for:** threads, tasks or executors started in a handler and not joined before it returns;
  "send and forget" telemetry or writes after the response is built
- **Why it matters:** Lambda freezes the environment when the handler returns; the work resumes in a
  later invocation, if ever, so the response claims a write that has not happened
- **Instead:** finish or join all work before returning; hand asynchronous work to a queue or an
  asynchronous invocation
- **Severity:** Major; Blocker when the unfinished work is a documented side effect
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html — "Make sure
  that any background processes or callbacks in your code are complete before the code exits."

## 7. AWS runtime: Lambda, boto3, DynamoDB, Powertools (PY-AWS)

### PY-AWS-01 Client lifecycle

- **Look for:** `boto3.client(...)` or `boto3.resource(...)` inside the handler, a per-record loop or a
  frequently called function; a client built at import that the tests neither create after `mock_aws`
  starts nor patch
- **Why it matters:** a client per call adds latency and connection churn on every invocation; a
  client built before moto starts misses moto's handlers unless the test patches it (PY-TST-04)
- **Instead:** one client per service at module scope or behind a lazy factory (`functools.cache`) that
  tests can reset
- **Severity:** Major (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html — "Initialize SDK
  clients and database connections outside of the function handler"

### PY-AWS-02 Retry mode, timeouts and the time budget

- **Look for:** an effective retry configuration (`Config(retries=...)`, the client factory, the AWS
  config file or environment) left in legacy mode; no `connect_timeout` or `read_timeout`;
  `max_attempts` where `total_max_attempts` was meant; a worst case (attempts times timeouts plus
  backoff, per page or record) beyond the function timeout; loops that never call
  `context.get_remaining_time_in_millis()`; adaptive mode on a shared client
- **Why it matters:** legacy mode is the implicit default, and 60-second default timeouts outlive most
  function timeouts, so the function dies mid-write instead of failing cleanly; adaptive mode is
  experimental and rate-limits every caller of the client
- **Instead:** explicit standard mode, timeouts below the remaining budget, and a check of the
  remaining time before the next unit of work
- **Severity:** Major (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/retries.html — "Legacy mode is the default
  mode used by any Boto3 client you create." and "Adaptive mode is an experimental mode";
  https://docs.aws.amazon.com/botocore/latest/reference/config.html (60-second timeouts);
  https://docs.aws.amazon.com/lambda/latest/dg/python-context.html

### PY-AWS-03 Missing pagination

- **Look for:** a single call to `list_objects_v2`, `list_*`, `describe_*`, `query` or `scan` whose
  result is treated as complete; no `get_paginator` or `LastEvaluatedKey` loop; `Limit` mistaken for a
  total
- **Why it matters:** results are silently truncated (S3 lists up to 1,000 keys per page, DynamoDB
  `Query` returns at most 1 MB per page), so decisions are made on partial data
- **Instead:** `client.get_paginator(op).paginate(...)` where `client.can_paginate(op)`, otherwise loop on
  the continuation token until it is absent
- **Severity:** Major; Blocker when the truncated result drives a delete, a uniqueness check or an
  item's documented count
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/paginators.html — "Some AWS operations
  return results that are incomplete"; https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html

### PY-AWS-04 Invocation data in the execution environment

- **Look for:** module-level variables assigned from the event, the caller's identity, request IDs or
  user data; caches keyed by user without bounds; Powertools Logger keys appended without
  `clear_state=True` (module-scope metrics are PY-LOG-04)
- **Why it matters:** the execution environment is reused, so one caller's data leaks into the next
  invocation
- **Instead:** keep invocation data in local variables or objects created per invocation; reset
  per-invocation logger keys
- **Severity:** Blocker for user or security data; Major otherwise
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html — "don't use the
  execution environment to store user data, events, or other information with security implications"

### PY-AWS-05 Handler return value the runtime cannot serialise

- **Look for:** handlers returning `datetime`, `set`, a pydantic model instance or another object with
  no JSON form; an API Gateway proxy response whose `body` is not a string; application code calling
  `json.dumps` on DynamoDB `Decimal` values without `default=`
- **Why it matters:** the runtime's marshaller raises after the work has been done. The managed runtime
  interface client encodes `Decimal` as its string form and returns `bytes` unchanged, so neither fails
  at the handler boundary; standard `json.dumps` still rejects `Decimal`
- **Instead:** `model.model_dump(mode="json")`, explicit conversion to the representation the contract
  specifies, `json.dumps(body)` for proxy responses
- **Severity:** Major; Blocker when the path is the main success path
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html — "objects that can't
  be serialized by `json.dumps`"; https://github.com/aws/aws-lambda-python-runtime-interface-client
  (`lambda_runtime_marshaller.py`: `RawJSON(str(obj))` for `Decimal`; verify the deployed runtime)

### PY-AWS-06 async handler

- **Look for:** `async def lambda_handler(event, context)` or an async function configured as the Lambda
  handler
- **Why it matters:** Lambda's Python runtime does not run coroutine handlers
- **Instead:** a synchronous handler that calls `asyncio.run(main(event))` once
- **Severity:** Blocker
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html — "You can't use the
  Python `async` function type for your handler function."

### PY-AWS-07 Powertools idempotency misuse

- **Look for:** an `@idempotent_function` called with positional arguments; no
  `config.register_lambda_context(context)` in the handler; `event_key_jmespath` that includes
  timestamps, request IDs or the whole event; `raise_on_no_idempotency_key` left `False` where a key is
  required; an expiry window shorter than the source's redelivery window (`unsure` when not in the
  change)
- **Why it matters:** the decorator cannot find the payload, keys that change on every delivery defeat
  idempotency, and a missing key silently skips it, so duplicates are processed
- **Instead:** call with the keyword named by `data_keyword_argument`, key on the business identifier,
  require the key, and size `expires_after_seconds` to the redelivery window
- **Severity:** Blocker when duplicates can be written; Major otherwise
- **Source:** https://docs.aws.amazon.com/powertools/python/latest/utilities/idempotency/ — "you must
  call your decorated function using keyword arguments"

### PY-AWS-08 Unconditional writes where the items require a guard

- **Look for:** `put_item`, `update_item` or `delete_item` without `ConditionExpression` where an item
  says create-once, version-checked or must-exist; `ConditionalCheckFailedException` mapped to a generic
  failure; a read followed by an unconditional write (check-then-act)
- **Why it matters:** concurrent or duplicate events overwrite or duplicate data
- **Instead:** `ConditionExpression="attribute_not_exists(pk)"` or a version check, map the condition
  failure to the item's error, and use `ReturnValuesOnConditionCheckFailure="ALL_OLD"` to avoid a re-read
- **Severity:** Blocker (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html — "Write idempotent
  code."; `python-practices.md` section 6

### PY-AWS-09 DynamoDB expressions built by string formatting

- **Look for:** `UpdateExpression`, `FilterExpression`, `ConditionExpression` or
  `ProjectionExpression` built with f-strings or `%` from values or attribute names, especially names
  taken from request input
- **Why it matters:** values in the expression text break on reserved words and special characters, and
  input-controlled names let a caller update or read attributes the code did not intend
- **Instead:** `ExpressionAttributeValues` (`:v`) and `ExpressionAttributeNames` (`#n`) placeholders,
  or `boto3.dynamodb.conditions.Key`/`Attr`; validate attribute names against an allowlist
- **Severity:** Major; Blocker when request input controls the expression
- **Source:** https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ExpressionAttributeValues.html
  — "They're substitutes for the actual values that you want to compare"

### PY-AWS-10 Init-time work and parameter caching

Retired 2026-10-16: merged into PY-ARC-03

### PY-AWS-11 Recursive invocation

- **Look for:** a function that writes to the bucket prefix, queue, topic or stream that triggers it,
  or that invokes itself, without a guard that stops the loop
- **Why it matters:** an unbounded loop of invocations and cost
- **Instead:** write to a different prefix or destination, or carry and check a marker that stops the
  recursion
- **Severity:** Major; Blocker when the loop is unconditional
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html — "Avoid using recursive
  invocations in your Lambda function"

## 8. Security (PY-SEC)

### PY-SEC-01 Shell and process execution

- **Look for:** `subprocess.*(..., shell=True)`, `os.system`, `os.popen`, or argument lists whose
  executable or arguments come from request data, file contents or model (LLM) output
- **Why it matters:** shell metacharacters in the input run arbitrary commands with the function's
  role; an argument list removes shell interpretation only, so an input-chosen executable or an
  argument starting with `-` still changes what runs
- **Instead:** argument lists without a shell, an allowlisted executable, `--` before positional input
  and validated values; `shlex.quote` only where a shell is unavoidable
- **Severity:** Blocker with untrusted input; Major otherwise
- **Source:** https://docs.python.org/3/library/subprocess.html#security-considerations — "this library
  will not implicitly choose to call a system shell"; Bandit `B602`, `B605`; Ruff `S602`, `S605`

### PY-SEC-02 eval, exec and dynamic import

- **Look for:** `eval`, `exec` or `compile` on strings from input or model output; `importlib.import_module`
  or `getattr(module, name)` with input-controlled names; `ast.literal_eval` on untrusted input
- **Why it matters:** arbitrary code execution; `ast.literal_eval` runs no code, but a small input can
  exhaust memory or the C stack and crash the process
- **Instead:** `json.loads` into a model for data, `ast.literal_eval` only on bounded trusted input, an
  explicit dispatch dict for names
- **Severity:** Blocker with untrusted input; Major otherwise
- **Source:** https://docs.python.org/3/library/ast.html#ast.literal_eval — "A relatively small input
  can lead to memory exhaustion or to C stack exhaustion"; Bandit `B307`, `B102`; Ruff `S307`

### PY-SEC-03 Unsafe deserialisation and parsers

- **Look for:** `pickle.loads`, `shelve`, `marshal`, `jsonpickle` or `joblib.load` on data from S3,
  queues, caches or users; `yaml.load` without `SafeLoader`; `xml.etree`, `minidom` or `xmlrpc` on
  attacker-controlled XML
- **Why it matters:** unpickling and unsafe YAML instantiate arbitrary objects (code execution); XML
  parsers on old Expat versions are open to entity-expansion attacks
- **Instead:** JSON with a pydantic model; `yaml.safe_load`; `defusedxml` for untrusted XML
- **Severity:** Blocker for pickle or unsafe YAML on untrusted data; Minor for XML on a current Expat
  (Python documents Expat below 2.7.2 as possibly vulnerable)
- **Source:** https://docs.python.org/3/library/pickle.html — "Only unpickle data you trust";
  https://docs.python.org/3/library/xml.html#xml-security; Bandit `B301`, `B506`, `B314`; Ruff `S301`,
  `S506`

### PY-SEC-04 SQL and query injection

- **Look for:** SQL built with f-strings, `%`, `.format` or `+` and passed to `cursor.execute`,
  SQLAlchemy `text()`, the Redshift Data API or Athena `StartQueryExecution` without parameters
- **Why it matters:** input becomes query syntax
- **Instead:** driver parameters (`cursor.execute(sql, params)`), bound parameters in `text()`, the
  `Parameters` or `ExecutionParameters` arguments of the AWS APIs
- **Severity:** Blocker with untrusted input; Major otherwise
- **Source:** Bandit `B608`; Ruff `S608` — "Possible SQL injection vector through string-based query
  construction"

### PY-SEC-05 Path traversal and archive extraction

- **Look for:** request data, S3 keys or model output joined into a local path
  (`os.path.join(base, name)`, `base / name`) without resolving and checking containment;
  `tarfile.extractall()` without the `'data'` filter, or availability inferred from the version
  number; `zipfile.extractall` on untrusted archives without size limits
- **Why it matters:** `../` or absolute names read or overwrite files outside the intended directory,
  and members can escape it or exhaust `/tmp`; where an attacker can also write in the directory, a
  resolved-path check races with a symlink swapped in before use (TOCTOU)
- **Instead:** `p = (base / name).resolve()` then `p.is_relative_to(base.resolve())` (3.9+), rejecting
  `..`, absolute paths and NUL, in a directory only this code writes; `extractall(filter="data")` after
  `hasattr(tarfile, "data_filter")`, failing closed without it; limit member count and total size
- **Severity:** Blocker with untrusted input
- **Source:** https://docs.python.org/3/library/tarfile.html#tarfile-extraction-filter — "may be
  backported to older versions as security updates" (default `'data'` from 3.14);
  https://cwe.mitre.org/data/definitions/367.html; Bandit `B202`; Ruff `S202`

### PY-SEC-06 Hard-coded secrets

- **Look for:** passwords, tokens, API keys or connection strings as literals in source, in defaults
  (`os.environ.get("API_KEY", <literal default>)`), in test fixtures that look real, or in sample events
- **Why it matters:** the secret is in version control and every artifact built from it
- **Instead:** Secrets Manager or Parameter Store through the project's helper; no default for a
  secret, so a missing one fails fast; obvious placeholders (`<from Secrets Manager>`) in fixtures
- **Severity:** Blocker (the lens brief's class)
- **Source:** Bandit `B105`, `B106`, `B107`; Ruff `S105` to `S107`

### PY-SEC-07 TLS verification and HTTP timeouts

- **Look for:** `verify=False`, `ssl._create_unverified_context()`, `urllib3.disable_warnings`, `http://`
  endpoints for credentials or data; `requests` calls with no effective `timeout=`; HTTPX clients or
  calls with `timeout=None`
- **Why it matters:** disabled verification allows interception; Requests has no default timeout and
  can hang until the function times out; HTTPX defaults to 5 seconds of inactivity, and neither
  library's timeout bounds the whole call
- **Instead:** default verification (or a pinned CA bundle), HTTPS, `timeout=(connect, read)` for
  Requests or an `httpx.Timeout` on the client, and an overall deadline from the remaining time
- **Severity:** Blocker for disabled verification on a production path; Major for a missing timeout
- **Source:** https://requests.readthedocs.io/en/latest/user/advanced/#timeouts — "By default, requests
  do not time out unless a timeout value is set explicitly."; https://www.python-httpx.org/advanced/timeouts/
  — "raise a TimeoutException after 5 seconds of network inactivity"; Bandit `B501`, `B113`; Ruff
  `S501`, `S113`

### PY-SEC-08 Server-side request forgery

- **Look for:** URLs from request data or model output passed to `requests.get`, `httpx`,
  `urllib.request.urlopen` (which also accepts `file:`) or an SDK `endpoint_url` without a scheme and
  host allowlist; redirects followed (Requests' default) without validating each hop; a host check
  followed by a second DNS lookup at connect time
- **Why it matters:** the caller makes the function reach internal endpoints, metadata services or
  local files with its network position and role, whether or not the response is returned
- **Instead:** parse with `urllib.parse`, allow only `https` and listed hosts, resolve once, reject
  private and link-local addresses and connect to the validated address; disable redirects or validate
  every hop; a fixed egress path (proxy, VPC endpoint policy) for model-chosen URLs
- **Severity:** Blocker when request or model input controls the destination unchecked; Major for a
  partial check
- **Source:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
  — "Domain allowlisting alone does not prevent DNS rebinding."; https://requests.readthedocs.io/en/latest/user/quickstart/
  (redirection); Bandit `B310`; Ruff `S310`

### PY-SEC-09 Insecure randomness and hashing

- **Look for:** `random.random`, `random.choice` or `uuid1` for tokens, IDs that must be unguessable,
  passwords or nonces; `hashlib.md5` or `sha1` for signatures, integrity or passwords
- **Why it matters:** `random` is predictable, and MD5 and SHA-1 collide
- **Instead:** `secrets.token_urlsafe()`, `uuid4`; `hashlib.sha256`, `hmac.compare_digest`; a password <!-- pragma: allowlist secret - names a password KDF, no value -->
  KDF; `usedforsecurity=False` for non-security hashing
- **Severity:** Major; Blocker when the value guards authentication
- **Source:** https://docs.python.org/3/library/secrets.html — "designed for modelling and simulation,
  not security or cryptography"; Bandit `B311`, `B324`; Ruff `S311`, `S324`

### PY-SEC-10 Sensitive data in logs, traces, errors and reprs

- **Look for:** `logger.info(event)`, `log_event=True`, logging `record["body"]`, headers, credentials
  or document content; Powertools Tracer capturing responses of handlers that return sensitive data;
  exception messages with PII returned to callers; pydantic models holding secrets as `str` (their
  `repr` prints them)
- **Why it matters:** logs and traces are widely readable and long-lived, so sensitive data spreads
  beyond its controls
- **Instead:** log identifiers, not payloads; `capture_response=False`; generic client-facing errors;
  `SecretStr` for secrets; Powertools data masking where the project uses it
- **Severity:** Blocker (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/powertools/python/latest/core/logger/ — "disabled by default
  to prevent sensitive info being logged"; https://docs.aws.amazon.com/powertools/python/latest/core/tracer/

### PY-SEC-11 Resource or tool selection without authorisation

- **Look for:** tenant IDs, object keys, account IDs, tool names or action arguments from the request
  or model output used because they pass the schema; a handler or Strands tool acting with the
  function's role without checking that the authenticated caller may reach that resource or action
- **Why it matters:** well-formed input can still point a privileged handler or agent at another
  caller's data or a forbidden action (insecure direct object reference)
- **Instead:** take identity from the trusted authentication context (authoriser claims, AgentCore
  identity); check resource and action permission in the code that acts; constrain agent tools in code
  (a `BeforeToolCallEvent` hook), not by prompt or guardrail
- **Severity:** Blocker when unauthorised access or side effects are reachable; `unsure` when the
  authoriser is outside the change
- **Source:** https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html — "Permission
  should be validated correctly on every request"; `python-practices.md` section 9; shared ARC-12

## 9. Logging and observability (PY-LOG)

### PY-LOG-01 Unstructured logging and print

- **Look for:** `print()` in handlers and libraries; values interpolated into the message where the
  project requires structured fields; expensive arguments (`json.dumps(payload)`) built eagerly in hot
  loops for a level that is usually off
- **Why it matters:** interpolated values cannot be queried as fields in CloudWatch Logs Insights, and
  eager formatting costs time on every record
- **Instead:** `logger.info("Order stored", extra={"order_id": oid})` with the Powertools Logger, or
  `logger.info("Order %s stored", oid)` with the standard library
- **Severity:** Minor where the project requires structured logs or in hot loops; Nit otherwise
- **Source:** https://docs.aws.amazon.com/powertools/python/latest/core/logger/ — "output structured as
  JSON"; Ruff `G004`, `T201`

### PY-LOG-02 Library code configuring logging

- **Look for:** `logging.basicConfig`, `addHandler` (other than `NullHandler`), `setLevel` on the root
  logger, or calls on the root logger (`logging.info(...)`) inside a shared library
- **Why it matters:** the library overrides the application's configuration and duplicates or drops
  its log lines
- **Instead:** `logger = logging.getLogger(__name__)` in libraries; configure once in the entry point
- **Severity:** Minor
- **Source:** https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library — "do not
  add any handlers other than `NullHandler` to your library's loggers"; Ruff `LOG015`

### PY-LOG-03 Exceptions logged without traceback, or at every layer

- **Look for:** `logger.error(f"failed: {e}")` inside `except` instead of `logger.exception(...)`; the
  same exception logged and re-raised at each layer
- **Why it matters:** the stack trace is lost, or one failure produces several log lines that look like
  several failures
- **Instead:** `logger.exception("Order write failed", extra={...})` once, at the layer that handles the
  error; lower layers raise with `from`
- **Severity:** Minor
- **Source:** https://docs.aws.amazon.com/powertools/python/latest/core/logger/ (`logger.exception`);
  Ruff `TRY400`, `TRY401`

### PY-LOG-04 Metric dimension misuse

- **Look for:** request IDs, user IDs, order IDs or timestamps as metric dimensions; more than 29 user
  dimensions; metrics or dimensions added at module scope or outside the handler
- **Why it matters:** each distinct dimension value is a new metric (cost and dashboard noise), the
  EMF limits reject the event, and module-scope metrics are emitted only on cold start
- **Instead:** low-cardinality dimensions, added inside the handler; high-cardinality values via
  `metrics.add_metadata`
- **Severity:** Major (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/powertools/python/latest/core/metrics/ — "Maximum of 29
  user-defined dimensions" and "Metrics or dimensions added in the global scope will only be added
  during cold start."

## 10. Performance (PY-PRF)

### PY-PRF-01 Quadratic patterns

- **Look for:** `if x in some_list` inside a loop over another collection; nested loops joining two
  lists; `list.pop(0)` or `insert(0, ...)` in loops; `s += piece` building a string in a loop
- **Why it matters:** list membership is O(n), front pops shift the whole list, and repeated string
  concatenation is quadratic in the total length, which means timeouts on real batch sizes
- **Instead:** a `set` or `dict` for membership and joins, `collections.deque` for queues,
  `"".join(parts)` or `io.StringIO`
- **Severity:** Minor; Major when the input size is unbounded
- **Source:** https://docs.python.org/3/library/stdtypes.html#common-sequence-operations — "repeated
  concatenation will have a quadratic runtime cost"; https://wiki.python.org/moin/TimeComplexity;
  https://docs.python.org/3/library/collections.html#collections.deque

### PY-PRF-02 Unbounded in-memory accumulation

- **Look for:** `list(paginator.paginate(...))` or collecting every page or item before processing;
  `resp["Body"].read()` of objects of unbounded size; `readlines()`; building one large response in
  memory
- **Why it matters:** memory grows with the data, and Lambda ends the invocation at its memory limit
- **Instead:** iterate pages and records as a stream (generators), `iter_chunks()` or `iter_lines()` on
  `StreamingBody`, process and release per page
- **Severity:** Major when the size is unbounded in Lambda; Minor otherwise
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/paginators.html (`PageIterator`);
  https://docs.aws.amazon.com/botocore/latest/reference/response.html (`iter_chunks`, `iter_lines`)

### PY-PRF-03 N+1 AWS calls

- **Look for:** `get_item` or `head_object` in a loop over keys, `put_item` per record where a batch
  fits, one `send_message` per message
- **Why it matters:** latency and request cost scale with the item count, and throttling arrives sooner
- **Instead:** `batch_get_item` (up to 100 keys), `Table.batch_writer()`, `send_message_batch`, a
  `query` on the partition key, bounded concurrency for unavoidable per-item calls; batch only when the
  batch API keeps the contract (no conditions in `BatchWriteItem`, per-entry failures: PY-ERR-10)
- **Severity:** Minor; Major when the loop is unbounded on the request path
- **Source:** https://docs.aws.amazon.com/boto3/latest/guide/dynamodb.html — `batch_writer()` can
  "reduce the number of write requests made to the service"

### PY-PRF-04 Expensive objects rebuilt per call

- **Look for:** `TypeAdapter(...)`, JSON-schema validators, compiled regular expressions or templates
  created inside frequently called functions or per record (boto3 clients are PY-AWS-01)
- **Why it matters:** each construction rebuilds validators, which dominates the cost of small calls
- **Instead:** build once at module scope or behind `functools.cache`
- **Severity:** Minor
- **Source:** https://pydantic.dev/docs/validation/latest/concepts/performance/ — "it will be
  instantiated each time"

## 11. Tests (PY-TST)

### PY-TST-01 Patching where defined instead of where looked up

Retired 2026-10-16: merged into PY-TST-04

### PY-TST-02 Mocks without a spec

- **Look for:** bare `MagicMock()` or `Mock()` standing in for boto3 clients or domain objects; misspelt
  methods on mocks (`put_itme`) that pass; mocks returning mocks for SDK responses
- **Why it matters:** a mock accepts any attribute and any call, so the test keeps passing after the real
  API changes or the code calls it wrongly
- **Instead:** `create_autospec(Class, instance=True)`, `patch(..., autospec=True)` or `spec_set=` for
  Python interfaces; the botocore Stubber for SDK clients, whose operation methods take `**kwargs`, so
  autospec cannot check their parameters
- **Severity:** Major
- **Source:** https://docs.python.org/3/library/unittest.mock.html#autospeccing — "your tests can all
  pass even though your code is broken"; https://github.com/boto/botocore/blob/develop/botocore/client.py
  — `def _api_call(self, *args, **kwargs):`

### PY-TST-03 Tests that bypass or restate the behaviour they claim to cover

- **Look for:** a sole `mock.assert_called_once()`; asserting a value the test put on a mock; expected
  values computed by re-implementing the code; no oracle (no `assert`, `pytest.raises` or Stubber
  `expected_params`); the function holding the new rule patched out; production parsing bypassed by
  hand-built models; round trips through one encoder and decoder with no independent payload fixture
- **Why it matters:** the test passes when the behaviour is broken or deleted
- **Instead:** assert the observable outcome (the returned model, the stored item, the emitted error
  code) and the call arguments that matter (`assert_called_once_with(...)`), through a public seam with
  only external dependencies stubbed
- **Severity:** Blocker when the suite for an item would pass with a named required behaviour removed
  (the lens brief's class); Major otherwise
- **Source:** `references/review-lenses.md` section 5 ("A test that asserts only that a mock was called,
  or that re-implements the code under test, proves nothing")

### PY-TST-04 Test doubles that miss the code under test, or tests able to reach real AWS

- **Look for:** `patch("orders.repo.Table")` when the service did `from orders.repo import Table`;
  `patch("boto3.client")` after the module built its client; clients built at import or in a
  module-scoped fixture before `mock_aws` starts and not patched; no fake AWS credentials and region in
  the unit-test environment; unit or default-selected tests calling real endpoints; one `mock_aws`
  context shared by tests that expect a clean state (merged from PY-TST-01)
- **Why it matters:** the double replaces a name the code under test no longer reads, so the real
  object runs, possibly with real credentials against real resources
- **Instead:** patch the name where the code under test looks it up, or inject a fake; start
  `mock_aws` first and create clients inside it, or `moto.core.patch_client` a client built earlier;
  fake credentials in `conftest.py`; keep marked, operator-run integration tests out of the default
  selection
- **Severity:** Blocker when a unit or default-selected test can reach real AWS unintentionally; Major
  otherwise. Operator-authorised integration tests (`python-practices.md` section 10) are not findings
- **Source:** https://docs.python.org/3/library/unittest.mock.html#where-to-patch — "you patch where an
  object is *looked up*"; https://docs.getmoto.org/en/latest/docs/getting_started.html — "ensure that
  you have your mocks set up BEFORE your boto3 client is established" (same page: `patch_client`)

### PY-TST-05 Fault tests: documented error codes not injected

- **Look for:** no test that injects each documented error code on the path (throttling, conditional
  check failure, transaction cancellation, timeout); a Stubber never activated (`activate()` or a
  `with stubber:` block), so the stub does not apply; moto relied on for error details it does not
  emulate
- **Why it matters:** the error mapping, which is where silent failures live, is never executed
- **Instead:** `stubber.add_client_error("put_item", service_error_code="ConditionalCheckFailedException")`
  per documented code, asserting the domain outcome; `expected_params` and
  `assert_no_pending_responses()` as hygiene
- **Severity:** Major (the lens brief's class)
- **Source:** https://docs.aws.amazon.com/botocore/latest/reference/stubber.html

### PY-TST-06 pytest.raises too broad or with trailing statements

- **Look for:** `pytest.raises(Exception)` where a specific exception exists, or without `match=` where
  the message is the contract; several statements inside the `with pytest.raises(...)` block, with
  assertions after the raising line
- **Why it matters:** an unrelated error satisfies the test, and assertions after the raise never run
- **Instead:** the specific type, with `match=` or assertions on `excinfo.value` attributes after the
  block; one statement in the block
- **Severity:** Major for assertions that never run; Minor for a broad type
- **Source:** https://docs.pytest.org/en/stable/how-to/assert.html — "pytest.raises will match the
  exception type or any subclasses"; Ruff `PT011`, `PT012`

### PY-TST-07 Wall-clock, randomness and timing dependence

- **Look for:** code that reads `datetime.now()`, `time.time()` or `uuid4()` directly while tests assert
  on derived values; `time.sleep` in tests; exact equality on floats or durations
- **Why it matters:** the test is flaky around midnight, on slow CI or across time zones
- **Instead:** inject a clock or ID provider (a parameter or a small `Protocol`), freeze time in the test,
  compare floats with `pytest.approx`
- **Severity:** Major when the assertion depends on the wall clock; Minor otherwise
- **Source:** https://docs.pytest.org/en/stable/explanation/flaky.html — "Overly strict assertions can
  cause problems with floating point comparison as well as timing issues." (clock injection itself is
  community practice)

### PY-TST-08 State leaking between tests

- **Look for:** cached clients (`functools.cache` factories), Powertools parameter caches, logger keys or
  module globals not reset between tests; `os.environ[...] = ...` instead of `monkeypatch.setenv`;
  session- or module-scoped fixtures returning mutable objects that tests modify
- **Why it matters:** tests pass or fail depending on order and parallelism
- **Instead:** function-scoped fixtures, `monkeypatch`, cache resets (`factory.cache_clear()`,
  `parameters.clear_caches()`) in an autouse fixture
- **Severity:** Major
- **Source:** https://docs.pytest.org/en/stable/explanation/flaky.html — "Tests that modify global state
  typically cannot be run in parallel."; https://docs.aws.amazon.com/powertools/python/latest/utilities/parameters/
  (`clear_caches`)

### PY-TST-09 Skips, xfails and weakened tests

- **Look for:** new `@pytest.mark.skip`, `skipif` or `xfail` without a reason and a tracking reference;
  `xfail` without `strict=True` where the configuration does not set `strict_xfail` (`xfail_strict`
  before pytest 9); `pytest.importorskip` hiding a missing dependency; assertions removed or loosened in
  the same change as the code
- **Why it matters:** the suite goes green without testing the behaviour
- **Instead:** fix the code or the test; when a skip is genuinely needed, give a reason and an
  `xfail(strict=True)` so an unexpected pass is reported
- **Severity:** Blocker when the skip or weakening is what makes the change pass (the lens brief's
  class); Major otherwise
- **Source:** https://docs.pytest.org/en/stable/how-to/skipping.html — "Both XFAIL and XPASS don't fail
  the test suite by default."; https://docs.pytest.org/en/stable/reference/reference.html — "Renamed from
  xfail_strict to strict_xfail."

### PY-TST-10 Unrealistic events and contexts

- **Look for:** handler tests with hand-built partial events missing fields the service sends;
  `context=None` while the code reads `context.aws_request_id` or `get_remaining_time_in_millis()`;
  events whose JSON types differ from the real ones (numbers as strings, missing `messageId`)
- **Why it matters:** the handler passes tests and fails on the first real event
- **Instead:** sample events from the service documentation or the project's fixtures, parsed through the
  same model as production; a context stub with the documented methods
- **Severity:** Minor; Major when the missing field is one the code depends on
- **Source:** https://docs.aws.amazon.com/lambda/latest/dg/python-context.html;
  https://docs.aws.amazon.com/lambda/latest/dg/python-testing.html (Powertools validation)

## 12. Style and readability (PY-STY)

### PY-STY-01 Names that mislead, and agent tool descriptions

- **Look for:** names that say how instead of what (lens brief 3), names that contradict what the code
  does, exception classes named unlike errors; Strands `@tool` functions with vague or stale docstrings
- **Why it matters:** a misleading name misleads the next change; the model chooses a tool by its
  docstring
- **Instead:** names for intent; precise `@tool` docstrings with arguments
- **Severity:** Nit; Major for a `@tool` whose docstring does not describe its behaviour
- **Source:** https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/ — "Language models rely
  heavily on tool descriptions"

### PY-STY-02 Imports

Retired 2026-10-16: cut; import order, unused and wildcard imports are the gate's Ruff (section 13)

### PY-STY-03 Truthiness and identity tests that change meaning

- **Look for:** `is` with a literal (`x is "a"`, `x is 1`); `if not value:` where `0`, `""` or an empty
  list are valid values distinct from `None`; `== None`; `type(x) == T` where subclasses must be
  accepted (an exact check can be deliberate: `bool` is a subclass of `int`)
- **Why it matters:** `is` with literals gives implementation-dependent results, and a truthiness test
  treats valid zero values as missing
- **Instead:** `is None`, `if value is None:` when zero is valid, `isinstance()` where subclasses are
  meant
- **Severity:** Major when a truthiness test drops a valid value or `is` compares literals; Nit
  otherwise
- **Source:** https://peps.python.org/pep-0008/#programming-recommendations — "Comparisons to singletons
  like None should always be done with `is` or `is not`"; https://docs.python.org/3/library/functions.html#bool
  — "The bool class is a subclass of int"; Ruff `E711`, `E721`, `F632`

### PY-STY-04 Magic values and duplicated literals

Retired 2026-10-16: merged into PY-ARC-09

### PY-STY-05 Dead code and shadowed builtins

Retired 2026-10-16: cut; commented-out code and shadowed builtins are the gate's Ruff (section 13)

## 13. Out of scope / handled elsewhere

- Formatting and the rules the project's Ruff selects, including import order and wildcard or unused
  imports (`I001`, `F403`, `F401`), commented-out code (`ERA001`) and shadowed builtins (`A001`): the
  gate (`ruff format --check`, `ruff check`); report them only when unselected or suppressed
- Type errors mypy reports: the gate (`mypy --strict` or the project's command); review the holes mypy
  cannot see (PY-TYP-01)
- Dependency vulnerabilities and lock-file integrity: `pip-audit` and `uv lock --check` in the gate when
  the project uses them; an unplanned dependency or lock change is the Specification fidelity lens
  (`review-focus.md`)
- Lambda runtime and SDK choice (deprecated or preview runtimes, the AWS SDK for Python developer
  preview), Strands model pinning, guardrails and `strands.experimental`: the Security and AWS runtime
  lens brief and `python-practices.md` sections 1, 5 and 9
- DynamoDB transaction mechanics (`CancellationReasons` by index, client request tokens, fences on a
  different item): the Failure handling lens brief and `python-practices.md` section 6
- Infrastructure security (IAM policies, encryption, network exposure), including CDK apps written in
  Python: `implement-from-spec:iac-security-reviewer` through `reviewing-cdk-changes` and
  `reviewing-cloudformation-changes`; Terraform through `reviewing-terraform-changes`
- Language-neutral principles and architecture-smell definitions:
  `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`

## Sources

Read on 2026-10-16; each check's Source line names the exact page. By publisher:

- Python: https://peps.python.org/ (PEPs 8, 20, 484, 544, 589, 604, 634, 654, 680, 686, 695, 698,
  765); https://docs.python.org/3/ (tutorial, FAQ, logging how-to, glossary, library reference);
  https://devguide.python.org/versions/; https://wiki.python.org/moin/TimeComplexity; https://pypi.org/
- Style and linters: https://google.github.io/styleguide/pyguide.html; https://docs.astral.sh/ruff/rules/;
  https://github.com/astral-sh/ruff/releases/tag/0.17.0; pylint, Bandit and mypy documentation
- pydantic: https://pydantic.dev/docs/validation/latest/
- AWS: the Lambda developer guide, boto3 and botocore guides and references, the DynamoDB, SQS and
  Kinesis API references, Powertools for AWS Lambda (Python) (all at https://docs.aws.amazon.com/);
  https://github.com/aws/aws-lambda-python-runtime-interface-client; https://github.com/boto/botocore;
  the AWS Compute blog on multiprocessing in Lambda
- HTTP and security: https://requests.readthedocs.io/; https://www.python-httpx.org/;
  https://cheatsheetseries.owasp.org/ (SSRF Prevention, Authorization); https://cwe.mitre.org/
- Testing: https://docs.getmoto.org/; https://docs.pytest.org/en/stable/
- Design and agents: https://martinfowler.com/articles/gateway-pattern.html; https://strandsagents.com/
- Plugin files: `references/review-lenses.md`,
  `${CLAUDE_PLUGIN_ROOT}/skills/implementing-python-from-spec/references/python-practices.md`,
  `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`
