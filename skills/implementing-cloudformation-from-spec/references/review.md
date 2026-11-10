# Review instructions (Claude stage, CloudFormation)

Each Claude-stage subagent reads this file and applies it to the change it was given: the IAM and
exposure reviewer (`implement-from-spec:iac-security-reviewer`) covers groups 4 and 5, the general
reviewer covers the rest, and each reports the groups it was not given as "not mine". Edit nothing.
Report every finding you see, minor and uncertain ones included (mark those "unsure"); the
orchestrator verifies and filters, so a finding you hold back is lost. Re-read every specification item
and Template Reference page you cite rather than recalling it.

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
set was inspected, its JSON under `ai-planning/` and the result of `rules/change-set-replacement.guard`.
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

## Blocker classes

A stateful resource that can be deleted or replaced by this change without a recorded ruling; secrets exposed; an item's interface
not realised or renamed; IAM wildcards without accepted reason; a removed or renamed export still imported;
a change that cannot deploy (quota, short-form LanguageExtensions function, invalid property); red validation.

## Output format

One line per finding:

    [Blocker|Major|Minor|Nit] <file>:<line> - <group> - <problem> (<item ID> if any). Why: <one sentence>. Fix: <concrete change>

Then one line per group, `clean` or `<n> findings`. A finding names the exact change: "Add
`UpdateReplacePolicy: Retain` beside `DeletionPolicy: Retain` on `OrdersTable` (infra/data.yaml:88)", not
"consider protecting the table".
