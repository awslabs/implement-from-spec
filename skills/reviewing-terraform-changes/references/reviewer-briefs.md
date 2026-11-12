# Reviewer briefs (Terraform)

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
- Terraform code reviewer
- Terraform security reviewer
- CloudFormation or CDK security hand-off

## Every reviewer

Never run terraform (init, fmt, validate, plan, apply, test, import or state), tflint, checkov or an aws
command: the main conversation runs the quality gate. Never open a *.tfstate* file or a real *.tfvars
file.

- Plan output: the `terraform plan` output in `<DIR>/input/` (pasted or run with the user's approval)
  when there is one; otherwise none
- Ledger: with an approved plan `ai-planning/<slug>.plan`, its ledger `ai-planning/<slug>.ledger.md`, when
  it exists, holds the Rulings that settle destroys and replacements, and the plan outputs it records

Read ${CLAUDE_PLUGIN_ROOT}/skills/implementing-terraform-from-spec/references/review.md and apply all of
it, with the defaults and severity classes in terraform-practices.md beside it. Read
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-terraform-changes/references/review-dimensions.md, its "How to
apply" first, and apply the checks it assigns to your check groups. The next section of this brief adds
what your role applies besides. The project's policy, its specification and the plan override those
defaults and the files the next section names; a deviation the project prescribes is not a finding.
Without a plan or specification, the group rule in this brief's section "3. Check groups without a plan
or specification" applies. Re-read every item, invariant and provider page you cite. Answer in the
findings format above (contract section 9), which replaces review.md's output format: findings outside
your check groups as out-of-lens head lines only, and the `Groups:` closing line giving every group of
review.md (`not assigned` for the others).

## Terraform code reviewer

Your check groups: 1, 2, 5, 6 and 7; write "not assigned" for the others.

Apply ${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md inside group 6
(Invariants).

## Terraform security reviewer

Your check groups: 3 and 4; write "not assigned" for the others.

## CloudFormation or CDK security hand-off

You are the security hand-off for the CloudFormation templates or CDK code in this change (contract
section 9): review the paths the hand-off reason in this brief names. Your check groups: groups 4 (IAM)
and 5 (Secrets and data exposure) of
${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/references/review.md for templates, or
of ${CLAUDE_PLUGIN_ROOT}/skills/implementing-cdk-from-spec/references/review.md for CDK code, on those
paths; write "not assigned" for the others. On those paths that review file replaces the one the section
above names.
