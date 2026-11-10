# Review instructions (Claude stage, AWS CDK)

The Claude-stage subagent reads this file and applies the check groups its brief assigns to the change set
it was given. Edit nothing. Report every finding you see, minor and uncertain ones included (mark those
"unsure"); the orchestrator verifies and filters, so a finding you hold back is lost. Re-read every
specification item, CDK API page and Template Reference page you cite rather than recalling it.

Precedence: the project's rules, the specification items and the approved plan override the defaults in
`cdk-practices.md`; a deviation the project prescribes is not a finding.

Plan scope: what the approved plan explicitly leaves out is the agreed scope, not a finding against the
change. That covers a stated exclusion ("the stack adds no bucket policy"), a `## Deferred` record, a
check the plan or ledger hands to the operator (a change-set diff, a pre-deploy check), and the
plan-local `SPEC-PLAN-n` items restated from an `ai-planning/` feature spec (contract section 2), which
need no specification entry of their own. A hardening the plan excludes is at most a Nit or a question;
an operator check is *needs runtime verification*. The one exception is a binding rule: when the
project's CLAUDE.md, its specifications index or a specification item requires what the plan leaves out
(for example a same-change specification update or the promotion of plan-local items), report it with
that rule quoted and the file the change lacks, because a plan cannot waive a binding rule. Before
reporting it, check that the change really lacks it.

## Inputs

The change set (a git diff command or a file list), the approved plan path, the specification files in
scope, the cdk-nag and validation output of the last `cdk synth`, the synthesised templates under
`cdk.out/`, and `cdk-practices.md` next to this file. The brief also names the CDK review dimensions
file, whose checks deepen the groups below, and, for the code reviewer, the shared principles file and
the app code's language review files.

## Checks

Walk every group you own and write "clean" for a group with no finding, so the reader can trust the
silence.

1. **Specification fidelity**: every item in the plan's Scope is realised as its `Interface:` names it
   (stack IDs, construct IDs, names, values); anything the change adds that no item asks for; acceptance
   criteria with no assertion test, nag rule or template rule
2. **Data safety and logical IDs**: a changed construct ID or construct-tree path of an existing resource
   (compare the logical IDs in the plan's inventory with `cdk.out`); stateful resources without an
   explicit removal policy, or without both `DeletionPolicy` and `UpdateReplacePolicy` in the synthesised
   template; a property change on an existing resource whose update behaviour is Replacement; `DESTROY` or
   `autoDeleteObjects` on data the items keep; deletion protection missing
3. **Cross-stack contract**: values consumed or published under names that differ from the owner's
   specification; an export removed or changed while imported; a strong cross-stack reference the
   project's pattern avoids
4. **IAM**: wildcard actions or resources without the reason the items accept; hand-written policies
   where a `grant*` method exists; action names that may not exist (say "verify in the service
   authorization reference"); trust policies broader than the caller; hard-coded partition, Region or
   account
5. **Secrets and data exposure**: secrets in context, props, environment variables, literals or Outputs;
   public access paths the items do not allow; encryption weaker than the items require; cdk-nag
   acknowledgements without a reason or at app scope
6. **CDK mechanics**: constructs created outside a stack's scope; environment-dependent lookups without a
   committed `cdk.context.json` where the pipeline synthesises without credentials; physical names on
   resources that may need replacement; a new dependency the plan does not name, or one without an exact
   version
7. **Tests**: assertions too loose to fail if the resource lost the property under test (empty or
   `Match.any_value()` matchers where other resources of that type remain; `resource_count_is` /
   `resourceCountIs` is one remedy), snapshot tests as the only proof of a behaviour, tests that do not cite their item
   ID, characterisation tests missing for logical IDs the plan pins
8. **Deploy path**: replacement evidence taken from a `--method template` diff, a missing whole-app
   change-set diff behind a claim that nothing else changes, a `cdk refactor` mixed into the same change as
   resource changes

## Blocker classes

A stateful resource that can be deleted or replaced by this change (including through a changed construct
ID); secrets exposed; an item's interface not realised or renamed; IAM wildcards without accepted reason;
a removed or renamed export still imported; a change that cannot synthesise or fails validation; red
tests; an unplanned dependency.

## Output format

One line per finding:

    [Blocker|Major|Minor|Nit] <file>:<line> - <group> - <problem> (<item ID> if any). Why: <one sentence>. Fix: <concrete change>

Then one line per group, `clean` or `<n> findings`. A finding names the exact change: "Keep construct ID
`UploadsBucket` on the bucket in `infra/storage_stack.py:21`; the new ID changes logical ID
`UploadsBucketXXXXXXXX` and replaces the bucket", not "consider keeping the ID".
