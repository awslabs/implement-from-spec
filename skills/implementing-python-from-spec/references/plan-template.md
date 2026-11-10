# Plan template (Python)

Write `<repo>/ai-planning/<slug>.plan` with these sections in this order. Replace the guidance under each
heading. No Python: describe modules, functions, models and handlers in prose, never as signatures or
code. `<PLUGIN_ROOT>/core/scripts/spec-trace.py plan` parses `## Scope` and the `### Task`
fields, so keep those headings and field names exactly.

```markdown
# <Feature>: plan

Items: <specification files> · Drafted: YYYY-MM-DD

## Scope
The specification item IDs this plan implements.

## Binding rules
CLAUDE.md or AGENTS.md, the specification index, the architecture sections the items realise.

## Global constraints
Exact values the items fix, verbatim with their item ID: module paths, function and model names, fields,
error codes, metric and event names, limits, timeouts.

## 1. Restated requirements
What the items ask for, item by item; each ambiguity and its resolution.

## 2. Architectural fit
The packages and modules the work lives in and why; the shared modules it uses and their owners; the
data flow from the trigger (event, request, schedule) to the result, module by module, in prose.

## 3. Detailed design
One subsection per module, model, handler or agent added or modified:
- Responsibility
- Data: each field's name, meaning and invariants, in prose
- Behaviour: for each function, what it receives, what it returns or emits, what it does step by step,
  and every failure it can meet with the error code or outcome the items assign
- Side effects: AWS calls (service, operation, condition), events and metrics emitted
- Configuration: parameters, environment variables, their source and default

## 4. Idempotency, concurrency and failure
Per handler: duplicate-event behaviour, conditional writes and transactions with their cancellation
mapping, retries and timeouts, partial batch failures, what the caller sees on each failure.

## 5. Dependencies
New packages with version, reason and the lock file they go into; lock file changes and how they are
regenerated; anything removed. The target Lambda runtime and why it is supported.

## 6. Test strategy
Every test named now, with the item IDs it proves: unit tests per module, property tests where an
invariant holds over many inputs, fault tests for each documented error code, integration or conformance
tests the items require and where they run.

## Open questions
Each question the change depends on that an item, a project rule or `specification/open-questions.md`
leaves open, and each user instruction a project rule forbids: its source (file and ID or line), the
options, the recommended answer the design follows (the rule's side, for a forbidden instruction), and
what changes with each other answer. The approval request lists them; approve accepts the recommended
answers. "none" when nothing is open.

## Review focus
Failure modes the items imply that no task's tests exercise.

## Tasks
### Task 1 — <title>
Implements: <item IDs>
Owns: `<module path>`, `<test path>`
Depends: none
Wave: 1
Tests: `<test path>`
Verify: <command and expected result>

Owns lists every file the task creates or changes, the small ones too: each new package's
`__init__.py` (`unittest discover -s <dir> -t .` needs the start directory to be a package),
`conftest.py`, `pyproject.toml` and lock files. A file found missing after approval is an
amendment, which revokes the approval.

## Deferred
One record per Scope item the user agreed to leave out: `- <ID> — <reason> (agreed YYYY-MM-DD)`. Otherwise "none".

## Risks and rollback
What could go wrong in production, how it would show (metrics, alarms, errors), and how to back it out.
```
