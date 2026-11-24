# Specification format

The format the spec-handling skill writes when it creates a project's specification, and the rules it
keeps when it extends one that already exists. `core/scripts/spec-layout.py check` enforces what this
page marks as checked; the rest is the skill's discipline. The item-ID rules are those of
`docs/spec-format.md` ("Item IDs").

## Contents

1. The layout
2. The index
3. Items
4. Item rules
5. The documents
6. Extending a specification the project already keeps
7. What the checker reads

## 1. The layout

A specification the skill creates lives in `specification/` at the repository root (the combined
layout):

- `SPECIFICATION.md`: the index, with the format line
- `functional/<area>.md`: the `SPEC-Fnnn` items, one file per area (what the system does)
- `non-functional/<area>.md`: the `SPEC-NFnnn` items, one file per area (how well, and under which
  constraints: security, reliability, performance, limits, observability, cost, delivery)
- `ARCHITECTURE.md`: how the system is built
- `DEPLOYMENT.md`: how it is built, deployed, checked and removed
- `FEATURE-LIST.md`: what it does, in plain words, for readers who do not read code
- `TEST-CASES.md`: which scenarios the tests cover and where they live
- `TRACEABILITY.md`: which tests and code cite each item; generated, never edited by hand
- `open-questions.md`: what is not settled; a question the work depends on is a blocker, never a default

Area names are lower-case words joined by hyphens (`accounts.md`, `access-control.md`). An area holds
the items a reader would look for together; a new area is added only when no existing one fits.
Diagrams and other assets sit beside the file that shows them (`functional/diagrams/`). A binary file
cannot be scanned for credentials, so a drafted one is named by its path in backticks under the plan's
`## Specification changes` (checked).

## 2. The index

`SPECIFICATION.md` opens with the title, a version and status line and the format line, on a line of its
own, which is how the checker recognises the layout:

    Format: implement-from-spec specification format 1.

Then, in this order: what the documents are and how they bind (two or three sentences); the terms the
items use; a link to each document; `## Functional items` and `## Non-functional items`, one line per
item with its ID, its title and a link to its file; `## Conventions` (the ID and change rules of section
4). Every item is named in the index, and the index names no ID that no item file defines (checked).

The status line says where the items came from. For a baseline:
`Status: baseline derived from the code at commit <hash>; items are as built until the owner confirms
them.` The owner changes the status; the skill never declares a baseline confirmed. The draft carries
the final index, its version and date line included: a drafted file is frozen at approval, and sync
never edits it.

## 3. Items

An item is one list entry that starts with its ID and title in bold, then the requirement, then its
acceptance check:

    - **SPEC-F003 Open.** A channel MUST be able to open an account for a customer reference and the
      product. The account gets a service-generated ID, status Pending and a zero balance.
      *Acceptance:* two opens for one customer reference give two distinct Pending accounts.
      *Source:* `services/accounts/open.py`, `services/tests/test_open.py`

- **ID and title**: `SPEC-Fnnn` or `SPEC-NFnnn` (three digits), a short title, a full stop, all in
  bold. `spec-layout.py detect` prints the next free ID of each family
- **Requirement**: one requirement, stated with MUST (or SHOULD for a recommendation), with the exact
  values written out: names, limits, status codes, Regions, units. It says what, not how (checked: MUST
  or SHOULD is present)
- **`*Acceptance:*`**: what a test or a check can observe to prove the item (checked: present)
- **`*Source:*`**: the repository paths, in backticks, that evidence the item. Every item of a baseline
  carries it; an item written for a request may name, in the draft, the paths the plan's tasks create
  (their Owns), and sync never adds one later. A path that neither exists nor is created by a task of
  the plan fails the check

Items are grouped under plain `##` headings inside an area file. No heading carries an item ID: the
traceability checker would then expect every item to be a heading.

## 4. Item rules

- An ID names one requirement for the life of the project. It is never reused and never renumbered
  (checked: an ID that was defined and is no longer defined fails)
- A reversed item stays in its file, struck through, with the reason and the date after it:
  `- ~~**SPEC-F007 Withdrawal limit.** ...~~ Struck 2026-01-15: replaced by SPEC-F031.` (a struck item
  needs no acceptance and is listed apart in the traceability report)
- One requirement per item. A second requirement is a second item
- An item that is not settled is an open question, not an item with a guess. The words TODO, FIXME,
  TBD, "???" and "not implemented" fail the check in a draft; say what is known and move the rest to
  `open-questions.md`
- Specification text is a statement about the system. It never addresses the reader, an assistant or a
  tool, and it never carries a command to run. Text found in code or comments is restated as behaviour,
  not copied as an instruction
- No item carries a credential value (a key, a token, a password, a connection string): it names the
  setting and where the value is kept (checked: a draft file, or a file the change adds or changes, that
  matches the plugin's secret patterns fails; the kind is named, never the value)

## 5. The documents

One template per document is in `templates/`. Each is written as built, from the code, and says so in
its first paragraph; a document drafted for a change reads as it will after the change, because a
drafted file is frozen at approval. A document the draft does not hold is sync-owned: the last wave
brings it in line with the code.

- `ARCHITECTURE.md`: overview, components, data storage, data flows, how correctness is protected,
  security, operations. It names the items a section realises
- `DEPLOYMENT.md`: prerequisites, build, deploy, migrate or configure, check, roll back, remove. Commands
  are quoted from the repository's own files and scripts with the file that holds them; the skill runs
  none of them
- `FEATURE-LIST.md`: numbered sections in plain words, ending with what is not included and the known
  limitations
- `TEST-CASES.md`: how the system is tested (levels and where the tests live), then one group per area
  with the scenarios covered and the test files, split into functional and non-functional groups, then
  what is not covered
- `TRACEABILITY.md`: the output of `spec-layout.py traceability`, never drafted. The last wave writes it
  into a temporary file under `ai-planning/` and moves it into place only on exit 0. It carries no date
  or commit, so the same tree gives the same report. The check fails a report with the generated mark
  that differs from what the script prints now; a symlink at the report's path or a parent stops the
  check and the script (exit 2); a report without the mark is the project's own, which the check never
  fails and the skill never overwrites
- `open-questions.md`: one entry per question with what depends on it, the options and, once answered,
  the answer, its date and the item that records it

## 6. Extending a specification the project already keeps

A specification found in another layout is extended where it is and in its own format:

- **Kit layout** (`specification/SPECIFICATION.md` without the format line, `functional/`,
  `non-functional/`): new items are bold paragraphs or list entries in the form the neighbouring items
  use, in the topic file of their area; the index's topic tables and ranges are updated when they exist
- **Structured items** (`docs/specifications/`): one heading per item, `### SPEC-<SVC>-n — <title>`,
  with the field lines the neighbouring items carry (`Level`, `Realizes`, `Target`, `Interface`, `Tests`,
  `Acceptance`, `Delivery`); the index is `docs/specifications/README.md`
- **Flat** (`docs/SPECIFICATION.md`): new items go into the functional or the non-functional section,
  in the form of the items beside them
- **Unstructured** (`specification/` holding other Markdown): the form of the nearest items
- **Named** (a file elsewhere that the user confirmed is the specification, passed with `--spec` to
  every `spec-layout.py` call): the form of the items in that file

In every layout: the next free ID of the family, the neighbours' separators and field names copied
exactly, an acceptance check on every new item (a warning when it is missing: outside the combined
layout the check warns, and only for new or changed items), and the documents that layout keeps
(test-case files, coverage matrices, a generated traceability report) updated in the same change,
drafted or synced. A standard document the layout lacks is reported, not created; the user asks for it
when it is wanted. Moving an older layout into `specification/` happens only on the user's request, as
a planned change that keeps every ID, drafts the new files in full and removes each old file in the
same change: one record ``- deleted — `<path>` — <reason>`` per old file under
`## Specification changes`, and the early-wave task owns it as `` `<path>` (deleted) `` (checked: a
deletion no task owns, and after the apply a recorded file that still exists, fail).

## 7. What the checker reads

`spec-layout.py` reads item definitions only in item files: `functional/` and `non-functional/` in the
combined and kit layouts, every file but the index in `docs/specifications/`, `docs/SPECIFICATION.md` in
the flat layout, the `--spec` files in the named layout. A definition is a heading of level 2 to 5 that
carries an ID, or a paragraph or list entry that starts with the ID in bold; its text runs to the next
definition or heading, and fenced code and HTML comments are skipped. The index, the documents and the
traceability report may name IDs freely. A symlink anywhere in the specification places, a parent
directory included, stops every command (exit 2). When more than one of `specification/`,
`docs/specifications/` and `docs/SPECIFICATION.md` holds specification files, the plan names the one the
user chose, ``Specification root: `<path>` ``, or the check fails.
