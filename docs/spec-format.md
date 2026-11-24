# Specification input formats

What the implementing skills accept as input, and the exact rules the two checkers apply to it:
`core/scripts/spec-trace.py` (the plan and the code against the items) and `core/scripts/spec-layout.py`
(the specification itself). Every rule on this page was checked by running the scripts on the examples
shown. The workflow that uses these inputs is [core/contract.md](../core/contract.md), sections 2, 3
and 13; how a specification is created and extended is in
[user-guide/specification.md](user-guide/specification.md).

Each implementing skill takes the repository and one input:

```
/implement-from-spec:implementing-<stack>-from-spec <repo> <SPEC ids | specification file | ai-planning/feature.md>
```

Plain words work too ("implement SPEC-F003 in this repo"). The specification is authoritative: the code
conforms to it, and a change to it is your decision. The skill records every item it would add, change
or strike in the plan, and writes none of them before you approve.

## The input forms

- **Structured items**, `SPEC-<SVC>-n`, in files under `docs/specifications/`, one heading per item
  with field lines
- **Items under `specification/`**, `SPEC-Fxxx` (functional) and `SPEC-NFxxx` (non-functional), in topic
  files under `functional/` and `non-functional/`, optionally verified by `TC-xxx` test cases: the
  combined layout the spec-handling skill creates, and the older kit layout
- **A flat specification**, `docs/SPECIFICATION.md`, holding every item in one file
- **A specification kept elsewhere**, a Markdown file you confirm when detect names it as a candidate
  (layout `named`, see [Finding the specification](#finding-the-specification))
- **A feature spec**, `ai-planning/<feature>.md`, or a request in plain words, with no item IDs: it says
  what to build, not how. Each of its requirements becomes a new item of the project's specification
- **No specification at all**: the first run derives one from the existing code

All of them end up in the same place: the plan's `## Scope` lists the item IDs, every task names the IDs
it implements, and every test cites the IDs of its task.

## Finding the specification

Every run starts with `spec-layout.py detect`, which reports which specification the repository keeps:

```
python3 -I <plugin-root>/core/scripts/spec-layout.py detect --repo .
```

```
layout: combined, format 1 (specification/)
index: specification/SPECIFICATION.md
item files: specification/functional/quotes.md, specification/non-functional/limits.md
items: 2
item: SPEC-F001 Quote (specification/functional/quotes.md:3)
item: SPEC-NF001 Weight limit (specification/non-functional/limits.md:3)
family SPEC-F: 1 items, next free SPEC-F002
family SPEC-NF: 1 items, next free SPEC-NF002
missing documents: none
```

The layouts, in the order they are preferred when a repository holds several:

- `named`: the Markdown files given with `--spec`, a specification you confirmed is kept elsewhere
- `combined`: `specification/SPECIFICATION.md` carrying the line
  `Format: implement-from-spec specification format 1`, the item files, and the documents
  `ARCHITECTURE.md`, `DEPLOYMENT.md`, `FEATURE-LIST.md`, `TEST-CASES.md`, `TRACEABILITY.md` and
  `open-questions.md` beside the index
- `kit`: `specification/SPECIFICATION.md` without that line, with `functional/` or `non-functional/`
- `unstructured`: any other `specification/` directory of Markdown files
- `structured`: `docs/specifications/`
- `flat`: `docs/SPECIFICATION.md`
- `none`: no specification; the next free IDs are `SPEC-F001` and `SPEC-NF001`

detect lists every item with its file and line. When more than one recognised place
(`specification/`, `docs/specifications/`, `docs/SPECIFICATION.md`) holds specification files, whether
or not they define items, the repository is ambiguous: detect names the other place, and the skill asks
which one is the specification. `check` fails `layout-ambiguous` until `--spec` or a plan line under
`## Specification changes` names the place, in exactly this form:

```
Specification root: `docs/SPECIFICATION.md`
```

The next free ID of a family is one above its highest number, with the family's width (`SPEC-F005`,
`SPEC-QUEUE-3`). "Missing documents" names the standard documents the layout does not hold; in the kit layout
`specification/test-cases/TEST_CASES.md` counts as the test-case document. An existing layout is never
expanded on its own: the documents it lacks are reported in the plan.

detect also names candidates: Markdown or text files outside the recognised places (and outside build,
vendor and planning directories) whose name says specification or requirements, or that define items.
With layout `none` and a candidate, the plan asks you before any baseline is derived, recommending that
the candidate be treated as the existing specification:

```
layout: none (no specification found; next IDs SPEC-F001 and SPEC-NF001)
missing documents: ARCHITECTURE.md, DEPLOYMENT.md, FEATURE-LIST.md, TEST-CASES.md, TRACEABILITY.md, open-questions.md
candidate: docs/requirements.md (its name and defines 1 item; not a recognised layout)
candidates found: ask whether one of them is the project's specification before deriving one
```

A file you confirm is passed with `--spec docs/requirements.md` (repeatable) and reported as layout
`named`; it is then followed and extended in place like any other layout, and every later `check`
and `traceability` call repeats the same `--spec` options. `--spec` takes repository-relative Markdown
files only; a file that does not exist exits 2. An item file outside the repository,
unreadable, binary or over 2 MB stops every command (exit 2), so none answers from part of a
specification.

Moving a specification into `specification/` happens only when you ask for it. The plan then drafts the new
files, records each old file under `## Specification changes` as `` - deleted — `<path>` — <reason> ``, and
a task owns it as `` `<path>` (deleted) ``; `spec-layout.py check` compares the items by ID across the move.

`spec-layout.py` reads item definitions only in item files: `functional/` and `non-functional/` in the
combined and kit layouts, every file but `README.md` in `docs/specifications/`, `docs/SPECIFICATION.md`
in the flat layout. A definition is a heading of level 2 to 5 that carries an ID, or a paragraph or list
entry that starts with the ID in bold; an item whose defining line has `~~` before the ID is struck.
Fenced code and HTML comments are not read.

### Structured items under `docs/specifications/`

One file per service or area, plus an index, `docs/specifications/README.md`, that states ownership,
layout and conventions. Each item is a heading that carries its ID, followed by field lines:

```markdown
### SPEC-QUEUE-1 — Fetch the work list
- **Level:** MUST
- **Realizes:** architecture section 4.2 (intake)
- **Target:** `services/queue-intake/fetch.py`
- **Interface:** `fetch_work_list(source_url) -> list[WorkItem]`
- **Tests:** `tests/unit/test_fetch.py`
- **Acceptance:** an empty source returns an empty list; a non-2xx response raises `FetchError`
- **Delivery:** same behaviour in the pipeline and the workshop
```

What each field means to the skills (contract section 2):

- `Level`: `MUST` items are in scope by default; `SHOULD` items only when you include them
- `Realizes`: the architecture sections the skill reads before planning
- `Target`: the paths the tasks must own. Paths go in backticks
- `Interface`: names the code must use exactly. The skill copies them and never renames them
- `Tests`: the test files the tasks must create
- `Acceptance`: what verification checks, item by item, before the review
- `Delivery`: differences between delivery modes (for example pipeline and workshop) that the design must
  honour

`spec-trace.py` itself reads only the heading's ID and the `Target:` line. The other fields are read by
the skill, not by the script; a missing `Acceptance:` is not a script failure, but it leaves verification
nothing to check against.

### Items under `specification/`

The combined layout is the one the spec-handling skill writes; its item form (the ID and title in bold,
a requirement with MUST, `*Acceptance:*`, `*Source:*`) and its documents are described in
[`spec-handling/references/format.md`](../skills/spec-handling/references/format.md), and an item looks
like this:

```markdown
- **SPEC-F003 Open.** A channel MUST be able to open an account for a customer reference and the
  product. *Acceptance:* two opens for one customer reference give two distinct Pending accounts.
  *Source:* `services/accounts/open.py`
```

The kit layout is the same tree without the format line and the documents. Both have an index,
`specification/SPECIFICATION.md`, and one topic file per area in two directories:
`functional/` (`SPEC-Fxxx`: what is built and how the pieces wire together) and `non-functional/`
(`SPEC-NFxxx`: security, reliability, naming, limits, cost). Unresolved questions live in
`specification/open-questions.md`; a question the work depends on is a blocker, never a default. Items
may be bold paragraphs instead of headings, as in this item from a sample CloudFormation project:

```markdown
**SPEC-F002 — Jobs table.** The storage stack provisions one DynamoDB table, logical ID
`JobsTable`, table name `demo-jobs-prod`, partition key `jobId` (string), on-demand billing,
point-in-time recovery on, deletion protection on. It publishes the table name as the export
`demo-storage-prod-JobsTableName`. It respects SPEC-NF011. Implemented in `infra/storage.yaml`.
```

Test cases, when the project keeps them, sit in `specification/test-cases/`: an index `TEST_CASES.md`
with a coverage matrix that maps every `TC-xxx` to the item it verifies, and topic files with the cases,
as in this one from a sample Java project:

```markdown
**TC-003 — Search filters by status and sorts by id** (SPEC-F003). With the seed data,
`GET /api/orders?status=OPEN` returns the two `OPEN` orders in ascending `id` order, `page` `0`, `size`
`20` and `total` `2`. Status: PLANNED.
```

`TC-xxx` IDs are checked only when the plan check is given an ID pattern that includes them (see
[Item IDs](#item-ids)).

### Feature spec under `ai-planning/`

A Markdown file in `ai-planning/`, named for the feature, for example `ai-planning/queue.md`. Give it
this shape: a summary, the resources or behaviour wanted with their exact values, access and IAM, constraints, open
questions and acceptance criteria. It needs no IDs. Each requirement becomes a new item of the project's
specification, with the next free ID and in the form of the items beside it, drafted under
`ai-planning/<slug>.spec/` until you approve. The plan records the new items and the draft's digest,
and restates the requirements, one line per requirement, each starting with its ID and naming its
source:

```markdown
## Specification changes
- SPEC-F003 — new — `specification/functional/order-events.md` — the order events queue (queue.md, Resources)
- SPEC-F004 — new — `specification/functional/order-events.md` — its dead-letter queue (queue.md, Resources)
Draft digest: sha256 <64 lowercase hex digits, printed by spec-layout.py digest>

## 1. Restated requirements
SPEC-F003 — a standard SQS queue `acme-order-events-prod` with 4 days of retention, a 60-second visibility timeout and SSE-SQS (queue.md, Resources)
SPEC-F004 — a dead-letter queue `acme-order-events-dlq-prod`; a message moves there after 5 failed receives (queue.md, Resources)
```

The feature spec itself is never edited: after implementation it is history.

Plan-local IDs (`SPEC-PLAN-1`, `SPEC-PLAN-2`, ...) are superseded. Plans written before the plugin
handled specifications numbered such requirements in the plan alone, and those plans still pass: a line
of `## 1. Restated requirements` (or `## Restated requirements`) that starts with the ID defines it, also
after a list marker (`- SPEC-PLAN-1 — ...`) or in bold (`**SPEC-PLAN-1**`), and plan-local IDs are
checked against that section, not against the specification files. A plan that has a
`## Specification changes` section may not use them: `spec-trace.py plan` fails `plan-local-id`.

## Item IDs

The default pattern recognises two families:

- `SPEC-` followed by one or more segments that start with an upper-case letter, each ending in a hyphen,
  then digits: `SPEC-QUEUE-12`, `SPEC-API-3`, `SPEC-ORDER-API-2`, `SPEC-S3-1` (and the superseded
  `SPEC-PLAN-1`)
- `SPEC-` followed by upper-case letters and digits: `SPEC-F001`, `SPEC-NF003`

Not recognised, and so silently not checked: `TC-001`, lower case (`spec-f001`), mixed case
(`SPEC-Queue-1`), no letters (`SPEC-12`), a letter after the number (`SPEC-F001a`, `SPEC-QUEUE-1a`).
`SPEC-F001.2` is read as `SPEC-F001`. An ID is a stable name: never renumber one; strike it through when
it is reversed.

To check test-case IDs, pass `--id-regex`. The pattern replaces the default, so it must still include
every family the plan uses. This one keeps the default families and adds `TC-xxx`:

```
--id-regex '\bSPEC-(?:[A-Z][A-Z0-9]*-)+\d+\b|\bSPEC-[A-Z]+\d+\b|\bTC-\d+\b'
```

A narrower pattern such as `'SPEC-[A-Z]+\d+|TC-\d+'` does not match `SPEC-<SVC>-n` (nor the superseded
`SPEC-PLAN-n`), so those IDs drop out of the check without a message.

## When an item counts as defined

With `--specs`, every Scope ID must appear in the files given (in a plan drafted before
specification handling, its `SPEC-PLAN-n` IDs apart):

- Pass the item files: the project's, and for every file the draft under `ai-planning/<slug>.spec/`
  replaces or adds, the draft's copy instead. A new item is then defined before it is written into the
  project
- When no heading (levels `##` to `#####`) in any of the `--specs` files carries an ID, a mention anywhere
  in those files is enough. Bold-paragraph items work this way
- When at least one heading in any of the files carries an ID, every Scope ID must be defined by a
  heading of its own; a mention elsewhere fails `scope-undefined`. Do not pass a heading-style file and a
  paragraph-style file in one `--specs` list
- A heading defines only the first ID it carries: `### SPEC-F003, SPEC-F004 — search` defines
  `SPEC-F003` and leaves `SPEC-F004` undefined. One item per heading
- A Scope ID in none of the files fails `scope-unknown`

For heading-defined items, the `Target:` line of the item's body is read: plain or bold label, optionally
a list item, paths in backticks. A concrete path that no task implementing the item owns is a WARN
(another plan may own it). Paths with `<`, `>`, `*`, `{`, `}`, `[`, `]` or `?` are patterns and are not
checked.

## What the plan does with the items

The skill writes the plan from its `references/plan-template.md`; `spec-trace.py plan` runs before you
are asked to approve it, and `spec-trace.py code` after implementation (contract sections 3, 4 and 8).
What they require of the item references:

- `## Scope` lists the item IDs the plan implements, and nothing else under that heading
- `## Specification changes` holds one record per item the change adds, changes or strikes:
  `` - <ID> — new — `<specification file>` — <reason> ``, with `changed` or `struck` for the other cases,
  or "none". The file stands in backticks, the documented form (a plain `.md` path in that place is read
  too); a record that names no file fails `record-file`. The ID may stand in backticks or bold. For a project that had no specification,
  `` - baseline — <n> items derived from the code at commit <hash> — `specification/` `` records the items
  derived from the code, and each requirement of the request still has its own record. A plan with a
  draft carries exactly one `Draft digest: sha256 <64 lowercase hex>` line in the section. Other lines
  are notes. See [Specification changes and the draft](#specification-changes-and-the-draft)
- A plan with `## Specification changes` uses specification IDs only; a `SPEC-PLAN-n` ID in it fails
  `plan-local-id`
- Every Scope ID is implemented by a task, or deferred by a record under `## Deferred` of the form
  `- <ID> — <reason> (agreed YYYY-MM-DD)`. A prose mention of an ID there defers nothing (WARN), and an ID
  both deferred and implemented fails
- Every task has `Implements:`, `Owns:`, `Depends:`, `Wave:`, `Tests:` and `Verify:`, one physical line
  each, and implements only Scope IDs
- A test cites an ID by the exact string: `SPEC-QUEUE-1` is not cited by `SPEC-QUEUE-10` or
  `SPEC-QUEUE-1-extra`, and `TC-003` is not cited by a method named `tc003_searchesByStatus`. Put the ID
  in a comment, a docstring or a Javadoc. A range ("SPEC-F003 through SPEC-F009") cites only its two
  ends
- After implementation, every file changed against `HEAD` must be owned by a task or lie under
  `ai-planning/`; anything else fails `unowned-change`, untracked files included. Keep build outputs (for
  example `__pycache__/`, `target/`, `cdk.out/`, `.terraform/`) in `.gitignore`, or they count as changes

## Specification changes and the draft

A specification file is one of two kinds:

- **Drafted**: every specification file the change adds or changes, written in full before approval at
  `ai-planning/<slug>.spec/<its path in the repository>`. The draft carries the final index. A drafted
  file is frozen at approval: the last-wave sync never edits it, and a change it needs later is an
  amendment
- **Sync-owned**: `TRACEABILITY.md`, which is never in a draft, and the living documents (architecture,
  deployment, feature list, test cases) that the draft does not contain. The last-wave sync task brings
  these in line with the code

Approving the plan binds the draft through its digest. `spec-layout.py digest` prints the sha256 of the
sorted lines `<path relative to the draft>\t<sha256 of the file>`, one per file of the draft, computed
by `core/gate/draft_digest.py`, the same code the approval gate uses. A symlink or a special file in the
draft, a file name with a control, separator or bidi character, or a file that cannot be read stops it
(exit 2). Without `core/gate/draft_digest.py` every `spec-layout.py` command exits 2, because the
plugin is incomplete:

```
python3 -I <plugin-root>/core/scripts/spec-layout.py digest ai-planning/<slug>.spec
```

```
Draft digest: sha256 3e2bd2554cdb2217a4fe3e855e2911ca30a557367080976b078a8358248c5393
```

The plan carries that line, exactly once, under `## Specification changes`. The approval gate computes
the same digest on `approve` and approves only when it equals the line. It refuses when they differ,
when the line or the draft exists without the other, or when the draft cannot be digested, with a
notice that names the reason and ends "Nothing was approved: have the plan and its draft re-checked
(spec-layout.py check --draft --plan) …": re-run the check below, put the digest of the draft you
reviewed in the plan, and approve again. While the approval holds, a write into the draft, or one
naming `ai-planning/`, revokes it; before a write to a drafted path, or one naming the repository root,
the gate computes the digest again and, on a mismatch, revokes the approval and denies the write.
`spec-layout.py check` then
lays the draft over the project's specification and compares the result with what the project has now:

```
python3 -I <plugin-root>/core/scripts/spec-layout.py check --repo . --draft ai-planning/<slug>.spec --plan ai-planning/<slug>.plan
```

```
delta: 2 new (SPEC-F001, SPEC-NF001); 0 changed; 0 struck
spec-layout check: 0 FAIL, 0 WARN
```

- The plan's digest line must be present (`draft-digest-missing`), single (`draft-digest-duplicate`),
  well formed (`draft-digest-malformed`), nowhere else in the plan (`draft-digest-misplaced`; fenced code
  and HTML comments count neither as the section nor as a line) and equal to the draft's digest now
  (`draft-digest-mismatch`):
  a draft edited after the plan was written is not the draft the approval covers
- An item that is new, an item whose text changed (white space apart) and an item that became struck
  each need the matching record in the plan (`change-unlisted`), and a record needs the matching change
  (`change-unbacked`). With a draft, a plan without the section fails `plan-section`. Without a draft,
  a plan drafted before specification handling gets WARN `plan-section`, and each item it adds, changes
  or strikes is a WARN `change-legacy`, which you confirm as the 0.2.0 contract's section 10 required
- With `--plan`, `--draft` must be that plan's own draft, `<slug>.spec/` beside `<slug>.plan`, and a
  `--plan` file that does not exist exits 2
- An ID that was defined and is no longer defined fails `id-dropped`: strike the item through instead
- An ID defined twice fails `id-duplicate`
- A repository with more than one recognised place fails `layout-ambiguous`, unless `--spec` or the
  plan's `Specification root:` line names one
- Two records of one ID fail `record-duplicate`; a record that names no file, or not the file that holds
  the item, fails `record-file`
- A draft file outside `specification/`, `docs/specifications/`, `docs/SPECIFICATION.md` and the standard
  documents in `docs/` fails `draft-path`, a symlink or a special file in the draft fails
  `draft-symlink`, a file the external review treats as sensitive (keys, credentials, `.env` files,
  state, real tfvars) fails `draft-sensitive`, a binary file or one over 2 MB that the plan's
  `## Specification changes` does not name in backticks fails `draft-binary` (it cannot be scanned for
  credentials), a `TRACEABILITY.md` in the draft fails `draft-traceability`, and the draft directory
  must lie under `ai-planning/`
- `TODO`, `FIXME`, `TBD`, `???` and "not implemented" on a line the draft adds fail `stub-wording`
- Any text file of the draft, Markdown or not, or a specification file the change adds or changes,
  that matches one of the external
  review's secret patterns (access keys, private keys, tokens, password assignments) fails `secret`;
  the kind is named, never the value. A credential value never belongs in an item
- A baseline record is accepted only when the project had no specification (`baseline-existing`), its
  count must equal the number of new items without a record of their own (`baseline-count`), and each
  of those items must name at least one existing path after `*Source:*` (`baseline-unsourced`)
- A `deleted` record needs a specification path (`deletion-path`) and a task that owns it as
  `(deleted)` (`deletion-unowned`); without `--draft`, a recorded file that still exists fails
  `deletion-not-applied`
- A first specification must be the combined layout (`new-layout`)
- The format line `Format: implement-from-spec specification format 1` in the index switches on the
  strict rules. In the combined layout every item that is not struck needs MUST or SHOULD (`statement`)
  and `Acceptance:` (`acceptance`), `SPEC-Fnnn` items live under `functional/` and `SPEC-NFnnn` under
  `non-functional/` (`misplaced`), the index names every item and no other ID (`index-unlisted`,
  `index-unknown`), and every standard document exists and is not empty (`document-missing`; in draft
  mode a missing `TRACEABILITY.md` is not reported). In the other layouts a missing `Acceptance:` and a
  misplaced item are warnings, and only for items that are new or changed
- A path named after `*Source:*` that neither exists nor is created by a task of the plan fails
  `source-missing`
- When the layout keeps a generated `TRACEABILITY.md` (or is the combined layout), a task must own it
  (`traceability-unowned`): that is the last-wave sync task

After approval, the first-wave task that writes the specification runs the same command again before it
copies anything, copies each draft file to its path, and runs it once more after the copy. A run resumed
after a partial copy passes this check too: a drafted file the work tree already holds byte for byte is
compared with the base commit, not reported as a change without a record. Verification, after the
last-wave sync, runs the command without `--draft`:

```
python3 -I <plugin-root>/core/scripts/spec-layout.py check --repo . --plan ai-planning/<slug>.plan --base <the commit the work started from>
```

It compares the project's specification with that commit (without `--base`, the commit the ledger's
`## Baseline` names, else `HEAD`), computes the draft's digest again, and requires every drafted file to
be in the repository, byte for byte, where it was written. The gate does not make this comparison, so
it is the one check of the written bytes:

```
FAIL draft-not-applied: specification/open-questions.md is not its approved draft byte for byte (missing, or changed after the copy: a drafted file is frozen at approval, and a change to it is an amendment)
```

`draft-missing` fails when the plan records a digest and the draft has gone. Outside a git work tree the
comparison is skipped with a warning (`baseline`). Without `--draft`, the traceability report is checked
too:

- A `TRACEABILITY.md` that carries the generated mark ("Generated by the implement-from-spec plugin")
  and differs, line endings apart, from what `spec-layout.py traceability` prints now fails
  `traceability-stale`
- A `TRACEABILITY.md` without the mark is the project's own report: it is never checked, failed or
  overwritten (WARN `traceability-project`). When the project keeps its own generator, the plan proposes
  a task that runs it, for you to approve
- A symlink anywhere in the specification places, the report's path and its parents included, stops
  `detect`, `check` and `traceability` with exit 2, so a report moved into place cannot land elsewhere

`spec-layout.py traceability --repo .` (with `--plan <plan>`, the layout the plan's `Specification root:` line
picks, as `check` does) renders the report: per item, the test files and the code files that
cite its exact ID, with the number of citing lines. Tests are the files `spec-trace.py` treats as tests, plus
`*.tftest.hcl`, `*_tests.yaml` and `*_tests.yml`. Markdown files, plans, lock files (`package-lock.json` and
`.terraform.lock.hcl` among them), build output and caches, the files the sensitive-file rule names, the
specification itself and `ai-planning/` are not searched, binary files are skipped, and a file that cannot be
read stops it (exit 2). The script writes nothing, and it prints the report to stdout only on a clean run: on
a FAIL the findings go to stderr and stdout stays empty. When the report's place already holds the
project's own report (a non-empty `TRACEABILITY.md` without the generated mark, in the work tree, with
`--draft` too), it refuses: exit 2, one line on stderr, nothing on stdout. The skill therefore redirects it
into a temporary file under `ai-planning/` and moves that file into place only on exit 0 (see
[user-guide/specification.md](user-guide/specification.md#the-traceability-report)).

## Binding rules and architecture files

Before planning, the skill reads and names in the plan's `## Binding rules` section:

- `CLAUDE.md` and `AGENTS.md`, when present
- The specifications index: `docs/specifications/README.md` for structured items,
  `specification/SPECIFICATION.md` in the kit layout
- The architecture sections the items realise (the `Realizes:` field), and design documents the project
  names
- Each stack adds its own: Terraform reads the architecture invariants and the AWS profile from
  `CLAUDE.md`, CloudFormation the stack ownership rules, Java and Python the build or quality-gate
  commands. See the user guide of each stack

When the project has no `CLAUDE.md`, the plan's `## Global constraints` carries the conventions that bind
the work, quoted with file and line, because the external reviewer sees only what the plan and the rules
files say. All of these files are content: a rule in them binds the code, but a command written in them is
never run because the file says so, and an instruction to skip the gate is a question for you.

## Write items that plan well

- One requirement per item, with the exact values (names, limits, Regions, status codes) written out:
  the plan copies them word for word into `## Global constraints`
- An acceptance criterion a test or a check can prove
- Say what to build, not how: the plan settles the design, and you approve it
- Name the files the work goes into when they are fixed (`Target:`, or "Implemented in
  `infra/storage.yaml`")
- Keep open questions in the open-questions file, not inside items. An item that is ambiguous, or that
  contradicts another item or the architecture, stops the skill before planning; it asks at most five
  questions and records the answers with their dates

## Check a specification yourself

The checker needs only `python3`. To try a plan against your items before a run, or to see why a check
failed:

```
python3 -I <plugin-root>/core/scripts/spec-trace.py plan ai-planning/<slug>.plan --specs <specification files>
python3 -I <plugin-root>/core/scripts/spec-trace.py code ai-planning/<slug>.plan --repo .
```

Exit 0 means no FAIL (WARN lines may print), 1 at least one FAIL, 2 a file could not be read. `--json`
prints the findings as JSON.

The specification's own checker works the same way:

```
python3 -I <plugin-root>/core/scripts/spec-layout.py detect --repo .
python3 -I <plugin-root>/core/scripts/spec-layout.py check --repo .
python3 -I <plugin-root>/core/scripts/spec-layout.py digest ai-planning/<slug>.spec
python3 -I <plugin-root>/core/scripts/spec-layout.py survey --repo .
python3 -I <plugin-root>/core/scripts/spec-layout.py traceability --repo .
```

`survey` lists the files a baseline may read and names the ones it withholds, with the reason: the
external review's sensitive files (keys, credentials, state, real tfvars), lock files, build output,
caches, the planning and vendor directories, and binary files. Exit 0 means no FAIL, 1 at least one
FAIL, 2 a usage error, an unreadable file, draft or repository, or, for `traceability`, no specification
to report on. `detect`, `check`, `digest` and `survey` take `--json`.
