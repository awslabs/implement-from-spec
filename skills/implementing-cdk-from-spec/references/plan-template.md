# Plan template (AWS CDK)

Write `<repo>/ai-planning/<slug>.plan` with these sections in this order; the slug is two to five
kebab-case words. Replace the guidance under each heading. No Python, Java, template JSON or policy JSON:
name stacks, constructs, construct IDs, logical IDs, properties and outputs, and describe them in prose.
`${CLAUDE_PLUGIN_ROOT}/core/scripts/spec-trace.py plan` parses `## Scope` and the `### Task` fields, so
keep those headings and field names exactly.

```markdown
# <Feature>: plan

Items: <specification files> · Drafted: YYYY-MM-DD

## Scope
The specification item IDs this plan implements, one per line or comma-separated. Nothing else.

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
The files that bind the work, with paths: CLAUDE.md or AGENTS.md, the specifications index, the
architecture sections the items realise. These are passed to the GPT reviewer as --rules.

## Global constraints
Exact values the items fix, copied verbatim with their item ID: stack IDs, construct IDs, resource
names, retention values, limits, Regions, accounts.

## 1. Restated requirements
What the items ask for, in your own words, item by item. Each ambiguity and how it was resolved, with the
user's dated answer where one was needed.

## 2. Construct and stack inventory
Per stack touched: the stack ID, its file, its place in the pipeline order and its environment (account
and Region, or environment-agnostic). Then one line per construct the plan adds or modifies: construct
path, construct ID, level (L1, L2 or L3), the CloudFormation resource types it synthesises, and for each
existing resource its current logical ID from the synthesised template, which must not change. For each
existing resource modified: the properties that change and each one's update behaviour from the Template
Reference, cited.

## 3. Cross-stack contract
Every value this change consumes from another stack and publishes for one: the name, the mechanism
(construct reference passed as props, SSM parameter, export) and the consumer, matching the owning
specification exactly.

## 4. IAM design
Per role or policy: the grant methods used or the actions, named and cited, and the narrowest resources.
Any wildcard with the reason the items accept.

## 5. Data protection and replacement evidence
Per stateful resource: removal policy (set explicitly), DeletionPolicy and UpdateReplacePolicy in the
synthesised template, deletion protection, encryption key. What the change-set diff for this plan must not
show (an existing resource destroyed or replaced, Replacement True or Conditional) and on which logical
IDs. Any construct rename and how it is handled: kept ID, the Default construct ID, or a separate cdk
refactor with its dry-run mapping.

## 6. Tests, nag and validation
The fine-grained assertion tests (and snapshot tests, if the project keeps them) that prove each item's
acceptance; the cdk-nag rule pack and any acknowledgement with its reason; the template-level rules
(cfn-lint, cfn-guard) the synthesised templates must pass.

## 7. Check commands
The exact commands of the project's checks this change must pass (test, synth, nag, template checks), the
change-set diff commands per stack and for the whole app, and the expected result of each.

## 8. Dependencies
Every new library or tool with its exact version and reason, or "none".

## Review focus
Inputs or failure modes the items imply that no task's tests exercise, for the reviewers.

## Tasks
### Task 1 — <title>
Implements: <item IDs>
Owns: `<path>`, `<path>`, `<test file the task writes>`
Depends: none
Wave: 1
Tests: `<test path>`
Verify: <command and expected result>

A test file the task writes or edits is in its `Owns:` as well as its `Tests:`: `spec-trace.py code` fails a
written file no task owns, and after approval only an amendment and a second approval fix it.

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
What could go wrong at the first change set or deploy, how it would show, and how to back it out.
```
