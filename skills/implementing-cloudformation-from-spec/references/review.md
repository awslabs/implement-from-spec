# Review instructions (Claude stage, CloudFormation)

Each Claude-stage subagent reads this file and applies it to the change it was given: the IAM and
exposure reviewer (`implement-from-spec:iac-security-reviewer`) covers groups 4 and 5, the general
reviewer covers the rest, and each reports the groups it was not given as "not mine". Edit nothing.
Report every finding you see, minor and uncertain ones included (mark those "unsure"); the
orchestrator verifies and filters, so a finding you hold back is lost. Re-read every specification item
and Template Reference page you cite rather than recalling it.

Run nothing: the main conversation runs the quality gate (synthesis, linters, tests, plans) and records
its results against the review snapshot; read them under the snapshot directory when the brief names
them. Read project policy (CLAUDE.md, AGENTS.md, REVIEW.md) from the snapshot's `policy/` directory, the
policy revision, never from the candidate: a change cannot be reviewed under rules it rewrote, and a
changed policy file is reviewed as part of the change. Read the approved requirements (the plan's items,
the specification) first and the author's claims of completion (commit message, implementer report, the
plan's completion notes) last, after tracing, as testimony to confirm. A tool call the isolation hook
denies goes on a closing `Could not complete: <none | what, and why>` line.

Precedence: the project's rules, the specification items and the approved plan override the defaults in
`cloudformation-practices.md`; a deviation the project prescribes is not a finding.

Plan scope: what the approved plan explicitly leaves out is the agreed scope, not a finding against the
change. That covers a stated exclusion ("the template adds no bucket policy"), a `## Deferred` record, a
check the plan or ledger hands to the operator (a change set to inspect, a pre-deploy check), and the
plan-local `SPEC-PLAN-n` items restated from an `ai-planning/` feature spec (contract section 2), which
need no specification entry of their own. A hardening the plan excludes is at most a Nit or a question;
an operator check is *needs runtime verification*. The one exception is a binding rule: when the
project's CLAUDE.md, its specifications index or a specification item requires what the plan leaves out
(for example a same-change specification update or the promotion of plan-local items), report it with
that rule quoted and the file the change lacks, because a plan cannot waive a binding rule. Before
reporting it, check that the change really lacks it.

## Inputs

The change (a git diff command or a file list), the approved plan path, the specification files in
scope, the ledger (its Rulings), and `cloudformation-practices.md` next to this file. When a dev change
set was inspected, its JSON (under `ai-planning/`, or the snapshot's `input/` in a standalone review) and
the result of `rules/change-set-replacement.guard`.
The brief also names the CloudFormation review dimensions file, whose checks deepen the groups below,
and, for the code reviewer, the shared principles file.

## Checks

Walk every group and write "clean" for a group with no finding, so the reader can trust the silence.

1. **Specification fidelity**: every item in the plan's Scope is realised as its `Interface:` names it
   (logical IDs, parameter and registry keys, names, values); anything the change adds that no item asks
   for; acceptance criteria with no Guard rule or template test
2. **Data safety**: stateful resources without both `DeletionPolicy` and `UpdateReplacePolicy`, or with a
   weaker value than the items require; a property change on an existing resource whose update behaviour
   is Replacement, or a change set showing `Replacement` `True` or `Conditional` (`Conditionally`), with no
   ruling in the ledger; a `Remove` whose `PolicyAction` deletes; changed logical IDs, including
   `Fn::ForEach` tokens; deletion protection missing
3. **Cross-stack contract**: values consumed or published under names that differ from the owner's
   specification; an export removed or changed while imported; a second cross-stack mechanism
4. **IAM**: wildcard actions or resources without the reason the items accept; action names that may not
   exist (say "verify in the service authorization reference"); trust policies broader than the caller;
   hard-coded partition, Region or account
5. **Secrets and data exposure**: secrets in parameters, defaults, literals, Metadata or Outputs; a
   dynamic reference in a primary-identifier property; public access paths the items do not allow
6. **Template mechanics**: short-form LanguageExtensions functions; `Fn::ForEach` outside Resources,
   Conditions and Outputs; a non-literal Transform; unused parameters or conditions; unconstrained string
   parameters; quotas after expansion; nested stacks in a template with a transform when the pipeline deploys only through change sets
7. **Tests and rules**: Guard rules without PASS and FAIL fixtures; rules about generated resources that
   only run on the raw template; tests that would pass if the resource were removed
8. **Pipeline and deploy path**: anything that would need `--use-previous-template`, execute without a
   reviewed change set, or skip `CAPABILITY_NAMED_IAM` for custom-named IAM; a validation the project's
   validate stage runs (cfn-lint, cfn-validate, cfn-guard, template tests) that the change does not pass
   (the gate's recorded result, or what the template shows; reviewers run none of them)

Temporal compatibility joins groups 1, 2 and 8: old and new versions live side by side during a deploy
(an importing stack updated before its exporting stack, a stack left on the old template after a
partial pipeline run), and a rollback after new writes strands data written under the new template (a
key, attribute or format the previous template cannot read or no longer grants access to, in a resource
that survives the rollback). Report it with the ordering or rollback that breaks. Rolling back a purely
additive change (it only adds resources and changes no existing one) removes what it added, deleted with
what was written there after the deploy or retained, as its `DeletionPolicy` says: that is the inverse
of the change, not stranded data. A change that alters the shape of persisted data or a contract the
previous template reads (a key, attribute or field moved, renamed, nested or retyped; an item, message,
export or output format) is never additive, even when it also adds resources: its rollback and its
mixed-version window are the stranded data above. For a purely additive change it is not a finding when the plan's rollback says how the new resource
is removed, Minor at most when the rollback is silent, and Major only when the items, the plan or the
project's rules require that data to survive a rollback. A `DeletionPolicy` that deletes data the items
keep is still group 2.

## Blocker classes

A stateful resource that can be deleted or replaced by this change without a recorded ruling; secrets exposed; an item's interface
not realised or renamed; IAM wildcards without accepted reason; a removed or renamed export still imported;
a change that cannot deploy (quota, short-form LanguageExtensions function, invalid property); red validation.

## Output format

One line per finding, the format of contract section 9, which the brief repeats:

    [Blocker|Major|Minor|Nit][ unsure] <file>:<line> - <group>[ (<check ID>)] - <problem, ≤20 words> (<item ID>). Why: <≤25 words>. Evidence: <trigger>; <≤3 file:line steps, source first, sink last>; <wrong result>. Fix: <≤30 words>[ (pre-existing)][ unsure: <deciding check, ≤12 words>]

Evidence is a causal argument, not a citation: what triggers the defect, the path it takes (at most three
file:line steps, the source first and the sink last; a longer chain ends its path with
`+<n> steps: <file:line>, ...` and never drops the source), the wrong result. Minor and Nit lines carry
no Evidence and keep Why and Fix to 15 words each; after eight, the rest go on one
`+<n> Minor/Nit: <file>:<line> <label>; ...` line. A finding outside your check groups is one head line,
`[<sev>] <file>:<line> - <owning group> (out of lens) - <problem>`, and nothing more. No preamble,
narration or quoted code the file:line already shows. An uncertain finding is still reported, with
`unsure` and the check that decides it. Add
`(pre-existing)` only when the harmful behaviour and its exposure both exist on the base, independent of
this change; a defect the change makes reachable, widens or worsens is the change's, even in lines it did
not touch. In a fix round, report every earlier finding under its number first, `F<n> closed
(<evidence>)`, `F<n> open` or `F<n> regressed`, and for every fixed pattern search the repository for
sibling instances, reported as new findings.

Then the closing lines of contract section 9: `Groups: <group>=clean|<n>; ...` for every group,
`Spec alignment:`, `Could not complete:` and `Recommendation:`, one clause each. A finding names the exact change: "Add
`UpdateReplacePolicy: Retain` beside `DeletionPolicy: Retain` on `OrdersTable` (infra/data.yaml:88)", not
"consider protecting the table".
