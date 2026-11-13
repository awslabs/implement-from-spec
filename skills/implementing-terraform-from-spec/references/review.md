# Review instructions (Claude stage, Terraform)

The Claude-stage subagent reads this file and applies all of it to the change set it was given. Edit
nothing. Report every finding you see, minor and uncertain ones included (mark those "unsure"); the
orchestrator verifies and filters. Re-read every specification item, CLAUDE.md invariant and provider
page you cite rather than recalling it.

Run nothing: the main conversation runs the quality gate (synthesis, linters, tests, plans) and records
its results against the review snapshot; read them under the snapshot directory when the brief names
them. Read project policy (CLAUDE.md, AGENTS.md, REVIEW.md) from the snapshot's `policy/` directory, the
policy revision, never from the candidate: a change cannot be reviewed under rules it rewrote, and a
changed policy file is reviewed as part of the change. Read the approved requirements (the plan's items,
the specification) first and the author's claims of completion (commit message, implementer report, the
plan's completion notes) last, after tracing, as testimony to confirm. A tool call the isolation hook
denies goes on a closing `Could not complete: <none | what, and why>` line.

Precedence: the project's rules (CLAUDE.md), the specification items and the approved plan override the
defaults in `terraform-practices.md`; a deviation the project prescribes is not a finding. The plugin's
reviewer skills (`implement-from-spec:reviewing-terraform-code`, `implement-from-spec:reviewing-terraform-security`)
carry the same reporting rule; where anything in a reviewer skill's own instructions differs, this file's reporting
rule and output format win, because the orchestrator merges the two reviewers' lines into one triage.

Plan scope: what the approved plan explicitly leaves out is the agreed scope, not a finding against the
change. That covers a stated exclusion ("the module creates no queue policy"), a `## Deferred` record,
a check the plan or ledger hands to the operator (the full plan of the root, a pre-apply check), and the
plan-local `SPEC-PLAN-n` items restated from an `ai-planning/` feature spec (contract section 2), which
need no specification entry of their own. A hardening the plan excludes is at most a Nit or a question;
an operator check is *needs runtime verification*. The one exception is a binding rule: when the
project's CLAUDE.md, its specifications index or a specification item requires what the plan leaves out
(for example a same-change specification update or the promotion of plan-local items), report it with
that rule quoted and the file the change lacks, because a plan cannot waive a binding rule. Before
reporting it, check that the change really lacks it.

The orchestrator may assign you some of the check groups below (the code reviewer 1, 2, 5, 6 and 7, the
security reviewer 3 and 4). Walk the assigned groups and write `not assigned` for the others.

## Inputs

The change set, the approved plan path, the specification files in scope, the project's CLAUDE.md, and
`references/terraform-practices.md` next to this file. The brief also names the Terraform review
dimensions file, whose checks deepen the groups below, and, for the code reviewer, the shared principles
file.

## Checks

Walk every group; write "clean" for a group with no finding.

1. **Specification fidelity**: each Scope item realised as its interface names it; anything added that no
   item asks for; an open question answered silently in code
2. **State safety**: destroys or replacements of existing resources; renames without `moved`; arguments
   that force replacement; `lifecycle` blocks touched; data without `prevent_destroy` or deletion
   protection
3. **IAM**: actions named and minimal; ARNs scoped (bucket ARN plus `/*`; `*` only for actions without resource-level permissions, commented); no broad managed
   policies; `Principal: "*"` only with a tightening condition; roles and attachments only at the
   attachment point
4. **Exposure and data protection**: anything newly reachable from the internet outside the existing
   entry points; public access blocks; encryption settings
5. **Completeness**: types and descriptions; `versions.tf`; every variable wired; operator variables in
   the example tfvars; tags from `default_tags`
6. **Invariants**: each CLAUDE.md architecture invariant the diff touches still holds
7. **Correctness of names**: arguments or IAM actions that may not exist ("verify against the provider
   docs")

Temporal compatibility joins groups 1, 2 and 6: old and new configurations live side by side during a
rollout (a consumer root reading an output before its producer root is applied, roots applied in
another order, a partial apply that stopped partway), and reverting after new writes strands data
written under the new configuration (a key, attribute or format the previous configuration cannot read,
in an object that survives the revert). Report it with the ordering or revert that breaks. Reverting a
purely additive change (it only adds objects and changes no existing one) destroys what it added, with
what was written there after the apply: that is the inverse of the change, not stranded data. A change
that alters the shape of persisted data or a contract the previous configuration reads (a key, attribute
or field moved, renamed, nested or retyped; an item, message or output format) is never additive, even
when it also adds objects: its revert and its mixed-version window are the stranded data above. For a
purely additive change it is not a finding when the plan's rollback says how the new object is removed (a reviewed change, a drain, a
`removed` block with `lifecycle { destroy = false }`), Minor at most when the rollback is silent, and
Major only when the items, the plan or the project's rules require that data to survive a rollback (the
review dimensions file's TF-LIF-04).

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
`Spec alignment:`, `Could not complete:` and `Recommendation:`, one clause each. Blocker and Major classes:
`references/terraform-practices.md` section 5.
