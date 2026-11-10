# Review lenses (Python)

Each lens subagent receives the change set, the plan path (or "none"), the specification files in scope and
its brief below, verbatim. Every brief ends with the shared instructions in section 6.

## Contents

1. Specification fidelity
2. Failure handling
3. Types and design
4. Security and AWS runtime
5. Tests
6. Shared instructions and findings format
7. Severity classes

## 1. Specification fidelity

Trace each item the plan's Scope (or the change's docstrings and test names) claims, from its trigger to
its result, before reading the author's description. Check that every name in the item's `Interface:`
exists exactly as written (module path, function, model, field, error code, metric, event); that each
`Acceptance:` is observable in the code; that nothing is a stub, a hard-coded happy path or unreachable
from the code that runs (exists, substantive, wired); and that the change adds nothing no item asks for.
A removed function, field or behaviour that some contract still needs is a finding even when nothing in
the diff mentions it.

## 2. Failure handling

Every call that can fail: what happens on each error the items document, on a timeout, on throttling, on
a duplicate event. Look for broad `except`, empty handlers, errors logged and swallowed, a batch that
reports success after a record failed, an empty or unknown `itemIdentifier`, a fallback that hides a logic
bug, branching on the error message instead of `Error.Code`, `TransactionCanceledException` reasons not
mapped by index, retries that repeat a non-idempotent write, and missing conditions or fences on writes
the items guard.

## 3. Types and design

mypy strict cleanliness (`Any` leaks, untyped defs, `# type: ignore` without a code); pydantic v2 models
with `extra="forbid"` at trust boundaries and `model_validate_json` for JSON; enums and literals instead
of bare strings for closed sets; naive datetimes; floats where DynamoDB needs `Decimal`; business logic in
the handler instead of a testable function; clients created per invocation or invocation data in globals;
shared code importing service code; functions over about 50 lines mixing I/O and logic; duplicated logic
a shared module already owns; names that say how instead of what.

## 4. Security and AWS runtime

Model output or request input reaching a shell command, SQL, a file path, a URL or a tool call unchecked;
raw events, PII, document or customer content in logs, metric dimensions, trace responses or error
messages;
secrets in code, defaults or environment variables; high-cardinality metric dimensions or more than 29
user dimensions or 100 metrics per EMF event; implicit legacy retry mode and 60-second default timeouts;
missing pagination; an async Lambda handler; an agent without a pinned `model_id` or without the guardrail
the items require; `strands.experimental` in production code; dependencies added without a pinned version;
a Lambda runtime that is deprecated or in preview; the AWS SDK for Python developer preview in production
code.

## 5. Tests

For each test: would it fail if the implementation were deleted or broken? A test that asserts only that
a mock was called, or that re-implements the code under test, proves nothing. Check that every item ID in
scope is cited by a test that exercises it; that every documented error code on the path has a fault
test; that moto mocks are set up before the client under test is created; that property tests cover the
invariants the items state; and that no test was skipped, weakened or given an `xfail` to pass.

## 6. Shared instructions and findings format

Report findings only; edit nothing. Report every finding you see, minor and uncertain ones included (mark
those "unsure"); the orchestrator verifies and filters. Re-read every specification item you cite. Mark a
claim about library or AWS behaviour you have not verified "verify against the docs". Apply the groups
`${CLAUDE_PLUGIN_ROOT}/skills/reviewing-python-changes/references/review-dimensions.md` assigns to your
lens (read its "How to apply" first); the types and design lens also applies
`${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`. One line per finding, with the
check ID (when a check applies) at the start of the problem and its shared ID, if any, after the lens:

    [Blocker|Major|Minor|Nit] <file>:<line> - <lens> (<shared ID>) - <check ID> <problem> (<item ID> if any). Why: <one sentence>. Fix: <concrete change>

End with `Lens: clean` or `Lens: <n> findings`, and list any part of the brief you could not complete. A
finding names the exact change: "Map `CancellationReasons[1].Code == 'ConditionalCheckFailed'` to
`ORDER_ALREADY_RESERVED` in `src/orders/commit.py:88` instead of re-raising", not "consider better
error handling".

## 7. Severity classes

- **Blocker**: an item's interface missing, renamed or stubbed; a write that can duplicate or lose data; a
  swallowed failure on a documented error path; untrusted input reaching a command, query or path; a
  secret or sensitive data exposed; a test suite that would pass with the feature broken; a red quality
  gate; an undeclared dependency
- **Major**: a missing fault test for a documented error code; a trust-boundary model without
  `extra="forbid"`; logic in the handler; a client per invocation; implicit retry mode or default
  timeouts; high-cardinality dimensions; a type hole that hides a real path
- **Minor**: worth fixing in this change if quick
- **Nit**: optional polish
