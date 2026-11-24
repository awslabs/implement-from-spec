# Plan template (specification)

For a run of spec-handling on its own, when no implementing skill owns the plan. Write
`<repo>/ai-planning/<slug>.plan` with these sections in this order and replace the guidance under each
heading. `<PLUGIN_ROOT>/core/scripts/spec-trace.py plan` parses `## Scope` and the `### Task` fields, and
`<PLUGIN_ROOT>/core/scripts/spec-layout.py check --plan` parses the records under
`## Specification changes`, so keep those headings, field names and record forms exactly. The plan
holds no specification text: that is the draft under `ai-planning/<slug>.spec/`.

```markdown
# <Project or request>: specification plan

Items: ai-planning/<slug>.spec/ · Drafted: YYYY-MM-DD

## Scope
The item IDs this plan writes: every new, changed and struck item, each ID written out (a range names
only its two ends).

## Specification changes
One record per item, and nothing but records and plain notes:
- <ID> — new — `<specification file>` — <one-line reason, or the request it comes from>
- <ID> — changed — `<specification file>` — <what changed and why>
- <ID> — struck — `<specification file>` — <why it no longer holds>
For a project that had no specification, one record covers the items derived from the code:
- baseline — <n> items derived from the code at commit <hash> — `specification/`
For a move the user asked for, one record per old file the move removes:
- deleted — `<path>` — <why>
Exactly one digest line, printed by `spec-layout.py digest ai-planning/<slug>.spec`, replaced after any
edit to the draft:
Draft digest: sha256 <64 lowercase hex>
When more than one recognised place holds specification files, the user's answer, the path in backticks:
Specification root: `<specification/ | docs/specifications/ | docs/SPECIFICATION.md>`
Then, as plain notes: the layout found (or "none found"), a candidate the user rejected, the standard
documents the existing layout lacks ("not created"), each binary draft file (a diagram) by its path in
backticks, and anything the user asked to move.

## Binding rules
CLAUDE.md or AGENTS.md when present, and the conventions of the specification index.

## Global constraints
The layout and format the draft follows (`references/format.md`, or the existing layout's own), the
commit the baseline was derived from, and the values the user fixed in the request, verbatim.

## 1. What was read
The areas of the code base read, with their directories; the documents and rules files read; what was
not read and why (the files `spec-layout.py survey` withheld, with its reasons, and generated code).

## 2. Areas and items
One line per area file: its path, the number of items, and what the area covers.

## 3. Evidence check
What a second read confirmed, what it corrected, and what moved to the open questions.

## Open questions
Each question the specification leaves open, with its source, the options and what depends on it; the
draft's `open-questions.md` holds the same list. "none" when nothing is open.

## Review focus
The items whose evidence is thinnest, and the behaviour the code shows that looks unintended.

## Tasks
### Task 1 — Write the specification from the approved draft
Implements: <every Scope ID>
Owns: `<each specification file the draft holds>`, and `<each file a move removes>` (deleted)
Depends: none
Wave: 1
Tests: none — specification text; `spec-layout.py check` verifies its format, its item delta and its digest
Verify: `spec-layout.py check --repo . --draft ai-planning/<slug>.spec --plan ai-planning/<slug>.plan` exits 0 before and after the copy

### Task 2 — Sync the documents and regenerate the traceability report
Implements: <every Scope ID>
Owns: `<the sync-owned files it writes: <root>/TRACEABILITY.md when the layout keeps a generated report, and the living documents the draft does not hold>`
Depends: 1
Wave: 2
Tests: none — generated and descriptive documents; `spec-layout.py check` fails a stale report
Verify: `spec-layout.py check --repo . --plan ai-planning/<slug>.plan --base <baseline commit>` exits 0 and `spec-trace.py code` exits 0

Task 2 is required whenever the layout keeps a generated `TRACEABILITY.md` (the combined layout always
does). Leave it out only when the layout keeps none and the change touches no living document the draft
does not hold, and say so under Specification changes. A project report without the generated mark is
never in Task 2's Owns; when the project keeps its own generator, a task that runs it is proposed here,
its command named, for the user's approval.

## Deferred
One record per Scope item the user agreed to leave out: `- <ID> — <reason> (agreed YYYY-MM-DD)`. Otherwise "none".

## Risks and rollback
What a wrong item would cost (work planned against it), how it would show, and how to back the change
out: the specification files are restored from the baseline commit.
```
