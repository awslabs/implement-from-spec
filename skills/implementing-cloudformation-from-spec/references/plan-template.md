# Plan template (CloudFormation)

Write `<repo>/ai-planning/<slug>.plan` with these sections in this order; the slug is two to five
kebab-case words. Replace the guidance under each heading. No YAML and no policy JSON: name resource
types, logical IDs, parameters and outputs, and describe them in prose. The plugin's `spec-trace.py plan`
(`${CLAUDE_PLUGIN_ROOT}/core/scripts/`) parses `## Scope` and the `### Task` fields, so keep those
headings and field names exactly.

```markdown
# <Feature>: plan

Items: <specification files> · Drafted: YYYY-MM-DD

## Scope
The specification item IDs this plan implements, one per line or comma-separated. Nothing else.

## Binding rules
The files that bind the work, with paths: CLAUDE.md or AGENTS.md, the specifications index, the
architecture sections the items realise. These are passed to the GPT reviewer as --rules.

## Global constraints
Exact values the items fix, copied verbatim with their item ID: stack names, logical IDs, parameter and
registry keys, resource names, retention values, limits, Regions.

## 1. Restated requirements
What the items ask for, in your own words, item by item. Each ambiguity and how it was resolved, with the
user's dated answer where one was needed.

## 2. Stack design
Per stack touched: the template path, the stack's place in the pipeline order, its parameters (type,
constraint, source: parameter file, registry, change-set parameter), its conditions, and its resources by
logical ID with one sentence each. For each existing resource modified: the properties that change and
each one's update behaviour from the Template Reference, cited.

## 3. Cross-stack contract
Every value this change consumes from another stack and publishes for one: the name, the mechanism (SSM
parameter, export, change-set parameter) and the consumer, matching the owning specification exactly.

## 4. IAM design
Per role or policy: the actions, named and cited, and the narrowest resources, built from pseudo
parameters. Any wildcard with the reason the items accept.

## 5. Data protection and safety
Per stateful resource: DeletionPolicy, UpdateReplacePolicy, deletion protection, encryption key. Any
termination protection or stack policy the items require. The change-set expectation: per existing
logical ID the change touches, the expected Action and Replacement (False, unless a ruling the user
agreed to is recorded), and that no Remove has PolicyAction Delete. The skill's
rules/change-set-replacement.guard checks a dev change set against it.

## 6. Policy rules and template tests
The Guard rules and template tests that prove each item's acceptance, with their passing and failing
fixtures.

## 7. Validation commands
The exact commands of the project's validate stage this change must pass, and the expected result.

## 8. Quotas
Resources, outputs and parameters per template after Fn::ForEach expansion, against the quotas.

## Review focus
Inputs or failure modes the items imply that no task's tests exercise, for the reviewers.

## Tasks
### Task 1 — <title>
Implements: <item IDs>
Owns: `<path>`, `<path>`, `<test or fixture file the task writes>`
Depends: none
Wave: 1
Tests: `<test or fixture path>`
Verify: <command and expected result>

A test or fixture file the task writes or edits is in its `Owns:` as well as its `Tests:`: `spec-trace.py
code` fails a written file no task owns, and after approval only an amendment and a second approval fix it.
`Tests:` lists only files that will cite every item ID the task implements (exact IDs, `SPEC-PLAN-n`
included), because `spec-trace.py code` fails each listed test that cites none of them. A project-wide
runner (`scripts/validate.sh`) or an existing rule the task does not edit goes in `Verify:`, not `Tests:`.

## Deferred
One record per Scope item the user agreed to leave out: `- <ID> — <reason> (agreed YYYY-MM-DD)`. Otherwise "none".

## Risks and rollback
What could go wrong at the first change set or deploy, how it would show, and how to back it out.
```
