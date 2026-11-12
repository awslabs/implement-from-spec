# Reviewer briefs (CloudFormation)

The text of the Claude reviewers' briefs. `${CLAUDE_PLUGIN_ROOT}/core/scripts/review-prepare.py` writes
one brief per reviewer to `<DIR>/briefs/<reviewer>.md`: its fixed text (the read-only rule, the isolation
note, the repository, the review snapshot and `<DIR>`, the change mode, the changed files, the plan, the
specification files, `<DIR>/policy/`, the risk, the manifest's `assign` line, a security hand-off's
reason, the precedence rule, the order of reading and the findings format of contract section 9), then
the sections `references/dispatch.json` lists for that reviewer, copied verbatim with
`${CLAUDE_PLUGIN_ROOT}` and `<DIR>` filled in: the sections below and section 3 of
`references/standalone-review.md`, the group rule without a plan or specification. The manifest names
each section by its exact heading: renaming a heading here means changing the manifest in the same edit.
Edit this file to change what a reviewer is told; never rewrite a brief the preparation wrote.

## Contents

- Every reviewer
- Code reviewer
- IaC security reviewer
- Terraform security hand-off

## Every reviewer

Never run cfn-lint, cfn-guard, a test or an aws command: the main conversation runs the quality gate.

- CloudFormation change set: the `describe-change-set` JSON file in `<DIR>/input/` when the user
  supplied one; otherwise none
- Ledger: with an approved plan `ai-planning/<slug>.plan`, its ledger `ai-planning/<slug>.ledger.md`, when
  it exists, holds the Rulings that settle replacements. Without a ledger (a standalone review), a
  replacement or a deleting removal with no ruling is a finding

Read ${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/references/review.md and apply all
of it, with the defaults in cloudformation-practices.md beside it. Read
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-cloudformation-changes/references/review-dimensions.md, its "How
to apply" first, and apply the sections it assigns to your check groups. The next section of this brief
adds what your role applies besides. The project's policy, its specification and the plan override those
defaults and the files the next section names; a deviation the project prescribes is not a finding.
Without a plan or specification, the group rule in this brief's section "3. Check groups without a plan
or specification" applies. Re-read every item, invariant and Template Reference page you cite; mark a
property, update behaviour or IAM action you have not verified "verify in the Template Reference" or
"verify in the service authorization reference". Answer in the findings format above (contract section
9), which replaces review.md's output format: findings outside your check groups as out-of-lens head
lines only, and the `Groups:` closing line giving every group of review.md (`not mine` for the others).

## Code reviewer

Your check groups: 1, 2, 3, 6, 7 and 8; write `not mine` for the others on the `Groups:` line.

Apply ${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md inside groups 3 and 6, where
the stack-design sections land.

## IaC security reviewer

Your check groups: 4 (IAM) and 5 (Secrets and data exposure); write `not mine` for the others on the
`Groups:` line.

## Terraform security hand-off

You are the security hand-off for the Terraform files in this change (contract section 9): review the
paths the hand-off reason in this brief names. Your check groups: groups 3 (IAM) and 4 (Exposure and data
protection) of ${CLAUDE_PLUGIN_ROOT}/skills/implementing-terraform-from-spec/references/review.md, on
those paths; write "not mine" for the others. On those paths this review file replaces the one the
section above names.
