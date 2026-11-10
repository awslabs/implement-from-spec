# CloudFormation review dimensions

Design, coupling, update-safety and operability checks for CloudFormation changes (YAML or JSON templates,
nested stacks, StackSets, the SAM and LanguageExtensions transforms), each observable in a diff. The
Claude-stage reviewers apply them inside the check groups of
`${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/references/review.md`; they add depth,
they do not replace those groups. Precedence: the project's rules (CLAUDE.md), its specification items, the
approved plan and the ledger's Rulings override every default here; a deviation the project prescribes is
not a finding. Facts below were read on 2026-10-16 (pages and tool versions in the plugin's provenance
note); re-read a cited page before a finding depends on it, above all a limitation the page itself calls
release-specific.

## Contents

- How to apply
- 1. Stack decomposition and coupling (CFN-STK)
- 2. Parameters, mappings and conditions (CFN-PAR)
- 3. Template mechanics and intrinsic functions (CFN-TPL)
- 4. Reuse: nested stacks, modules, macros, StackSets and SAM (CFN-REU)
- 5. Update safety and data lifecycle (CFN-UPD)
- 6. Custom resources (CFN-CR)
- 7. Deploy path, drift and stack guardrails (CFN-OPS)
- 8. IAM in templates (CFN-IAM)
- 9. Secrets and data exposure (CFN-SEC)
- 10. Tests, rules and suppressions (CFN-TST)
- 11. Out of scope / handled elsewhere
- Sources

## How to apply

The language-neutral principles and architecture smells (DRY, KISS, YAGNI, cohesion and coupling, layer
skipping, cyclic and unstable dependencies, hub-like and god components, hidden coupling, leaking
abstractions) are defined once in `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`.
This file gives their CloudFormation manifestation only; a check that is the stack form of a shared entry
names it ("stack form of ARC-04"), and a finding that rests on it puts the shared ID after the group, as
that file's "How to apply" section shows.

Evidence rule. Every finding names the changed line, the repository or specification evidence it rests
on, and its assumptions. A diff cannot show deployed state (live importers, account defaults, which
stacks are ephemeral, how often a stack is redeployed): where the finding depends on it, report it
"unsure, needs runtime verification" with the command the operator runs, and never assign a destructive
outcome from absence in the repository alone. Several checks below are investigation prompts (said in the
check); they become findings only with a concrete consequence in this change.

Reviewer split, matching `review.md` and `skills/reviewing-cloudformation-changes/SKILL.md` step 2:

- **`implement-from-spec:code-reviewer`** (review.md groups 1 to 3 and 6 to 8): sections 1 to 7 and 10
  of this file. Sections 1 and 4 land in group 3 (Cross-stack contract) or group 6 (Template mechanics);
  section 2 and 3 in group 6; section 5 in group 2 (Data safety); section 6 in group 6, except
  CFN-CR-05, which belongs to the security reviewer; section 7 in group 8 (Pipeline and deploy path);
  section 10 in group 7 (Tests and rules)
- **`implement-from-spec:iac-security-reviewer`** (review.md groups 4 and 5): sections 8 and 9, plus
  CFN-CR-05 and the IAM half of CFN-OPS-07. Its own checklist (`skills/iac-security-reviewer/SKILL.md`)
  supplies the depth; the checks here name the CloudFormation constructs and the linter rule IDs that
  make a finding concrete
- A check outside a reviewer's sections that it happens to see is reported in one line and left to the
  owner, as `skills/code-reviewer/SKILL.md` says. Report each finding in review.md's output format with the
  check ID in the problem text, for example `[Major] infra/app.yaml:42 - 6 Template mechanics -
  CFN-TPL-01 hard-coded account in role ARN ...`

Severity classes. The main conversation sets the final severity from
`skills/reviewing-cloudformation-changes/references/standalone-review.md` section 4; the defaults below are
consistent with it.

- **Blocker**: data loss or exposure, or a change that cannot deploy: a stateful resource deleted or
  replaced with no ruling, a removed or renamed export still imported, a secret in a parameter default,
  literal or output, an `Allow` with an IAM wildcard or a `Principal: "*"` that no condition narrows,
  with no accepted reason (a protective `Deny` with `Principal: "*"` is not one), a construct
  CloudFormation rejects, red validation
- **Major**: a defect that will bite on a later update or in another account, Region or environment:
  hard-coded partition, Region or account, missing data-protection policies or deletion protection where
  no project rule requires them, an unstable cross-stack contract, a custom resource that can hang or
  delete on update, an unconstrained string parameter
- **Minor**: worth fixing in this change if quick: redundant `DependsOn`, unused parameters, a missing
  description, a duplicated block that a parameter or mapping would remove
- **Nit**: optional polish (`Fn::Sub` over `Fn::Join`, ordering, naming style)

Per-check severities assume no Blocker class of `review.md` applies. A verified deployment rejection, an
exposed secret, an unaccepted IAM wildcard or a failed required validation overrides a lower default. A
tool rule ID alone does not prove the impact when the tool did not run.

## 1. Stack decomposition and coupling (CFN-STK)

### CFN-STK-01 God template mixing lifecycles

- **Look for:** one template that gains resources with different lifecycles or owners (VPC and subnets,
  a database, and application functions in one stack); a stateful resource added to a stack that is
  redeployed on every application change; cfn-lint I3010 or I1002 (approaching the resource or size
  quota)
- **Why it matters:** every routine application update then puts the data store inside the same change
  set, rollback and replacement analysis; stack form of ARC-04 (god component). An investigation prompt:
  cohesion and single ownership can justify one stack
- **Instead:** split by lifecycle and ownership into layered stacks, the data layer below the application
  layer; move existing resources with stack refactoring after checking its eligibility (it refuses
  stacks with a stack policy, and resources whose pseudo-parameter values differ between source and
  destination), not by delete and re-create
- **Severity:** Major when the change forces independently owned resources into one coordinated
  deployment or puts a stateful resource in a stack the project redeploys with every application
  change; Minor otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "as your
  stack grows in scale and broadens in scope, managing a single stack can be cumbersome and time
  consuming"; cfn-lint I3010, I1002; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stack-refactoring.html —
  "Stack refactor doesn't support stacks that have stack policies attached, regardless of what the
  policies allow or deny"

### CFN-STK-02 Over-split nested stacks

- **Look for:** a new `AWS::CloudFormation::Stack` that holds one or two resources; a parent that passes
  most of its parameters straight through to children; output-to-parameter chains three or more levels
  deep; a `CommaDelimitedList` parameter passed to a nested stack
- **Why it matters:** each boundary adds parameter plumbing and update work, and the nested stack still
  updates with its parent, so a boundary that is not a reuse, privilege or ownership unit buys little;
  stack form of SML-07 (speculative generality) and SML-10 (middle man). Size alone is an investigation
  prompt
- **Instead:** keep cohesive resources in one template; nest only a reusable unit with its own
  interface; pass lists to a nested stack as a `String` and split inside
- **Severity:** Minor; Blocker when a `CommaDelimitedList` is passed by `Ref` or E3043 reports missing
  nested-stack parameters (cannot deploy, review.md Blocker class)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html —
  "If the template includes one or more nested stacks, CloudFormation also initiates an update for every
  nested stack"; https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-stack.html —
  "you can't pass values that are of type `CommaDelimitedList` to nested stacks"; cfn-lint E3043

### CFN-STK-03 Upward or cyclic stack dependency

- **Look for:** a lower-layer stack (network, data, security) gaining `Fn::ImportValue` or an SSM lookup
  of a value an application stack publishes; two stacks importing from each other; a nested child
  reading its parent's exports
- **Why it matters:** the layering inverts, so the foundation cannot be created or replaced without the
  layer that depends on it; a cycle between exports cannot be created from scratch in a new account
- **Instead:** move the value to the lower layer or to a third, lower stack both depend on; pass
  values down through parameters
- **Severity:** Major; Blocker when the cycle prevents creating the stacks from an empty account the
  specification targets
- **Source:** stack form of ARC-02 (broken layering) and ARC-03 (cyclic dependencies);
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "A
  layered architecture organizes stacks into multiple horizontal layers that build on top of one
  another, where each layer has a dependency on the layer directly below it"

### CFN-STK-04 Export of an unstable value

- **Look for:** a new `Outputs.*.Export` whose value belongs to a resource the change or the plan is
  likely to replace (a Lambda version ARN, an instance ID, a resource whose replacement-only properties
  the project changes), or an export added "for later" with no importer. A generated ID is not unstable
  by itself: VPC and subnet IDs are common, legitimate export contracts
- **Why it matters:** once imported, the export can neither change nor be deleted, so replacing the
  resource behind it fails the update; stack form of ARC-20 (incompatible boundary evolution), and a
  lock-in on the producer
- **Instead:** export stable identifiers only (an alias ARN, a name the project pins); prefer the
  project's registry mechanism for values that change; add an export only when a consumer exists
- **Severity:** Major when a replacement of the producer is planned or likely; Minor for an export with
  no consumer
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html —
  "After another stack imports an output value, you can't delete the stack that is exporting the output
  value or modify the exported output value"

### CFN-STK-05 Export removed, renamed or changed while imported

- **Look for:** a resolved `Export.Name` or exported value changed or deleted while any template in the
  repository still has a matching `Fn::ImportValue`; compare the resolved name and value before and after.
  Renaming only the output's key leaves the export as it was; it matters to consumers of that key (a
  nested-stack `!GetAtt Child.Outputs.X`, a `Fn::GetStackOutput`), not to importers. A change that
  updates producer and consumers in one commit still needs a deploy order the pipeline enforces
- **Why it matters:** the producer's update fails, or the consumer breaks on its next update; stack
  form of ARC-20
- **Instead:** expand and contract: add the new export beside the old one, move every importer, then
  remove the old export in a later change (sequence is community practice; the restriction is AWS's)
- **Severity:** Blocker (review.md Blocker class); with no importer in the repository, or when importers
  outside the repository may exist, "unsure, needs runtime verification" with
  `aws cloudformation list-imports --export-name <name>` in the producer's account and Region
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html —
  "All the imports must be removed before you can delete the exporting stack or modify the output value"

### CFN-STK-06 Export naming

- **Look for:** an `Export.Name` without the stack name or the project's prefix; an `Export.Name` or
  `Fn::ImportValue` argument that uses `Ref` or `Fn::GetAtt` of a resource
- **Why it matters:** export names are unique per account and Region, so an unprefixed name collides when
  the template is deployed twice; a resource-dependent name is rejected
- **Instead:** `Name: !Sub '${AWS::StackName}-VpcId'` or the project's pinned name
- **Severity:** Minor for the prefix; Blocker for a resource-dependent name (cannot deploy; cfn-lint E1016)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html —
  "the value of the `Name` property of an `Export` can't use `Ref` or `GetAtt` functions that depend on a
  resource"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "you can
  use the `AWS::StackName` pseudo parameter to create a prefix for your export"

### CFN-STK-07 Weak reference through Fn::GetStackOutput

- **Look for:** a new `Fn::GetStackOutput` (or `!GetStackOutput`), above all one that replaces an
  existing `Fn::ImportValue`; one placed directly in `Outputs`, inside an `Fn::Sub` variable map,
  `Fn::Base64`, `Fn::ImportValue` or a `Conditions` `Fn::Equals`; the short form wrapping other short
  forms (`!GetStackOutput` with `StackName: !Ref ...`); a cross-account `RoleArn` whose role trusts more
  than the consumer's execution role
- **Why it matters:** the reference is weak: the producer can change or delete the output and the
  consumer is not told, so the producer can make an ARC-20 incompatible change unseen (PRN-16, explicit
  over implicit); the listed positions are
  documented as returning `InternalFailure` "in this release"
- **Instead:** keep `Fn::ImportValue` where same-account, same-Region referential integrity is wanted;
  use `Fn::GetStackOutput` for cross-account or cross-Region values, directly as a property value or
  inside `Fn::Join`, `Fn::If` or `Fn::Select`, in the long form when it contains other functions, and
  protect the producer's output
- **Severity:** Major when it removes referential integrity with no recorded decision; Blocker in a
  position the current page still lists as unsupported (cannot deploy; re-read the page, since it says
  support "will be added in a future update"). cfn-lint E1033 validates the function's configuration;
  whether it reports these positions is unverified
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getstackoutput.html —
  "If the referenced stack or output is later deleted or modified, the consuming stack is not
  automatically updated or notified"; Known limitations: "The following usage patterns are not supported
  in this release. All return an `InternalFailure` error"; "You can't use the short form of
  `!GetStackOutput` when it contains other short form functions" (read 2026-10-16); cfn-lint E1033
  ("Making sure the GetStackOutput function is properly configured")

### CFN-STK-08 Hard-coded physical IDs of another stack's resources

- **Look for:** literal `vpc-`, `subnet-`, `sg-`, `arn:` or bucket-name values of resources another stack
  in the project owns, in template properties or parameter defaults; a second cross-stack mechanism
  beside the one the project uses. A per-environment parameter file naming an external resource the
  project does not manage is configuration, not this finding
- **Why it matters:** the template only works in the account it was written against and silently points
  at the wrong resource after the producer is replaced; stack form of ARC-17 (module API bypassed) and
  ARC-15 (configuration sprawl)
- **Instead:** the project's mechanism (exports or the SSM registry); one mechanism per project
  (practices section 4)
- **Severity:** Major for a hidden literal in a reusable template; Minor in a parameter file for a
  resource the project owns
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "You can
  hardcode values or use input parameters to pass resource names and IDs. However, these methods can
  make templates difficult to reuse"

### CFN-STK-09 SSM parameter coupling without a contract

- **Look for:** a consumer that reads another stack's value through an `AWS::SSM::Parameter::Value<...>`
  parameter type or `{{resolve:ssm:...}}` with no owner named in the registry, or a producer that writes
  an `AWS::SSM::Parameter` other stacks read with no registry entry
- **Why it matters:** an SSM parameter type resolves the latest value at each stack operation, so the
  consumer takes whatever is current at its next update (a versioned dynamic reference stays on its
  version); the producer can delete the parameter freely, and drift detection does not see the
  reference: decoupled at deploy time, coupled at run time (stack form of ARC-11)
- **Instead:** declare every shared key once in the project's registry with its owner; version the
  reference where the project requires repeatable deploys
- **Severity:** Minor; Major when it introduces SSM coupling into a project whose mechanism is exports
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html —
  "CloudFormation retrieves the latest value from Parameter Store to use for the stack"; practices
  section 4 (dynamic references and drift)

### CFN-STK-10 Outputs that leak implementation or feed runtime

- **Look for:** outputs for every internal role, subnet or queue "just in case"; an output whose value is
  an `Fn::ImportValue` (cfn-lint W6001); application code or scripts in the change that call
  `describe-stacks` at run time to read outputs; a reusable nested child whose parameters expose
  implementation settings every caller must understand, or callers that rebuild a child's physical
  names instead of reading its outputs
- **Why it matters:** each output becomes an interface others start depending on (stack form of ARC-01,
  and PRN-09; rebuilt physical names are ARC-17), and AWS says output values "might not be available at all times"
- **Instead:** output only what the specification's interface names; give runtime configuration through
  environment variables, parameters or the registry
- **Severity:** Minor; Major for a runtime dependency on outputs in a production path
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html —
  "We don't recommend establishing dependencies between a service runtime and the stack output value
  because output values might not be available at all times"; cfn-lint W6001

## 2. Parameters, mappings and conditions (CFN-PAR)

### CFN-PAR-01 Parameter sprawl

- **Look for:** parameters for values the specification fixes; new parameters no item or environment
  needs to vary (a parameter every file leaves at its `Default` is a prompt to ask, not proof); a
  template approaching 200 parameters (cfn-lint I2010)
- **Why it matters:** each parameter widens the input space every deploy path can set and the tests
  must cover; unused variability hides the real configuration (stack form of ARC-15 and PRN-09;
  community consensus, with the quota from AWS)
- **Instead:** a literal or a `Mappings` entry for fixed values; parameters only for what differs between
  environments; keep an approved interface parameter even when one caller uses it today
- **Severity:** Minor
- **Source:** cfn-lint I2010; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html —
  "To make templates reusable, use the parameters, mappings, and conditions sections"

### CFN-PAR-02 Unconstrained or weakly typed parameter

- **Look for:** a `String` parameter with neither `AllowedValues` nor `AllowedPattern` (length limits
  alone do not meet practices section 3); a `String` used for a VPC, subnet, security group, key pair
  or AMI where an AWS-specific type exists (cfn-lint W2506 for `ImageId`); a cross-parameter invariant
  the items state with no `Rules` assertion; unquoted `Yes` and `No` in YAML `AllowedValues`
- **Why it matters:** an invalid value fails late, mid-update, instead of before any resource changes
- **Instead:** `Type: AWS::EC2::Subnet::Id`, `AllowedPattern`, `ConstraintDescription`, a `Rules`
  assertion for cross-parameter invariants
- **Severity:** Major for an unconstrained string (standalone-review section 4); Minor for a missing
  AWS-specific type or `Rules` entry
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html —
  "CloudFormation can quickly validate values for AWS-specific parameter types before creating your
  stack"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html —
  "use single-quotes to prevent the YAML parser from considering these boolean values"

### CFN-PAR-03 Magic strings and duplicated literals

- **Look for:** the same literal (an environment name, retention days, an instance class, a CIDR) repeated
  across resources; `Fn::Equals` comparing environment names spelled differently (`prod`, `Prod`,
  `production`); `Fn::Equals` of two literals (cfn-lint W8003)
- **Why it matters:** a change updates some copies and not others (DRY); a misspelt environment silently
  takes the non-production branch
- **Instead:** one parameter with `AllowedValues` and one condition per environment fact
  (`IsProduction`), or a `Mappings` table keyed by environment
- **Severity:** Minor; Major when a misspelt comparison changes protection or capacity in production
- **Source:** cfn-lint W8003; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/mappings-section-structure.html —
  "One common use case for the `Mappings` section is to set values based on the AWS Region"

### CFN-PAR-04 Mapping misuse

- **Look for:** a `Mappings` value containing `Ref`, a pseudo parameter or an intrinsic function; a
  Region-to-AMI mapping of literal image IDs; a change that edits only an unused mapping
- **Why it matters:** the first is rejected; literal AMI maps go stale; a change to a mapping the stack
  does not use cannot be deployed on its own (a change to a used mapping changes the resources that read
  it and deploys normally)
- **Instead:** literals only in mappings; AMIs through `AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>`
  on the public AMI parameters
- **Severity:** Blocker for an intrinsic inside `Mappings` (cannot deploy); Minor otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/mappings-section-structure.html —
  "You can't include parameters, pseudo parameters, or intrinsic functions in the `Mappings` section"
  and "If the values in a mapping aren't currently used by your stack, you cannot update the mapping
  alone"; cfn-lint E7001, W2506

### CFN-PAR-05 Condition that can delete an existing resource

- **Look for:** a `Condition:` added to, or changed on, a resource that already exists in deployed
  stacks; a condition's inputs changed (parameter, mapping) so it can now evaluate false for an existing
  environment; whole environment-specific resource sets toggled by conditions
- **Why it matters:** a resource whose condition becomes false is deleted on the next update, which for
  a stateful resource is data loss
- **Instead:** keep stateful resources unconditional, or protect them with `DeletionPolicy: Retain` and
  a ruling; prefer separate stacks over condition-heavy environment templates
- **Severity:** Blocker for a stateful resource with no ruling; Major otherwise; "unsure, needs runtime
  verification" when the repository cannot show which environments already hold the resource
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/conditions-section-structure.html —
  "Entities that remain associated with a true condition are updated, while those that become associated
  with a false condition are deleted"

### CFN-PAR-06 Condition mismatch between related resources

- **Look for:** an unconditional resource or output that `Ref`s or `GetAtt`s a conditional resource
  (cfn-lint W1001); an `Fn::If` branch that can never be taken (W1028); a condition-only change expected to
  deploy on its own
- **Why it matters:** an unconditional reference to a conditional resource works in the environment the
  author tested and fails in the other; a dead `Fn::If` branch is only noise; a condition-only change is
  rejected as an update
- **Instead:** the same condition on both, or `Fn::If [Cond, !Ref X, !Ref AWS::NoValue]`; delete dead
  branches; ship a condition change with the resource change it governs
- **Severity:** Major for W1001; Blocker when the failing environment is one the specification targets;
  Minor for W1028
- **Source:** cfn-lint W1001, W1028; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/conditions-section-structure.html —
  "During a stack update, you can't update conditions by themselves"

### CFN-PAR-07 Unused parameters, mappings and conditions

- **Look for:** declarations nothing references after the change (cfn-lint W2001, W7001, W8001), often
  left behind by a refactor
- **Why it matters:** dead inputs mislead operators and keep parameter files alive
- **Instead:** delete them with the code that used them
- **Severity:** Minor
- **Source:** cfn-lint W2001, W7001, W8001

## 3. Template mechanics and intrinsic functions (CFN-TPL)

### CFN-TPL-01 Hard-coded partition, Region or account

- **Look for:** `arn:aws:` literals (including AWS managed policy ARNs), 12-digit account IDs, Region
  names and endpoint `amazonaws.com` suffixes inside property values, policies or `Fn::Sub` strings.
  Not this finding: an account ID that deliberately names another account (cross-account trust, a
  central logging account), which `AWS::AccountId` would silently change into the deploying account;
  service principals in `Principal.Service`, whose form follows each service's documentation, not
  `AWS::URLSuffix`
- **Why it matters:** the template breaks in another partition, Region or account; cfn-lint I3042 checks
  only the partition by default (`region` and `accountId` options default to false in the rules
  catalogue read 2026-10-16), so a clean lint does not clear this
- **Instead:** `!Sub 'arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/x'`,
  `${AWS::URLSuffix}` for endpoints; enable I3042's region and account options in `.cfnlintrc`
- **Severity:** Major (standalone-review section 4)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "Instead
  of hard-coding these values, you can use `AWS::Partition`, `AWS::Region`, and `AWS::AccountId` pseudo
  parameters to make your template more portable"; cfn-lint I3042

### CFN-TPL-02 Hard-coded or index-selected Availability Zones

- **Look for:** literal `us-east-1a`-style values (cfn-lint W3010); `!Select [N, !GetAZs '']` feeding a
  property whose update behaviour is Replacement (a subnet's `AvailabilityZone`)
- **Why it matters:** AZ names differ per account, and the `Fn::GetAZs` order can change, which turns a
  later unrelated update into a subnet replacement
- **Instead:** AZ or subnet parameters of AWS-specific types, or a pinned list in a parameter file that
  is itself a deployment contract to validate against every target account and Region
- **Severity:** Major for index selection feeding a Replacement property; Minor elsewhere
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getavailabilityzones.html —
  "the order of the results from the `Fn::GetAZs` function isn't guaranteed and can change when new
  Availability Zones are added"; cfn-lint W3010

### CFN-TPL-03 DependsOn overuse or omission

- **Look for:** `DependsOn` naming a resource the dependent already references through `Ref`, `GetAtt`
  or `Sub` (cfn-lint W3005); long `DependsOn` chains added to "fix" ordering; conversely, a resource with
  a public IP or an internet-gateway route in a template that declares the VPC and gateway but no
  `DependsOn` on the `AWS::EC2::VPCGatewayAttachment`
- **Why it matters:** a `DependsOn` that repeats an implicit edge changes no ordering but is noise that
  outlives the reference it mirrors; extra edges with no reference behind them serialise the deployment;
  the missing gateway edge fails intermittently
- **Instead:** rely on implicit references; keep `DependsOn` for the documented cases
- **Severity:** Minor for redundancy; Major for a missing required gateway dependency
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-dependson.html —
  "You can use `DependsOn` to explicitly specify dependencies, which overrides the default parallelism";
  cfn-lint W3005 ("A Ref or a Fn::GetAtt already is an implicit dependency")

### CFN-TPL-04 Circular dependencies

- **Look for:** security groups that reference each other through inline `SecurityGroupIngress`; a bucket
  notification and a Lambda permission that reference each other; cfn-lint E3004
- **Why it matters:** the stack cannot be created
- **Instead:** break the cycle with standalone `AWS::EC2::SecurityGroupIngress` or `...Egress` resources,
  or a name built with `Fn::Sub` instead of a `Ref`
- **Severity:** Blocker (cannot deploy)
- **Source:** cfn-lint E3004 ("Check that Resources are not circularly dependent by DependsOn, Ref, Sub,
  or GetAtt")

### CFN-TPL-05 Substitution mistakes

- **Look for:** a `${...}` variable in a plain string without `Fn::Sub` (cfn-lint E1029); a pseudo
  parameter written as a plain string, `'AWS::Region'` (W1054); `Fn::Sub` with no variable (W1020);
  `Fn::Join` with an empty delimiter (I1022)
- **Why it matters:** the first two deploy the literal text or fail; the last two are noise. A `${...}`
  meant for a shell, an application or another template language is not this finding: escape it as
  `${!Literal}` inside `Fn::Sub`, or leave it in a plain string
- **Instead:** `!Sub '...${AWS::Region}...'`, `!Ref AWS::Region`
- **Severity:** Blocker for an E1029 result in the project's validation (red validation); Major for an
  intended CloudFormation variable left unsubstituted where lint did not run, and for W1054; Nit for
  W1020 and I1022
- **Source:** cfn-lint E1029 ("If a substitution variable exists in a string but isn't wrapped with the
  Fn::Sub function the deployment will fail"), W1054, W1020, I1022

### CFN-TPL-06 YAML anchors, aliases and merge keys

- **Look for:** `&anchor`, `*alias` or `<<:` in a template (cfn-lint W1100, W1101)
- **Why it matters:** the CloudFormation service does not resolve them; only `aws cloudformation package`
  or SAM expands them client-side, so the template deploys through one path and fails through another.
  The best-practices page says "leverage its features like anchors and aliases", which contradicts the
  linter; the linter describes the service behaviour, so follow it
- **Instead:** a parameter, mapping or module for repetition
- **Severity:** Blocker when a deploy path in the change submits the unprocessed file to the service
  (cannot deploy, review.md Blocker class); Major "unsure" when the deploy path is not in the change;
  Minor when every deploy path preprocesses it. Judge the artifact each path actually submits
- **Source:** cfn-lint W1101 — "The CloudFormation service does not support YAML anchors or aliases.
  Templates that use them can only be deployed through the AWS CLI 'package' command or AWS SAM";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html (the contradicting
  sentence)

### CFN-TPL-07 Transform declaration and ordering

- **Look for:** `AWS::LanguageExtensions` short forms (`!ForEach`, `!Length`, `!ToJsonString`), its
  functions outside `Resources`, `Conditions` and `Outputs`, a non-literal `Transform`, and a transform
  list with `AWS::Serverless-2016-10-31` before `AWS::LanguageExtensions`; a custom macro whose position
  in the list does not match what its contract expects to receive
- **Why it matters:** each of the first four is rejected or silently mis-processed; review.md group 6
  lists the first three, the LanguageExtensions ordering is the one most often missed. Macros at the same
  level run in list order, so a custom macro sees either the raw or the already transformed template
- **Instead:** `Transform: [AWS::LanguageExtensions, AWS::Serverless-2016-10-31]`, with a custom macro
  placed where its documented input is produced
- **Severity:** Blocker for the first four (cannot deploy); Major "unsure" for a custom macro's
  position until its contract is read
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/transform-aws-languageextensions.html —
  "the `AWS::LanguageExtensions` transform must come before the `AWS::Serverless` transform in the list";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-author.html — "Macros at
  the same location in the template are evaluated serially based on the order in which they're listed";
  practices section 5

### CFN-TPL-08 Template conventions and rationale

- **Look for:** a changed or new template departing from its siblings' section order, logical-ID naming
  or comment style; a non-obvious, replacement-sensitive choice (a custom name, a `Retain`, a
  suppressed rule) whose rationale lives only in unrelated documentation or nowhere
- **Why it matters:** inconsistent structure hides lifecycle and interface changes from the reader, and
  an unexplained exception invites a later "cleanup" that breaks deployment safety
- **Instead:** copy a sibling's skeleton; a one-line YAML comment or `Metadata` note beside the resource;
  never rename an existing logical ID for style (CFN-UPD-01); no secrets in either
- **Severity:** Nit for presentation; Minor for missing rationale on a replacement-sensitive choice
- **Source:** practices section 1 ("Follow the section order and comment style the project's existing
  templates use"; "Keep design rationale next to the resource it explains") and section 7

## 4. Reuse: nested stacks, modules, macros, StackSets and SAM (CFN-REU)

### CFN-REU-01 Duplication versus premature abstraction

- **Look for:** the same resource block (a bucket with its policy, encryption and logging) pasted into
  several templates in the change; or the opposite, a new nested stack, module or macro wrapping a
  single use with a parameter for every property
- **Why it matters:** copies drift apart; a single-use wrapper adds an interface to maintain and hides
  the resource from the reviewer; stack form of PRN-01, PRN-02 and PRN-08
- **Instead:** extract a module or nested stack once the same pattern recurs with the same policy; keep a
  one-off resource inline
- **Severity:** Minor; Major when copies of the same policy already differ in a security or retention
  setting with no stated reason (mark "unsure" when the difference may be intended per environment)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "common
  patterns can emerge in which you declare the same components in each of your templates. *Modules* are
  a way for you to package resource configurations"

### CFN-REU-02 Module version taken from the account default

- **Look for:** a new `<Org>::<Service>::<Name>::MODULE` type in a template deployed to several accounts or
  Regions or through a StackSet, with nothing in the change or the project that pins the default module
  version everywhere
- **Why it matters:** the same template expands differently per account, and a default-version change
  alters stacks on their next unrelated update without any template diff
- **Instead:** register and set the same default version in every target account and Region as part of
  the pipeline, and record the version in the project's docs
- **Severity:** Major for multi-account or StackSet use; Minor for one account
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/module-versioning.html — "if
  you have different versions of the same module registered as the default version in different
  accounts or Regions, using the same template may result in different results"

### CFN-REU-03 Custom macros and AWS::Include as opaque code

- **Look for:** a new custom macro in `Transform` or `Fn::Transform`, or an `AWS::Include` whose snippet
  lives in S3 outside the repository; a macro expected to process `Fn::ImportValue` or another macro
  (the deploy step's change-set review is CFN-OPS-06)
- **Why it matters:** what deploys is not what the diff shows, and the macro's Lambda can change behaviour
  with no template change; the reviewer cannot see generated IAM resources
- **Instead:** keep macro code and snippets in the repository and review the processed template
  (`get-template --template-stage Processed`) or the change set; prefer the LanguageExtensions functions
  or a module where they suffice
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-stack.html —
  "Be aware that the Lambda function owner can update the function operation without CloudFormation
  being notified"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-overview.html —
  "The `Fn::ImportValue` intrinsic function isn't currently supported in macros"

### CFN-REU-04 Custom names on account-wide or globally unique resources

- **Look for:** in a StackSet, or a template deployed to several Regions or several times in one
  account, custom names on IAM resources (`RoleName`, `ManagedPolicyName`, `InstanceProfileName`,
  `UserName`; "IAM resources must be globally unique within your account") or on S3 buckets
  (`BucketName`, whose names are globally unique) that do not include `${AWS::Region}` and, for buckets,
  the account (merged from CFN-IAM-04)
- **Why it matters:** the second stack instance fails on the name, or, as AWS warns for IAM, stacks
  "might share the same IAM resources", so an update in one changes the other
- **Instead:** omit the name, or include `${AWS::Region}` (and the account where needed)
- **Severity:** Major; Blocker when the StackSet or pipeline already targets more than one Region or
  copy
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-bestpractices.html —
  "be sure that global resources (such as IAM roles and Amazon S3 buckets) do not have naming conflicts
  when they are created in more than one region in the same account";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/control-access-with-iam.html — "If your
  template contains custom named IAM resources, don't create multiple stacks reusing the same template"
  and "your stacks might share the same IAM resources, rather than each having a unique one"

### CFN-REU-05 StackSet rollout and permission model

- **Look for:** `AWS::CloudFormation::StackSet` or pipeline `OperationPreferences` with high
  `FailureToleranceCount` or percentage, `MaxConcurrentPercentage: 100`, parallel Regions and no
  `RegionOrder` on a change to organisation-wide IAM, network or guardrail resources; self-managed
  permissions where the project deploys into an organisation; a service-managed StackSet whose template
  references a macro
- **Why it matters:** one bad change reaches every account at once; service-managed StackSets cannot use
  macros
- **Instead:** `MaxConcurrentCount: 1` and `FailureToleranceCount: 0` with the lowest-impact Region first
  for risky changes; service-managed permissions through AWS Organizations
- **Severity:** Minor; Major for organisation-wide IAM or network changes; Blocker for a macro under
  service-managed permissions (cannot deploy)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-bestpractices.html —
  "For a more conservative deployment, set **Maximum Concurrent Accounts** to 1, and **Failure
  Tolerance** to 0"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-overview.html —
  "StackSets doesn't currently support creating or updating stack sets with service-managed permissions
  from templates that reference macros"

### CFN-REU-06 SAM functions without safe deployment

- **Look for:** an `AWS::Serverless::Function` in a production path with `AutoPublishAlias` but no
  `DeploymentPreference`, or with `Type: AllAtOnce` and no `Alarms`; callers wired to the unqualified
  function ARN instead of the alias
- **Why it matters:** a bad version takes all traffic at once with no automatic rollback
- **Instead:** `DeploymentPreference: {Type: Canary10Percent10Minutes, Alarms: [...]}` and invoke through
  the alias
- **Severity:** Minor; Major when the items or the project require gradual deployment
- **Source:** https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/automating-updates-to-serverless-apps.html —
  "Automatically rolls back the deployment if CloudWatch alarms are triggered"

### CFN-REU-07 Mutable artifact behind an unchanged reference

- **Look for:** a Lambda `Code.S3Key` (and, once its reference behaviour is read, any other S3-hosted
  artifact such as a nested template) whose object the pipeline overwrites at the same key with no `S3ObjectVersion` or content hash in the key; an `ImageUri` by
  mutable tag; packaging that does not tie the uploaded artifact to the reviewed commit
- **Why it matters:** the update does not pick up the new code, or it deploys content the diff never
  showed, and a rollback restores whatever the key holds now
- **Instead:** content-addressed keys (as `aws cloudformation package` writes), `S3ObjectVersion`, image
  digests; review the packaged template the pipeline submits
- **Severity:** Major for a production path; Minor otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html —
  "Changes to a deployment package in Amazon S3 or a container image in ECR are not detected
  automatically during stack updates. To update the function code, change the object key or version in
  the template"; other artifact types: verify their reference behaviour in the Template Reference

### CFN-REU-08 StackSet automatic deployment and account removal

- **Look for:** a service-managed `AWS::CloudFormation::StackSet` with `AutoDeployment.Enabled: true`
  and `RetainStacksOnAccountRemoval: false` over durable resources; a changed
  `RetainStacksOnAccountRemoval`; OU targets changed on a StackSet that holds data or guardrails
- **Why it matters:** moving an account out of a target OU deletes its stack instances outside any
  template release; retaining them leaves resources nobody's StackSet manages
- **Instead:** choose retention from the resources' lifecycle and name who owns retained stacks; mark the
  current OU membership "unsure, needs runtime verification"
- **Severity:** Blocker when stateful data can be deleted with no ruling; Major for an unowned retention
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-cloudformation-stackset-autodeployment.html —
  "If an account is removed from a target organization or OU, StackSets deletes stack instances from the
  account" and `RetainStacksOnAccountRemoval`: "If set to `false`, stack resources are deleted"

## 5. Update safety and data lifecycle (CFN-UPD)

### CFN-UPD-01 Logical ID changes

- **Look for:** a renamed resource key, a resource moved into or out of a nested stack or module, a changed
  `Fn::ForEach` collection value or `OutputKey` pattern. Compare the generated logical IDs before and
  after expansion with each parameter set: renaming the loop's logical name, or its identifier
  consistently, changes nothing
- **Why it matters:** CloudFormation sees a removed resource and an added one, not a rename. For a
  stateful resource that is data loss
- **Instead:** keep the logical ID; to rename or move, use stack refactoring after checking its
  eligibility (CFN-STK-01), which keeps the physical resource, or `Retain` plus resource import
- **Severity:** Blocker for a stateful resource with no ruling; Major otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stack-refactoring.html — "You
  can rename logical IDs during this process"; https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-foreach.html —
  the loop logical name "isn't in the transformed output", and the `OutputKey` "is the logical ID of
  each resource"; practices section 7

### CFN-UPD-02 Replacement-triggering property change

- **Look for:** a changed, added or removed property whose Template Reference entry says "Update
  requires: Replacement" on a resource that already exists (DynamoDB `KeySchema`, `TableName`, RDS
  `Engine` or `Port`, a security group's `GroupDescription`); a property restated at its current value
  where it was previously omitted
- **Why it matters:** the resource is re-created with a new physical ID, and adding or removing such a
  property triggers that even when the effective value does not change
- **Instead:** avoid the change, or plan the replacement with a ruling, the `UpdateReplacePolicy` the
  data needs and the migration CFN-UPD-05 asks for; confirm with a change set
- **Severity:** Blocker for a stateful resource with no ruling; Major otherwise; mark "verify in the
  Template Reference" when the update behaviour was not read
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html —
  "If you're adding or removing a property that requires a replacement, it will also trigger an update.
  The update will happen even if the real value of the property doesn't change"

### CFN-UPD-03 Custom physical names

- **Look for:** new name properties (`BucketName`, `TableName`, `FunctionName`, `QueueName`, `RoleName`)
  on resources the items do not require to be named (cfn-nag W28)
- **Why it matters:** a later replacement of a custom-named resource fails, and the template can be
  deployed only once per account and Region
- **Instead:** let CloudFormation generate the name and publish it through an output or the registry;
  name only what the specification pins
- **Severity:** Minor; Major on a resource whose replacement-only properties are likely to change, or in a
  template deployed more than once per account
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-name.html —
  "You can't perform an update that causes a custom-named resource to be replaced. If you must replace
  the resource, specify a new name"; cfn-nag W28

### CFN-UPD-04 Stateful resource without both policies

- **Look for:** a table, bucket, key, user pool, file system, database, stream or audit log group without
  both `DeletionPolicy` and `UpdateReplacePolicy` (cfn-lint W3011, I3011); `Snapshot` on a type that
  cannot snapshot; `Delete` set explicitly on data
- **Why it matters:** `UpdateReplacePolicy` defaults to `Delete` for every type; `DeletionPolicy`
  defaults to `Delete` except `Snapshot` for `AWS::RDS::DBCluster` and for `AWS::RDS::DBInstance` without
  `DBClusterIdentifier`; and `DeletionPolicy` does not protect the old physical resource during a
  replacement. `Snapshot` on a type that cannot snapshot falls back to `Delete`
- **Instead:** set both explicitly: `Retain`, or `Snapshot` on a type the attribute's page lists;
  `RetainExceptOnCreate` is a `DeletionPolicy` value only (not an `UpdateReplacePolicy` value), for
  deleting an empty resource left by a failed create
- **Severity:** Major; Blocker where the project's rules require them (standalone-review section 4),
  or where this change can replace or delete stateful data with no ruling, including through an
  unsupported `Snapshot` falling back to `Delete`
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html —
  "The default policy is `Snapshot` for `AWS::RDS::DBCluster` resources and for `AWS::RDS::DBInstance`
  resources that don't specify the `DBClusterIdentifier` property" and "This capability doesn't apply to
  resources whose physical instance is replaced during stack update operations";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html —
  "If you specify the `Snapshot` option in the `UpdateReplacePolicy` for a resource that doesn't support
  snapshots, CloudFormation reverts to the default option, which is `Delete`" (options listed there:
  `Delete`, `Retain`, `Snapshot`); cfn-lint W3011, I3011; practices section 6

### CFN-UPD-05 Retain without a re-create or migration plan

- **Look for:** `Retain` on a custom-named resource in a template that may be deleted and re-created
  (a dev or ephemeral stack, when the project says so); `Retain` on high-volume, cheap-to-rebuild
  resources; an approved replacement of a table, bucket, database or file system whose plan relies on
  `Retain` or `Snapshot` and names no data transfer, consumer cutover, rollback or cleanup of the old
  resource
- **Why it matters:** the re-create fails on the retained name, and retained resources keep billing.
  Retention keeps the old resource, outside CloudFormation's scope; it does not fill the new one or move
  the applications to it, so an update can succeed and still leave data unavailable or split
- **Instead:** generated names for re-creatable resources; `Retain` for data; for a replacement, the
  migration, cutover order and rollback steps in the plan, and the import or refactoring path checked
  for eligibility
- **Severity:** Minor for the re-create case; Major for an approved replacement with no migration or
  cutover; Blocker when the replacement has no ruling (CFN-UPD-02)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html —
  "Resources that are retained continue to exist and continue to incur applicable charges" and
  "`UpdateReplacePolicy` retains the old physical resource or snapshot, but removes it from
  CloudFormation's scope"; the migration requirement is an operational inference

### CFN-UPD-06 Resource-level deletion protection or recovery missing

- **Look for:** `AWS::DynamoDB::Table` without `DeletionProtectionEnabled: true`, `AWS::RDS::DBInstance`
  or `DBCluster` without `DeletionProtection: true`, and similar flags on user pools and load balancers
  where the items treat the resource as durable; a change that removes or shortens a recovery setting
  the items require (DynamoDB `PointInTimeRecoverySpecification` and its `RecoveryPeriodInDays`, RDS
  backup retention, a backup plan's selection), or a new durable resource left out of the project's
  backup mechanism
- **Why it matters:** the template policies protect against CloudFormation deleting the resource, not
  against an operator or another tool, and `Retain` is not a backup: it does nothing for corrupted or
  overwritten data
- **Instead:** set the flag (conditionally off only for ephemeral environments the items name); keep the
  recovery settings the items state; never treat retention as recovery
- **Severity:** Major where the resource has the flag (standalone-review section 4) and for a weakened
  recovery setting the items require; Blocker when it contradicts a specification item
- **Source:** practices section 6; AWS Guard Rules Registry 1.0.2 rule
  `RDS_INSTANCE_DELETION_PROTECTION_ENABLED`; https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-dynamodb-table-pointintimerecoveryspecification.html —
  "Your table data is only recoverable to any point-in-time from within the configured recovery period"

### CFN-UPD-07 Retention left to service defaults

- **Look for:** `AWS::Logs::LogGroup` without `RetentionInDays` (never expires), and resources with
  auto-expiring content without an explicit retention (cfn-lint I3013, cfn-nag W86); a Lambda or other
  service writing to an implicit log group the stack does not declare
- **Why it matters:** either unbounded cost or silent loss of data the items need to keep
- **Instead:** declare the log group with the retention the items state
- **Severity:** Minor; Major for audit data
- **Source:** cfn-lint I3013 ("If no retention period is specified the default for some services is to
  delete the data after a period of time"); cfn-nag W86

### CFN-UPD-08 Removing a nested stack or stateful resource

- **Look for:** an `AWS::CloudFormation::Stack` resource or a stateful resource deleted from a template
- **Why it matters:** an update that removes a nested stack deletes the whole nested stack even when the
  root has termination protection; a removed resource follows its `DeletionPolicy`
- **Instead:** set `Retain` in a prior change and deploy it, then remove; or move the resource with stack
  refactoring where eligible (CFN-STK-01); a retained resource still needs the ownership and cleanup
  plan of CFN-UPD-05
- **Severity:** Blocker when data would be deleted with no ruling; Major otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html —
  "if a user performs a stack update that would delete the nested stack, CloudFormation deletes the
  nested stack accordingly"

### CFN-UPD-09 Template fighting run-time scaling

- **Look for:** an `AWS::AutoScaling::AutoScalingGroup` with scheduled actions and a literal
  `MinSize`, `MaxSize` or `DesiredCapacity`, without
  `UpdatePolicy.AutoScalingScheduledAction.IgnoreUnmodifiedGroupSizeProperties: true`; a literal
  `DesiredCapacity` beside policy-driven scaling, or other scaled capacity properties (the documented
  reset covers scheduled actions; verify other cases in the Template Reference before stating them)
- **Why it matters:** with scheduled actions, every stack update resets the group to the template's
  size, which can cut capacity during peak load
- **Instead:** the update policy for scheduled actions; omit `DesiredCapacity` where scaling owns it
- **Severity:** Major for production capacity under scheduled actions; Minor "unsure" for the other
  cases
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatepolicy.html —
  "CloudFormation always sets the group size property values of your Auto Scaling group to the values
  that are defined in the ... resource of your template, even if a scheduled action is in effect"

### CFN-UPD-10 Update completion without workload readiness

- **Look for:** an Auto Scaling group whose launch template or AMI changes with no `UpdatePolicy`
  (`AutoScalingRollingUpdate`, `AutoScalingReplacingUpdate` or `AutoScalingInstanceRefresh`) when the
  items expect running instances to be replaced; a rolling update with `MinInstancesInService` below
  `MinSize`, or `MinSuccessfulInstancesPercent: 0`; `WaitOnResourceSignals` or a `CreationPolicy` with no
  `cfn-signal` path in the bootstrap, or a signal sent before the application is ready
- **Why it matters:** stack form of ARC-19 (hidden lifecycle protocols). Stack completion is not
  application readiness: old instances keep running,
  capacity drops during the roll, or the update waits for signals that never arrive and fails, and a
  short `PauseTime` can make the rollback fail too
- **Instead:** pick the update policy that matches the intended replacement; keep healthy capacity at or
  above `MinSize`; signal after a real health check (`cfn-init` plus a verify step)
- **Severity:** Major for a demonstrated availability or rollout defect; Blocker when the update cannot
  complete (no signal path under a signal-waiting policy)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatepolicy.html —
  "To perform a rolling update of the instances in an Auto Scaling group rather than wait for scaling
  activities to gradually replace older instances with newer instances, use the
  `AutoScalingRollingUpdate` policy", "healthy capacity can drop below the `MinHealthyPercentage` set on the group", "We recommend that you
  set the value of the `MinInstancesInService` property to at least the MinSize", "If the `PauseTime` is
  exceeded before CloudFormation receives the expected signals, the update fails";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-creationpolicy.html —
  "prevent its status from reaching create complete until CloudFormation receives a specified number of
  success signals or the timeout period is exceeded"

## 6. Custom resources (CFN-CR)

### CFN-CR-01 No ServiceTimeout

- **Look for:** a new `AWS::CloudFormation::CustomResource` or `Custom::*` without `ServiceTimeout`
- **Why it matters:** a stuck handler holds the stack for an hour before it fails, and again on rollback
- **Instead:** `ServiceTimeout` slightly above the handler's worst case (1 to 3600 seconds)
- **Severity:** Minor; Major for a new handler written in this change
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-custom-resources.html —
  "The default timeout for your custom resource is 3600 seconds (1 hour). If no response is received
  during this time, the stack operation fails"

### CFN-CR-02 Handler that can exit without responding

- **Look for:** handler code in the change with a path that sends no response, or two (a blanket
  `finally` that sends `FAILED` after a `SUCCESS` was already sent); no branch for `Delete` of a
  resource whose `Create` failed; unknown `RequestType` falling through; a serialized response (the whole
  body, not only `Data`) that can exceed 4096 bytes; a Lambda timeout that leaves no time to report a
  failure; a VPC-attached provider with no network path to the presigned S3 `ResponseURL` (an S3
  endpoint or egress the change removes or never adds)
- **Why it matters:** no response means the operation waits for the timeout, and a failed `Delete` blocks
  rollback and stack deletion; work the provider finished still fails the stack when the response
  cannot reach S3
- **Instead:** exactly one protocol response on every handled path, directly or through the adopted
  provider framework; `Delete` of something absent is CFN-CR-04; keep the response small; leave the
  handler time to report; verify the response path from the provider's network
- **Severity:** Major; Blocker when the changed network configuration demonstrably cuts the response
  path
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref.html — "If the custom
  resource provider doesn't send a response, CloudFormation waits until the operation times out" and "The
  total size of the response body can't exceed 4096 bytes";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-custom-resources.html — "If they
  can't send responses to Amazon S3, CloudFormation won't receive a response and the stack operation
  fails"

### CFN-CR-03 Unstable PhysicalResourceId

- **Look for:** `cfnresponse.send(...)` without the `physicalResourceId` argument, or a handler that
  returns a new ID (a timestamp, a request ID) on an in-place `Update`; a `Delete` branch that acts on
  the currently configured target instead of the event's `PhysicalResourceId`
- **Why it matters:** the module's default is the log stream name, which is not tied to the managed
  object and can differ between invocations; a changed ID is a replacement, so CloudFormation sends
  `Delete` for the old ID, and a `Delete` branch that targets the configured object rather than that ID
  destroys the live resource
- **Instead:** return the same stable ID for the life of the resource (the managed object's identifier);
  a new ID only for an intended replacement; `Delete` acts on the event's `PhysicalResourceId`
- **Severity:** Blocker when the `Delete` branch can destroy the live object's data or access; Major
  otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lambda-function-code-cfnresponsemodule.html —
  "By default, the module uses the name of the Amazon CloudWatch Logs log stream that's associated with the
  Lambda function"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref.html — the
  value "must be identical for all responses for the same resource" and "If the value changes, CloudFormation interprets the update as a replacement and sends a delete request to the
  old resource"

### CFN-CR-04 Non-idempotent handler

- **Look for:** `Create` that, on finding the target exists, either fails on its own earlier attempt
  or silently adopts an object another stack or operator owns; `Update` that ignores
  `OldResourceProperties` and re-applies destructive steps; `Delete` that fails when the target is gone;
  side effects keyed on nothing (no use of `StackId` plus `RequestId`)
- **Why it matters:** retries, rollbacks and replacement send the same logical operation more than once;
  blind adoption hands one stack's lifecycle (and its later `Delete`) an object it does not own
- **Instead:** record ownership (a tag or marker naming the stack and logical ID) and deduplicate on
  `StackId` plus `RequestId`; adopt only what this resource created, reject other collisions; compare old
  and new properties; `Delete` of something absent returns `SUCCESS` (idempotency is an inference from
  the protocol, not an AWS-stated rule)
- **Severity:** Major; Blocker where the change can adopt and later delete an object it does not own
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref.html — "Combining the
  `StackId` with the `RequestId` forms a value that you can use to uniquely identify a request on a
  particular custom resource"

### CFN-CR-05 Secrets through a custom resource (security reviewer)

- **Look for:** a secret passed in a custom resource's properties, including through a
  `{{resolve:secretsmanager:...}}` or `ssm-secure` reference; a handler returning sensitive `Data` without
  `NoEcho: true`
- **Why it matters:** secure dynamic references are not supported there, and returned values show in APIs
  such as `DescribeStackEvents`
- **Instead:** pass the secret's ARN and have the handler read it with its own scoped permission; set
  `NoEcho` on sensitive responses
- **Severity:** Blocker for a plaintext secret in properties, and for sensitive `Data` the change
  demonstrably exposes; Major for a secure reference in custom-resource properties (unsupported: what
  the stack does with it is unverified, so mark "unsure") and for possibly sensitive `Data` without
  `NoEcho`
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html —
  "Dynamic references can't be used for secure values (like those stored in Parameter Store or Secrets
  Manager) in custom resources"; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-custom-resources.html —
  "If the name-value pairs contain sensitive information, you should use the `NoEcho` field"

### CFN-CR-06 Custom resource where a native type exists, or on a dying runtime

- **Look for:** a custom resource that creates something with an `AWS::` resource type (verify in the
  Template Reference); an inline `ZipFile` handler on an end-of-life runtime (cfn-lint E2531, W2531,
  E2533); `cfnresponse` imported under another name
- **Why it matters:** hand-written lifecycle code where CloudFormation would manage it, and a handler that
  can no longer be updated
- **Instead:** the native type; a supported runtime; `import cfnresponse` exactly
- **Severity:** Minor; Major for E2533 on an unchanged function (approaching or past the update block);
  Blocker when this change updates code or configuration of a function whose runtime is past Lambda's
  "block function update" date (cannot deploy)
- **Source:** cfn-lint E2531, W2531, E2533; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lambda-function-code-cfnresponsemodule.html —
  "Use this exact import statement"; https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html —
  "Block function update ... Lambda begins blocking the update of code and configuration for existing
  functions"

## 7. Deploy path, drift and stack guardrails (CFN-OPS)

### CFN-OPS-01 Out-of-band changes built into the design

- **Look for:** comments or docs in the change saying a value is "set in the console after deploy";
  scripts that call service APIs to modify stack-managed resources; resources the template depends on by
  name that no stack creates
- **Why it matters:** the next stack update reverts the manual change or fails on the mismatch
- **Instead:** model the setting in the template or move the resource out of CloudFormation entirely
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "Don't
  make changes to stack resources outside of CloudFormation" and "If a change is made to a resource
  outside of the CloudFormation template and you update the stack, the changes made directly to the
  resource will be discarded"; Well-Architected REL08-BP05 anti-pattern
  "You perform manual changes"

### CFN-OPS-02 Drift-prone ownership

- **Look for:** one setting owned by two resources or two stacks (inline security-group rules plus
  standalone ingress resources on the same group; one bucket's notifications or policy declared in two
  stacks); properties the design relies on left at service defaults
- **Why it matters:** each owner overwrites the other on update (community consensus); drift detection
  ignores properties the template does not set, so a default changed outside the stack is invisible
- **Instead:** one owner per setting; set explicitly the properties whose value matters
- **Severity:** Minor; Major when the overwritten setting is access control
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html —
  "CloudFormation only determines drift for property values that are explicitly set ... This doesn't
  include default values for resource properties"

### CFN-OPS-03 Stack policy for critical resources

- **Look for:** in the pipeline or bootstrap files of the change: a stack holding critical stateful
  resources created without a stack policy; a policy of only `Deny` statements (it blocks every other
  update); a stack policy changed to `Allow Update:*` on everything; a stack-refactoring plan for a
  stack that has a stack policy
- **Why it matters:** the stack policy is the fail-safe against an accidental replacement. Once set it
  cannot be deleted, only replaced, and stack refactoring refuses any stack that has one, whatever it
  allows, so an `Allow`-all replacement does not make the stack eligible
- **Instead:** an `Allow Update:*` baseline plus explicit `Deny` of `Update:Replace` and `Update:Delete`
  on the data resources' logical IDs; for a one-off protected update, a temporary stack policy for that
  update (`StackPolicyDuringUpdateBody`); move resources out of a policy-protected stack by a path that
  does not need refactoring (`Retain`, then resource import), or set no policy on stacks the plan will
  refactor
- **Severity:** Minor; Major when the change removes or weakens an existing protection
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "Specify
  a stack policy whenever you create a stack that has critical resources";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html — "any
  update not explicitly allowed is denied by default" and "You can't delete a stack policy";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stack-refactoring.html — "Stack refactor
  doesn't support stacks that have stack policies attached, regardless of what the policies allow or
  deny"; https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html —
  `StackPolicyDuringUpdateBody` "the temporary overriding stack policy body"

### CFN-OPS-04 Termination protection

- **Look for:** pipeline changes that create production root stacks without
  `--enable-termination-protection` or that disable it
- **Why it matters:** it is off by default, and it is the stack-level guard against a `DeleteStack`
  call, beside the access controls on that call and the resources' own `DeletionPolicy`; it does not
  stop an update that removes resources (CFN-UPD-08)
- **Instead:** enable it in the pipeline or bootstrap for every non-ephemeral root stack
- **Severity:** Major when the change disables it; Minor when a new production stack lacks it
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html —
  "Termination protection on stacks is disabled by default" and "Termination protection applies only to
  attempts to delete stacks"

### CFN-OPS-05 Rollback configuration

- **Look for:** `--disable-rollback` or `OnFailure: DO_NOTHING` outside development; production deploys
  with no `RollbackConfiguration` triggers for the alarms the items define; a trigger naming an alarm the
  change deletes
- **Why it matters:** a failed or unhealthy deployment stays half-applied; a missing trigger alarm fails
  the whole operation
- **Instead:** keep rollback on; up to five alarm triggers with a monitoring time for critical stacks
- **Severity:** Minor; Major for disabled rollback in production; Blocker when a trigger names an alarm
  the change deletes or that is known not to exist (the operation fails, review.md Blocker class)
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html —
  "If a given CloudWatch alarm is missing, the entire stack operation fails and rolls back";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "Configure rollback
  triggers for critical metrics such as application error rates"

### CFN-OPS-06 Change sets skipped for transformed templates

- **Look for:** `aws cloudformation deploy` or `create-stack`/`update-stack` with `CAPABILITY_AUTO_EXPAND`
  and no change-set inspection step for a template with SAM, `AWS::Include` or a custom macro; a pipeline
  that executes a change set in the same step that creates it with no replacement check
- **Why it matters:** transforms add resources the diff does not show, and only the change set reveals
  replacements
- **Instead:** create the change set, run the change-set rule on its `describe-change-set` output, then
  execute (review.md group 8, practices section 10)
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-overview.html —
  "Processing macros can add multiple resources that you might not be aware of. To ensure that you're
  aware of all of the changes introduced by macros, we strongly advise that you use change sets"

### CFN-OPS-07 Tagging and deployment role

- **Look for:** no stack-level tags in the pipeline where the project defines a tagging scheme; tag keys
  or values starting with `aws:`; ASG tags without `PropagateAtLaunch`; a stack created without
  `--role-arn` where the project uses a service role (an update without it keeps the role already
  associated with the stack, so check the stack's creation or bootstrap before calling it a
  caller-credential deploy), or a service role with `AdministratorAccess` (the IAM half goes to the
  security reviewer)
- **Why it matters:** untagged resources break cost allocation and tag-based access control; an `aws:`
  tag cannot be updated or removed; a stack with no service role runs every operation with the caller's
  credentials, so the deployer needs everything the template needs
- **Instead:** stack-level `Tags` on the deploy call; a least-privilege CloudFormation service role
- **Severity:** Minor; Major for an administrator service role
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-resource-tags.html —
  "If you use this prefix in the `Key` or `Value` property, you can't update or delete the tag";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "To separate
  permissions between a user and the CloudFormation service, use a service role";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html — "If you don't
  specify a value, CloudFormation uses the role that was previously associated with the stack. If no
  role is available, CloudFormation uses a temporary session that is generated from your user
  credentials"

### CFN-OPS-08 Nested changes left out of the change-set review

- **Look for:** a pipeline that changes nested templates but creates the root change set without
  `--include-nested-stacks`, or runs the replacement rule only on the root change set's `Changes`; an
  execute step that runs a change set other than the one inspected
- **Why it matters:** the root shows only that a nested stack is modified, while the destructive change
  sits in the child; reviewing one change set authorises nothing about another
- **Instead:** create the change set with `--include-nested-stacks`, run the change-set rule on every
  nested change set it lists, and execute the root change set that was reviewed; respect practices
  section 5 on macros together with nested stacks
- **Severity:** Major; Blocker when an unreviewed nested change replaces or deletes stateful data with no
  ruling
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/change-sets-for-nested-stacks.html —
  "Change sets for nested stacks isn't enabled by default for the AWS CLI. To create a change set for
  the entire stack hierarchy, specify the `--include-nested-stacks` option" and "The execute operation
  must be made from the root change set"; practices section 10

## 8. IAM in templates (CFN-IAM) — security reviewer

### CFN-IAM-01 Wildcards and Not-elements in inline policies

- **Look for:** in `Allow` statements, `Action: "*"` or `service:*`, `Resource: "*"` on resource-scoped
  actions, and `NotAction`, `NotResource` or `NotPrincipal`, in `AWS::IAM::Role.Policies`,
  `AWS::IAM::Policy`, `AWS::IAM::ManagedPolicy` and resource policies (cfn-nag F3, F4, F5, W11, W12, W13,
  W15, W21, F6; Guard registry `IAM_POLICY_NO_STATEMENTS_WITH_ADMIN_ACCESS`). Read the effect, the
  conditions and the trust relationship before classifying: a `Deny` with `Principal: "*"` and a
  condition (TLS-only, organisation-only) is protective
- **Why it matters:** the template grants more than the workload uses, invisible to cfn-lint's schema
  checks
- **Instead:** named actions and ARNs built with pseudo parameters, `!GetAtt` and `!Ref`
- **Severity:** Blocker without the reason the items accept (review.md); Major for `Not*` elements
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "avoid
  using wildcard permissions whenever possible"; cfn-nag rule IDs (v0.8.10 source)

### CFN-IAM-02 iam:PassRole unscoped

- **Look for:** two separate gaps (cfn-nag F38, F39, F40): role scope, `iam:PassRole` on `"*"` or on a
  role-path wildcard whose path the same principals can create or change roles in; destination scope,
  no `iam:PassedToService` condition. A condition does not cure a wildcard role scope, nor a narrow role
  ARN a missing condition
- **Why it matters:** the principal can hand any role in scope, including administrator roles, to a
  service it controls; `iam:PassedToService` narrows only the receiving service
- **Instead:** the specific role ARN plus `Condition: {StringEquals: {iam:PassedToService:
  lambda.amazonaws.com}}`
- **Severity:** Blocker for a wildcard role scope with no accepted reason; Major for a missing
  destination condition on a specific role
- **Source:** https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_iam-passrole-service.html
  (example statement with `"iam:PassedToService"`);
  https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html —
  `iam:PassedToService` "Specifies the service principal of the service to which a role can be
  passed"; cfn-nag F38, F39, F40

### CFN-IAM-03 Managed policy choice

- **Look for:** `ManagedPolicyArns` with AWS managed `AdministratorAccess` or `*FullAccess` on workload
  roles (cfn-nag W43, W44); the same inline statement copied into several roles where one
  `AWS::IAM::ManagedPolicy` would serve
- **Why it matters:** broad managed policies grow as AWS adds actions; duplicated inline policies drift.
  Judge a `*FullAccess` policy by the permissions it grants, not its name
- **Instead:** a customer managed policy scoped to the workload, attached where needed; inline only for a
  policy unique to one role (a design recommendation; the Guard registry's `IAM_NO_INLINE_POLICY_CHECK`
  forbids inline policies outright, so follow the project's rule where it adopts that rule)
- **Severity:** Blocker for `AdministratorAccess` on a workload role without an accepted reason (its
  document is `Action: "*"` on `Resource: "*"`, review.md's IAM wildcard class); Major for other broad
  full-access attachments; Minor for duplication
- **Source:** cfn-nag W43, W44; https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AdministratorAccess.html
  (policy document `"Action" : "*", "Resource" : "*"`); AWS Guard Rules Registry 1.0.2 rule
  `IAM_NO_INLINE_POLICY_CHECK`

### CFN-IAM-04 Custom-named IAM resources

Retired 2026-10-16: merged into CFN-REU-04 (custom names); the missing `CAPABILITY_NAMED_IAM` is
review.md group 8 (section 11 here)

### CFN-IAM-05 Lambda permissions without source scoping

- **Look for:** `AWS::Lambda::Permission` with `Principal: "*"` (cfn-nag F13), a service principal and a
  `SourceArn` without account (S3 bucket ARNs) but no `SourceAccount` (cfn-lint W3663), a principal that
  does not match the `SourceArn` service (W3664), or an action other than `lambda:InvokeFunction` (cfn-nag
  W24)
- **Why it matters:** another account's resource can invoke the function (confused deputy)
- **Instead:** `SourceArn` plus `SourceAccount: !Ref AWS::AccountId`
- **Severity:** Blocker for `Principal: "*"`; Major for missing `SourceAccount`
- **Source:** cfn-lint W3663 ("When configuration a Lambda permission with a SourceArn that doesn't have
  an AccountId you should also specify the SourceAccount"), W3664; cfn-nag F13, W24

### CFN-IAM-06 Policies that lint cannot vouch for

- **Look for:** cfn-lint E3510, E3512, E3530 (identity, resource and trust policy structure), W3037
  (invalid permission), I3510 (resources that do not match the action); action names the reviewer has not
  verified
- **Why it matters:** an invalid action deploys but grants nothing, so the workload fails at run time, or
  a typo in a `Deny` silently allows
- **Instead:** fix the names against the Service Authorization Reference; run `cfn-policy-validator`
  where the project adopts it
- **Severity:** Blocker for an E35xx result in the project's validation (an error bit is red
  validation, standalone-review section 2); Major for W3037 and for unverified action names where lint
  did not run (report them as unvalidated observations); Minor for I3510
- **Source:** cfn-lint E3510, E3512, E3530, W3037, I3510; practices section 8

## 9. Secrets and data exposure (CFN-SEC) — security reviewer

### CFN-SEC-01 Secrets as parameters

- **Look for:** a password, token or key as a `Parameter` (cfn-lint W1011, W2501), with or without
  `NoEcho`; a `NoEcho` parameter referenced in `Metadata` (W2010; in `Outputs` it is CFN-SEC-05); a
  secret `Default`
- **Why it matters:** the project forbids secret parameters (practices section 8) whether or not they
  leak today; `NoEcho` masks the stack's describe calls but not `Metadata` or `Outputs`, and the value
  still passes through whatever supplies the parameter (parameter files, CI variables) and any service
  that logs it
- **Instead:** `{{resolve:secretsmanager:...}}`, or a managed-secret property of the resource (for RDS,
  `ManageMasterUserPassword`; verify in the Template Reference)
- **Severity:** Blocker for a secret default or literal, or a demonstrated exposure (review.md);
  Major for a `NoEcho` secret parameter, the policy violation alone
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html — "Be aware
  that `NoEcho` doesn't prevent the value from being logged if it's passed to other services or resources
  that might log the value"; cfn-lint W1011, W2501, W2010

### CFN-SEC-02 Dynamic reference in the wrong place

- **Look for:** a dynamic reference or `NoEcho` value in a property that is part of the resource's primary
  identifier (the `Ref` return value); a `{{resolve:...}}` inside EC2 `UserData` or
  `AWS::CloudFormation::Init`; `ssm-secure` in an unsupported property (cfn-lint E1027); a reference
  passed through `AWS::Include` or SAM expecting resolution before the transform
- **Why it matters:** the plaintext can become the resource ID and appear in outputs and ARNs, or the
  literal reference string is deployed
- **Instead:** keep dynamic references out of identifier properties; fetch secrets at boot from the
  instance role
- **Severity:** Blocker for a secure reference (`secretsmanager`, `ssm-secure`) or a `NoEcho` value in
  an identifier property; Minor for a non-secret `ssm` reference there (AWS still advises against it);
  Major otherwise
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html —
  "Avoid including dynamic references, or any sensitive data, in resource properties that are part of a
  resource's primary identifier" and "Dynamic references are also not supported in
  `AWS::CloudFormation::Init` metadata and Amazon EC2 `UserData` properties"

### CFN-SEC-03 Secret resolved into a visible configuration

- **Look for:** `{{resolve:secretsmanager:...}}` in a Lambda `Environment.Variables`, an ECS container
  `Environment` (not `Secrets`), a Step Functions definition or any property the service shows back in its
  console or describe API
- **Why it matters:** CloudFormation does not persist the value, but the target service keeps it as
  resource configuration, readable by whoever may read that configuration. Lambda encrypts environment
  variables at rest, so the risk is who can read the configuration and that the function receives the
  plaintext, not unencrypted storage
- **Instead:** pass the secret ARN and read at run time, or the service's native secret injection (ECS
  `Secrets`)
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html —
  "the secret value may show up in the service whose resource it's being used in. Review your usage to
  avoid leaking secret data"; https://docs.aws.amazon.com/lambda/latest/dg/security-encryption-at-rest.html —
  "AWS Lambda always provides at-rest encryption for the following resources: Environment variables"

### CFN-SEC-04 Pinned secret versions and rotation assumptions

- **Look for:** `secretsmanager` references with an explicit `version-id` or `version-stage` outside a
  test or rollback case; a design that expects a rotated secret to reach the resource without a stack
  update
- **Why it matters:** a `version-id` pins one version; a `version-stage` pins a label, which rotation
  moves (a versionless reference defaults to `AWSCURRENT`); and CloudFormation re-reads a secret only
  when the resource holding the reference is updated, so a rotated value does not reach that resource
  until then
- **Instead:** versionless references; rotation handled by the service integration, not by redeploys
- **Severity:** Minor; Major when the design depends on a rotated value reaching a resource with no
  update (the documented RDS `MasterPassword` case); mark the outage impact "unsure" unless the
  change shows it
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html —
  "Use versionless references for your CloudFormation templates", "Secrets Manager uses staging labels
  to keep track of different versions during the rotation process", "If you don't specify either
  `version-stage` or `version-id`, then the default is the `AWSCURRENT` version" and "CloudFormation
  retrieves the secret value only during resource creation or updates that modify the resource
  containing the dynamic reference"

### CFN-SEC-05 Sensitive outputs

- **Look for:** `Outputs` values carrying passwords, keys, connection strings with credentials, or a
  `NoEcho` parameter
- **Why it matters:** outputs are never redacted and are readable by anyone with `DescribeStacks`
- **Instead:** output the secret's ARN or name only
- **Severity:** Blocker
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html —
  "We strongly recommend you don't use this section to output sensitive information, such as passwords
  or secrets"

## 10. Tests, rules and suppressions (CFN-TST)

### CFN-TST-01 Unjustified suppressions

- **Look for:** new `Metadata: cfn-lint: config: ignore_checks` at template or resource level, Guard
  `Metadata: guard: SuppressedRules`, cfn-nag `rules_to_suppress`, or `.cfnlintrc` `ignore_checks`
  entries, without a reason that names the specification item or ruling; template-wide ignores of whole
  classes (`W`, `I`, `W3`)
- **Why it matters:** a suppression turns a reported defect into silence for every future change
- **Instead:** suppress per resource, per rule ID, with a reason; never class-wide
- **Severity:** Major when the suppressed rule is a Blocker or Major class here (W3011, I3011, I3042,
  W1011, E35xx, F3, F38); Minor otherwise
- **Source:** cfn-lint README, "Resource Based Metadata" ("you can configure cfn-lint to ignore checks");
  AWS Guard Rules Registry 1.0.2 `docs/Guard-Rules-Dev-Guide.md` ("By adding in the `SuppressedRules`
  metadata, you override the rule within the code-base")

### CFN-TST-02 Lint that cannot see the deployed shape

- **Look for:** a `.cfnlintrc` or validate script in the change with no parameter files (so
  `Fn::ForEach` collections lack the real values, practices section 11), a single Region where the stacks
  deploy to several, or `I` rules not included while the project relies on I3011 or I3042
- **Why it matters:** expansions and Regions the pipeline deploys are never checked. This is a coverage
  gap; a validation that ran and failed is red validation, a Blocker under review.md, not this check
- **Instead:** parameter files per environment, every target Region, `include_checks: [I]` (practices
  section 11)
- **Severity:** Minor; Major when a Blocker-class rule is effectively disabled
- **Source:** practices section 11; cfn-lint README — "`info` rules are not included by default. To
  include these rules you will need to include `-c I` or `--include-checks I`"

### CFN-TST-03 Unpinned or legacy rule packs

- **Look for:** Guard Rules Registry rules copied without the release they came from or without
  `*_tests.yaml`; a new dependency on cfn-nag (last release v0.8.10, 2022-06-07) or on the registry as a
  live download (last release 1.0.2, 2022-09-02; both checked on the GitHub releases API 2026-10-16)
- **Why it matters:** rules change or rot under the project without a diff, and untested rules give false
  passes; avoiding both tools as live dependencies is the project default (practices section 12), which
  the release dates illustrate rather than prove
- **Instead:** vendor the adopted rules with their release and tests; prefer cfn-lint, cfn-guard and
  cfn-validate (practices sections 11 and 12)
- **Severity:** Minor
- **Source:** practices sections 11 and 12; https://api.github.com/repos/stelligent/cfn_nag/releases/latest
  and https://api.github.com/repos/aws-cloudformation/aws-guard-rules-registry/releases/latest

## 11. Out of scope / handled elsewhere

- Specification fidelity, Guard fixtures, quotas after expansion, `--use-previous-template`, Lambda
  versions and aliases, the change-set replacement rule, `CAPABILITY_NAMED_IAM` on the deploy call:
  `review.md` groups 1, 6, 7 and 8 and `cloudformation-practices.md` sections 2, 5, 8, 9 and 10; this
  file does not restate them
- The full IAM, encryption, network-exposure, confused-deputy and S3 public-access checklist:
  `skills/iac-security-reviewer/SKILL.md`
- Schema validity of every property and value (E3002, E3003, E3012, E3030 and the rest of the E rules):
  cfn-lint and cfn-validate in the read-only checks. Reuse the recorded validation result and report the
  underlying finding once; when the tool did not run, label a manual observation "unvalidated", never
  as a lint result
- Code inside Lambda handlers beyond the custom-resource protocol: the language stack's review dimensions
  (Python, Java)
- CDK apps and their synthesised templates: `reviewing-cdk-changes`; Terraform: `reviewing-terraform-changes`
- Deployed state, drift and live stack settings: not reviewable from a diff; report as "unsure, needs
  runtime verification" with the command the operator runs (the evidence rule in "How to apply")

## Sources

- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getstackoutput.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-update-behaviors.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-stack.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/mappings-section-structure.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/conditions-section-structure.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-getavailabilityzones.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-dependson.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/transform-aws-languageextensions.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/module-versioning.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-overview.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacksets-bestpractices.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/control-access-with-iam.html
- https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/automating-updates-to-serverless-apps.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stack-refactoring.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-name.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatepolicy.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-custom-resources.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lambda-function-code-cfnresponsemodule.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-resource-tags.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_iam-passrole-service.html
- https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_tracking_change_management_automated_changemgmt.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/change-sets-for-nested-stacks.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-macros-author.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-foreach.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-lambda-function-code.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-cloudformation-stackset-autodeployment.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-creationpolicy.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-dynamodb-table-pointintimerecoveryspecification.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html
- https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AdministratorAccess.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html
- https://docs.aws.amazon.com/lambda/latest/dg/security-encryption-at-rest.html
- cfn-lint rules catalogue, https://github.com/aws-cloudformation/cfn-lint/blob/v1.57.2/docs/rules.md
  (tag v1.57.2, read 2026-10-16), and README (configuration and Metadata sections)
- cfn_nag v0.8.10 rule sources, https://github.com/stelligent/cfn_nag/tree/v0.8.10/lib/cfn-nag/custom_rules
- AWS Guard Rules Registry 1.0.2, https://github.com/aws-cloudformation/aws-guard-rules-registry/tree/1.0.2
- `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cloudformation-from-spec/references/cloudformation-practices.md`
  (cited as "practices section N")
- `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md` (shared principles)
