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

## Specification changes
One record per specification item this change adds, changes or strikes (contract sections 3 and 13),
the file in backticks:
- <ID> — new — `<specification file>` — <one-line reason, or the request it comes from>
- <ID> — changed — `<specification file>` — <what changed and why>
- <ID> — struck — `<specification file>` — <why it no longer holds>
The full text of every specification file that is new or changes is drafted under
`ai-planning/<slug>.spec/`. For a project that had no specification, one record covers the items
derived from the code:
- baseline — <n> items derived from the code at commit <hash> — `specification/`
Then, as plain notes, the layout found and the standard documents it lacks (not created). "none" when
no item is added, changed or struck.
When the draft holds files, the section also carries exactly one line
`Draft digest: sha256 <64 lowercase hex>`, computed once the draft is final with
`python3 -I "<PLUGIN_ROOT>/core/scripts/spec-layout.py" digest <REPO>/ai-planning/<slug>.spec`; the
analysis gate fails `draft-digest-mismatch`, and the approval gate refuses approval, when the draft
changes after it (contract section 13). A plan with this section
uses real specification item IDs throughout, never `SPEC-PLAN-n` (`plan-local-id`).
A specification file the change removes (a move into another layout) is recorded as
``- deleted — `<path>` — <reason>``, and a task owns it as `` `<path>` (deleted) ``.
When more than one specification place holds files, the user's answer is one line
`` Specification root: `<place>` ``, for example `` Specification root: `docs/SPECIFICATION.md` ``. A draft
file that is binary or over 2 MB is named here in backticks, or `check` fails `draft-binary`.

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
New or changed packages with their PyPI name, exact version, reason and the lock file they go into; lock
file changes and how they are regenerated; anything removed. Beside each one: where its version comes
from (the specification, the project's declarations or lock file, or "the plan's own choice"), and the
dependency check's result (`dependency-audit.py check pypi:<name>==<version>`), in one of three forms:
"no advisory matches this version in the dataset of <date>"; the match, with its advisory ids, the
reported fix and the open question or approval line that raises it; or "not checked (<reason>)". When a
project rule requires the user's explicit approval for a kind of dependency, quote the rule next to it.
The target Lambda runtime and why it is supported. "none" when nothing changes.

## 6. Test strategy
Every test named now, with the item IDs it proves: unit tests per module, property tests where an
invariant holds over many inputs, fault tests for each documented error code, integration or conformance
tests the items require and where they run.

## Open questions
Each question the change depends on that an item, a project rule or `specification/open-questions.md`
leaves open, each user instruction a project rule forbids, and each advisory match on a version the
specification or the project asked for: its source (file and ID or line, or "dependency check"), the
options, the recommended answer the design follows (the rule's side, for a forbidden instruction; the
reported fix, for an advisory match), and what changes with each other answer. When the recommended
answer changes what a specification item states (the reported fix for a version an item names), the item
is drafted changed and recorded under `## Specification changes`. The approval request lists them; approve accepts the recommended
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

Specification tasks (contract section 13): when `ai-planning/<slug>.spec/` holds files, a first-wave
task owns the specification files and writes them from the draft; when the draft holds files, the
layout keeps a generated TRACEABILITY.md or the change touches a living document, a last-wave task owns the documents that follow the code (the
traceability report, the test-case document, the feature list and the others the layout keeps), never a
file the draft holds, which is frozen at approval. Each names the Scope IDs it writes or documents and
carries `Tests: none — <reason>` with `spec-layout.py check` as its `Verify:`. When no last-wave task
is needed, `## Specification changes` says so.

## Deferred
One record per Scope item the user agreed to leave out: `- <ID> — <reason> (agreed YYYY-MM-DD)`. Otherwise "none".

## Risks and rollback
What could go wrong in production, how it would show (metrics, alarms, errors), and how to back it out.
```
