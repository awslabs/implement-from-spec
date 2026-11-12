# CDK review: change modes, synthesis, quality gate, severity and rollback

What the review skill adds to `implementing-cdk-from-spec`'s `review.md`, `cdk-practices.md` and
`review-focus.md` (read in place under `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cdk-from-spec/references/`;
this file does not restate them). It applies standalone and when the implementing skill calls the
review. The snapshot, the review state and the fix rounds are contract section 9 and SKILL.md steps 1, 5
and 6.

## Contents

1. What counts as a CDK change
2. Synthesis, read-only
3. Read-only checks (the quality gate)
4. Severity classes
5. Rollback evidence

## 1. What counts as a CDK change

- In scope: constructs, stacks, the app entry point, tests, `cdk.json`, committed `cdk.context.json`,
  the dependency files (`requirements*.txt`, `pom.xml`) and cdk-nag acknowledgements. No change in those:
  say so and stop
- No `cdk.json`: not a CDK app; for plain templates point to `reviewing-cloudformation-changes`, and stop
- Read `cdk.json` (the `app` command, context, feature flags), `cdk.context.json` when committed, the
  dependency files and the app entry point, and name the app's language and the stacks the change
  touches. A CDK app in a language other than Python or Java gets the CDK groups and the template checks;
  its language-level review follows the project's own rules, and the report says so
- Change modes map to the snapshot's and the external script's arguments exactly as SKILL.md step 1 lists
  them. For a pull request: the user checks out the branch; the range is
  `$(git -C <repo> merge-base <target> HEAD)..HEAD` with `<target>` the branch the PR merges into. Never
  fetch, pull or check out a branch yourself
- Without a plan or specification the review still runs: group 1 checks the change against the project's
  policy and what the change claims (commit messages, PR text, names and comments, read after the code)
- Lambda handler code the change bundles is application code: when the change alters a handler beyond a
  line or two, say so in the report and offer `reviewing-python-changes` or `reviewing-java-changes` for
  it

## 2. Synthesis, read-only

The IaC security reviewer reads the synthesised templates; the code reviewer, the Terraform hand-off and
the runner do not. So the main conversation synthesises right after it has dispatched those three (SKILL.md
step 2, wave 1), into the review's scratch directory `<work>` (SKILL.md step 1), copies the assembly and
the output into the snapshot directory, where the isolation hook lets reviewers read, and dispatches the
security reviewer (wave 2) as soon as the synthesis has ended and been recorded:

    <Python: the project's virtual environment first on PATH, and PYTHONDONTWRITEBYTECODE=1>
    cdk synth --quiet --lookups=false --output <work>/change.out > <work>/cdk-synth.txt 2>&1
    python3 -I "${CLAUDE_PLUGIN_ROOT}/core/scripts/review-snapshot.py" attach <DIR> --to synth/change.out \
        --from <work>/change.out
    python3 -I "${CLAUDE_PLUGIN_ROOT}/core/scripts/review-snapshot.py" attach <DIR> --to gates/cdk-synth.txt \
        --from <work>/cdk-synth.txt

The synthesis never writes into `<DIR>` itself: in the implementing skill's gated session the approval
gate denies every write there (the snapshot is written only by the plugin's scripts), so a `--output`
under `<DIR>` would leave the security reviewer without templates. `attach` copies the templates, the
manifests and the tree, not CDK's `asset.<sha256>` staging (the reviewers read that code in the repository), and
never replaces what it attached.

- `--lookups` and `--output` are global CDK CLI options: "Synthesis will fail if this value is `false`
  and context lookups need to be performed", and `--output` names "the directory to output the
  synthesized cloud assembly to" (https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd.html). When a
  lookup is missing from `cdk.context.json`, ask the user whether to allow it (it reads the account with
  the lookup role and writes `cdk.context.json`, `cdk-practices.md` section 7); without a yes, review
  without the synthesised templates and say "synthesised template not reviewed"
- Synthesis runs the registered validation plugins (the default CloudFormation validation plugin, and
  cdk-nag when the app registers it). The whole output, attached as `<DIR>/gates/cdk-synth.txt`, is for
  the security reviewer and the triage; record it as the gate `cdk-synth`. A synth that runs and fails, or a validation
  violation, is a red gate. A synth that cannot start because the CDK CLI or the app's dependencies are
  missing is "not run (<reason>)": never green, never fixed by installing anything, and verification is
  incomplete
- For committed changes, synthesise `<b>`, not the working tree: extract it with
  `git -C <repo> archive <b> | tar -x -C <tmp>/b` (`<tmp>` a new `mktemp -d` directory) and synthesise
  there with the same `--output`
- A synth that writes in the repository (bytecode, an unignored build directory) changes the candidate,
  and `record-gate` refuses its result with exit 3. Synthesise from a copy of the tree instead
  (`tar -C <repo> --exclude ./cdk.out --exclude ./.git -cf - . | tar -C <tmp>/w -xf -`) and say so in
  the report line

## 3. Read-only checks (the quality gate)

Run from the main conversation while the stages work, from the app root on the tree section 2
synthesised; the reviewers never run them. Write each output to `<work>/<name>.txt` and attach it as
`<DIR>/gates/<name>.txt`:

    <Python> python -m pytest            <Java> mvn compile && mvn test   (or the project's wrapper)
    cfn-lint <DIR>/synth/change.out/*.template.json                       when installed or the project uses it
    cfn-guard validate --rules <the project's rules> --data <DIR>/synth/change.out --show-summary fail   when the project has rules
    cfn-validate <DIR>/synth/change.out/                                  optional

- **Blocking checks, recorded with `record-gate`**: `cdk-synth` (with its validation plugins) and
  `tests`. Red tests, a failed synth or a validation violation are a red gate. Both are required: one
  that could not run (a missing toolchain, a sandbox that blocks it, a download declined) is reported as
  not run with its reason, never as clean and never as `fail`, and recorded so:
  `python3 -I "${CLAUDE_PLUGIN_ROOT}/core/scripts/review-snapshot.py" record-gate <DIR> --name tests
  --status not-run --command "<the command that could not run>" --reason "<why, one line>"`. `state`
  then reports verification incomplete with `<name> not run: <reason>`, never Blocked by itself. A result
  recorded by mistake stays in `gates.json`: record the right one after it (`state` reads each name's
  latest result), never edit, rewrite or delete the file. Nothing is installed to make a check run. Maven downloads what a build needs (`cdk-practices.md` section 9): when
  the change adds or changes a `pom.xml` dependency, ask before the build
- **Advisory checks**: cdk-nag findings that do not fail synthesis, cfn-lint, cfn-guard and cfn-validate.
  Their findings go into the triage like a reviewer's, tagged *(tool)*; a missing optional tool is "not
  run: not installed", never "clean"
- **Logical-ID comparison.** Extract the base (`git -C <repo> archive <base> | tar -x -C <tmp>/base`),
  synthesise it into `<work>/base.out` with the same command and environment, attach it as
  `<DIR>/synth/base.out`, and compare, per
  stack template, the `Resources` keys and their `Type`. A resource of a stateful type whose logical ID
  disappeared while one of the same type appeared is a changed construct ID or path: CloudFormation
  creates a new resource and deletes the old one (`cdk-practices.md` section 3). The comparison yields
  candidates for triage, tagged *(tool)*; it is not replacement evidence. When the base cannot be
  synthesised, say so and rely on the plan's inventory and the diff
- **Change-set diff, only with approval.** The replacement evidence is
  `cdk diff <stack> --method change-set --exclusively` per changed stack, then `cdk diff --method
  change-set` for the whole app (`implementing-cdk-from-spec` SKILL.md section 6). It creates a change set
  with the deploy role (`cdk-practices.md` section 10), so it runs only after the user explicitly approves
  that exact command in this conversation, with the account and profile the project's rules name. This
  skill has no approval gate of its own: ask in plain text and wait; when the implementing skill's gate
  is active, its command rules ask too. From `implementing-cdk-from-spec`, the diffs its section 6 ran
  after the last edit and recorded in the ledger are the evidence instead. Without either: "Replacement
  evidence: not run (cdk diff creates a change set with the deploy role; not approved)". A
  `--method template` diff is never replacement evidence
- **Never in this skill**: `cdk deploy`, `destroy`, `bootstrap`, `import`, `watch`, `orphan`,
  `publish-assets`, `cdk refactor` without `--dry-run`, or a mutating `aws` call

## 4. Severity classes

The main conversation sets severity from the code and the synthesised template, never from a reviewer or
a tool.

- **Blocker**: the Blocker classes of `review.md` (a stateful resource that this change can delete or
  replace, including through a changed construct ID; secrets exposed; an item's interface not realised or
  renamed; IAM wildcards without an accepted reason; a removed or renamed export still imported; a change
  that cannot synthesise or fails validation; red tests; an unplanned dependency), plus public access or
  missing encryption on data the items or the project's rules keep private
- **Major**: a real problem that does not block the merge, such as a hand-written policy where a `grant*`
  method exists, a stateful resource whose removal policy is only the construct default, deletion
  protection missing where the resource has it, a snapshot test as the only proof, a missing or weakened
  characterisation test for a pinned logical ID, a cdk-nag acknowledgement without a reason or wider than
  one construct, a deprecated property, a test that cites no item
- **Minor**: worth fixing in this change if quick
- **Nit**: optional polish
- A finding attributed to the base keeps its class under *Pre-existing* (SKILL.md step 4); it is outside
  the recommendation, and a pre-existing Blocker carries an escalation note

## 5. Rollback evidence

The report's `Rollback:` line rests on the synthesised templates and the change-set diff, never on the
author's word, and states code rollback and data recovery separately: reverting the app and deploying
again restores configuration, not the data a replacement or a deleting removal destroyed. A report never
says the change replaces or deletes nothing unless an approved change-set diff showed it: without one,
the replacement analysis rests on the logical-ID comparison and the Template Reference's update
behaviour, and the report says so.

- **Evidence that counts**: an approved change-set diff (resources marked replaced, `Replacement` `True`
  or `Conditional`, and removed resources); the logical-ID comparison; `DeletionPolicy` and
  `UpdateReplacePolicy` in the synthesised template of every stateful resource the change touches (from
  `removal_policy` / `removalPolicy`), `autoDeleteObjects` / `auto_delete_objects`, deletion protection,
  point-in-time recovery and backups; the Template Reference update behaviour of every changed property
- **not applicable**: the change alters no synthesised resource (tests only, documentation, a construct
  no stack instantiates yet), shown by an unchanged template comparison
- **supported (<evidence>)**: code: revert the app and the operator deploys the previous version (a failed
  deploy rolls back on its own); data: no stateful resource replaced or removed, shown by the change-set
  diff or by the logical-ID comparison plus the update behaviour of every changed property, and each
  touched stateful resource keeps `Retain` or `Snapshot` in both policies. Name the evidence, for example
  `supported (code: previous app version via the pipeline; data: change-set diff StorageStack, no
  replacement; UploadsBucket Retain/Retain)`. A change that only adds resources and changes no existing
  one is supported: a rollback removes the new resources, deleted with what was written to them after the
  deploy or retained outside the stack as their removal policy says, which is the inverse of the change,
  not stranded writes; say so in the evidence (`data: logical-ID comparison 2 added, 0 removed; a
  rollback deletes the new queue and its messages`). That revert is not a finding when the plan's
  rollback says how the new resources are removed, Minor at most when it is silent, and Major only when
  the items, the plan or the project's rules require that data to survive a rollback. A change that
  alters the shape of persisted data or a contract the previous version reads (a key, attribute or field
  moved, renamed, nested or retyped; an item, message, export or output format) is never additive, even
  when it also adds resources: it is judged under unsafe below
- **unsafe (<finding>)**: a finding shows a stateful resource replaced or removed whose policy deletes it,
  `DESTROY` or auto-delete on data the items keep, or a change whose revert strands writes made after it
  (the previous version cannot read data in a resource that survives the revert, or a revert deletes data
  that the items, the plan or the project's rules require to survive a rollback); name the F-number and
  the data recovery it needs (a snapshot or PITR restore, a backup), or "no recovery path" when none
  exists
- **unknown (<what settles it>)**: the change-set diff was not approved and a changed property's update
  behaviour is Replacement or Conditional, or a logical ID moved and the base could not be synthesised:
  name the operator's `cdk diff <stack> --method change-set` command
