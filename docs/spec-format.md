# Specification input formats

What the implementing skills accept as input, and the exact rules the traceability checker
(`core/scripts/spec-trace.py`) applies to it. Every rule on this page was checked by running
`spec-trace.py` on the examples shown. The workflow that uses these inputs is
[core/contract.md](../core/contract.md), sections 2 and 3.

Each implementing skill takes the repository and one input:

```
/implement-from-spec:implementing-<stack>-from-spec <repo> <SPEC ids | specification file | ai-planning/feature.md>
```

Plain words work too ("implement SPEC-F003 in this repo"). The input is authoritative: the code conforms
to it, and a change to it is your decision, never the skill's.

## The three input forms

- **Structured items**, `SPEC-<SVC>-n`, in files under `docs/specifications/`, one heading per item
  with field lines
- **Kit layout items**, `SPEC-Fxxx` (functional) and `SPEC-NFxxx` (non-functional), in topic files
  under `specification/`, optionally verified by `TC-xxx` test cases
- **A feature spec**, `ai-planning/<feature>.md`, with no item IDs: it says what to build, not how. The
  plan gives each of its requirements a plan-local `SPEC-PLAN-n` ID

All three end up in the same place: the plan's `## Scope` lists the item IDs, every task names the IDs
it implements, and every test cites the IDs of its task.

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

### Kit layout under `specification/`

An index, `specification/SPECIFICATION.md`, and one topic file per area in two directories:
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
questions and acceptance criteria. It needs no IDs. The skill restates it in the plan, one line per
requirement, each starting with a plan-local ID and naming its source:

```markdown
## 1. Restated requirements
SPEC-PLAN-1 — a standard SQS queue `acme-order-events-prod` with 4 days of retention, a 60-second visibility timeout and SSE-SQS (queue.md, Resources)
SPEC-PLAN-2 — a dead-letter queue `acme-order-events-dlq-prod`; a message moves there after 5 failed receives (queue.md, Resources)
```

A line may start with a list marker (`- SPEC-PLAN-1 — ...`) or bold (`**SPEC-PLAN-1**`). The heading is
`## 1. Restated requirements` or `## Restated requirements`. Plan-local IDs are checked against that
section, not against the specification files. The feature spec itself is never edited: after
implementation it is history.

## Item IDs

The default pattern recognises two families:

- `SPEC-` followed by one or more segments that start with an upper-case letter, each ending in a hyphen,
  then digits: `SPEC-QUEUE-12`, `SPEC-API-3`, `SPEC-ORDER-API-2`, `SPEC-S3-1`, `SPEC-PLAN-1`
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

A narrower pattern such as `'SPEC-[A-Z]+\d+|TC-\d+'` does not match `SPEC-PLAN-n` or `SPEC-<SVC>-n`, so
those IDs drop out of the check without a message.

## When an item counts as defined

With `--specs`, every Scope ID other than a `SPEC-PLAN-n` ID must appear in the files given:

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
- Every Scope ID is implemented by a task, or deferred by a record under `## Deferred` of the form
  `- <ID> — <reason> (agreed YYYY-MM-DD)`. A prose mention of an ID there defers nothing (WARN), and an ID
  both deferred and implemented fails
- Every task has `Implements:`, `Owns:`, `Depends:`, `Wave:`, `Tests:` and `Verify:`, one physical line
  each, and implements only Scope IDs
- A test cites an ID by the exact string: `SPEC-QUEUE-1` is not cited by `SPEC-QUEUE-10` or
  `SPEC-QUEUE-1-extra`, and `TC-003` is not cited by a method named `tc003_searchesByStatus`. Put the ID
  in a comment, a docstring or a Javadoc. A range ("SPEC-PLAN-1 through SPEC-PLAN-7") cites only its two
  ends
- After implementation, every file changed against `HEAD` must be owned by a task or lie under
  `ai-planning/`; anything else fails `unowned-change`, untracked files included. Keep build outputs (for
  example `__pycache__/`, `target/`, `cdk.out/`, `.terraform/`) in `.gitignore`, or they count as changes

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
