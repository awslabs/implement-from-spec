# AWS CDK review dimensions

Design, abstraction, state-safety, synthesis and test checks for AWS CDK v2 changes in Python and Java
apps, each observable in a diff or in the synthesised template. The Claude-stage reviewers apply them
inside the check groups of `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cdk-from-spec/references/review.md`;
they add depth, they do not replace those groups, and the rules and verified quotations in `cdk-practices.md`
beside it still hold. Precedence: the project's rules (CLAUDE.md, AGENTS.md), its specification items, the
approved plan and the ledger's Rulings override every default here; a deviation the project prescribes is
not a finding. Facts below were read on 2026-10-16 (aws-cdk-lib's latest release then was v2.273.0, published
2026-10-08); re-read a cited page before a finding depends on it, and say "verify in the CDK API reference"
for any API the app's pinned CDK version may not have.

Recent APIs and the aws-cdk-lib release that introduced them, from the GitHub release notes read on
2026-10-16 (compare with the app's pinned `aws-cdk-lib` before recommending one; on an older pin the
established API in the same check is the fix): aspect priorities (`AspectPriority`) v2.172.0;
reference interfaces (`IBucketRef` and similar) v2.214.1, moved to the `aws-cdk-lib.interfaces` submodule
in v2.224.0; Grants classes (`bucket.grants`, `BucketGrants`) v2.227.0; Mixins (`.with_()` / `.with()`)
in `aws-cdk-lib` v2.241.0, earlier only in a preview package; weak and transitional cross-stack
references (`ReferenceStrength`, `CrossStackReferences`) v2.254.0. cdk-nag's v3 `Validations` model is
versioned separately from aws-cdk-lib: check the app's `cdk-nag` pin.

## Contents

- How to apply
- 1. Principles and architecture smells (CDK-ARC)
- 2. Construct API and abstraction (CDK-API)
- 3. Construct identity and stateful resources (CDK-STA)
- 4. Environments, context and cross-stack references (CDK-ENV)
- 5. IAM and grants (CDK-IAM)
- 6. Secrets and data exposure (CDK-SEC)
- 7. Synthesis mechanics: tokens, aspects, assets (CDK-SYN)
- 8. Tests (CDK-TST)
- 9. Python and Java app code (CDK-LNG)
- 10. Out of scope / handled elsewhere
- Sources

## How to apply

The language-neutral principles and architecture smells (DRY, KISS, YAGNI, SOLID, Law of Demeter,
composition over inheritance, cohesion and coupling, leaking abstractions, layer skipping, cyclic, hub-like
and unstable dependencies, god components, feature envy, scattered functionality) are defined once in
`${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`. This file gives their CDK
manifestation only. A check marked "(stack form of ARC-04)" applies that shared entry: when a finding
rests on it, put both IDs in the finding (`CDK-ARC-01 (ARC-04)`), follow the shared file's rule that a
principle finding names its concrete cost, and weigh the tensions it lists (DRY against acceptable
duplication, YAGNI against extension points). Where the plan and the project's rules do not settle a
design intent, do not report the preference: report only a concrete cost, marked `unsure`, at the
severity that cost earns, as the shared file says.

Evidence rule. A diff shows code; it does not show deployment frequency, out-of-repository importers of
an export, whether a file holds a secret, what CI has installed, or whether a test was red before the
change. Use what the review has: the repository, the plan's inventory, the synthesised templates and
asset manifests in `cdk.out` (in a review, the snapshot's `synth/change.out`), CI configuration and the supplied test and synth output. A finding that
needs evidence none of those holds is reported `unsure, needs runtime verification` and listed under
"Needs runtime verification" in the SKILL.md report; it is never stated as fact. Report one finding per failure mode, under the check
that names its root cause, and cite related checks in the text rather than reporting them again.

Reviewer split, matching `review.md` and `skills/reviewing-cdk-changes/SKILL.md` step 2:

- **`implement-from-spec:code-reviewer`** (review.md groups 1 to 3 and 6 to 8): sections 1 to 4 and 7
  to 9 of this file. Sections 1, 2 and 7 land in group 6 (CDK mechanics, which here includes construct
  design); section 3 in group 2 (Data safety and logical IDs); section 4 in group 3 (Cross-stack contract)
  for CDK-ENV-09 and CDK-ENV-10 and in group 6 for the rest, except CDK-ENV-08, which lands in group 8
  (Deploy path); section 8 in group 7 (Tests); section 9 in group 6 and in the app-code language review the
  code reviewer's brief assigns (`references/reviewer-briefs.md`: the Python lenses or the Java dimensions)
- **`implement-from-spec:iac-security-reviewer`** (review.md groups 4 and 5): section 5 in group 4 (IAM)
  and section 6 in group 5 (Secrets and data exposure). Its own checklist (`skills/iac-security-reviewer/SKILL.md`)
  supplies the depth; the checks here name the CDK constructs, methods and cdk-nag rule IDs that make a
  finding concrete
- review.md group 1 (Specification fidelity) and the evidence rules of group 8 are not restated here; they
  apply as written
- A check outside a reviewer's sections that it happens to see is reported in one line and left to the
  owner, as `skills/code-reviewer/SKILL.md` says. Report each finding in review.md's output format with the check
  ID in the problem text, for example `[Major] infra/storage_stack.py:42 - 6 CDK mechanics - CDK-ENV-01
  account ID literal in the role ARN ...`

Python and Java spell the same API differently: Python uses `snake_case` keyword arguments
(`removal_policy=RemovalPolicy.RETAIN`, `bucket.grant_read(fn)`), Java uses builders and `camelCase`
(`Bucket.Builder.create(this, "Id").removalPolicy(RemovalPolicy.RETAIN).build()`, `bucket.grantRead(fn)`).
A check names the Python form first and the Java form where it differs by more than case.

Severity classes. The main conversation sets the final severity from
`skills/reviewing-cdk-changes/references/standalone-review.md` section 4; the defaults below are consistent with it and with review.md's Blocker classes. Apply review.md's
Blocker classes first: a per-check default holds only when no Blocker condition is established, so a
demonstrated synthesis failure, red test, replaced stateful resource or still-imported export changed is
a Blocker whatever the check below says. A latent path (an input no current caller passes) keeps the
check's default.

- **Blocker**: a stateful resource this change can delete or replace (including through a changed
  construct ID or path); a secret exposed in code, context, environment variables, Outputs or the template;
  an IAM wildcard or a public principal with no accepted reason; public access, or encryption weaker
  than the items require, on data they keep private; a removed or renamed export still imported; a change that cannot synthesise
  or fails validation; red tests; an unplanned dependency
- **Major**: a defect that bites on a later deploy, in another account, Region or stage, or that silently
  weakens a safeguard: a hand-written policy where a grant exists, a removal policy left to the construct
  default, hard-coded account or Region inside a construct, synth-time non-determinism, token misuse that
  renders a wrong template, a snapshot test as the only proof, a cdk-nag acknowledgement without a reason
  or wider than one construct
- **Minor**: worth fixing in this change if quick: a construct API that leaks the CloudFormation layer,
  boolean behaviour toggles, duplicated construct configuration, test hygiene
- **Nit**: optional polish (props naming, import style, documentation of defaults)

## 1. Principles and architecture smells (CDK-ARC)

### CDK-ARC-01 God stack: logic built in the stack, not in constructs

- **Look for:** a `Stack` subclass whose constructor instantiates many resources of several logical units
  directly (bucket, queue, functions, alarms and API in one `__init__` or constructor), loops and
  conditionals over resource configuration inside the stack, a change that adds another logical unit
  inline instead of in a construct
- **Why it matters:** the stack becomes the only unit of reuse and test, so nothing can be composed into
  another deployment shape (stack form of ARC-04 and PRN-03)
- **Instead:** one `Construct` subclass per logical unit (`class Ingestion(Construct)`), and stacks that
  only instantiate and wire constructs; extract the new unit first rather than moving deployed stateful
  resources (that is a CDK-STA-01 change)
- **Severity:** Minor, marked `unsure` when the units' boundaries depend on intent; Major when the change adds
  an unrelated logical unit to a stack that already holds two or more, as the shared ARC-04 rates a new
  responsibility. A small stack declaring several resources of one unit directly is not a finding
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "represent each logical unit
  as a Construct, not as a Stack. Use stacks only to describe how your constructs should be composed and
  connected"

### CDK-ARC-02 Stack used as the unit of reuse

- **Look for:** a stack class instantiated several times in one environment to get several copies of a
  resource group when the plan does not make each copy its own deployment unit; a stack parametrised by
  flags so it can play different roles; a new stack created only to share code between two others.
  One stack class per stage or tenant, deployed separately on purpose, is not a finding (stack form of
  PRN-13)
- **Why it matters:** every reuse adds a deployment unit, cross-stack references and an independent
  rollback; reuse belongs to constructs, deployment to stacks
- **Instead:** extract the group into a construct and instantiate it inside the existing stacks; add a
  stack only for a deployment reason (lifecycle, ownership, environment, quota)
- **Severity:** Minor
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Stacks are the unit of
  deployment: everything in a stack is deployed together"

### CDK-ARC-03 Stack boundaries that ignore lifecycle

- **Look for:** a new stateful resource (table, bucket, database, key, user pool) added to a stack that
  holds the app's frequently changed stateless resources (functions, APIs); a new stateful resource
  nested deep inside a construct the plan expects to restructure; or the opposite, a new stack split off
  with no deployment reason. How often a stack is deployed is not in the diff: take it from the plan or
  the project's rules, otherwise mark the finding `unsure`
- **Why it matters:** stateful resources in a frequently changed stack share every change set and every
  refactor; a split without a reason adds cross-stack coupling for nothing (stack form of PRN-12 and
  PRN-08)
- **Instead:** for new stateful resources, their own stack (with termination protection, CDK-STA-07) and
  a place near the stack root; otherwise keep resources together. Never move an existing stateful
  resource only to improve the layout: that is a CDK-STA-01 change with its own workflow
- **Severity:** Minor; Major when the change moves an existing stateful resource into a stack the plan
  marks as frequently deployed
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Consider keeping stateful
  resources (like databases) in a separate stack from stateless resources"; "keep them together unless you
  know you want them separated"

### CDK-ARC-04 Cyclic, upward or hub-like stack dependencies

- **Look for:** two stacks passing constructs to each other; `add_dependency` / `addDependency` both
  ways; a lower layer (network, data) consuming a value from an application stack; a "Common" or "Shared"
  stack that both feeds many stacks and itself consumes values from feature stacks, or that the change
  grows in both directions. A foundation stack with many consumers and no outgoing feature dependencies
  is not a hub
- **Why it matters:** CDK rejects cycles at synthesis; an upward dependency means the foundation cannot be
  rebuilt without its consumers; a hub stack couples every owner's release to one change set (stack form
  of ARC-03, ARC-02, ARC-05 and ARC-06)
- **Instead:** move the shared value down a layer, or into a lower stack both depend on; split the hub by
  owner and lifecycle
- **Severity:** Blocker when synthesis fails; Major for an upward dependency that synthesises; Minor for a
  hub stack
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md — "Cyclic
  dependencies are not allowed, so if `stackA` is using resources from `stackB`, the reverse is not possible
  anymore"; `cdk-practices.md` section 1 (layered stacks)

### CDK-ARC-05 Reaching into another construct's internals

- **Look for:** `node.find_child("...")` / `getNode().findChild("...")`, `node.try_find_child` or indexing
  `node.children` to reach a named child of a construct the code does not own (another team's construct,
  a third-party library, an L3 pattern's inner resources), then mutating it. The documented
  `node.default_child` escape hatch on an L2 (CDK-API-07) is a different, supported case. This is the
  primary check for tree reach-in; CDK-API-02 and CDK-API-07 cite it rather than report it again
- **Why it matters:** the code depends on another construct's tree, which its owner may restructure; for
  aws-cdk-lib constructs the tree is part of the construct's contract, so the risk sits mainly with
  project and third-party constructs (stack form of ARC-08, ARC-17 and PRN-10)
- **Instead:** a prop or method on the owning construct, or a Mixin where the pinned version has one; if
  the owner cannot change, wrap the reach-in in one place with a comment naming the missing prop and a
  test that fails when the child is not found
- **Severity:** Minor; Major when the target is a third-party or another team's construct whose child IDs
  it does not document
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/cfn-layer.html — "When Mixins and Facades don't
  cover your use case, you can use escape hatches and raw overrides to customize constructs at a lower
  level"; https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "treat the construct
  hierarchy and all construct IDs as part of the **external contract** of the construct" (the reason
  library trees are stable)

### CDK-ARC-06 Duplicated construct configuration

- **Look for:** the same block of props (encryption, versioning, block public access, log retention,
  alarm thresholds) copied into two or more constructs or stacks that encode the same rule; a second
  near-identical function definition differing in one value. Two similar configurations owned by
  independently evolving services are acceptable duplication (PRN-02); mark `unsure` when the diff does
  not show whether they encode one rule. This is the primary check for copied configuration; CDK-SYN-05
  covers enforcing a rule across the tree
- **Why it matters:** the copies drift, and a security default fixed in one copy stays wrong in the others
  (stack form of PRN-01, balanced against PRN-02)
- **Instead:** a project construct or a factory function that returns the configured construct, used
  everywhere; values that differ become props
- **Severity:** Minor; Major when the copies already disagree on a security or retention setting
- **Source:** https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/organizing-code-best-practices.html —
  "a factory can serve as a single source of truth to help you avoid repetitive code"

### CDK-ARC-07 Wrapper constructs as the only compliance control

- **Look for:** a change that removes a cdk-nag pack, an Aspect or a Guard rule because a company wrapper
  (`SecureBucket(s3.Bucket)`) "already enforces it"; a wrapper that hides the L2 API so standard and
  third-party constructs cannot be used
- **Why it matters:** wrappers are bypassed by any construct that creates the resource directly
  (including L3 patterns), so the guarantee is weaker than it looks
- **Instead:** keep the wrapper for defaults and enforce with Aspects, cdk-nag, cfn-guard or
  organization policies
- **Severity:** Major when a check is removed; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "This pattern is useful for
  surfacing security guidance early in the software development lifecycle, but don't rely on it as the sole
  means of enforcement"

## 2. Construct API and abstraction (CDK-API)

### CDK-API-01 L1 construct where an L2 exists

- **Look for:** a new `Cfn*` construct (`s3.CfnBucket`, `dynamodb.CfnTable`, `iam.CfnRole`) for a
  resource the library models as an L2 (`s3.Bucket`, `dynamodb.TableV2` or `Table`, `iam.Role`) that
  supports the configuration the items need, with hand-set properties the L2 would default (encryption,
  public access block, removal policy)
- **Why it matters:** the L1 carries only CloudFormation's and the service's defaults, none of the L2's
  safeguards or CDK's retain default, so every safeguard is manual
- **Instead:** the L2; keep an L1 where no L2 or L3 exists or the pinned L2 lacks the needed feature (a
  supported escape hatch), and then add the safeguards by hand. Removal policy: CDK-STA-04
- **Severity:** Minor; the removal-policy defect is reported once, under CDK-STA-04
- **Source:** https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/constructs-best-practices.html —
  "We recommend that you only use an L1 construct if you can't find the L2 or L3 construct for it";
  https://docs.aws.amazon.com/cdk/v2/guide/cfn-layer.html — "there are L2 constructs for the service,
  but these don't yet expose the feature"

### CDK-API-02 L3 pattern whose defaults the items contradict

- **Look for:** an L3 pattern (`ecs_patterns.ApplicationLoadBalancedFargateService`,
  `apigateway.LambdaRestApi`) adopted and then patched through escape hatches to undo the defaults its
  props do not expose (public load balancer, proxy integration, generated roles); reach-in to its
  children is reported under CDK-ARC-05
- **Why it matters:** the pattern was chosen for assumptions the items contradict, so each patch works
  against the abstraction instead of using it, and the template's real behaviour lives in the patches
- **Instead:** first the pattern's own props; when the items contradict its core assumptions (what it
  exposes, which integration it builds), compose the needed L2s in a project construct. Judge by whether
  the pattern's purpose still holds, not by counting overrides
- **Severity:** Minor; Major when a patched default is a security setting
- **Source:** https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/constructs-best-practices.html —
  "As construct levels get higher, more assumptions are made as to how these constructs are going to be
  used"

### CDK-API-03 Construct API that leaks the CloudFormation layer

- **Look for:** project-construct props typed with `Cfn*` types or `Cfn*.XxxProperty` structs, raw
  CloudFormation dictionaries as props, a public attribute that exposes the inner L1
  (`self.cfn_bucket = bucket.node.default_child`), props typed `typing.Any`, `object` or `IResolvable`
- **Why it matters:** callers now depend on the template shape, so the construct cannot change its
  implementation (stack form of ARC-01)
- **Instead:** intent-based props and construct interfaces (`encryption_key: kms.IKey`), and attributes
  for the values callers need (`bucket_arn`)
- **Severity:** Minor; Major in a construct library shared across apps
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "Do not “leak” the
  details or types of the CFN layer when defining your construct API" (awslint:props-no-cfn-types;
  awslint:props-no-tokens)

### CDK-API-04 Strings and concrete classes where interfaces belong

- **Look for:** props such as `table_arn: str`, `bucket_name: str`, `role_arn: str` for resources the app
  defines when the construct then needs grants, metrics or other capabilities of the resource; props typed
  with the concrete class (`bucket: s3.Bucket`, Java `Bucket bucket`) instead of the interface
  (`s3.IBucket`, or `s3.IBucketRef` where the app's CDK version has reference interfaces); an interface
  prop that the body casts to the concrete class, or a construct that accepts imported resources but
  then calls methods that only work on resources the app creates (CDK-IAM-05)
- **Why it matters:** a string attribute such as `bucket.bucket_arn` still carries its token and its
  reference, but not the resource's grant and metric methods, so the construct rebuilds them by hand; a
  literal ARN or name carries neither. A concrete class or a cast rejects imported resources
  (`Bucket.from_bucket_name`) that satisfy the declared type (stack form of PRN-05, PRN-06 and PRN-07)
- **Instead:** accept the narrowest interface that offers what the construct calls; a string is right
  when an identifier is all the construct needs. Which L1, L2 and imported types implement a reference
  interface depends on the version: verify in the CDK API reference
- **Severity:** Minor; Major when a cast or an unsupported operation breaks a path the items specify
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "instead of
  **keyArn**, use **kms.IKey**" (awslint:props-no-arn-refs); "you should accept them by an interface, not
  by their class" (awslint:ref-via-interface); https://docs.aws.amazon.com/cdk/v2/guide/constructs.html —
  "When configuring construct properties that reference other AWS resources, you have two equivalent
  options" (string references and object references)

### CDK-API-05 Boolean props that switch behaviour

- **Look for:** `is_prod`, `use_vpc`-style boolean props that select between two different designs or
  stage behaviours; two or three booleans that are valid only in certain combinations; a construct whose
  body is mostly `if props.flag:` branches. A single capability switch (`enable_logging`) that adds one
  optional feature is not a finding (stack form of PRN-03)
- **Why it matters:** each flag doubles the configurations to test and hides two constructs behind one
  name; stage differences belong in stage code, not in flags threaded through constructs
- **Instead:** separate constructs or factory methods for distinct behaviours; an enum-like class for a
  choice; a required-together nested struct for co-dependent values; per-stage configuration objects
- **Severity:** Minor
- **Source:** https://martinfowler.com/bliki/FlagArgument.html — "My general reaction to flag arguments
  is to avoid them"; https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "Properties
  that are mutually exclusive rather than required-together are usually better modeled with factory
  methods or subtypes"

### CDK-API-06 Props surface: too many, required without need, undocumented defaults

- **Look for:** a project construct whose props mirror every L1 property one-to-one, or that forwards a
  whole `BucketProps`/`FunctionProps` plus its own; required props that have an obvious default; optional
  props whose docstring or Javadoc does not say what happens when they are omitted; artificial nesting of
  independent props (awkward in Java builders)
- **Why it matters:** the construct stops encapsulating anything (stack form of SML-03), and callers
  cannot tell the default behaviour without reading the code
- **Instead:** expose the few props callers vary, default the rest, document each default as behaviour
  ("default - a new KMS key is created"), keep independent props flat
- **Severity:** Minor; Nit for documentation only
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "A prop should be
  *required* only if there is no possible sensible default value that can be provided *or calculated*"
  (awslint:props-default-doc)

### CDK-API-07 Escape hatches and raw overrides

- **Look for:** `node.default_child` casts, `add_property_override`, `add_override`,
  `add_deletion_override`, `add_property_deletion_override` / Java `addPropertyOverride`; an override path
  string (`"Properties.VersioningConfiguration.Status"`) for a property the L2 exposes; overrides scattered
  through stacks rather than wrapped in one construct; a second L2 created over an extracted L1
  (`Bucket.from_cfn_bucket(cfn_bucket)`)
- **Why it matters:** overrides "bypass all typing", so a misspelt path synthesises silently, and the
  cdk-nag README (v3, read 2026-10-16) says raw-override fixes are not caught by cdk-nag, so a security
  fix made by override needs its own test (verify against the app's cdk-nag version and whether it runs
  as an Aspect or a template validator)
- **Instead:** in order: the L2 prop; a Mixin where the app's CDK version has one (v2.241.0 and later); a
  typed L1 property set on `node.default_child` of an L2 that lacks the feature (a documented, supported
  escape hatch, not a finding by itself); a raw override only where no typed property exists. Wrap what
  remains in the construct that owns it, with a comment naming the missing feature, and verify the
  property path in the Template Reference
- **Severity:** Minor; Major when an override sets a security or retention property with no assertion
  test, or its path does not exist in the Template Reference
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/cfn-layer.html — "you can bypass all typing using
  raw overrides"; "do not create multiple L2 constructs that refer to the same L1 construct";
  https://github.com/cdklabs/cdk-nag/blob/main/README.md — "Since raw overrides take place after template
  synthesis these fixes are not caught by cdk-nag"

### CDK-API-08 Inheritance where composition belongs

- **Look for:** a subclass of an L2 (`class AuditBucket(s3.Bucket)`) that also creates unrelated
  resources (alarms, functions, queues) in its constructor; a deep chain of construct subclasses; a
  subclass that overrides library methods
- **Why it matters:** the subclass inherits the L2's whole mutable API and breaks when the base changes;
  an "is a" relationship that is really "has a" (stack form of PRN-11)
- **Instead:** extend an L2 only to set defaults on the same resource; otherwise a `Construct` that
  composes the L2 and the extra resources
- **Severity:** Minor
- **Source:** https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/constructs-best-practices.html —
  "Composition is the better choice when there's a "has a" relationship with an existing construct";
  https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "Prefer representing polymorphic
  behavior through interfaces and not through inheritance"

### CDK-API-09 Environment variable lookups inside constructs and stacks

- **Look for:** `os.environ[...]`, `os.getenv(...)`, `System.getenv(...)` below the app entry point (in a
  construct or stack class), deciding names, sizes, account, Region or which resources exist
- **Why it matters:** the template depends on the machine that synthesises it, so CI and a developer
  laptop produce different infrastructure from the same commit (stack form of PRN-16)
- **Instead:** read the environment once in `app.py` / `main()` and pass values as props
- **Severity:** Major when the value changes resources or their properties; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Environment variable
  lookups inside constructs and stacks are a common anti-pattern"

### CDK-API-10 Error handling in construct code

- **Look for:** `try`/`except` (Java `try`/`catch`) around construct creation that falls back to another
  resource or swallows the error and carries on with the partly built construct;
  `Annotations.of(self).add_warning(...)` for a misconfiguration that must stop the deploy;
  `node.add_validation` used for a prop that is known in the constructor; error messages that name
  internals rather than the prop the caller set
- **Why it matters:** CDK errors are unrecoverable, so a caught error leaves a half-built tree; a
  warning does not fail synthesis without `--strict`, so the misconfiguration ships (stack form of PRN-14)
- **Instead:** three distinct tools: validate props known at construction in the constructor and raise
  (`ValueError` / `IllegalArgumentException`) naming the prop and the value; `node.add_validation` for
  an invariant that holds only once composition is complete (an add-method that was never called);
  `Annotations.of(self).add_error` for environmental failures such as a missing lookup value. Do not
  catch CDK errors to continue building
- **Severity:** Major when an error is swallowed or a blocking check is only a warning; Minor otherwise
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "All CDK errors are
  unrecoverable"; "Never Catch Exceptions"; "In the rare case where the integrity of your construct can
  only be checked after the app has completed its initialization, call the **this.node.addValidation()**
  method"; "Errors will not allow deployment and warnings will only be displayed in highlight (unless
  `--strict` mode is used)"

### CDK-API-11 Children created outside the owning construct's scope

- **Look for:** a project construct that creates its own resources with the caller's `scope` instead of
  `self` / `this`; a helper function that creates resources under a module-level or global stack; a
  resource created directly under `App` or a `Stage` rather than a stack; a change to the scope argument
  of an existing resource
- **Why it matters:** the children escape the construct's boundary, so the construct's Aspects, tags and
  tests miss them and sibling IDs can collide; changing the scope of a deployed resource changes its
  path and logical ID (CDK-STA-01)
- **Instead:** create owned resources under `self` / `this`; pass a scope into a helper explicitly and
  keep existing paths unchanged
- **Severity:** Major; Blocker when synthesis fails or an existing stateful resource's path changes
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/constructs.html — "You should usually pass `this`
  (`self` in Python), which represents the current object, for the scope"; "All constructs that represent
  AWS resources must be defined, directly or indirectly, within the scope of a `Stack` construct"

## 3. Construct identity and stateful resources (CDK-STA)

### CDK-STA-01 Construct ID or tree path of an existing resource changed

- **Look for:** a changed string ID on an existing construct (`s3.Bucket(self, "Uploads")` becomes
  `"UploadsBucket"`); an existing construct moved under a new parent construct or another stack; a parent
  construct's ID changed (every child's logical ID changes); a wrapping construct that does not give the
  moved child the ID `Default`
- **Why it matters:** the logical ID changes, so CloudFormation creates a new resource under the new ID
  and removes the old one from the stack; the old one's `DeletionPolicy` decides whether it is deleted or
  orphaned, and either way the stack now serves a new, empty resource. Claim a changed logical ID only
  after comparing the synthesised IDs with the plan's inventory or the base branch's `cdk.out`
- **Instead:** keep the ID; when wrapping, give the inner construct the ID `Default` in the position the
  original construct held (`cdk-practices.md` section 3): it preserves the logical ID only for that
  wrap, not for a move to another parent or stack; a wanted rename is a separate `cdk refactor` change
- **Severity:** Blocker for a stateful resource or one holding identity (VPC, key, user pool); Major for
  a stateless resource whose replacement interrupts service
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Changing the logical ID of a
  resource results in the resource being replaced with a new one at the next deployment"

### CDK-STA-02 Construct IDs derived from unstable inputs

- **Look for:** IDs built from a loop index or list position (`f"Queue{i}"`, `enumerate(...)`), from a
  value read from context or configuration that can change, from a dictionary iteration whose order is
  not fixed, or concatenated to force uniqueness (`"Bucket" + name + env`)
- **Why it matters:** inserting an item, reordering a list or renaming a stage shifts IDs and replaces
  every resource after it
- **Instead:** IDs from a stable key of each item (its name in the specification); a namespace
  `Construct(self, "PrivateSubnets")` instead of concatenation
- **Severity:** Major; Blocker when the change itself reorders or inserts items in front of deployed
  stateful resources
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "any change to a
  logical ID in this path will invalidate all the logical IDs within this scope"; "There is no need to
  concatenate logical IDs"

### CDK-STA-03 Hard-coded physical names

- **Look for:** `bucket_name=`, `table_name=`, `function_name=`, `role_name=`, `queue_name=` (Java
  `.bucketName(...)`) with a literal or stage-built string that no item pins
- **Why it matters:** the stack cannot be deployed twice in one account, and any update that needs
  replacement fails because the new resource cannot take the name
- **Instead:** omit the name and pass `bucket.bucket_name` to consumers; use
  `PhysicalName.GENERATE_IF_NEEDED` where cross-environment references need one
- **Severity:** Major when the same change touches a property whose update behaviour is Replacement (the
  update then fails); Blocker when that resource is stateful, because the change itself is a replacement
  (review.md Blocker class); Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "you can't make changes to the
  resource that require it to be replaced"; https://docs.aws.amazon.com/cdk/v2/guide/resources.html
  (PhysicalName.GENERATE_IF_NEEDED)

### CDK-STA-04 Removal policy left implicit

- **Look for:** a new stateful L2 with no `removal_policy=` (relying on the construct default); a
  stateful L1 or an L2 without a `removal_policy` prop and no `apply_removal_policy(...)`; in `cdk.out`, a
  stateful resource without both `DeletionPolicy` and `UpdateReplacePolicy`
- **Why it matters:** L2 defaults differ by construct and version, and L1s have no CDK default at all,
  so CloudFormation's default applies: delete for most types, snapshot for RDS DB clusters and for DB
  instances outside a cluster. The two attributes protect different events and neither covers the other:
  `DeletionPolicy` applies when the resource is removed from the template or the stack is deleted,
  `UpdateReplacePolicy` decides what happens to the old physical resource when an update replaces it
- **Instead:** set the policy the items require explicitly and assert both attributes in a test
  (CDK-TST-04); an Aspect can enforce it app-wide (CDK-SYN-05)
- **Severity:** Major for an L2 on its default, and for a missing `UpdateReplacePolicy` alone; Blocker for
  a stateful resource the items keep whose template has no `DeletionPolicy` and whose type defaults to
  delete. This is the primary check for policy defaults; CDK-API-01 does not report them again
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Consider carefully what you
  want these policies to be for each production resource and specify them accordingly";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html —
  "If a resource has no `DeletionPolicy` attribute, CloudFormation deletes the resource by default";
  "The default policy is `Snapshot` for `AWS::RDS::DBCluster` resources"; "This capability doesn't apply
  to resources whose physical instance is replaced during stack update operations"; `cdk-practices.md`
  section 4

### CDK-STA-05 DESTROY or auto-delete on kept data, or gated by a flag

- **Look for:** `RemovalPolicy.DESTROY` or `auto_delete_objects=True` on a resource the items keep;
  either one selected by a boolean, context value or stage name (`DESTROY if not is_prod else RETAIN`);
  `auto_delete_objects` without noticing the custom resource and the `s3:PutBucketPolicy` grant it adds
- **Why it matters:** a mis-set flag in the production stage deletes data on the next stack removal;
  auto-delete adds a Lambda-backed custom resource and a bucket-policy permission to the stack
- **Instead:** `RETAIN` (or `SNAPSHOT` where supported) for kept data; DESTROY only in stages the items
  name, decided by stage code with a test per stage that asserts the policy
- **Severity:** Blocker on data the items keep; Major when gated by a context or environment string
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3/README.md — "When
  `autoDeleteObjects` is enabled, `s3:PutBucketPolicy` is added to the bucket policy"; `cdk-practices.md`
  section 4

### CDK-STA-06 Log groups without retention or with the legacy retention mechanism

- **Look for:** new functions or services whose log group the service creates implicitly (kept with no
  expiry); `log_retention=` on a Lambda function (the deprecated custom-resource mechanism) in new code;
  an explicit `logs.LogGroup` without `retention` (it then defaults to two years, not to the items'
  period) or without `removal_policy`; an existing function switched from `log_retention` to `log_group`
  without noting that the log group's name changes
- **Why it matters:** implicitly created log groups keep data with no expiry, which grows cost and keeps
  data past its retention requirement; the deprecated property adds a `Custom::LogRetention` resource
  and its provider function; switching mechanisms on a deployed function moves logging to a new log group,
  so consumers of the old name and the old history are affected
- **Instead:** an explicit `logs.LogGroup(retention=..., removal_policy=...)` passed as `log_group=`
  (verify the prop in the app's CDK version); for a migration, update every reference to the log group
  name in the same change
- **Severity:** Minor; Major when the items set a retention period
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "the CDK's default is to
  retain all logs forever"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-logs/lib/log-group.ts —
  `retention` "@default RetentionDays.TWO_YEARS";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-lambda/lib/function.ts — `logRetention`
  "This is a legacy API"; "Migrating from `logRetention` to `logGroup` will cause the name of the log
  group to change"

### CDK-STA-07 Deletion and termination protection missing

- **Look for:** a stateful stack without `termination_protection=True` (Java `.terminationProtection(true)`
  in `StackProps`); a database, table or user pool without its `deletion_protection` prop; cdk-nag
  `AwsSolutions-RDS10`
- **Why it matters:** each protection covers a different event. `DeletionPolicy` acts when the resource
  leaves the template or the stack is deleted; stack termination protection rejects a stack deletion but
  not the removal of a resource through an update; a resource's own deletion protection blocks a delete
  through the service's API, including one made outside CloudFormation
- **Instead:** turn on termination protection for stateful stacks and deletion protection on resources
  that have it, in addition to the removal policy (CDK-STA-04)
- **Severity:** Major for a resource's deletion protection the items or project rules require; Minor for
  stack termination protection
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "You can then turn on
  termination protection on the stateful stack";
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html —
  "Termination protection applies only to attempts to delete stacks";
  https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-RDS10

### CDK-STA-08 Logical-ID overrides and custom ID allocation

- **Look for:** `override_logical_id(...)` / `overrideLogicalId(...)` added, changed or removed on an L1
  or `node.default_child`; a `Stack` subclass overriding `allocate_logical_id` / `allocateLogicalId`; IDs
  computed by a project helper; a CDK upgrade or feature-flag change in the same diff that alters ID
  generation (CDK-ENV-08)
- **Why it matters:** an override replaces path-based IDs, so the usual reasoning about construct paths no
  longer predicts the template: removing or changing an override replaces the resource, and two equal
  overrides collide; a changed allocator re-keys every resource in the stack
- **Instead:** compare the synthesised IDs with the plan's inventory and keep a characterisation test
  (CDK-TST-03); keep an override that a deployed resource relies on; never add one only for nicer
  template names; a wanted ID change is a separate `cdk refactor` change
- **Severity:** Major; Blocker when the change replaces an existing stateful resource or synthesis fails
  on a duplicate ID
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/cfn-element.ts —
  `overrideLogicalId` "Overrides the auto-generated logical ID with a specific ID";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/stack.ts — `allocateLogicalId`
  "If a component is named "Default" it will be omitted from the path"

## 4. Environments, context and cross-stack references (CDK-ENV)

### CDK-ENV-01 Account, Region or partition hard-coded inside constructs

- **Look for:** 12-digit account literals, Region strings (`"us-east-1"`) or `"arn:aws:..."` literals in
  construct or stack code; ARNs assembled by string formatting or `Fn.sub` with embedded logical IDs
- **Why it matters:** the code breaks in another account, Region or partition (GovCloud, China) and the
  string hides the reference CDK would otherwise track (stack form of ARC-15)
- **Instead:** `Stack.of(self).account`, `.region`, `.partition`, `Stack.of(self).format_arn(...)`, or the
  construct's attribute (`bucket.bucket_arn`); concrete environments belong only in the `env=` at the app
  entry point
- **Severity:** Major; Blocker when the literal ARN grants IAM access to another account (CDK-IAM-06)
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md — "`formatArn()` can
  be used to build an ARN from components. It will automatically use the region and account of the stack";
  https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "Do not use `Fn::Sub` in constructs"

### CDK-ENV-02 Production environment taken from the synthesising machine

- **Look for:** a production stage or stack whose `env` uses `CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION`
  (`os.environ[...]`, `System.getenv(...)`), or a production stack with no `env` at all, while the plan
  targets a specific account
- **Why it matters:** the same commit synthesises a different template depending on who runs it, and an
  environment-agnostic template can deploy to whatever profile is active
- **Instead:** hard-code the account and Region of each production stage in the app entry point; keep
  the environment-variable form for development stacks
- **Severity:** Major for production stages; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/configure-env.html — "we do not recommend this
  approach for production environments since the same CDK code can synthesize different templates"

### CDK-ENV-03 Environment logic in an environment-agnostic stack

- **Look for:** `if stack.region == "us-east-1":`, `fromLookup` / `from_lookup` calls, or logic on
  `availability_zones` in a stack instantiated without `env`
- **Why it matters:** in an agnostic stack `region` is a token, so the comparison is always false and the
  branch silently never runs; lookups fail, and AZ-dependent constructs see only two zones
- **Instead:** give the stack an explicit `env` or move the decision to deploy-time constructs
- **Severity:** Major; Blocker when the lookup makes synthesis fail
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/configure-env.html — "you cannot write code like
  `if (stack.region ==== 'us-east-1')` or use construct methods that require environment information such
  as `Vpc.fromLookup`"

### CDK-ENV-04 Context cache not committed or edited by hand

- **Look for:** `cdk.context.json` added to `.gitignore` or deleted; new `from_lookup` calls with no
  matching entry in a committed `cdk.context.json`; changed values in it that the change description
  does not explain (whether they were edited by hand is not visible in a diff: `unsure`);
  `cdk context --clear` in a build script
- **Why it matters:** CI either fails (lookups off) or re-queries the account and synthesises different
  infrastructure from the same commit
- **Instead:** commit `cdk.json` and `cdk.context.json`; refresh one entry deliberately with
  `cdk context --reset <key>` in its own change
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/context.html — "cdk.json and cdk.context.json must
  be committed to source control along with the rest of your app’s source code"

### CDK-ENV-05 Non-deterministic values at synthesis

- **Look for:** two different failure modes, reported separately. Synthesis-time non-determinism:
  `datetime.now()`, `uuid.uuid4()`, `random`, `Instant.now()` in resource properties, names or IDs, or
  values fetched by a script during every build, so each synthesis yields a different template.
  Deploy-time floating values: "latest" AMI helpers (`MachineImage.latest_amazon_linux2023()`) without
  `cached_in_context=True` on instances that hold state, which synthesise a stable SSM parameter
  reference whose value changes between deploys
- **Why it matters:** both make deploys replace or update resources nobody changed; the first shows as a
  template diff on every synth, the second shows no template diff at all
- **Instead:** pin values in code or context; for AMIs, `cached_in_context=True` or `MachineImage.lookup`
  (cached in `cdk.context.json`); refresh with a separate script on demand. Check the helper's synthesised
  form in `cdk.out` before claiming either mode
- **Severity:** Major; Blocker when the changing value forces replacement of a stateful resource
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "a subsequent deployment
  picks up the new AMI and replaces all your instances";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-ec2/README.md — "Since this retrieves
  the value from an SSM parameter at deployment time, the value will be resolved each time the stack is
  deployed"; `cachedInContext: true, // default is false`

### CDK-ENV-06 Context values used as if typed

- **Look for:** `if self.node.try_get_context("prod"):` or `bool(...)` on a context value; Java
  `(Boolean) getNode().tryGetContext("prod")` or an unchecked `(Integer)` cast; no `None`/`null` check on
  `try_get_context`
- **Why it matters:** context from `--context` is always a string, so `"false"` is truthy in Python and a
  `ClassCastException` in Java; a missing key returns `None`/`null`
- **Instead:** parse explicitly (`== "true"`, `Boolean.parseBoolean`), validate allowed values and fail
  synthesis on anything else
- **Severity:** Major when the value toggles removal policies, environments or exposure; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/context.html — "Context values passed from the
  command line are always strings"

### CDK-ENV-07 Deploy-time decisions through CloudFormation parameters and conditions

- **Look for:** new `CfnParameter`, `CfnCondition`, `Fn.condition_if` used to pick resources or values per
  environment; one parametrised stack expected to serve every stage
- **Why it matters:** the operations available are limited to CloudFormation's expression language, and
  the outcome depends on deploy-time input rather than on the commit, so a synthesis-time test sees the
  expression but not which branch a deploy takes
- **Instead:** decide in code at synthesis with `if` and per-stage props; model each stage as its own
  stack instance
- **Severity:** Minor
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "we recommend against using
  them. The types of values that you can use and the types of operations you can perform on them are
  limited"; "Model all production stages in code"

### CDK-ENV-08 Feature flags changed in cdk.json

- **Look for:** an `@aws-cdk/...` key under `context` in `cdk.json` added, removed or flipped, often
  alongside a CDK version bump
- **Why it matters:** flags enable potentially breaking behaviours, which can change logical IDs,
  policies or resource shapes across the whole app with no code change
- **Instead:** change flags in their own change, with a whole-app `cdk diff --method change-set`
  (`cdk-practices.md` section 10) as the evidence
- **Severity:** Major; Blocker when the change-set diff shows replacement of stateful resources
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/featureflags.html — "The AWS CDK uses feature flags
  to enable potentially breaking behaviors in a release"

### CDK-ENV-09 Strong cross-stack references created or removed in one step

- **Look for:** a consumer stack using an attribute of a construct from another stack in the same
  environment (a construct passed as a prop and then referenced in a resource property; the reference,
  not the prop, synthesises the export and `Fn::ImportValue`: confirm in `cdk.out`); a change that removes
  or replaces a resource, or a consumer's use of it, that another stack imports;
  `cross_region_references=True` on stacks (strong cross-Region references use custom resources)
- **Why it matters:** the "deadly embrace": CloudFormation cannot remove an export while it is imported,
  so the producer's update fails; cross-Region strong references depend on custom resources with a
  4096-byte response limit
- **Instead:** follow the project's cross-stack mechanism; to remove a shared resource, use one of two
  staged procedures, each a separate deploy, never one change. On aws-cdk-lib v2.254.0 or later:
  `CrossStackReferences.of(resource).produce(ReferenceStrength.BOTH)` and deploy both stacks, then `WEAK`
  and deploy both, then remove the resource. On older versions: remove the consumer's use while the
  producer keeps the exact existing export (`producer.export_value(resource.attr)`, matching the
  synthesised export name and value in `cdk.out`), deploy both stacks and confirm the consumer no longer
  imports it, then remove the temporary export and the resource in a later change. Whether importers
  outside the repository exist is deployed state: `unsure` unless the plan lists them
- **Severity:** Blocker when the change removes or changes an export still imported (review.md Blocker
  class); Major for a new strong reference where the project uses SSM parameters or weak references
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/resources.html — "CloudFormation cannot remove an
  export while another stack still imports it"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md —
  "Strong references create a *deadly embrace*"; resources.html, "Manual workaround (legacy)" — "manually
  add the same export to the producing stack using exactly the same logical ID as the automatically
  generated export"

### CDK-ENV-10 Hand-wired exports and outputs as runtime contracts

- **Look for:** `CfnOutput(..., export_name="...")` / `stack.export_value(...)` added "for later" with no
  importer; `Fn.import_value("literal-name")` in a consumer; application or runtime code that reads stack
  outputs (`DescribeStacks`) to find a resource; outputs that publish internal IDs nobody consumes
- **Why it matters:** an export becomes immutable once imported, a string-named import hides the
  dependency from CDK, and outputs are not available during stack updates
- **Instead:** pass constructs within an app; across apps use a `from_*` method with an ARN or name the
  items pin, or an SSM parameter; pass runtime values as environment variables or parameters
- **Severity:** Minor; Blocker when an existing export that is still imported is renamed or removed
  (review.md Blocker class, CDK-ENV-09); `unsure` when importers may live outside the repository
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html —
  "We don't recommend establishing dependencies between a service runtime and the stack output value";
  `cdk-practices.md` section 5 (exports are a contract)

## 5. IAM and grants (CDK-IAM)

### CDK-IAM-01 Hand-written policy statements where a grant exists

- **Look for:** `iam.PolicyStatement(actions=["s3:GetObject", ...], resources=[bucket.arn_for_objects("*")])`
  added with `add_to_policy`, `add_to_role_policy` or `add_to_principal_policy` (Java `addToPolicy`) for a
  resource the app owns that has `grant_*` methods or a `grants` property
- **Why it matters:** hand-written actions drift from what the resource needs (KMS decrypt for an
  encrypted bucket is a common omission or over-grant), and the grant's scoping is lost
- **Instead:** `bucket.grant_read(fn)` / `bucket.grantRead(fn)`, or `bucket.grants.read(fn)` where the
  app's CDK version has Grants classes
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "The AWS CDK grants only the
  minimal permissions required for the function to read from the bucket"

### CDK-IAM-02 Over-broad grants and wildcard statements

- **Look for:** `table.grant(role, "*")` or `grant(role, "dynamodb:*")`; `grant_full_access` or
  `grant_read_write` where the items need read; `resources=["*"]` on resource-scoped actions; cdk-nag
  `AwsSolutions-IAM5` findings
- **Why it matters:** the role can delete or rewrite data it only needs to read; a compromised function
  gets the whole service
- **Instead:** the narrowest named grant; for a generic `grant`, list the exact actions; resource ARNs
  from the construct
- **Severity:** Blocker for `*` actions or resources without the reason the items accept; Major for a
  broader named grant than the items need
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-IAM5 "The IAM entity
  contains wildcard permissions and does not have a cdk-nag rule suppression with evidence for those
  permission"

### CDK-IAM-03 AWS managed policies on workload roles

- **Look for:** `iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")`, `*FullAccess`,
  `PowerUserAccess` in `managed_policies=` or `add_managed_policy`; cdk-nag `AwsSolutions-IAM4`
- **Why it matters:** many AWS managed policies do not restrict resource scope, so the role reaches every
  resource of the service in the account
- **Instead:** grants or scoped statements; a managed policy only when the items name it (for example
  the Lambda basic execution role, with a reason in the acknowledgement)
- **Severity:** Blocker for administrator or full-access policies without an accepted reason; Major
  otherwise
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-IAM4 "Currently, many
  AWS managed policies do not restrict resource scope"

### CDK-IAM-04 Imported roles modified by the app

- **Look for:** `iam.Role.from_role_arn(self, "R", arn)` without `mutable=False` for a role another team or
  stack owns, followed by grants to it; `role.without_policy_updates()` missing where a construct must not
  add statements
- **Why it matters:** CDK attaches new policies to a role it does not own, widening another owner's
  principal from this app's deploy
- **Instead:** `mutable=False` and an explicit request to the owner for the permissions, or a role the
  app creates
- **Severity:** Major
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-iam/README.md — "The
  default is 'true', which means the role may be modified as part of the deployment"

### CDK-IAM-05 Grants and policy additions that silently do nothing

- **Look for:** `add_to_resource_policy` on an imported resource (`Bucket.from_bucket_name(...)`),
  `add_to_role_policy` on an imported construct whose role is undefined, a grant whose resource-policy half
  is skipped because the resource is imported
- **Why it matters:** synthesis succeeds and the permission is missing at runtime, discovered only as an
  access-denied error in production
- **Instead:** grant on the principal side the app owns, or have the resource's owner add the
  statement; assert the statement in a test
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/resources.html — "calling addToResourcePolicy
  (Python: add_to_resource_policy) on an external s3.Bucket does nothing";
  https://docs.aws.amazon.com/cdk/v2/guide/permissions.html — "The method does nothing if the construct is
  an external resource"

### CDK-IAM-06 Principals broader than the caller

- **Look for:** `iam.AnyPrincipal()`, `iam.StarPrincipal()`, `iam.ArnPrincipal("*")` in an **Allow**
  statement of a trust or resource policy; `iam.AccountRootPrincipal()` or `iam.AccountPrincipal(<other
  account>)` where the items name one role; a `grant_*` to another account's principal with no condition.
  Read the synthesised statement's `Effect` and `Condition` first: `AnyPrincipal` in a **Deny** (the
  statement `enforce_ssl=True` adds) narrows access and is not a finding
- **Why it matters:** with `*` in an Allow, the resource policy alone admits any caller the conditions do
  not exclude; an account principal delegates authority to the whole account, so any identity there that
  the account's own policies allow gets in, rather than the one caller the items name
- **Instead:** the specific role or service principal, with `conditions` (`aws:SourceArn`,
  `aws:SourceAccount`, `aws:PrincipalOrgID`) as the security reviewer's checklist describes
- **Severity:** Blocker for a public principal without a tightening condition or accepted reason; Major
  for an account root where one caller is specified
- **Source:** https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html —
  "We strongly recommend that you do not use a wildcard (*) in the Principal element"; "This delegates
  authority to the account. When you allow access to a different account, an administrator in that account
  must then grant access to an identity"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3/lib/bucket.ts —
  `enforceSSLStatement` uses `effect: iam.Effect.DENY` with `principals: [new iam.AnyPrincipal()]`

### CDK-IAM-07 AwsCustomResource with ANY_RESOURCE

- **Look for:** `cr.AwsCustomResource(..., policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE))`;
  several `AwsCustomResource` instances in one stack each adding grants
- **Why it matters:** the SDK call may act on any resource, and the stack's singleton provider function
  accumulates every instance's permissions
- **Instead:** `resources=[specific ARNs]` or `from_statements` with scoped statements
- **Severity:** Blocker for `ANY_RESOURCE` without a reason the items accept (a resource wildcard,
  review.md Blocker class), whether the calls read or write; Major for several instances whose scoped
  grants accumulate on the shared provider role
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/custom-resources/README.md —
  "the function's role will eventually accumulate the permissions/grants from all resources"

### CDK-IAM-08 Deploy-time consumers that race their grant

- **Look for:** a custom resource, `Trigger` or provider that calls a resource during deployment, granted
  with `grant_*` but with no dependency on the returned `iam.Grant`
- **Why it matters:** CloudFormation may invoke the consumer before the policy exists, failing the deploy
  intermittently
- **Instead:** `grant = bucket.grant_read(fn); custom.node.add_dependency(grant)`
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/permissions.html — "To force the grant’s
  permissions to be applied before another resource is created, you can add a dependency on the grant
  itself"

## 6. Secrets and data exposure (CDK-SEC)

### CDK-SEC-01 Plain-text secrets in code, props or context

- **Look for:** `SecretValue.unsafe_plain_text("...")` / `SecretValue.unsafePlainText(...)`, password or
  token literals in props, secrets in `cdk.json` context or passed with `--context`, a `CfnParameter`
  default value holding a secret. (`SecretValue.cfn_parameter` already throws unless the parameter has
  `no_echo=True`; `NoEcho` masks the value in describe calls but not in a template default)
- **Why it matters:** the secret lands in the repository, the cloud assembly and the template, readable
  by anyone with access to any of them
- **Instead:** `SecretValue.secrets_manager("id", json_field="password")`, `secretsmanager.Secret` with
  generated values, or `SecretValue.ssm_secure`
- **Severity:** Blocker
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md —
  "`SecretValue.unsafePlainText(secret)`: stores the secret as plain text in your app and the resulting
  template (not recommended)"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/secret-value.ts —
  "CloudFormation parameter must be configured with "NoEcho""

### CDK-SEC-02 Secrets unwrapped into environment variables and strings

- **Look for:** `secret.secret_value.unsafe_unwrap()` / `unsafeUnwrap()` passed into Lambda `environment`,
  container `environment` (not `secrets`), tags, names or string concatenation; cdk-nag
  `AwsSolutions-ECS2`
- **Why it matters:** environment variables and resource properties are readable through describe calls
  and the console by anyone with read access, and many resources log them
- **Instead:** pass the secret's ARN or name and read it at runtime (`secret.grant_read(fn)`); ECS
  `secrets={"DB_PASSWORD": ecs.Secret.from_secrets_manager(secret)}`
- **Severity:** Blocker when a secret value reaches environment variables or tags; Major otherwise.
  Outputs are reported under CDK-SEC-03
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/secret-value.ts —
  "This method has 'unsafe' in the name on purpose!"; https://github.com/cdklabs/cdk-nag/blob/main/RULES.md —
  AwsSolutions-ECS2

### CDK-SEC-03 Sensitive values in CfnOutput

- **Look for:** `CfnOutput(value=...)` of a secret, a connection string with credentials, a generated
  password attribute, or a presigned URL
- **Why it matters:** outputs are stored and shown in plain text to anyone who can describe the stack
- **Instead:** output the secret's ARN or name, never its value
- **Severity:** Blocker
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html —
  "CloudFormation doesn't redact or obfuscate any information you include in the `Outputs` section"

### CDK-SEC-04 S3 exposure, transport and encryption

- **Look for:** a public grant path: `public_read_access=True`, `bucket.grant_public_access()`, or a bucket
  policy Allow to `AnyPrincipal` without a narrowing condition, together with `block_public_access`
  weakened from `BlockPublicAccess.BLOCK_ALL`; separately, `block_public_access` weakened with no grant yet
  (defence in depth); encryption weaker than the items require (`S3_MANAGED` where they name a KMS key,
  `encryption=BucketEncryption.UNENCRYPTED`); `enforce_ssl` missing or `False` on buckets, queues and
  topics (verify the prop in the CDK API reference); KMS keys without `enable_key_rotation=True`; cdk-nag
  `AwsSolutions-S2`, `-S10`, `-SQS4`, `-SNS3`, `-KMS5`
- **Why it matters:** the data becomes readable by anyone, or travels or rests weaker than the items
  require. An omitted setting is not exposure by itself: the L2's `block_public_access` default keeps new
  buckets non-public, and S3 encrypts every new object with SSE-S3 since 2023-01-05, so an omitted
  `encryption` means SSE-S3, not plaintext; compare the effective setting with what the items require
- **Instead:** `BLOCK_ALL`, `enforce_ssl=True`, encryption with the key the items name, key rotation on
  customer managed keys
- **Severity:** Blocker for a public grant path or encryption weaker than the items require on data they
  keep private; Major for missing TLS enforcement, key rotation, or a weakened public access block with no
  grant
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-S2 "The S3 Bucket does
  not have public access restricted and blocked"; AwsSolutions-S10 "The S3 Bucket or bucket policy does not
  require requests to use SSL"; https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html —
  "Starting January 5, 2023, all new object uploads to Amazon S3 are automatically encrypted";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3/lib/bucket.ts — `blockPublicAccess`
  "@default - CloudFormation defaults will apply. New buckets and objects don't allow public access"

### CDK-SEC-05 Network exposure through security groups

- **Look for:** `ec2.Peer.any_ipv4()` / `Peer.anyIpv4()` or `any_ipv6()` in `add_ingress_rule`,
  `connections.allow_from_any_ipv4(...)`, `allow_default_port_from_any_ipv4`, wide port ranges, and
  `allow_all_outbound=True` (the default) where the items restrict egress; cdk-nag `AwsSolutions-EC23`
- **Why it matters:** the security group admits traffic from any address, or lets the resource send to
  anywhere. Whether it is reachable from the internet also depends on the subnet's route to an internet
  gateway and a public address: report "permits ingress from any address" as the fact, and internet
  reachability only when the diff or `cdk.out` shows a public subnet or internet-facing load balancer
- **Instead:** `connections.allow_from(other_sg, port)` between constructs; explicit egress rules with
  `allow_all_outbound=False`
- **Severity:** Blocker for administrative or database ports open to any address on a resource in a
  public subnet or behind an internet-facing load balancer; Major otherwise, `unsure` when the placement
  is not in the change
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-EC23 "The Security
  Group allows for 0.0.0.0/0 or ::/0 inbound access"

### CDK-SEC-06 Unauthenticated endpoints

- **Look for:** `fn.add_function_url(auth_type=FunctionUrlAuthType.NONE)`; API Gateway methods whose
  effective authorization is none: `authorization_type=AuthorizationType.NONE`, or no authorizer on the
  method and none in `default_method_options` on the method's resource or the `RestApi` (methods inherit
  those defaults, so a method without a local authorizer may still be protected; read the synthesised
  `AuthorizationType`); REST APIs without request validation; cdk-nag `AwsSolutions-APIG4`, `-COG4`,
  `-APIG2`
- **Why it matters:** anyone who finds the URL can invoke the function or API
- **Instead:** `FunctionUrlAuthType.AWS_IAM`, an IAM, Cognito or Lambda authorizer, as the items specify
- **Severity:** Blocker when the items do not allow anonymous access; Minor for missing request
  validation alone
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/RULES.md — AwsSolutions-APIG4 "The API does not
  implement authorization"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-lambda/README.md —
  "To create a Function URL which can be called anonymously, pass `authType: FunctionUrlAuthType.NONE`";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-apigateway/README.md — "Unless
  explicitly overridden, the specified defaults will be applied across all `Method`s"

### CDK-SEC-07 Secret rotation not picked up by consumers

- **Look for:** a consumer resource other than the rotation target (an application setting, an endpoint
  or connection definition) that receives a Secrets Manager value through `SecretValue.secrets_manager`
  while the items expect rotation; a rotation schedule added with no plan for those consumers; cdk-nag
  `AwsSolutions-SMG4`. The rotation target itself (the database the rotation function updates) is not
  stranded by rotation
- **Why it matters:** CloudFormation re-reads the secret only when the consuming resource is updated, so
  after rotation that consumer keeps the old value until its next update
- **Instead:** consumers that read the secret at runtime and refresh it; trace the path from rotation
  function to target to every consumer before reporting. Forcing a property change on each rotation is a
  workaround the README describes, not a default
- **Severity:** Minor; Major when the items require rotation
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md — "you must also
  change at least one property on the resource where you are using the secret, to force CloudFormation to
  re-read the secret"

### CDK-SEC-08 cdk-nag acknowledgements that hide findings

- **Look for:** `Validations.of(app)` or `Validations.of(stack).acknowledge(...)` (cdk-nag v3), or
  `NagSuppressions.add_stack_suppressions` (v2), covering a rule for many constructs; a missing or
  formulaic `reason`; an `AwsSolutions-IAM5` acknowledgement without the finding-specific suffix
  (`AwsSolutions-IAM5[Action::s3:*]` in v3, `applies_to` in v2); an acknowledgement for a fix made only by a
  raw override (CDK-API-07); a removed nag pack
- **Why it matters:** a broad acknowledgement silences future violations of the same rule in that scope
  without anyone reviewing them
- **Instead:** acknowledge on the narrowest construct, per finding, with a reason that names the item
  or evidence; fix rather than acknowledge where a prop exists
- **Severity:** Major; Blocker when the acknowledgement covers a public-access, encryption or wildcard
  finding without an accepted reason
- **Source:** https://github.com/cdklabs/cdk-nag/blob/main/README.md — "In v3, each finding must be
  acknowledged individually"; https://docs.aws.amazon.com/cdk/v2/guide/policy-validation-synthesis.html
  ("Suppression is scope-based", quoted in `cdk-practices.md` section 7)

## 7. Synthesis mechanics: tokens, aspects, assets (CDK-SYN)

### CDK-SYN-01 Tokens parsed, inspected or validated at synthesis

- **Look for:** string operations on attributes or imported values (`bucket.bucket_name.split("-")`,
  slicing, `len(...)`, regex, `.startswith`, `.upper()`), indexing a token list (`subnet_ids[0]` where the
  list comes from a deploy-time value), arithmetic on number tokens; constructor validation such as
  `if len(props.name) > 63: raise ...` with no `Token.is_unresolved` guard
- **Why it matters:** the code operates on the placeholder text `${Token[TOKEN.21]}`, not the value, so
  the template contains garbage or the branch takes the wrong path, silently; unguarded validation
  rejects valid deploy-time references
- **Instead:** pass tokens through untouched; use `Fn.select`, `Fn.split`, `Fn.join` or
  `Stack.of(self).split_arn` for deploy-time manipulation; guard checks with
  `if not Token.is_unresolved(props.name) and ...`
- **Severity:** Major; Minor for an unguarded validation that no current caller hits
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/tokens.html — "if you attempt to parse a string to
  extract a value from it, and the string is an encoded token, your parsing fails";
  https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "don't forget to account for the
  fact that these values may be `Token`s and not available for inspection at synthesis time"

### CDK-SYN-02 JSON built with the language serialiser

- **Look for:** `json.dumps({...})` / Jackson `ObjectMapper.writeValueAsString(...)` over a structure that
  contains attributes or ARNs, feeding a property such as a state-machine definition, an event pattern
  string or a custom resource property
- **Why it matters:** a string token survives native serialisation as its encoded text and CDK still
  resolves it, but the language serialiser does not know a token's type or the resolved value's
  characters: list and number tokens come out as their encoded placeholders, and a resolved value that
  needs JSON escaping is not escaped, so the deployed JSON can be wrong
- **Instead:** `Stack.of(self).to_json_string({...})` / `Stack.of(this).toJsonString(...)`, or the
  construct's typed API
- **Severity:** Major when the structure holds list or number tokens, `Lazy` values or values that can
  contain quotes, shown in `cdk.out` or a focused test; Minor for string tokens only
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/tokens.html — "To properly JSON-encode any data
  structure, regardless of whether it contains tokens, use the method `stack.toJsonString`";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/private/cloudformation-lang.ts —
  "we'll use the type of the encoded value as a type hint ... we add quotes (") around strings, and don't
  add anything around non-strings"

### CDK-SYN-03 Lazy values that mutate the tree or replace plain values

- **Look for:** `Lazy.string`, `Lazy.list`, `Lazy.any` / `Lazy.uncachedString` whose producer creates
  constructs, calls `bind` or adds children; `Lazy` used for a value already known at construction time
- **Why it matters:** lazies resolve after the tree is complete, so a mutation at that point has
  non-obvious effects (missing resources, unresolved references); an unneeded lazy only adds indirection
- **Instead:** compute the value before constructing; for accumulating state use add-methods called
  during construction
- **Severity:** Major for a mutating producer; Minor otherwise
- **Source:** https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "Do not use a `Lazy`
  to perform a mutation on the construct tree"

### CDK-SYN-04 Side effects and network calls during synthesis

- **Look for:** `boto3` / AWS SDK for Java clients, HTTP calls, subprocesses or file writes outside
  `cdk.out` in stack or construct code; a call that creates or modifies anything in an account
- **Why it matters:** synthesis then needs credentials, differs between runs, cannot be rolled back by
  CloudFormation, and breaks unit tests
- **Instead:** context providers (`from_lookup`) whose results are cached in `cdk.context.json`, a
  separate refresh script that writes a committed file, or a custom resource for deploy-time actions
- **Severity:** Blocker for a mutating call; Major for a read-only call
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Never modify your AWS account
  or resources during synthesis"; "Even strictly read-only calls are not necessarily safe"

### CDK-SYN-05 Aspects: scope, order, and cross-cutting policy done by hand

- **Look for:** `Aspects.of(app).add(...)` (including cdk-nag v2 packs and `Tags.of(app)`) in an app whose
  stacks live inside `Stage` constructs; a validating aspect and a mutating aspect added without
  `priority` (`AspectPriority.MUTATING` before `AspectPriority.READONLY`, v2.172.0 and later); an aspect
  that adds constructs in an app without the `@aws-cdk/core:aspectStabilization` flag (without it, nodes
  an aspect adds higher in the tree are not visited) or that is not idempotent when re-run on new nodes;
  or the opposite, the same tag, removal policy, log setting or encryption check repeated by hand on each
  resource, or enforced in one stack only (copied configuration blocks are CDK-ARC-06)
- **Why it matters:** aspects do not cross Stage boundaries, so the compliance check silently never
  visits the staged stacks; a validator that runs before a mutator approves a tree that later changes;
  hand-repeated rules miss every new resource (stack form of ARC-07). Adding nodes from a mutating aspect
  is a supported use, so judge its scope, ordering and idempotence, not the addition itself
- **Instead:** apply aspects on each `Stage` (or lower); give mutating aspects the mutating priority and
  validators the read-only one; `Tags.of(scope).add(...)` for tags and an Aspect that sets or validates
  the policy for the rest
- **Severity:** Major when a compliance aspect or nag pack does not reach deployed stacks; Minor
  otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/aspects.html — "Aspects don’t propagate across
  Stage construct boundaries"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md —
  "mutating aspects (such as adding tags or resources) run before validation aspects"; "Aspects
  automatically run on newly added nodes to the construct tree. This is controlled by the flag
  `@aws-cdk/core:aspectStabilization`";
  https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Use Aspects and the AWS CDK to validate
  the removal and logging policies in your stack"

### CDK-SYN-06 Aspect implementation pitfalls

- **Look for:** a Python aspect class without `@jsii.implements(IAspect)`; a `visit` that casts or reads
  construct-specific attributes without an `isinstance(node, s3.CfnBucket)` / `instanceof` check; a
  validating aspect that raises instead of adding an annotation, or that only warns
- **Why it matters:** without `jsii.implements` the class does not declare the `IAspect` interface the
  jsii layer expects (verify the behaviour on the app's CDK version); an unchecked cast fails on the first
  unrelated construct; a raise stops synthesis of every stack
- **Instead:** `@jsii.implements(IAspect)`, a type check first, `Annotations.of(node).add_error(...)` for
  violations
- **Severity:** Blocker when the aspect makes synthesis fail; Major when synthesis output shows the aspect
  is not applied; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html — "To indicate that a class
  implements a particular interface, you can use the @jsii.implements decorator";
  https://docs.aws.amazon.com/cdk/v2/guide/aspects.html — "cast the received construct to a more specific
  type before accessing construct-specific properties or methods"

### CDK-SYN-07 Asset paths broader than the asset

- **Look for:** `lambda_.Code.from_asset(".")`, `from_asset("..")` or the repository root; an asset
  directory that contains `cdk.out`, `.git`, a virtual environment, tests, `.env` files or credentials; no
  `exclude=` list; `exclude` relied on together with `bundling` (it has no effect there)
- **Why it matters:** the asset hash changes on unrelated edits (every deploy updates the function), the
  package grows, and local secrets are uploaded to the staging bucket
- **Instead:** point the asset at the handler directory, or bundle from a narrow source with an explicit
  output
- **Severity:** Minor; Blocker when the staged asset under `cdk.out` contains credentials (inspect the
  staged files; a `.env` filename alone is `unsure`)
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/fs/options.ts —
  "Has no effect on Assets bundled using the `bundling` property"; https://docs.aws.amazon.com/cdk/v2/guide/assets.html —
  "the AWS CDK creates a copy of the asset in the cloud assembly directory"

### CDK-SYN-08 Custom asset hashes that go stale

- **Look for:** `asset_hash="v1"` or another static string, `asset_hash_type=AssetHashType.CUSTOM` with a
  value not derived from the content, an `OUTPUT` hash on non-deterministic bundling output
- **Why it matters:** with a static custom hash, code changes are not deployed; with an unstable output
  hash, every synthesis redeploys
- **Instead:** the default `SOURCE` hash; `OUTPUT` only for deterministic bundling of a broad source; a
  custom hash computed from the inputs that matter
- **Severity:** Major for a static custom hash; Minor otherwise
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/assets.ts — "you will
  need to make sure it is updated every time the asset changes, or otherwise it is possible that some
  deployments will not be invalidated"

### CDK-SYN-09 Bundling that depends on the build machine

- **Look for:** bundling commands that install unpinned dependencies (`pip install` without `==` or a
  lock, `npm install` without a lock file); `network="host"` or privileged Docker options; a bundling image
  tag of `latest`; Docker bundling with no `local` provider where the CI configuration in the repository
  shows no Docker (when CI is not in the repository, `unsure`)
- **Why it matters:** the same commit produces different code in different environments, and the build
  pulls whatever version is current
- **Instead:** pinned bundling images and locked dependencies; the plugin language skills' handler
  bundling rules. A local bundling provider is a performance and availability choice the README
  recommends, not a reproducibility fix
- **Severity:** Minor; Major when unpinned dependencies reach production code
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3-assets/README.md —
  "Although optional, it's recommended to provide a local bundling method which can greatly improve
  performance"; `cdk-practices.md` section 8 (exact versions)

### CDK-SYN-10 Resource expansion and template quotas

- **Look for:** a new L2 or L3, loop, subnet or AZ count, subscription or feature prop whose synthesised
  template adds many resources or auxiliary ones the plan's inventory does not list (provider functions,
  roles, policies, log groups, custom resources); a template in `cdk.out` near the CloudFormation quotas
  (`cdk-practices.md` section 2)
- **Why it matters:** one construct line can add many billable and permission-bearing resources, and a
  small source change can push a template past a quota, failing the deploy
- **Instead:** count resources in `cdk.out`, compare with the plan's inventory, and split a deployment
  unit only for an evidenced quota or lifecycle reason
- **Severity:** Major for unplanned auxiliary resources that carry permissions or cost; Blocker when
  validation fails on a quota
- **Source:** https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-limits.html —
  "The maximum number of resources that you can declare in your CloudFormation template", "500 resources";
  `cdk-practices.md` section 2 ("count the resources in `cdk.out`, not the constructs in the code")

### CDK-SYN-11 Synthesizer and bootstrap contract changes

- **Look for:** a changed or new `synthesizer=` (`DefaultStackSynthesizer(qualifier=...)`,
  `CliCredentialsStackSynthesizer`, `LegacyStackSynthesizer`, a custom `IStackSynthesizer`); a changed
  `@aws-cdk/core:bootstrapQualifier` in `cdk.json`; custom asset bucket, repository or role names; assets
  in the template that the cloud assembly's asset manifest does not publish
- **Why it matters:** synthesis still succeeds, but the deploy needs the bootstrap resources the
  synthesizer names in every target account and Region, so a mismatch fails asset publishing or the
  deploy, and some synthesizers drop cross-account or pipeline deployment
- **Instead:** keep the project's synthesizer and qualifier; a change goes through the plan with the
  matching bootstrap; compare the asset manifest in `cdk.out` with the template. This review checks the
  configuration statically and never runs bootstrap or deploy
- **Severity:** Major; Blocker when synthesis or validation fails
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/customize-synth.html — "Its bootstrap contract
  requires an existing Amazon S3 bucket with a known name, an existing Amazon ECR repository with a known
  name, and five existing IAM roles with known names"; `CliCredentialsStackSynthesizer` "doesn't support
  cross-account deployments or CDK Pipelines";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/stack-synthesizers/default-synthesizer.ts —
  `BOOTSTRAP_QUALIFIER_CONTEXT = '@aws-cdk/core:bootstrapQualifier'`

## 8. Tests (CDK-TST)

### CDK-TST-01 Snapshot as the only proof, or regenerated with the change

- **Look for:** a snapshot or golden-template file (`__snapshots__/`, syrupy `.ambr`, a stored
  `*.template.json`) updated in the same change as the resources it covers, with no fine-grained test for
  the new behaviour
- **Why it matters:** a regenerated snapshot approves whatever the code now synthesises, including the
  defect; snapshots also fail on CDK upgrades unrelated to the change
- **Instead:** `Template.from_stack(stack).has_resource_properties(...)` per behaviour; keep snapshots for
  refactors, with other factors held constant
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/testing.html — "snapshot testing isn’t useful in
  catching regressions"; "Snapshot tests can be of great help in refactoring"

### CDK-TST-02 Assertions that would pass with the intended resource removed

- **Look for:** `has_resource_properties` called with an empty object or `Match.any_value()` everywhere,
  in a stack that has other resources of the same type; no `resource_count_is` / `resourceCountIs` where
  the item specifies how many exist or a duplicate would be a defect; `find_resources` results not
  asserted; IAM tests that check one action while the statement allows `*`; aspect or nag errors never
  asserted with `Annotations.from_stack(stack).has_no_error(...)`
- **Why it matters:** `has_resource_properties` does fail when no resource of the type matches, so the
  gap is narrower: a lenient match is satisfied by any other resource of that type, so the test stays
  green if the intended resource disappears or its properties or policy widen. (review.md group 7 words
  this as "no `resource_count_is`"; the count is one remedy, not the definition)
- **Instead:** match the properties the item specifies, count resources where quantity matters, use
  `Match.object_equals` for policy documents, and assert annotations; prove which resource is meant with
  CDK-TST-07
- **Severity:** Major
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/testing.html — "Matchers range from lenient
  (Match.anyValue) to strict (Match.objectEquals)"; https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/README.md —
  "`hasError()`, `hasNoError()`, and `findError()`";
  https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/lib/template.ts —
  `hasResourceProperties` "Assert that a resource of the given type and properties exists in the
  CloudFormation template"

### CDK-TST-03 No characterisation test for stateful logical IDs

- **Look for:** a stateful resource with a pinned logical ID (deployed, or named by the items, the
  project's rules or the plan as an ID that must not change) that the plan touches, refactors or moves,
  with no test that asserts its logical ID in `template.to_json()["Resources"]`; a characterisation test
  the change weakens or deletes
- **Why it matters:** a construct-ID change then reaches a change set before anyone notices (CDK-STA-01)
- **Instead:** a test per stateful resource asserting the logical-ID key and type, written before the
  refactor and green before and after. A stateful resource the change adds has no deployed logical ID
  yet: recommend the test before its first deploy
- **Severity:** Major for a pinned logical ID (`references/standalone-review.md` section 4); Minor for a
  resource the change adds and nothing pins yet, since no change set can replace it before its first
  deploy
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "Write unit tests that assert
  that the logical IDs of your stateful resources remain static"

### CDK-TST-04 Retention asserted with the wrong matcher

- **Look for:** stateful resources whose `DeletionPolicy` and `UpdateReplacePolicy` no test asserts;
  tests that put those keys inside `has_resource_properties` (which matches only `Properties`)
- **Why it matters:** the policy sits beside `Properties` in the template. A `has_resource_properties`
  assertion on it looks for a property that does not exist and fails, so such a test is red rather than
  vacuous; the common gap is that no test asserts the policies at all
- **Instead:** `template.has_resource("AWS::DynamoDB::Table", {"DeletionPolicy": "Retain",
  "UpdateReplacePolicy": "Retain"})`
- **Severity:** Major when the policies go unasserted; a failing wrong-matcher test is a red test
  (review.md Blocker class)
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/README.md — "if you
  would like to assert the entire resource definition, you can use the `hasResource()` API"

### CDK-TST-05 Test hygiene

- **Look for:** copy-pasted app and stack setup in every test; one test asserting many unrelated
  behaviours; test names that do not say what broke; no item ID in the name or docstring. General test
  naming and structure beyond CDK setup belong to the language review the code reviewer's brief assigns; report
  them once, there
- **Why it matters:** a failure does not identify the behaviour, and setup drift makes tests disagree
  about the stack under test
- **Instead:** a fixture (`pytest` fixture, JUnit `@BeforeEach`) that builds the stack; one behaviour
  per test, named for it
- **Severity:** Minor; Major for a test that cites no item where review.md requires it
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/testing.html — "Preferably, a test should test one
  and only one behavior"; "Don’t copy and paste setup lines or common assertions"

### CDK-TST-06 Tests that depend on the machine or the network

- **Look for:** unit tests that synthesise stacks with lookups but no context, read `CDK_DEFAULT_*` or
  other environment variables, need AWS credentials, or run Docker bundling for every test
- **Why it matters:** tests then pass on one machine and fail in CI, or pass against a different
  template than the pipeline deploys
- **Instead:** explicit `env` and context in the test's `App(context={...})`, and assets that do not need
  bundling in unit tests (or a test-only code location, where the project allows it)
- **Severity:** Minor; Major when tests are skipped in CI as a result
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html — "avoid network lookups during
  synthesis and model all your production stages in code"

### CDK-TST-07 Assertions that match resources but not their relationship

- **Look for:** separate assertions that a function, a role, a policy and a queue exist, which would all
  pass if the function were wired to a different queue or the policy attached to a different role; a
  match on one encrypted bucket while another bucket in the stack is the one the item means; broad
  matchers on policy statements that allow extra statements
- **Why it matters:** existence and property checks do not show that the intended consumer uses the
  intended resource, or that access is limited to it as the item specifies
- **Instead:** capture the reference with `Capture` (or read the logical ID from `find_resources`) and
  assert it in the related resource's properties (the role's policy `Resource`, the event source's
  `EventSourceArn`); assert that prohibited statements are absent
- **Severity:** Major when an item specifies the relationship; Minor otherwise
- **Source:** https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/README.md — "The
  matcher APIs documented above allow capturing values in the matching entry"; "the `getResourceId()` API
  ... Useful for asserting that certain cloudformation resources correlate expectedly" (`getResourceId`:
  verify in the app's CDK version)

## 9. Python and Java app code (CDK-LNG)

### CDK-LNG-01 Python: mutable default arguments in construct signatures

- **Look for:** `def __init__(self, scope, construct_id, *, tags: dict = {}, subnets: list = [], **kwargs)`;
  a module-level dict of props mutated by constructs; a construct that appends to or edits a list or
  dict the caller passed in as a prop
- **Why it matters:** the default is created once, so one construct's additions appear in every later
  instance, across stacks and tests; mutating a caller's collection makes one construct's configuration
  depend on another's construction order (stack form of ARC-11 and of the Python file's PY-IDM-01)
- **Instead:** `tags: Optional[Mapping[str, str]] = None` and `tags = dict(tags or {})` in the body
- **Severity:** Major when the default is mutated; Minor otherwise
- **Source:** https://docs.python.org/3/tutorial/controlflow.html — "The default value is evaluated only
  once. This makes a difference when the default is a mutable object"; pylint W0102 dangerous-default-value

### CDK-LNG-02 Python: scope, id and kwargs handling

- **Look for:** `scope=` or `id=` passed as keywords; a stack or construct subclass that accepts
  `**kwargs` but does not forward it to `super().__init__(scope, construct_id, **kwargs)` (dropping `env`,
  `termination_protection`, `description`); `kwargs["x"]` instead of `kwargs.get("x")`; own props whose
  names may collide with future library props
- **Why it matters:** a dropped `env` turns a pinned stack into an environment-agnostic one with no
  error; positional names change when a construct has a prop called `scope` or `id`
- **Instead:** positional `scope, construct_id`; keyword-only own props; forward `**kwargs`; prefix own
  props so they clearly belong to the construct
- **Severity:** Major when stack props are dropped; Minor otherwise
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html — "scope and id should
  always be passed as positional arguments, not keyword arguments"; "use keyword-only arguments to accept
  the arguments you’re interested in"

### CDK-LNG-03 Python: types that only fail in the jsii layer

- **Look for:** a single value where a list is expected (`security_groups=sg`), an L1 type passed to an L2
  prop or the reverse, `Any`-typed helpers that hide the mismatch, and no type checker (mypy, pyright) in
  the project's checks for the CDK code
- **Why it matters:** Python's hints are not enforced, so the error appears only at synthesis, through
  the jsii layer, often with an unhelpful message
- **Instead:** typed helpers and the project's type checker on the infrastructure code
- **Severity:** Minor; Blocker when the mismatch makes synthesis fail
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html — "Passing a value of a
  type associated with a layer 1 (CfnXxxxxx) construct to a L2 or L3 construct, or vice versa"

### CDK-LNG-04 Java: null handling and unchecked casts

- **Look for:** `(String) getNode().tryGetContext("key")` with no null check, `.get(...)` on map props
  without a default, chained getters on optional props (`props.getVpc().getVpcId()`), unboxing a
  possibly-null `Number`
- **Why it matters:** missing values are `null`, so synthesis fails with a `NullPointerException` far
  from the cause
- **Instead:** check and fail with a message naming the missing prop or context key (`Objects.requireNonNull(x,
  "context key 'stage' is required")`), or a documented default
- **Severity:** Minor; Major when the null path is a production stage's configuration; Blocker when synthesis
  fails
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html — "In Java, missing values in
  AWS CDK objects such as props are represented by null. You must explicitly test any value that could be
  null"

### CDK-LNG-05 Java: construct props without a props type and builder

- **Look for:** a project construct with a long positional constructor (`new Ingestion(this, "Ingest",
  bucket, queue, 30, true, "x")`), boolean positional arguments, or overloaded constructors standing in
  for optional values; a props class without a `Builder`
- **Why it matters:** callers cannot tell which argument is which, and adding a prop breaks every caller
  (stack form of SML-03)
- **Instead:** an `IngestionProps` record or class with a builder, following the library's pattern
  (`IngestionProps.builder().bucket(b).retentionDays(30).build()`)
- **Severity:** Minor
- **Source:** https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html — "In Java, props are
  expressed using the Builder pattern"; "We recommend that you follow these builder patterns";
  https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md — "named **FooProps**"
  (awslint:props-struct-name)

## 10. Out of scope / handled elsewhere

- Specification fidelity, the Blocker classes, the output format and replacement evidence: review.md
  groups 1 and 8 and `skills/reviewing-cdk-changes/SKILL.md` steps 3 to 5 with its `references/standalone-review.md`; a claim that nothing is
  replaced needs `cdk diff --method change-set`, never a template diff
- IAM and exposure depth beyond the CDK forms above (policy-document consistency, confused-deputy
  conditions, KMS key policies, bootstrap roles): `skills/iac-security-reviewer/SKILL.md`
- The rules and quotations behind logical IDs, removal policies, cross-stack values, cdk-nag set-up,
  template tools, dependency pinning and `cdk refactor`: `cdk-practices.md`, not repeated here
- Rule violations the tools already report on the synthesised templates (the default validation plugin,
  cdk-nag, cfn-lint, cfn-guard): reviewers treat tool output as leads tagged *(tool)* and judge the
  acknowledgements (CDK-SEC-08), not the rules themselves
- Language-level review of the app code (naming, error handling, typing beyond section 9): the Python
  lenses (`skills/reviewing-python-changes/references/review-lenses.md`) and the Java dimensions
  (`skills/reviewing-java-changes/references/review-dimensions.md`) as the code reviewer's brief assigns
- Lambda handler code bundled by the app: `reviewing-python-changes` or `reviewing-java-changes`
- Template-level design that is not specific to CDK (nested-stack plumbing, custom-resource protocol,
  StackSets): `skills/reviewing-cloudformation-changes/references/review-dimensions.md`
- Running anything against an account (deploy, bootstrap, `cdk refactor`) is out of scope: the skill
  never deploys. Reviewing their configuration is not: the synthesizer, qualifier and asset contract are
  checked statically under CDK-SYN-11. CDK Pipelines definitions and deployment-role permissions get their
  depth from `skills/iac-security-reviewer/SKILL.md` (roles) and the plan's owner; the code reviewer reports
  what it sees in one line

## Sources

AWS CDK v2 Developer Guide (read 2026-10-16 through the aws-documentation MCP and direct fetches):

- https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html
- https://docs.aws.amazon.com/cdk/v2/guide/configure-env.html
- https://docs.aws.amazon.com/cdk/v2/guide/context.html
- https://docs.aws.amazon.com/cdk/v2/guide/featureflags.html
- https://docs.aws.amazon.com/cdk/v2/guide/resources.html
- https://docs.aws.amazon.com/cdk/v2/guide/permissions.html
- https://docs.aws.amazon.com/cdk/v2/guide/tokens.html
- https://docs.aws.amazon.com/cdk/v2/guide/aspects.html
- https://docs.aws.amazon.com/cdk/v2/guide/assets.html
- https://docs.aws.amazon.com/cdk/v2/guide/cfn-layer.html
- https://docs.aws.amazon.com/cdk/v2/guide/constructs.html
- https://docs.aws.amazon.com/cdk/v2/guide/customize-synth.html
- https://docs.aws.amazon.com/cdk/v2/guide/testing.html
- https://docs.aws.amazon.com/cdk/v2/guide/policy-validation-synthesis.html (via `cdk-practices.md`)
- https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html
- https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html

AWS Prescriptive Guidance, "Best practices for using the AWS CDK in TypeScript to create IaC projects"
(principles applied to Python and Java):

- https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/constructs-best-practices.html
- https://docs.aws.amazon.com/prescriptive-guidance/latest/best-practices-cdk-typescript-iac/organizing-code-best-practices.html

AWS CloudFormation and IAM:

- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-limits.html
- https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-encryption.html

aws-cdk repository, `main` branch, read 2026-10-16 (some APIs, such as `ReferenceStrength`, Grants classes,
Mixins and reference interfaces, are recent: verify them in the app's pinned version):

- https://github.com/aws/aws-cdk/blob/main/docs/DESIGN_GUIDELINES.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-iam/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-lambda/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3-assets/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/custom-resources/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/assets.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/fs/options.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/secret-value.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/cfn-element.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/stack.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/private/cloudformation-lang.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/lib/stack-synthesizers/default-synthesizer.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/assertions/lib/template.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-s3/lib/bucket.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-logs/lib/log-group.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-lambda/lib/function.ts
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-ec2/README.md
- https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-apigateway/README.md
- https://github.com/aws/aws-cdk/releases (v2.172.0, v2.214.1, v2.224.0, v2.227.0, v2.241.0, v2.254.0
  release notes: the version floors in the introduction)

cdk-nag (cdklabs), `main` branch, read 2026-10-16:

- https://github.com/cdklabs/cdk-nag/blob/main/RULES.md (AwsSolutions-APIG2, APIG4, COG4, EC23, ECS2,
  IAM4, IAM5, KMS5, RDS10, S2, S10, SMG4, SNS3, SQS4)
- https://github.com/cdklabs/cdk-nag/blob/main/README.md

General:

- https://martinfowler.com/bliki/FlagArgument.html
- https://docs.python.org/3/tutorial/controlflow.html (default argument values)
- https://pylint.readthedocs.io/en/stable/user_guide/messages/warning/dangerous-default-value.html (W0102)

Plugin files:

- `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md` (shared principles)
- `${CLAUDE_PLUGIN_ROOT}/skills/implementing-cdk-from-spec/references/review.md` and `cdk-practices.md`
- `${CLAUDE_PLUGIN_ROOT}/skills/iac-security-reviewer/SKILL.md`
