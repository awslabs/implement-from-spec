# Review instructions (Claude stage, Terraform)

The Claude-stage subagent reads this file and applies all of it to the change set it was given. Edit
nothing. Report every finding you see, minor and uncertain ones included (mark those "unsure"); the
orchestrator verifies and filters. Re-read every specification item, CLAUDE.md invariant and provider
page you cite rather than recalling it.

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

## Output format

One line per finding:

    [Blocker|Major|Minor|Nit] <file>:<line> - <group> - <problem> (<item ID> if any). Why: <one sentence>. Fix: <concrete change>

Then one line per group, `clean` or `<n> findings`. Blocker and Major classes:
`references/terraform-practices.md` section 5.
