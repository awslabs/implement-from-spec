# Plan template (Terraform)

Write `<repo>/ai-planning/<slug>.plan` with these sections in this order. Replace the guidance under each
heading. No HCL, no policy JSON, no Terraform-like pseudocode: name resource types, variables and outputs
and describe them in prose. `${CLAUDE_PLUGIN_ROOT}/core/scripts/spec-trace.py plan` parses `## Scope` and the
`### Task` fields, so keep those headings and field names exactly.

```markdown
# <Feature>: plan

Spec: <specification files or ai-planning/<feature>.md> · Drafted: YYYY-MM-DD

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
CLAUDE.md (AWS profile, architecture invariants, layout), the specification index, any other file that
binds the work. Passed to the GPT reviewer as --rules.

## Global constraints
Exact values the items fix, verbatim with their item ID: names, the naming pattern, limits, Regions.

## 1. Restated requirements
What the items ask for, item by item; each ambiguity and its resolution.

## 2. Module structure
New modules: directory, one-sentence responsibility, variables, outputs. Existing modules modified:
exactly what is added and why it belongs there. How outputs thread into inputs in the environment root.

## 3. IAM design
For each resource the workload must reach: actions named explicitly, the narrowest ARN scope, how the
policy document flows to the role through the project's attachment point, environment variables injected.

## 4. Variable and output inventory
Every new variable and output: name, type, description, default; which variables the operator supplies.

## 5. Architecture invariant compliance
Each CLAUDE.md invariant the change touches and how the design satisfies it.

## 6. Provider version check
Any resource that needs a newer provider than the current constraint: the minimum version and why.

## 7. Pre-apply manual checks
What the operator verifies before apply, including the spec's open questions about live state.

## 8. Validation commands
The exact fmt, validate and targeted plan commands under the project's AWS profile, and the expected
outcome: additions only, zero destroys, and zero changes to existing resources apart from the documented
attachment point receiving additions. Then the full plan of the root that confirms nothing outside the
target changes, or the statement that it was not run.

## 9. Post-apply smoke checks
Read-only AWS CLI commands that prove the resources exist and are configured, with expected output.

## 10. Cost delta
The monthly cost added, in the project's cost-file format.

## Review focus
Failure modes the items imply that no task's check exercises.

## Tasks
### Task 1 — <title>
Implements: <item IDs>
Owns: `<path>`, `<path>`, `<terraform test file the task writes>`
Depends: none
Wave: 1
Tests: `<terraform test file, check or policy fixture>`
Verify: <command and expected result>

A test file the task writes or edits (a `.tftest.hcl`, a policy fixture) is in its `Owns:` as well as its
`Tests:`: Owns is every file the task writes, and `spec-trace.py code` fails a written file no task owns,
which after approval can only be fixed by an amendment and a second approval.

Each field is one physical line, however long: never wrap it. spec-trace reads only the line its label
starts, so an `Owns:` path on a wrapped line counts as unowned and fails verification after approval. In
`Tests:`, backticks hold test paths and nothing else, outside a `none — <reason>` field (spec-trace reads
every backticked span there as a test file, so `command = plan` fails the same way); describe what the
test asserts in plain prose.

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
What could go wrong, how it would show, and what a targeted destroy or manual remediation would look like.
```
