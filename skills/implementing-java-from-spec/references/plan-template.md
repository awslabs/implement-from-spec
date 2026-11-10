# Plan template (Java)

Write `<repo>/ai-planning/<slug>.plan` with these sections, in this order. The slug is 2–5 kebab-case
words; the `.plan` extension keeps plans apart from feature specs. Replace the guidance under each
heading with the content. The file contains no Java: describe types, record components and methods in
prose, never as code. `core/scripts/spec-trace.py plan` parses `## Scope`, `## Global constraints`,
`## Review focus`, `## Deferred` and the `### Task` fields, so keep those headings and field names exactly
(contract section 3).

## Contents

1. The template: Scope, Binding rules, Global constraints, sections 1 to 8, Open questions, Review
   focus, Tasks, Deferred, Risks and rollback
2. Task rules
3. Task fields

```markdown
# <Feature name>: plan

Items: <specification files or ai-planning/<feature>.md> · Drafted: YYYY-MM-DD

## Scope
The item IDs this plan implements (SPEC-Fxxx, SPEC-NFxxx, or SPEC-PLAN-n for a feature spec), and nothing else.

## Binding rules
CLAUDE.md or AGENTS.md, the specification index, the design-doc sections the items realise, and the
build commands the project defines.

## Global constraints
Exact values the items fix, verbatim with their item ID: paths and methods of endpoints, request and
response fields, status codes, property names and defaults, limits, timeouts, error bodies.

## 1. Restated requirements
What the items ask for, in your own words, item by item. Each ambiguity and how it was resolved (with the
date of the user's answer). For a feature spec, one line per requirement starting with its SPEC-PLAN-n ID
and naming its source file and section.

## 2. Spec and test-case impact
- New SPEC-Fxxx / SPEC-NFxxx: id, topic file, proposed text
- Amended SPECs: id, topic file, proposed change
- New TC-xxx: id, topic file, what it verifies; the coverage-matrix rows to add
- Open questions this feature closes, with the answer and where it came from
(Omit when the project keeps no specification tree.)

## 3. Architectural fit
The packages the feature lives in, including any new ones, and why that slot fits the patterns found in
the ingest. The data flow from the trigger (request, event, schedule) to the response or output, in
prose: each class in sequence and what it transforms. For network or persistence work, name the adapter
class that does the lookup and the client that sends the request.

## 4. Detailed design
One subsection per class, record or interface added or modified:
- Responsibility
- Data model: each component's name, kind of value and invariants, in prose rather than types
- Behaviour: for each method or constructor, what it receives, what it produces and what it does, step
  by step and without signatures, and every failure it can meet with the status, exception or outcome
  the items assign
- AWS calls: service, operation, the client that makes it, its timeouts and what a throttle or timeout
  becomes
- Configuration: each new property, its name, default, unit and what it tunes
- Record, plain class or Spring bean, and why

## 5. Algorithm and edge cases
For non-trivial logic, numbered plain-English steps, each with its inputs and outputs, the structures it
traverses and its termination condition. Every edge case and how it is handled. Each documented invariant
the feature touches and how it is preserved.

## 6. Dependencies
New dependencies and plugins with coordinates, version (or the BOM that manages it) and reason, the
build file they go into and the CLAUDE.md tech-stack line that records them; anything removed. When a
project rule requires the user's explicit approval for a kind of dependency (a cloud SDK, a new
framework), quote the rule next to the dependency. "none" when nothing changes.

## 7. Test strategy
Unit tests per class, slice tests (`@WebMvcTest`, plain JUnit) before `@SpringBootTest`, and fault tests
for each documented error. Name every test now, each with the item ID or TC-xxx it proves, because the
implementation writes them first. The context-loads test must still pass. The coverage target, when the
project sets one.

## 8. Scripts and smoke
New `scripts/` entries the project's rules require (for example a `scripts/curl-<feature>.sh` per new
HTTP behaviour), and the representative call the smoke gate makes with its expected result.

## Open questions
Each question the feature depends on that an item, a project rule or `specification/open-questions.md`
leaves open: its source (file and ID, such as Q1), the options, the recommended answer the design
follows, and what changes with each other answer. The approval request lists them; approve accepts the
recommended answers. "none" when nothing is open.

## Review focus
Failure modes the items imply that no task's tests exercise.

## Tasks
### Task 1 — <title>
Implements: <item IDs>
Owns: `<production file>`, `<test file>`
Depends: none
Wave: 1
Tests: `src/test/java/<package path>/<Class>Test.java` (cites <item IDs or TC-xxx>; methods: <names>)
Verify: <the build command that runs those tests, and its expected result>

## Deferred
One record per Scope item the user agreed to leave out: `- <ID> — <reason> (agreed YYYY-MM-DD)`. Otherwise "none".

## Risks and rollback
What could go wrong in production (degraded output, latency, thread or connection exhaustion, cache
thrash), how it would show, and how to back the change out cleanly.
```

Task rules (contract section 3): the documentation edits, the `@ConfigurationProperties` class,
`application.yml` and any build-file change are shared work, owned by their own early-wave task; one
class with its test per task where possible; two tasks that modify the same existing class go into
different waves.

Task fields: `spec-trace.py` reads them mechanically, and after approval the plan cannot be corrected
without revoking the approval, so get them right before asking:

- Each field is one line, however long. Never wrap `Owns:` or `Tests:`: the checker reads only the
  field's own line, so a path on a continuation line is not owned, and `spec-trace.py code` fails the
  file as an unowned change
- Backticks hold repository-relative file paths and nothing else. A test class goes in as its path
  (`src/test/java/com/acme/billing/InvoiceServiceTest.java`, not `InvoiceServiceTest`); its method names
  follow in plain text. `spec-trace.py code` fails every backticked `Tests:` entry that is not a file
- A test file the task writes or edits is in its `Owns:` as well as its `Tests:`
