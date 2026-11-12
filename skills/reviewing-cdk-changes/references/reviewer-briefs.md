# Reviewer briefs (AWS CDK)

The text of the Claude reviewers' briefs. `${CLAUDE_PLUGIN_ROOT}/core/scripts/review-prepare.py` writes
one brief per reviewer to `<DIR>/briefs/<reviewer>.md`: its fixed text (the read-only rule, the isolation
note, the repository, the review snapshot and `<DIR>`, the change mode, the changed files, the plan, the
specification files, `<DIR>/policy/`, the risk, the manifest's `assign` line, a security hand-off's
reason, the precedence rule, the order of reading and the findings format of contract section 9), then
the sections `references/dispatch.json` lists for that reviewer, copied verbatim with
`${CLAUDE_PLUGIN_ROOT}` and `<DIR>` filled in. The manifest names each section by its exact heading:
renaming a heading here means changing the manifest in the same edit. Edit this file to change what a
reviewer is told; never rewrite a brief the preparation wrote.

## Contents

- Every reviewer
- Code reviewer
- IaC security reviewer
- Terraform security hand-off

## Every reviewer

Never run cdk synth, cdk diff, cdk deploy, a test, a build or an aws command: the main conversation runs
the quality gate.

- App language and stacks touched: the language of the `app` command in `cdk.json` (Python, Java or
  other), and the stacks the changed paths belong to, from the app entry point
- Ledger: with an approved plan `ai-planning/<slug>.plan`, its ledger `ai-planning/<slug>.ledger.md`, when
  it exists, holds the Rulings that settle construct-ID changes and replacements. Without a ledger (a
  standalone review), a changed logical ID or a replacement with no ruling is a finding

Read ${CLAUDE_PLUGIN_ROOT}/skills/implementing-cdk-from-spec/references/review.md and apply all of it,
with the rules in cdk-practices.md beside it. Read
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-cdk-changes/references/review-dimensions.md, its "How to apply"
first, and apply the sections it assigns to your check groups. The next section of this brief adds what
your role applies besides. The project's policy, its specification and the plan override those defaults
and the files the next section names; a deviation the project prescribes is not a finding. Re-read every
item, CDK API page and Template Reference page you cite; mark a construct, property, update behaviour or
IAM action you have not verified "verify in the CDK API reference", "verify in the Template Reference"
or "verify in the service authorization reference". Answer in the brief's findings format, which replaces
review.md's output format: review.md's check groups are your lanes, a CDK- check ID goes in the line's
check-ID field, and the closing `Groups:` line names each check group of your review file once.

## Code reviewer

Your check groups: 1, 2, 3, 6, 7 and 8, and the app code's language review; write "not mine" for the
others.

You are dispatched before synthesis, so the review is not held up by it: read the construct code, the
tests, the plan and the specification, never `<DIR>/synth/` or `<DIR>/gates/` (they are not written yet;
do not wait or look for them). Where review.md or review-dimensions.md reads a property in the
synthesised template (a logical ID, `DeletionPolicy` and `UpdateReplacePolicy`, an export, a resolved
value), derive it from the code (the construct path and ID, an explicit `removal_policy`, the construct's
documented default, an aspect) and end the finding's Evidence (a Minor's or Nit's Why) with "verify in
template": the main conversation checks it there and runs the logical-ID comparison with the base.

Apply ${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md inside group 6 (CDK
mechanics, which includes construct design). For the app's own code and tests, also apply, for Python,
lenses 3 (types and design) and 5 (tests) of
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-python-changes/references/review-lenses.md with the groups
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-python-changes/references/review-dimensions.md assigns to those
lenses and cdk-practices.md section 8; for Java, the groups of
${CLAUDE_PLUGIN_ROOT}/skills/reviewing-java-changes/references/review-dimensions.md that report under
Correctness, Design and Readability, with cdk-practices.md section 9. Your `Groups:` line includes
`App code=clean|<n>`.

## IaC security reviewer

Your check groups: 4 (IAM) and 5 (Secrets and data exposure); write "not mine" for the others.

You are dispatched as soon as synthesis ends, so read the synthesised policies and resources beside the
construct code:

- Synthesised templates: `<DIR>/synth/change.out/*.template.json`. When that directory holds no template,
  the app was not synthesised: `<DIR>/gates/cdk-synth.txt` gives the reason; review from the code and
  say "synthesised template not reviewed: <reason>" on your Could not complete line
- Synth, validation and cdk-nag output: `<DIR>/gates/cdk-synth.txt`

## Terraform security hand-off

You are the security hand-off for the Terraform files in this change (contract section 9): review the
paths the hand-off reason in this brief names. Your check groups: groups 3 (IAM) and 4 (Exposure and data
protection) of ${CLAUDE_PLUGIN_ROOT}/skills/implementing-terraform-from-spec/references/review.md, on
those paths; write "not mine" for the others. On those paths this review file replaces the one the
section above names.
