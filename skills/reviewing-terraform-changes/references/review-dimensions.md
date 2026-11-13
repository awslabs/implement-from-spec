# Terraform review dimensions

The checks a Terraform reviewer applies to a change set beyond the seven check groups of `review.md`: module
design, coupling, state layout, refactoring blocks, interfaces, idioms, drift, versions, security coding
rules, tests and style. Each is a static check on the HCL in the change and the repository around it, or
names the runtime evidence that would settle it. Precedence: the project's rules (CLAUDE.md), its
specification and the approved plan win over everything here, then
`${CLAUDE_PLUGIN_ROOT}/skills/implementing-terraform-from-spec/references/review.md` and
`terraform-practices.md` beside it; a deviation the project prescribes is not a finding.

## Contents

- How to apply
- 1. Module design and boundaries (TF-MOD)
- 2. Dependencies and coupling (TF-DEP)
- 3. State layout, backends and environments (TF-STA)
- 4. Lifecycle and refactoring blocks (TF-LIF)
- 5. Interface: variables, outputs and locals (TF-VAR)
- 6. Meta-arguments and expression idioms (TF-IDM)
- 7. Drift and plan stability (TF-DRF)
- 8. Providers, versions and tags (TF-PRV)
- 9. Security coding rules (TF-SEC)
- 10. Testing (TF-TST)
- 11. Style (TF-STY)
- 12. Out of scope / handled elsewhere
- Sources

## How to apply

The language-neutral principles and architecture smells (PRN-, ARC- and SML- entries: DRY, KISS, YAGNI,
speculative generality, leaking abstraction, god component, hub-like and cyclic dependencies, layer
skipping) are defined once in `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`.
This file gives only their Terraform form, marked "(stack form of ARC-04)" and the like; read the shared
file for the definitions and for its "What to report" rules, which apply here unchanged.

**Evidence.** A **Look for** signal is a cue to investigate, not a finding: report the consequence the
change introduces. Absence holds only within what was searched (callers, tests, declarations). Deployed
state, external consumers, other repositories and effective permissions are not in a diff: a finding
resting on them says `unsure, needs runtime verification` and names the plan or check that settles it.

**Reviewer split.** The groups below extend the check groups of `review.md`; they do not replace them.
The format is the findings format of contract section 9, which the brief repeats and which replaces
`review.md`'s output format. Report a finding under the `review.md` group named here, with the check ID
in brackets after the group, for example
`[Major] modules/queue/main.tf:12 - Invariants (TF-MOD-05) - module creates its own KMS key ...`.

- `implement-from-spec:reviewing-terraform-code` (review.md groups 1, 2, 5, 6 and 7):
  - Group 2 *State safety*: TF-STA, TF-LIF, TF-DRF, TF-IDM-01, TF-IDM-02 and TF-IDM-05
  - Group 5 *Completeness*: TF-VAR, TF-PRV-01 to TF-PRV-05, TF-TST, TF-STY, TF-MOD-10
  - Group 6 *Invariants*: TF-MOD-01 to TF-MOD-09, TF-MOD-11, TF-DEP, TF-IDM-03 and TF-IDM-04. When
    CLAUDE.md documents no architecture invariants, these checks are the default design invariants
  - Group 7 *Correctness of names*: TF-PRV-06 (deprecated resources and arguments)
- `implement-from-spec:reviewing-terraform-security` (review.md groups 3 and 4):
  - Group 3 *IAM*: TF-SEC-01 to TF-SEC-05
  - Group 4 *Exposure and data protection*: TF-SEC-06 to TF-SEC-09, and the security angle of TF-STA-03
    (backend credentials), TF-DEP-03 (state read access), TF-DRF-03 (unsafe image filters) and TF-IDM-05
    (commands built from inputs). The code reviewer reports those checks' design angle in its own groups
  - Either reviewer that sees the other's issue reports it as one out-of-lens head line, as the reviewer
    skills' own instructions say; the main conversation de-duplicates or traces it

**Severity classes.** `terraform-practices.md` section 5 is authoritative: whenever it names a case, its
class applies and a check's default below never lowers it. The defaults fill the rest:

- **Blocker**: the cases section 5 names (an unapproved destroy or replacement of any existing resource,
  a rename without `moved`, a secret in HCL, an open principal or unjustified `"*"` resource, a role in a
  resource module, a broken documented invariant, red fmt, validate or plan), plus a data store or
  administration port shown reachable from the internet
- **Major**: should be fixed before apply: a plan that churns, an interface that cannot be verified (no
  type, no description), coupling that blocks independent change, drift Terraform will fight forever,
  missing data protection
- **Minor**: maintainability: needless abstraction or indirection, overuse of a construct, a missing test
  for new logic
- **Nit**: naming, layout and syntax polish

A check's **Severity** line is its default and names when it escalates. A Blocker needs a demonstrated
case (the HCL, a plan or the provider page shows it); a suspected outcome keeps its class, marked `unsure`.

**Versions.** Judge engine features against the pinned `required_version` and arguments against the
pinned `hashicorp/aws` version; a fix needing a newer version is a migration option, not a mandatory fix.
Terraform versions, read on 2026-10-16:

| Feature | Terraform |
|---|---|
| `terraform test`, `*.tftest.hcl` | 1.6 |
| `removed` blocks; test mocks (`mock_provider`, `override_*`) | 1.7 |
| Variable validation referring to other variables | 1.9 |
| Ephemeral variables, outputs and resources; S3 backend `use_lockfile` | 1.10 |
| Write-only arguments (`*_wo`) | 1.11 |
| Per-resource `region` argument (`hashicorp/aws`) | provider 6.0 |

OpenTofu's versions and some semantics differ (its S3 backend keeps DynamoDB locking fully supported; it
warns on a `removed` block without `lifecycle`): check its documentation before citing a version or default.

**Where this file differs from the reviewer skills' built-in checklists** (the reviewers apply those only without a
review file; with one, the classes here and in `terraform-practices.md` apply):

- `count` where `for_each` belongs (TF-IDM-01) is a Major for new code and a Blocker only when the change
  re-indexes existing instances, matching `terraform-practices.md`'s Blocker class (a destroy or
  replacement of an existing resource)
- Provider version constraints (TF-PRV-03): HashiCorp recommends a minimum-only `>=` constraint in reusable
  modules and `~>` in root modules, not `~>` everywhere
- An unpinned remote module source (TF-MOD-09) is a Major, not a Minor: it changes the code that runs on the
  next module installation; a `version` argument on a local source makes `init` fail
- AWS Prescriptive Guidance's attachment-resource example uses `aws_security_group_rule`; the provider now
  recommends `aws_vpc_security_group_ingress_rule` and `aws_vpc_security_group_egress_rule` (TF-PRV-06)

## 1. Module design and boundaries (TF-MOD)

### TF-MOD-01 Thin wrapper module around one resource

- **Look for:** a new `modules/<x>/` whose `main.tf` holds one resource (plus at most its policy document)
  and adds no defaults, validation or companion resources over declaring the resource directly; a module
  named after its resource type or called from one place is a cue to look, not the finding
- **Why it matters:** speculative generality (stack form of SML-07): the module adds an address prefix,
  a variables file and an outputs file to read through, and later collapsing it needs `moved` blocks
- **Instead:** declare the resource in the calling module; create a module once it raises the abstraction
  (resource plus its policy, alarms and defaults)
- **Severity:** Minor; a wrapper that also mirrors the resource's arguments is reported once, under
  TF-MOD-02
- **Source:** developer.hashicorp.com/terraform/language/modules/develop — "We do not recommend writing
  modules that are just thin wrappers around single other resource types"

### TF-MOD-02 Pass-through variables mirroring resource arguments

- **Look for:** module variables named one-to-one after the arguments of the resource inside
  (`var.versioning_enabled`, `var.lifecycle_rules`, `var.cors_rules`) that are used once with no
  transformation, `dynamic` blocks fed straight from such a variable, variables added "for flexibility"
  that no caller found in the repository sets
- **Why it matters:** speculative generality (stack form of SML-07 and PRN-09): the module's interface
  becomes the provider schema twice over, every variable is a compatibility promise, and nothing is
  encapsulated. A forwarded input that is the module's intended stable interface is not a finding
- **Instead:** hard-code what does not vary between deployments, expose only what the specification or a
  real caller varies, and derive the rest inside the module
- **Severity:** Minor
- **Source:** developer.hashicorp.com/terraform/language/expressions/dynamic-blocks — "that might suggest
  that your module is not creating a useful abstraction"; docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/structure.html
  — "If there's only a small chance that a variable might be needed, don't expose it"

### TF-MOD-03 God module mixing unrelated concerns

- **Look for:** a module over about 300 lines of HCL (the plugin's default, `terraform-practices.md`
  section 2); a "core" or "platform" module every new feature extends; resources with different owners or
  lifecycles in one module (a shared network, a long-lived data store, frequently changed compute).
  Resources that together form one capability are not a finding
- **Why it matters:** god component (stack form of ARC-04): the pieces cannot be reused or composed
  separately, and a change to one concern changes the interface and review scope of all
- **Instead:** one module per capability (resources that work together), composed in the root
- **Severity:** Major for a module over about 300 lines (`terraform-practices.md` section 5); Minor for
  mixed concerns below that size
- **Source:** docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/structure.html
  — "A reusable module should encapsulate infrastructure pieces that work together to enable a capability";
  the line threshold is plugin policy

### TF-MOD-04 Deep module trees and modules calling siblings

- **Look for:** a child module that calls further child modules (`module.app.module.network.module.subnets`),
  `source = "../<sibling>"` inside `modules/`, outputs re-exported unchanged through an intermediate
  module to reach the root
- **Why it matters:** layer skipping in reverse (stack form of ARC-02 and SML-10): values tunnel through
  modules that do nothing with them, and the nested modules cannot be recombined by a caller
- **Instead:** keep one level of child modules and wire them together in the root with
  `module.a.<output>` arguments
- **Severity:** Minor; Major when a new nesting level forces existing resources to change address (then
  TF-LIF-01 applies)
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/composition — "we strongly
  recommend keeping the module tree flat, with only one level of child modules"; AWS Prescriptive
  Guidance, structure.html — "Modules should build on other modules―not build tunnels through them"

### TF-MOD-05 Module embeds its dependencies instead of receiving them

- **Look for:** a module that creates its own VPC, KMS key, log bucket or SNS topic that other modules
  also need; `create_<x> = true` booleans with `count` to make a dependency optional; several `create_*`,
  `use_existing_*` or `enable_*` switches that admit contradictory combinations with no `validation`
  rejecting them; a module that looks up a sibling's object with a data source (`data "aws_vpc"` by tag)
  inside itself
- **Why it matters:** dependency inversion broken (stack form of PRN-07): the module cannot coexist with
  shared infrastructure, "create if missing" logic hides which environment owns the object, and each mode
  switch multiplies the combinations callers must understand and test
- **Instead:** accept the dependency as an input (`vpc_id`, `kms_key_arn`, or a typed object), and let the
  root decide whether it comes from a resource or a data source; for real modes, one typed input with a
  `validation` of the supported combinations (cross-variable validation needs Terraform 1.9)
- **Severity:** Major when the duplicated object is shared (network, key, log destination) or an accepted
  combination breaks the module's documented contract; Minor otherwise
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/composition — "we recommend
  applying the dependency inversion approach: making the module accept the object it needs as an argument,
  via an input variable"; Terraform 1.9.0 changelog — "Input variable validation rules can refer to other
  objects"

### TF-MOD-06 Child module configures a provider

- **Look for:** a `provider "aws" {}` block (region, `assume_role`, `default_tags`) inside a directory that
  is called with a `module` block
- **Why it matters:** the module cannot be used with `count`, `for_each` or `depends_on`, and removing the
  module call removes the provider configuration its resources need to be destroyed
- **Instead:** declare `required_providers` (and `configuration_aliases` when it needs several
  configurations) in the module and pass configurations from the root with `providers = { aws = aws.x }`
- **Severity:** Major
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/providers — "A module intended to
  be called by one or more other modules must not contain any provider blocks"

### TF-MOD-07 Leaking or pass-through module outputs

- **Look for:** a reusable module's whole-resource output (`value = aws_s3_bucket.this`) whose callers
  read implementation attributes; an output returning an input unchanged (`value = var.vpc_id`) that
  callers treat as "the module is ready"; no output referencing the module's resources; an input typed
  `any` or mirroring a whole resource where the module reads two attributes
- **Why it matters:** leaking abstraction (stack form of ARC-01): callers couple to the provider schema
  inside, so a provider upgrade or resource swap breaks them; an echoed variable carries only the input's
  dependencies, so callers can be ordered before the module's resources exist
- **Instead:** named attribute outputs (`bucket_arn`, the policy JSON consumers need), or a deliberately
  designed object output of supported attributes; object inputs typed with only the attributes read
- **Severity:** Minor; Major for a pass-through output a caller uses for ordering
- **Source:** AWS Prescriptive Guidance, structure.html — "Don't pass outputs directly through input
  variables, because doing so prevents them from being properly added to the dependency graph"; the
  whole-object part is synthesis from developer.hashicorp.com/terraform/language/modules/develop/composition
  — "Declare an object using only the subset of attributes the module needs"

### TF-MOD-08 Duplicated configuration knowledge

- **Look for:** the same resource blocks in `envs/dev/main.tf` and `envs/prod/main.tf` (or two roots)
  differing only in literal values; the same naming, retention or encryption rule written out in several
  blocks or modules of one root; a fix applied to one copy in the diff but not the other
- **Why it matters:** duplicated knowledge and shotgun surgery (stack form of PRN-01 and SML-12): the
  copies drift, and the drift is usually in a security or data-protection argument
- **Instead:** a local module under `modules/` called from each environment root with its own inputs and
  backend; for a rule repeated inside one root, a local or typed input at the narrowest common owner. Do
  not merge look-alike resources whose lifecycles differ
- **Severity:** Minor; Major when the copies already differ in an encryption, exposure, IAM or deletion
  protection argument and the specification does not make the difference intentional
- **Source:** developer.hashicorp.com/terraform/language/style — "use modules to encapsulate your
  configuration, and use a directory for each environment so that each one has a separate state file"

### TF-MOD-09 Module source and version not pinned

- **Look for:** a registry `source` without `version`; a git source without `?ref=` (or with a branch
  ref); a third-party module bumped without the change saying so; a `version` argument on a local
  (`./modules/...`) or VCS source
- **Why it matters:** the lock file tracks providers only, so each fresh module installation (a new CI
  runner, `init -upgrade`) takes the newest matching code without a diff, a supply chain path into the
  account. A `version` on a local path is not ignored: `init` fails
- **Instead:** `version = "x.y.z"` for registry modules, `?ref=<commit hash>` (or a version tag the project
  allows) for git sources, no `version` on local paths
- **Severity:** Major for an unpinned remote source; Blocker for a `version` on a local source (red
  validate, `terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/files/dependency-lock — "Terraform does not
  remember version selections for remote modules"; Terraform source `internal/initwd/module_install.go` —
  "Cannot apply a version constraint to module %q (at %s:%d) because it has a relative local path" (the
  style guide's "Terraform ignores the version parameter" is wrong here); tflint rules
  `terraform_module_version`, `terraform_module_pinned_source`; Checkov `CKV_TF_1`, `CKV_TF_2`

### TF-MOD-10 Standard module structure missing

- **Look for:** a new module without `main.tf`, `variables.tf`, `outputs.tf` or `versions.tf`; variables
  or outputs scattered across resource files; a reusable module without a README; examples whose module
  `source` is a relative path
- **Why it matters:** Terraform reads every `.tf` file, so the layout is the plugin's coding standard
  (`terraform-practices.md` section 2), not a loader rule: it is where reviewers and documentation tools
  find the interface. Examples get copied elsewhere, where a relative source breaks
- **Instead:** the minimal structure plus `versions.tf`, as `terraform-practices.md` section 2 lists;
  example sources set to the address an external caller would use
- **Severity:** Major for a new module without `versions.tf` (`terraform-practices.md` checklist); Minor
  for the other files
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/structure — "These are the
  recommended filenames for a minimal module"; same page — "set to the address an external caller would
  use, not to a relative path"; tflint rule `terraform_standard_module_structure`

### TF-MOD-11 Module writes generated files into a shared path

- **Look for:** `local_file`, `archive_file` `output_path` or a provisioner writing under `path.module`;
  several instances of one local module writing the same filename; artifacts located through `path.cwd`
  or an absolute developer-machine path
- **Why it matters:** implicit coupling through shared files (stack form of ARC-11): instances overwrite
  each other's output, and local and remote module sources resolve the path differently
- **Instead:** read packaged assets through `path.module`; write generated artifacts to a caller-supplied
  path that is unique per instance, or build them outside Terraform and pass the path in
- **Severity:** Minor; Major when two instances in the change write the same path
- **Source:** developer.hashicorp.com/terraform/language/expressions/references — "We do not recommend
  using path.module in write operations because it can produce different behavior depending on whether
  you use remote or local module sources"; same page — "Multiple invocations of local modules use the same
  source directory, overwriting the data in path.module during each call"

## 2. Dependencies and coupling (TF-DEP)

### TF-DEP-01 Explicit depends_on where a reference would do

- **Look for:** `depends_on = [aws_x.y]` on a resource that already references `aws_x.y`, `depends_on`
  on a `module` block, `depends_on` added to "fix ordering" with no comment saying what hidden dependency
  it encodes
- **Why it matters:** Terraform plans more conservatively: values become "known after apply" and more
  resources are replaced than necessary
- **Instead:** reference the attribute the resource needs (`role = aws_iam_role.x.name`); keep
  `depends_on` for hidden dependencies, with a comment
- **Severity:** Minor (redundant `depends_on`, `terraform-practices.md` section 5); Major on a `module`
  block whose module holds data sources or resources that would be replaced
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/depends_on — "You should only use
  depends_on as a last resort because it can cause Terraform to create more conservative plans that
  replace more resources than necessary"

### TF-DEP-02 Hidden dependency left implicit

- **Look for:** a Lambda function, instance or task that needs an IAM policy attachment, a VPC endpoint,
  a route or a bucket policy to work at first start, with neither a reference to it nor `depends_on`;
  an `aws_lambda_event_source_mapping` created before its role's policy is attached
- **Why it matters:** explicit over implicit (stack form of PRN-16): the first apply fails or the service
  starts without permission, and the failure appears only against a real account
- **Instead:** `depends_on = [aws_iam_role_policy_attachment.x]` with a comment naming the behaviour relied
  on
- **Severity:** Major
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/depends_on — "when a resource or
  module relies on another resource's behavior but does not access any of that resource's data in its
  arguments"

### TF-DEP-03 terraform_remote_state as hidden cross-stack coupling

- **Look for:** a new `data "terraform_remote_state"` reading another root's outputs, consumers indexing
  `data.terraform_remote_state.x.outputs.<name>` across many files, a backend key path of another stack
  hard-coded in the consumer
- **Why it matters:** the consumer couples to the producer's backend layout and output names, and needs
  read access to the whole producer state, secrets included
- **Instead:** the producer publishes what it shares (an `aws_ssm_parameter`, DNS records, tags) and the
  consumer reads it with the matching data source, wrapped in a data-only module when several stacks read
  it
- **Severity:** Minor; Major when the producer's state holds secrets (database passwords, generated keys)
  the consumer's role should not read (security reviewer, group 4; `unsure, needs runtime verification`
  unless the producer's HCL in the repository shows the secret)
- **Source:** developer.hashicorp.com/terraform/language/state/remote-state-data — "its user must have
  access to the entire state snapshot, which often includes some sensitive information"; same page — "we
  recommend explicitly publishing data for external consumption to a separate location instead of
  accessing it via remote state"

### TF-DEP-04 Cyclic dependency between stacks

- **Look for:** root A reads root B's state or published parameters while B reads A's, or a chain that
  returns to its start; a stack that must be applied twice ("apply A, then B, then A again") to converge.
  Name every edge of the cycle; an edge in another repository needs evidence, otherwise `unsure`
- **Why it matters:** cyclic dependency (stack form of ARC-03): no stack can be created from scratch in
  one pass, and disaster recovery depends on the manual order
- **Instead:** move the shared objects into a lower stack both read, or invert one edge by passing the value
  as an input variable
- **Severity:** Major
- **Source:** synthesis from developer.hashicorp.com/terraform/cli/workspaces — "This setup creates a
  tighter coupling between configurations" (about `terraform_remote_state` between configurations)

### TF-DEP-05 Data source reading an object the same configuration manages

- **Look for:** `data "aws_s3_bucket"`, `data "aws_iam_role"` or `data "aws_security_group"` looking up by
  name or tag an object a `resource` block in the same configuration creates, instead of referencing the
  resource
- **Why it matters:** with no dependency path the read can run before the create and fail on the first
  apply; with one, the read defers to apply whenever the resource has changes pending or the arguments are
  unknown, and everything downstream becomes "known after apply"
- **Instead:** reference the resource (`aws_s3_bucket.x.arn`), or pass the value in from the module that
  owns it
- **Severity:** Minor; Major when nothing orders the data source after the resource
- **Source:** developer.hashicorp.com/terraform/language/data-sources — "The data block configuration
  directly depends on a Terraform-managed resource that is configured to change in the current plan"; same
  page — "Arguments in a data block refer to values that must be computed during the apply phase"

### TF-DEP-06 Hub-like configuration object

- **Look for:** one `var.config` or `local.settings` map holding every setting of the system passed whole
  into every module; a "common" or "globals" module whose outputs every other module reads
- **Why it matters:** hub-like dependency (stack form of ARC-05): no module's real interface is visible,
  and any change to the hub is a change to every module's input, so each review has to consider all of
  them
- **Instead:** pass each module the few typed inputs it uses
- **Severity:** Minor (synthesis)
- **Source:** synthesis from developer.hashicorp.com/terraform/language/modules/develop/composition — "where
  possible we prefer to keep modules relatively small and pass in their dependencies"

### TF-DEP-07 Constructed identifiers for objects the configuration manages

- **Look for:** `"arn:aws:iam::${var.account_id}:policy/${var.name}"`, a role or bucket name typed as a
  string where `aws_iam_policy.x.arn` or `aws_s3_bucket.x.id` exists in the same configuration
- **Why it matters:** the string carries no dependency, so creates and destroys happen in the wrong order
  (`DeleteConflict`, `NoSuchEntity`), and a renamed object silently breaks the reference
- **Instead:** reference the resource attribute
- **Severity:** Major
- **Source:** registry docs for `aws_iam_policy_attachment` (github.com/hashicorp/terraform-provider-aws,
  website/docs/r/iam_policy_attachment.html.markdown) — "use a reference to the IAM resource when defining
  the `policy_arn` for `aws_iam_policy_attachment`, rather than constructing the ARN directly"

## 3. State layout, backends and environments (TF-STA)

### TF-STA-01 Monolithic root state

- **Look for:** a new, unrelated system (a second application, a shared network) added to an existing root
  module instead of its own root; long-lived data stores in the same root as frequently changed
  application resources
- **Why it matters:** god component at state level (stack form of ARC-04): every plan touches everything,
  one lock serialises all teams, and one bad apply has the whole estate as its scope
- **Instead:** one root (and state) per component boundary, connected through published values (TF-DEP-03)
- **Severity:** Minor; Blocker when the change breaks a component boundary CLAUDE.md documents as an
  architecture invariant (`terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/style — "split your resources across multiple
  workspaces to prevent large state files and limit unintended consequences from changes"

### TF-STA-02 Environments without separate state access boundaries

- **Look for:** `terraform.workspace == "prod" ? ... : ...`, `count` or names derived from
  `terraform.workspace`, docs telling operators to `workspace select prod`; production and development
  state in one bucket (keys per environment via `-backend-config`) with nothing splitting access to them
- **Why it matters:** workspaces share one backend configuration and, unless an IAM policy splits the state
  paths, one access boundary: an identity that can write development state can write production state
- **Instead:** one root (or backend configuration) per environment calling the shared modules; a bucket or
  at least an IAM boundary per environment's state path, production writable only by the pipeline
- **Severity:** Major; not a finding when the project documents its isolation mechanism; `unsure, needs
  runtime verification` when the bucket policy lives outside the repository
- **Source:** developer.hashicorp.com/terraform/language/state/workspaces — "Workspaces are not appropriate
  for system decomposition or deployments requiring separate credentials and access controls"; AWS
  Prescriptive Guidance, backend.html — "distinct backends provide stronger isolation. If you have shared
  workspaces, accidents can still impact multiple environments"

### TF-STA-03 Backend configuration

- **Look for:** credential values (`access_key`, `secret_key`, `token`) in a `backend` block or a committed
  `-backend-config` file (a `profile` name is not a credential); a new S3 backend with neither
  `use_lockfile = true` (Terraform 1.10+) nor `dynamodb_table`; two roots resolving to the same complete
  state address (bucket, `key`, `workspace_key_prefix` and workspace); `dynamodb_table` in new 1.10+ code
- **Why it matters:** backend credentials land in `.terraform/` and plan files; without a lock, concurrent
  runs can corrupt state; a shared address makes two roots overwrite each other's state
- **Instead:** credentials from the environment or the project's profile, a partial backend configuration,
  `use_lockfile = true` (DynamoDB locking on older pins), `encrypt = true`, a unique key per root
- **Severity:** Blocker for a committed credential (`terraform-practices.md` section 5; security reviewer)
  or a demonstrated shared address; Major for no locking; Minor for `dynamodb_table` in new Terraform
  1.10+ code (not a finding for OpenTofu)
- **Source:** developer.hashicorp.com/terraform/language/backend/s3 — "Terraform will include these values in
  both the .terraform subdirectory and in plan files"; same page — "DynamoDB-based locking is deprecated";
  .../language/state/locking — "potentially corrupting your state"; AWS Prescriptive Guidance,
  backend.html — S3 native locking "Available since Terraform 1.10.0"

### TF-STA-04 Environments sharing a backend

Retired 2026-10-16: merged into TF-STA-02

### TF-STA-05 Backend or state ownership changed without a migration procedure

- **Look for:** a changed backend type, `bucket`, `key`, `workspace_key_prefix` or Region in an existing
  root; resources handed between roots (`removed` in one, `import` or a new resource block in the other);
  no stated order, state backup or owner for `init -migrate-state`
- **Why it matters:** `-reconfigure` instead of `-migrate-state` leaves the root on an empty state that
  plans to create what exists, and a handoff without an order lets both roots claim one object, or neither
- **Instead:** name source and destination state addresses, the backup, the apply order and who runs it
  (state commands are the operator's, `terraform-practices.md` section 3); require a full plan of each root
  with no create of an existing object and no destroy
- **Severity:** Major for a missing procedure; Blocker when a plan shows a destroy or replacement of an
  existing resource (needs runtime verification)
- **Source:** developer.hashicorp.com/terraform/cli/commands/init — "Either -reconfigure or -migrate-state
  must be supplied to update the backend configuration"; same page — "The -reconfigure option disregards
  any existing configuration, preventing migration of any existing state"

## 4. Lifecycle and refactoring blocks (TF-LIF)

### TF-LIF-01 Address change without a correct moved block

- **Look for:** a renamed resource label or module call, a resource moved into or out of a module, a
  `count` list turned into a `for_each` map, a module split, with no `moved {}` block per old address;
  `moved` blocks with wrong instance keys, a missing instance, a broken chain, or a move between resource
  types the provider does not document
- **Why it matters:** Terraform destroys the object at the old address and creates a new one; for a data
  store that is data loss. Terraform infers one case only: adding `count` to a resource that had none
  moves the object to `[0]`
- **Instead:** `moved { from = aws_s3_bucket.this  to = module.bucket.aws_s3_bucket.this }`, one per
  address, mapping every old instance key, written out even where Terraform would infer index 0
- **Severity:** Blocker for a rename, module move or `for_each` conversion without a correct `moved`
  (`terraform-practices.md` section 5); Minor when only the implicit `count` index 0 inference covers it
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/refactoring — "By default,
  Terraform interprets a change as an instruction to destroy the existing resource and create a new
  resource at the new address"; same page — "When you add count to an existing resource that didn't
  previously have the argument, Terraform automatically proposes moving the original object to instance
  0"

### TF-LIF-02 Change to an argument that forces replacement

- **Look for:** an edited argument on an existing resource that the provider cannot update in place
  (identifiers and names, `engine`, `availability_zone`, `subnet_id`, KMS key on some resources), or a new
  `replace_triggered_by`
- **Why it matters:** the plan shows `-/+`: downtime, new identifiers for everything that references the
  resource, data loss for stores
- **Instead:** stop and ask (`terraform-practices.md` section 3); if replacement is intended, say so and
  pair it with `create_before_destroy` where names allow
- **Severity:** Blocker when the resource exists and the approved plan does not accept the replacement
  (`terraform-practices.md` section 5: any replacement of an existing resource); mark `unsure` and give the
  provider page to verify when the replacement behaviour is not confirmed
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/lifecycle — "Destroys and
  re-creates resources whose arguments have changed but that Terraform cannot update in-place because of
  remote API limitations"

### TF-LIF-03 Historical moved blocks deleted

- **Look for:** `moved` blocks removed from a module that other configurations call, or removed from a root
  whose environments may not all have applied the move
- **Why it matters:** any state still at the old address plans a destroy instead of a move
- **Instead:** keep historical `moved` blocks; chain them (`a` to `b`, `b` to `c`) when an object moves twice
- **Severity:** Major, `unsure, needs runtime verification` unless the change shows every state has
  applied the move; Blocker when a plan shows the resulting destroy
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/refactoring — "Removing a moved
  block is a breaking change because any configurations that refer to the old address will plan to delete
  the existing object instead of move it"

### TF-LIF-04 Resource block deleted to stop managing an object

- **Look for:** a `resource` or `module` block this change deletes whose object should survive (handed to
  another stack or team), with `prevent_destroy` relied on to protect it. A future revert of a change
  that adds the block is not this check, because the change deletes nothing: it is `review.md`'s temporal
  compatibility (reverting after new writes destroys the object this change created, with what was
  written to it), rated in the Severity line
- **Why it matters:** removing the block destroys the object, and `prevent_destroy` does not stop it because
  the rule lives in the deleted block
- **Instead:** replace the block with `removed { from = aws_x.y  lifecycle { destroy = false } }`
  (Terraform 1.7 or later); on an older pin, an operator-run `terraform state rm` under the approval gate
  (`terraform-practices.md` section 3); a handoff to another root also needs TF-STA-05
- **Severity:** Blocker. The revert of a change that only adds the object: not a finding when the plan's
  rollback says removing it takes a reviewed change, a drain, or a `removed` block with
  `lifecycle { destroy = false }`; Minor when the rollback is silent or says `prevent_destroy` survives
  a revert; Major only when the items, the plan or the project's rules require that data to survive a
  rollback
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/lifecycle — "Terraform destroys the
  actual infrastructure during an apply operation if you remove the resource's configuration, even if
  prevent_destroy is enabled"; .../language/state/remove — "we recommend using the removed block instead"
  (of `terraform state rm`)

### TF-LIF-05 removed block that still destroys

- **Look for:** `removed { from = ... }` without a `lifecycle { destroy = false }` block on an object meant
  to be kept, or `destroy = true` on a data store the plan does not mean to delete
- **Why it matters:** in Terraform the default of a `removed` block is to destroy the object as well as
  forget it (OpenTofu warns on a `removed` block without `lifecycle`; write it explicitly either way)
- **Instead:** `lifecycle { destroy = false }`, and delete references to the resource's attributes
- **Severity:** Blocker when the object is meant to be kept (`terraform-practices.md` section 5: a destroy
  of an existing resource); not a finding when destroying it is the approved intent
- **Source:** developer.hashicorp.com/terraform/language/block/removed — "By default, Terraform removes the
  resource from state and destroys the actual resource"

### TF-LIF-06 import block that does not match its target

- **Look for:** an `import` block whose `to` address has no matching `resource` block outside a
  configuration-generation step (`plan -generate-config-out`, run by the operator); a resource block whose
  arguments differ from the imported object's current settings when the change does not mean to modify
  the object; an import of an object another root in the repository already manages
- **Why it matters:** the first apply after import modifies or replaces the real object, and two states
  owning one object fight forever
- **Instead:** a matching resource block written from the object's current settings (or generated by the
  operator), any intended change stated in the plan, and one owning root per object
- **Severity:** Major; Blocker when the plan would replace the imported object (needs runtime verification)
- **Source:** developer.hashicorp.com/terraform/language/import — "you must create a destination resource
  block that matches the address declared in the import block"; .../import/generating-configuration —
  "Terraform can generate code for the resources you define in import blocks that do not already exist in
  your configuration"; the "one owner" part is synthesis

### TF-LIF-07 Data store without prevent_destroy or deletion protection

- **Look for:** a new or changed data-holding resource (`aws_db_instance`, `aws_rds_cluster`,
  `aws_dynamodb_table`, a data `aws_s3_bucket`, `aws_kms_key`, `aws_efs_file_system`) without
  `lifecycle { prevent_destroy = true }` and, where the resource has one, its deletion protection
  (`deletion_protection` on the RDS resources, `deletion_protection_enabled` on `aws_dynamodb_table`;
  `aws_s3_bucket` and `aws_kms_key` have none)
- **Why it matters:** one wrong plan deletes data that cannot be recreated
- **Instead:** both protections where the provider has the argument; never invent one. `prevent_destroy`
  elsewhere is not a finding unless it blocks a change the plan needs
- **Severity:** Major for a missing protection (`terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/lifecycle — "Use this rule as
  protection against accidentally replacing objects that may be costly to reproduce"; same page — "Use
  prevent_destroy sparingly"; `terraform-practices.md` section 3 — "deletion protection argument where it
  has one"; Checkov `CKV_AWS_293`

### TF-LIF-08 create_before_destroy missing or impossible

- **Look for:** a replacement (shown by a plan, or forced per the provider page) of a resource in use while
  it is replaced (`aws_acm_certificate` on a listener, a security group attached to running instances)
  without `create_before_destroy = true`; `create_before_destroy` on a resource whose name must be unique
  in its scope and is fixed (no `name_prefix`). An in-place update, such as a launch template change that
  creates a new template version, needs neither
- **Why it matters:** without it the replacement leaves a gap; with a fixed unique name the create fails
  because the old object still holds the name
- **Instead:** `create_before_destroy = true` plus `name_prefix` (or a generated suffix) where names must
  be unique
- **Severity:** Major
- **Source:** tflint rule `aws_acm_certificate_lifecycle`; developer.hashicorp.com/terraform/language/meta-arguments/lifecycle
  — "many remote object types have unique name requirements or other constraints that must be
  accommodated for both a new and an old object"; registry docs for `aws_launch_template` — "whenever a
  change to this resource creates a new version"

### TF-LIF-09 ignore_changes used to silence drift

- **Look for:** `ignore_changes = all`; `ignore_changes` added in the same change as a perpetual diff
  appeared; on security-relevant arguments (`policy`, `ingress`, `encryption`, `tags` used for access
  control); no comment naming the other owner. An ignored argument that is also set in HCL is the normal
  pattern for a value another process owns after creation
- **Why it matters:** Terraform stops correcting drift on that argument, so an out-of-band change, including
  a weakened control, persists while the code claims otherwise
- **Instead:** fix the cause (TF-DRF); keep `ignore_changes` for arguments another process owns, listed
  individually, with a comment naming that process
- **Severity:** Major for `all` or a security-relevant argument; Minor otherwise
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/lifecycle — "Terraform considers
  the arguments corresponding to the given attribute names when planning a create operation, but are
  ignored when planning an update operation"; same page — "Terraform can create and destroy the remote
  object but will never propose updates to it"

## 5. Interface: variables, outputs and locals (TF-VAR)

### TF-VAR-01 Variable without type or description

- **Look for:** a `variable` block without `type` or `description`
- **Why it matters:** an untyped variable accepts anything and fails late with a provider error; the
  description is the module's documentation
- **Instead:** `type` and a one- or two-sentence `description` on every variable, in that order
- **Severity:** Major (`terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/style — "Define a type and a description for every
  variable"; tflint rules `terraform_typed_variables`, `terraform_documented_variables`

### TF-VAR-02 Imprecise types and silent fallbacks

- **Look for:** `type = any`, `map(any)` or `list(any)` on a value whose attributes the module reads;
  structured settings passed as `map(string)`; `lookup(var.x, "key", default)` or `try(var.x.key, ...)`
  sprinkled where `optional()` would declare the default; `try(..., null)`, `can()` or an empty-collection
  fallback around a required attribute, so a misspelled key silently removes a resource or a policy
  statement
- **Why it matters:** fail fast (stack form of PRN-14): the interface is unverifiable, type errors surface
  inside resources, defaults are scattered, and malformed input produces a clean plan that omits required
  infrastructure
- **Instead:** `object({ name = string, retention_days = optional(number, 30) })`; `any` only for values
  passed through opaque (for example to `jsonencode`); `try` only in one normalising local, then a
  `validation` for what is required
- **Severity:** Major for `any` on a value the module inspects or a fallback that silently drops required
  configuration; Minor for scattered `lookup` or `try` defaults
- **Source:** developer.hashicorp.com/terraform/language/expressions/type-constraints — "Do not use any just
  to avoid specifying a type constraint"; same page — "An optional attribute with a non-null default value
  is guaranteed to never have the value null within the receiving module";
  developer.hashicorp.com/terraform/language/functions/try — "We strongly suggest using try only in special
  local values whose expressions perform normalization"

### TF-VAR-03 Validation missing or redundant

- **Look for:** a variable with a constraint the specification states (CIDR format, enum of environments,
  name pattern, minimum count) and no `validation` block; a `validation` that repeats the type check; an
  `error_message` that does not say what is allowed
- **Why it matters:** fail fast (stack form of PRN-14): without validation the error arrives at apply time
  from the AWS API, after other resources changed
- **Instead:** `validation { condition = can(cidrhost(var.cidr, 0))  error_message = "<what is allowed>" }` for real
  constraints only
- **Severity:** Minor; Major when the specification states the constraint
- **Source:** developer.hashicorp.com/terraform/language/style — "Only use variable validation when your
  variable values have uniquely restrictive requirements"; developer.hashicorp.com/terraform/language/validate
  — "While provider APIs often error on these same validations, this helps your users avoid the error and
  issues a helpful error message"

### TF-VAR-04 Defaults on environment-specific values

- **Look for:** a `default` for an account ID, environment name, domain, VPC ID or anything that differs
  per deployment; empty-string defaults the API rejects; required variables without `nullable = false`
  where `null` would break the module
- **Why it matters:** a forgotten input silently deploys with another environment's value
- **Instead:** no default for environment-specific values, so the caller must set them; defaults for
  environment-independent values (sizes, retention)
- **Severity:** Minor; Major when the default is a real production identifier
- **Source:** AWS Prescriptive Guidance, structure.html — "For variables that have environment-specific
  values (such as `project_id`), don't provide default values"; same page — "consider whether setting
  `nullable = false` makes sense"

### TF-VAR-05 Output without description

- **Look for:** an `output` block without `description`
- **Why it matters:** outputs are the module's contract with its callers and the documentation's source
- **Instead:** a `description` on every output (sensitive outputs: TF-SEC-07)
- **Severity:** Major (`terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/style — "Include a description for every output";
  tflint rule `terraform_documented_outputs`

### TF-VAR-06 Locals overuse

- **Look for:** a local that only renames a variable (`local.region = var.region`), a chain of locals whose
  intermediate names add nothing, a large `locals` map acting as the real configuration. A local used once
  that names a complex expression is fine
- **Why it matters:** each indirection hides where a value comes from
- **Instead:** reference the variable directly; keep locals for values reused in several places or for a
  complex expression that deserves a name
- **Severity:** Minor; Nit for a single aliasing local
- **Source:** developer.hashicorp.com/terraform/language/style — "Use local values sparingly, as overuse can
  make your code harder to understand"; developer.hashicorp.com/terraform/language/values/locals — "they
  can make configuration harder to read because they obscure where values originate"

### TF-VAR-07 Declared but unused or unwired

- **Look for:** a variable, local or data source nothing references; a module variable the root never sets
  while the specification expects a value; an operator variable missing from `*.tfvars.example`
- **Why it matters:** an unwired input means the value the specification asks for never reaches the
  resource, and dead declarations mislead readers
- **Instead:** wire it from the root and add it to the example tfvars, or delete it
- **Severity:** Major for an unwired input or a missing operator variable (`terraform-practices.md`
  sections 2 and 5); Minor for a dead declaration
- **Source:** tflint rule `terraform_unused_declarations` — "Disallow variables, data sources, and locals
  that are declared but never used"

### TF-VAR-08 Breaking change to a shared module contract

- **Look for:** in a module other roots or repositories call (name the callers found): a removed or
  renamed variable or output, a narrowed `type`, a new variable without a default; or, behind unchanged
  names, a changed default, null handling, generated name, output meaning or permission scope; no version
  bump or caller update
- **Why it matters:** every caller breaks on its next `init` or plan, or plans cleanly with changed
  behaviour
- **Instead:** add new variables with defaults, deprecate before removing, document changed semantics, and
  bump the module's major version when the contract breaks
- **Severity:** Major; Blocker when the change causes an unapproved replacement of an existing resource
  (TF-LIF-02)
- **Source:** AWS Prescriptive Guidance, structure.html — "Adding a variable with a default value is
  backward compatible"; same page — "Removing a variable is backward incompatible"; the semantic part is
  synthesis

### TF-VAR-09 Hard-coded environment facts

- **Look for:** Region names, the `arn:aws:` partition, AMI IDs or availability zone names as literals in
  resources, policy documents and ARNs; the configuration's own account ID as a literal. A literal account
  ID that names an intended external account (a trust target, a log archive account) is correct, best as a
  typed input
- **Why it matters:** the configuration only works in one account, Region and partition, and literal AMIs
  rot; in a trust or resource policy a mistyped account ID grants a stranger access
- **Instead:** `data.aws_caller_identity.current.account_id` for the current account,
  `data.aws_region.current`, `data.aws_partition.current.partition`, an AMI data source or SSM public
  parameter; with AWS provider 6, the per-resource `region` argument where the resource is Region-aware
  (IAM and other global resources are not)
- **Severity:** Minor; Major when a literal account ID in a trust or resource policy is not documented as
  the intended principal (report it to the security reviewer too)
- **Source:** tflint rule `aws_iam_policy_document_gov_friendly_arns` — "Ensure `iam_policy_document` data
  sources do not contain `arn:aws:` ARN's"; provider guide enhanced-region-support (github.com/hashicorp/terraform-provider-aws,
  website/docs/guides) — "While most resources are now Region-aware, there are exceptions"

### TF-VAR-10 check blocks used as enforcement

- **Look for:** a constraint the specification says must stop a deployment implemented only as a `check`
  block assertion; comments or documentation claiming a failed `check` prevents apply
- **Why it matters:** fail fast (stack form of PRN-14): a failed `check` assertion is a warning, so the
  apply goes ahead with the condition broken
- **Instead:** a variable `validation`, a `precondition` or a `postcondition`, chosen by when the value is
  known; an external policy gate for organisation policy; `check` blocks for non-blocking health
  assertions
- **Severity:** Major when the specification requires the constraint to block; Blocker when the change
  demonstrably breaks a documented architecture or security invariant
- **Source:** developer.hashicorp.com/terraform/language/block/check — "The check block is the only
  validation that does not block operations, if a check block's assertion fails, Terraform reports a
  warning and continues executing the current operation"

## 6. Meta-arguments and expression idioms (TF-IDM)

### TF-IDM-01 count over a list of distinct objects

- **Look for:** `count = length(var.x)` with `var.x[count.index]`; `for_each = { for i, v in var.x : i => v }`
  (index keys); instances whose identity is a name, not a position
- **Why it matters:** instances are tracked by position: removing a middle element changes every later
  instance, and for stateful resources that is replacement
- **Instead:** `for_each = { for s in var.subnets : s.name => s }` keyed on a stable identifier; `count` for
  identical instances or a zero-or-one condition
- **Severity:** Major for new code; Blocker when the change reorders or removes an element of an existing
  `count` list or converts `count` to `for_each` without `moved` blocks (TF-LIF-01)
- **Source:** developer.hashicorp.com/terraform/language/v1.5.x/meta-arguments/count — "If an element was
  removed from the middle of the list, every instance after that element would see its subnet_id value
  change"

### TF-IDM-02 Instance keys unknown, unstable or sensitive

- **Look for:** a `count` value known only after apply; `for_each` whose map keys or set elements derive
  from attributes known only after apply (`aws_subnet.x[*].id`, generated names) or from `uuid()`,
  `timestamp()` or `bcrypt()`; `for_each` over a sensitive value. Unknown map values under known keys are
  fine, and `count` accepts a sensitive number
- **Why it matters:** the plan fails ("cannot be determined until apply"), `for_each` keys are shown in the
  UI as instance identities, and once a plan succeeds a key change re-keys and replaces instances
- **Instead:** key on plan-time, non-sensitive values from variables or literals
  (`for_each = var.subnet_config`), and use computed or sensitive values inside the block
- **Severity:** Major (`unsure` without a plan); Blocker for a confirmed failing plan or keys that change
  for existing instances
- **Source:** developer.hashicorp.com/terraform/language/meta-arguments/for_each — "The keys of the map or
  all values in a set of strings must be known values"; same page — "You cannot use sensitive values ...
  as arguments in for_each"; .../meta-arguments/count — "the count value must be known before Terraform
  performs any remote resource operations"; Terraform source `internal/terraform/eval_count.go` —
  "Sensitive values are allowed in count but not for_each"

### TF-IDM-03 Conditional resources referenced unsafely

- **Look for:** `count = var.enabled ? 1 : 0` resources referenced as `aws_x.y[0].arn` from places that run
  when the resource is absent; `count` and `for_each` toggles mixed for the same optional object
- **Why it matters:** the configuration errors with an invalid index when the feature is off
- **Instead:** `one(aws_x.y[*].arn)` (null when absent), and guard the consumer with the same condition
- **Severity:** Major when an existing toggle path errors; Minor otherwise
- **Source:** developer.hashicorp.com/terraform/language/functions/one — "This is a specialized function
  intended for the common situation where a conditional item is represented as either a zero- or
  one-element list"

### TF-IDM-04 dynamic blocks overuse

- **Look for:** `dynamic` blocks generating one or two fixed nested blocks, nested `dynamic` blocks,
  `dynamic` fed directly from a variable that mirrors the nested block schema (then TF-MOD-02 is the
  finding)
- **Why it matters:** the nested structure is no longer readable in the diff, and reviewers cannot see what
  will be created
- **Instead:** write nested blocks literally; use `dynamic` only behind a module interface that hides the
  detail
- **Severity:** Minor
- **Source:** developer.hashicorp.com/terraform/language/expressions/dynamic-blocks — "Overuse of dynamic
  blocks can make configuration hard to read and maintain"; same page — "Always write nested blocks out
  literally where possible"

### TF-IDM-05 Provisioners and script glue

- **Look for:** `provisioner "local-exec"` or `"remote-exec"`, `null_resource` or `terraform_data` running
  `aws` CLI commands or scripts, `data "external"`, scripts that create or modify cloud objects
- **Why it matters:** Terraform does not track what the script creates or changes, so drift and failed
  half-runs are invisible; a command string built from variables is an injection path, and the script
  runs with the operator's credentials (security reviewer, group 4)
- **Instead:** the provider resource for the object; when none exists, a narrowly scoped
  `terraform_data` with idempotent commands, inputs passed as environment variables, and a comment saying
  why
- **Severity:** Major; Blocker when a command interpolates a value a caller controls into a shell string
- **Source:** developer.hashicorp.com/terraform/language/provisioners — "You should exhaust all alternatives
  before using provisioners in your configurations. This is because Terraform cannot predictably model
  provisioner behaviors represented in the configuration"; AWS Prescriptive Guidance, structure.html —
  "Terraform doesn't account for, or manage, the state of resources that are created through scripts"

## 7. Drift and plan stability (TF-DRF)

### TF-DRF-01 Inline blocks mixed with standalone resources for the same object

- **Look for:** `aws_security_group` with `ingress`/`egress` blocks plus `aws_vpc_security_group_*_rule` or
  `aws_security_group_rule` for the same group; `aws_s3_bucket` with `lifecycle_rule`, `logging`, `grant`
  or `cors_rule` plus the matching `aws_s3_bucket_*` resource; `aws_iam_role` `inline_policy` plus
  `aws_iam_role_policy`, or `managed_policy_arns` plus `aws_iam_role_policy_attachment` or
  `aws_iam_policy_attachment`, for the same role; `aws_ec2_tag` on an object whose own resource sets `tags`
- **Why it matters:** two resources manage one set of rules, so every plan removes what the other added:
  perpetual diffs, rules overwritten, access briefly revoked on each apply
- **Instead:** standalone resources only (`aws_vpc_security_group_ingress_rule` with one CIDR per rule,
  `aws_s3_bucket_lifecycle_configuration`, `aws_iam_role_policy`, `aws_iam_role_policy_attachment`)
- **Severity:** Major; Blocker when the overwritten rules are security group rules or policies on a live
  resource
- **Source:** registry docs for `aws_security_group` (github.com/hashicorp/terraform-provider-aws,
  website/docs/r/security_group.html.markdown) — "Doing so may cause rule conflicts, perpetual
  differences, and result in rules being overwritten"; `aws_s3_bucket` docs — "Terraform will assume
  management over the full set of Lifecycle rules for the S3 bucket, treating additional Lifecycle rules as
  drift"; `aws_iam_role` docs — "take over exclusive management of the role's respective policy types";
  `aws_ec2_tag` docs — "should not be combined with the Terraform resource for managing the parent
  resource"

### TF-DRF-02 Volatile values in arguments

- **Look for:** `timestamp()`, `uuid()` or `plantimestamp()` in tags, names or descriptions, or in the
  `input` or `triggers_replace` of a `terraform_data` that a `replace_triggered_by` references;
  `default_tags` built from such a value
- **Why it matters:** every plan shows a change, or a replacement on every run, so real changes drown in
  noise
- **Instead:** `time_static` or `random_*` resources from the time and random providers, generated once and
  kept in state
- **Severity:** Major; Blocker when it drives a replacement of an existing resource
  (`terraform-practices.md` section 5)
- **Source:** developer.hashicorp.com/terraform/language/functions/timestamp — "using this function directly
  with resource attributes will cause a diff to be detected on every Terraform run";
  developer.hashicorp.com/terraform/language/functions/uuid — "using it directly in resource arguments will
  result in spurious diffs"; developer.hashicorp.com/terraform/language/meta-arguments/lifecycle — "You can
  only reference managed resources in replace_triggered_by expressions"

### TF-DRF-03 Moving-target image lookups

- **Look for:** `data "aws_ami"` with `most_recent = true` feeding `aws_instance.ami` (a new image means a
  new instance; confirm on the provider page) or a launch template (a new version; instances change only
  through the group's rollout) with no stated rollout; `allow_unsafe_filter = true`; no `owners`
- **Why it matters:** the plan depends on the date it runs, and an unsafe filter lets a third party
  publish the image that gets picked (security reviewer, group 4)
- **Instead:** separate trusted selection (`owners` or an image ID), pinning (an immutable AMI ID or
  versioned image input where deployments must be reproducible) and rollout (a launch template version);
  an SSM public parameter is a rolling alias, right only where rolling is intended; never
  `allow_unsafe_filter`
- **Severity:** Major
- **Source:** registry docs for data source `aws_ami` (github.com/hashicorp/terraform-provider-aws,
  website/docs/d/ami.html.markdown) — "With unsafe filters and `most_recent` set to `true`, a third party
  may introduce a new image which will be returned by this data source";
  docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami-parameter-store.html — "always points to the
  latest version of the Amazon Linux 2023 AMI"; the rollout part is synthesis

### TF-DRF-04 Exclusive-management resources

- **Look for:** `aws_iam_policy_attachment`, `*_exclusive` resources (`aws_iam_role_policies_exclusive`),
  or arguments that take exclusive ownership of a sub-collection, on objects other stacks or teams also
  attach to
- **Why it matters:** the resource revokes every attachment it does not list, including those made by other
  Terraform resources, which is an outage elsewhere
- **Instead:** `aws_iam_role_policy_attachment` (one per pair); exclusive resources only where the project
  wants exclusive ownership, with a comment
- **Severity:** Major; Blocker when the policy or role is shown to be shared
- **Source:** registry docs for `aws_iam_policy_attachment` — "even any users/roles/groups that have the
  attached policy via any other mechanism (including other Terraform resources) will have that attached
  policy revoked by this resource"; tflint rule `aws_iam_policy_attachment_exclusive_attachment`

## 8. Providers, versions and tags (TF-PRV)

### TF-PRV-01 required_version missing or too low

- **Look for:** a root or new module without `terraform { required_version = ... }`; a feature newer than
  the declared minimum (`removed` blocks, ephemeral values, write-only arguments, cross-variable
  validation; see How to apply); `mock_provider` or `override_*` in tests while the minimum admits
  Terraform older than 1.7.0
- **Why it matters:** an older binary fails with confusing errors, or parses the file differently
- **Instead:** `required_version = ">= <minimum with every feature used>"` in `versions.tf`; a test-runner
  version may be pinned separately (CI or documentation) above the consumers' minimum
- **Severity:** Major; Minor when the newer feature appears only in tests and the project pins the test
  runner separately
- **Source:** developer.hashicorp.com/terraform/language/style — "We also recommend that you set a minimum
  required version of the Terraform binary using the required_version in your terraform block"; tflint
  rule `terraform_required_version`; developer.hashicorp.com/terraform/language/tests/mocking — "Test
  mocking is available in Terraform v1.7.0 and later"

### TF-PRV-02 Child module without its own required_providers

- **Look for:** a module that uses `aws_*` resources without `required_providers { aws = { source =
  "hashicorp/aws", version = ... } }`; a provider without `source`; required providers declared but unused
- **Why it matters:** requirements are not inherited; without a declaration Terraform assumes
  `hashicorp/<local name>`, so a non-HashiCorp provider resolves to the wrong source and the module's
  minimum version is lost from version selection
- **Instead:** a `versions.tf` in every module with source and constraint
- **Severity:** Major; Minor for an unused required provider
- **Source:** developer.hashicorp.com/terraform/language/modules/develop/providers — "Only provider
  configurations are inherited by child modules, not provider source or version requirements. Each module
  must declare its own provider requirements"; developer.hashicorp.com/terraform/language/providers/requirements
  — implied source "registry.terraform.io/hashicorp/<LOCAL NAME>"; tflint rules
  `terraform_required_providers`, `terraform_unused_required_providers`

### TF-PRV-03 Constraint style and lock file

- **Look for:** a root module with `version = ">= 5.0"` only (no upper bound) or no constraint; a reusable
  module with an exact or `~>` pin that callers cannot satisfy together; a root's `.terraform.lock.hcl`
  deleted, ignored in `.gitignore`, or changed without the change saying which provider moved
- **Why it matters:** once `init -upgrade` runs or the lock file is missing, an unbounded root takes a
  breaking major version; an over-pinned shared module blocks every caller's upgrade; an unreviewed lock
  change is an unreviewed dependency change. Only the root's lock file counts
- **Instead:** roots `~> 6.0` (or the project's pin) with the lock file committed; reusable modules
  `>= <minimum>`
- **Severity:** Major for an unbounded or missing root constraint or a deleted lock file; Minor for an
  over-pinned reusable module or an unexplained lock change
- **Source:** developer.hashicorp.com/terraform/language/expressions/version-constraints — "Reusable modules
  should constrain only their minimum allowed versions of Terraform and providers"; same page — "Root
  modules should use a ~> constraint to set both a lower and upper bound on versions for each provider they
  depend on"; developer.hashicorp.com/terraform/language/files/dependency-lock — "Terraform will always
  re-select that version for installation"; same page — "You should include this file in your version
  control repository"

### TF-PRV-04 Provider configuration binding and hygiene

- **Look for:** a new resource, data source or module call bound to the default (or an unintended)
  configuration when the specification puts it in another account or Region; a wrong alias in
  `providers = {}`; a provider block or alias removed while its resources remain in state. Style: only
  aliased `provider "aws"` blocks with no default; providers spread over several files
- **Why it matters:** valid HCL operates in the wrong account or Region, and removing a provider
  configuration before its resources makes the plan fail
- **Instead:** explicit `provider =` and `providers = { aws.dst = aws.usw2 }` wiring checked against the
  specification; with AWS provider 6, a per-resource `region` only where the resource supports it; destroy
  or move resources before removing their provider; one default plus named aliases in `providers.tf`
- **Severity:** Major for an evidenced binding mismatch or a provider removed with resources left (`unsure,
  needs runtime verification` for state); Blocker when it breaks a documented account-isolation invariant;
  Minor for the style cases
- **Source:** developer.hashicorp.com/terraform/language/style — "Always include a default provider
  configuration and define all of your providers in the same file"; .../modules/develop/providers — "you
  must ensure that all resources that belong to a particular provider configuration are destroyed before
  you can remove that provider configuration's block"

### TF-PRV-05 Tags outside default_tags

- **Look for:** the same `tags = { Environment = ..., Project = ... }` on many resources instead of provider
  `default_tags`; resource tags repeating a `default_tags` key with the same value; required tags missing;
  `aws_autoscaling_group` relying on `default_tags` (not supported there)
- **Why it matters:** per-resource tag maps drift, and tag-based cost allocation and access control miss
  resources
- **Instead:** `provider "aws" { default_tags { tags = var.tags } }` in the root; per-resource `tags` only
  for resource-specific keys such as `Name`; `tag` blocks with `propagate_at_launch` on Auto Scaling groups
- **Severity:** Major (`terraform-practices.md` section 5: per-resource tags instead of `default_tags`)
- **Source:** AWS provider documentation, `default_tags` (github.com/hashicorp/terraform-provider-aws,
  website/docs/index.html.markdown) — "This is designed to replace redundant per-resource `tags`
  configurations"; tflint rules `aws_provider_missing_default_tags`, `aws_resource_missing_tags`

### TF-PRV-06 Deprecated resources and arguments

- **Look for:** `aws_security_group_rule` and inline security group rules in new code; `aws_iam_role`
  `inline_policy` or `managed_policy_arns`; inline sub-configuration blocks on `aws_s3_bucket`; deprecated
  Lambda runtimes. Previous-generation instance types are supported, not deprecated: report them only when
  the project's rules ask for current generation (Nit)
- **Why it matters:** a deprecated argument can be removed in a later major provider version, and several
  carry the drift problems of TF-DRF-01
- **Instead:** `aws_vpc_security_group_ingress_rule` and `aws_vpc_security_group_egress_rule`,
  `aws_iam_role_policy` and `aws_iam_role_policy_attachment`, the `aws_s3_bucket_*` resources, a supported
  runtime; mark `unsure` with the registry page when unsure an argument is deprecated (a linter rule name
  is not proof)
- **Severity:** Minor; Major for a deprecated Lambda runtime
- **Source:** registry docs for `aws_iam_role` — "The `inline_policy` argument is deprecated. Use the
  `aws_iam_role_policy` resource instead"; tflint rules `aws_security_group_rule_deprecated` — "The
  `aws_security_group_rule` resource should be replaced with `aws_vpc_security_group_egress_rule` or
  `aws_vpc_security_group_ingress_rule`", `aws_lambda_function_deprecated_runtime`;
  docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html — "we continue to support the following
  previous generation instance types"

## 9. Security coding rules (TF-SEC)

These are the Terraform coding forms of the security reviewer's checklist; its reviewer skill carries the
depth (confused deputy, encryption defaults, false positives). Grant checks (TF-SEC-02 to TF-SEC-05) apply
to `Allow` statements, the default `effect` of `aws_iam_policy_document`; a wildcard in a `Deny` statement
restricts access and is not a grant.

### TF-SEC-01 Policies built as strings

- **Look for:** IAM, bucket, key or queue policies as heredoc JSON, `templatefile()` output or string
  concatenation; a variable that can widen `Action`, `Principal` or a `Resource` pattern unvalidated;
  `${aws:username}` inside an HCL string. A `Resource` referencing a managed resource's ARN is normal
- **Why it matters:** the rendered policy is hard to review, string JSON is prone to formatting diffs, and
  `${...}` is consumed by Terraform instead of IAM
- **Instead:** `data "aws_iam_policy_document"` with `&{aws:username}`, or `jsonencode()` with
  `$${aws:username}`; judge the rendered policy, not whether a variable appears in it
- **Severity:** Minor; Major when an unvalidated variable can widen `Action`, `Resource` or `Principal`
  (an actual excessive grant is TF-SEC-02 to TF-SEC-04)
- **Source:** registry docs for `aws_iam_role` — "you can sidestep potential complications arising from
  formatting discrepancies, whitespace inconsistencies, and other nuances inherent to JSON"; data source
  `aws_iam_policy_document` docs — "use `&{...}` notation for interpolations that should be processed by
  AWS rather than by Terraform"; developer.hashicorp.com/terraform/language/expressions/strings — `$${` is
  "Literal ${, without beginning an interpolation sequence"

### TF-SEC-02 Wildcard actions and resources

- **Look for:** in an `Allow` statement, `actions = ["*"]` or `["s3:*"]`, `resources = ["*"]` for actions
  that support resource-level permissions, `"arn:aws:s3:::*"` where one bucket is meant
- **Why it matters:** the role can do more than its task on more than its resources, so a compromise
  spreads
- **Instead:** named actions and ARNs (bucket ARN plus `"${bucket_arn}/*"`); `"*"` only for actions without
  resource-level permissions, with a comment
- **Severity:** Blocker for `"*"` in a resource without a justified comment (`terraform-practices.md`
  section 5) and for `"*"` actions; Major for service-wide wildcards such as `s3:*`
- **Source:** Checkov `CKV_AWS_1`, `CKV_AWS_49`, `CKV_AWS_356` (`aws_iam_policy_document`), `CKV_AWS_62`,
  `CKV_AWS_63`, `CKV_AWS_355` (inline policy resources); AWS Prescriptive Guidance, security.html — "Define
  actions at the operation level, and allow calls only to required APIs on specific resources";
  docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic_AccessPolicyLanguage_Interplay.html
  — "the Deny statement trumps the Allow statement"

### TF-SEC-03 Escalation and credential-exposure actions

- **Look for:** in an `Allow` statement, `iam:PassRole` on `"*"` or without an `iam:PassedToService`
  condition; `iam:CreatePolicyVersion`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:CreateAccessKey`,
  `sts:AssumeRole` on broad resources; `secretsmanager:GetSecretValue` or `kms:Decrypt` on `"*"`
- **Why it matters:** a principal that can write its own policies, or pass a broader role to a service,
  exceeds its intended access; how far depends on the passable roles, which the security reviewer names
- **Instead:** scope to the specific role, policy, secret or key ARN and add the condition key
- **Severity:** Blocker for `iam:PassRole` or policy-writing actions on `"*"` (`terraform-practices.md`
  section 5: `"*"` in an IAM resource); Major otherwise
- **Source:** Checkov `CKV_AWS_107` (credentials exposure), `CKV_AWS_108` (data exfiltration),
  `CKV_AWS_109` (permissions management), `CKV_AWS_110` (privilege escalation), `CKV_AWS_111` (write
  access without constraints); `CKV_AWS_286` to `CKV_AWS_290` for inline policy resources;
  IAM `id_roles_use_passrole.html` — "make sure that a user doesn't pass a role where the role has more
  permissions than you want the user to have"

### TF-SEC-04 Open principals in trust and resource policies

- **Look for:** `principals { type = "AWS"  identifiers = ["*"] }` without a tightening condition; a trust
  policy any account can assume; an `aws_lambda_permission` whose `principal` is a service principal and
  that has no `source_arn` (and no `source_account` for S3 or SES); bucket, queue, topic or key policies
  granting a service principal without the source condition that service documents
- **Why it matters:** anyone, or another customer's resource acting through an AWS service (confused
  deputy), can use the resource
- **Instead:** the specific account, role or service principal; for a service principal, the source
  condition that integration populates (`aws:SourceArn`, `aws:SourceAccount` or the service's own
  mechanism). A grant to a named account or role is scoped by its principal, not by `source_arn`
- **Severity:** Blocker for `Principal: "*"` without a tightening condition (`terraform-practices.md`
  section 5); Major for a service-principal grant missing the documented source condition
- **Source:** docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html — "not all
  service integrations require the use of this global condition key"; `aws_lambda_permission` docs —
  `source_account` "for cross-account access, S3, or SES"; Checkov `CKV_AWS_60`, `CKV_AWS_61`,
  `CKV_AWS_283`, `CKV_AWS_70`, `CKV_AWS_33`, `CKV_AWS_301`, `CKV_AWS_364`

### TF-SEC-05 Broad managed policies and attachments outside the attachment point

- **Look for:** `AdministratorAccess`, `PowerUserAccess` or `*FullAccess` attached to a workload role;
  policies attached to users; roles, policies or attachments created inside a resource module
- **Why it matters:** the grant is far wider than the task, and grants spread across modules cannot be
  reviewed in one place
- **Instead:** a customer-managed policy built from the resource modules' exported policy JSON, attached
  only at the documented attachment point (`terraform-practices.md` section 2)
- **Severity:** Blocker for a role or attachment in a resource module (`terraform-practices.md` section 5);
  Major for a broad managed policy
- **Source:** Checkov `CKV_AWS_274` (AdministratorAccess), `CKV_AWS_40` (policies attached only to groups or
  roles); the attachment-point rule is plugin policy (`terraform-practices.md` section 2)

### TF-SEC-06 Secrets in configuration

- **Look for:** passwords, tokens, keys or connection strings as literals or variable defaults in `.tf`,
  `*.tfvars.example`, provider blocks (`access_key`, `secret_key`), Lambda `environment` variables or EC2
  `user_data`
- **Why it matters:** the secret is in version control history and in state
- **Instead:** Secrets Manager or SSM `SecureString` read at run time, or a managed secret
  (`manage_master_user_password = true`); provider credentials from the environment or a role
- **Severity:** Blocker (`terraform-practices.md` section 5)
- **Source:** AWS provider documentation — "Hard-coded credentials are not recommended in any Terraform
  configuration"; Checkov `CKV_AWS_41` (provider), `CKV_AWS_45` (Lambda environment), `CKV_AWS_46` (EC2
  user data)

### TF-SEC-07 Secrets persisted to state and unmarked sensitive values

- **Look for:** `password = var.db_password` where `password_wo` or a managed secret exists; a `*_wo`
  argument fed from a persistent source (a `random_password` resource, a non-ephemeral variable) or
  without its `*_wo_version` managed; secrets without `sensitive = true`; `nonsensitive()` on a secret
- **Why it matters:** `sensitive` hides a value from the CLI, not from state and plan files; a write-only
  argument is not stored, but its source can be, and without a version change no new value is sent.
  Fixing the destination does not clean older state versions
- **Instead:** `manage_master_user_password = true`, or an ephemeral source (Terraform 1.10) into a `*_wo`
  argument (1.11) with its version argument; `sensitive = true` on every secret; rotate a leaked secret
- **Severity:** Major (`terraform-practices.md` section 5 for an unmarked sensitive output); Blocker for
  `nonsensitive()` on a secret
- **Source:** developer.hashicorp.com/terraform/language/manage-sensitive-data — "Terraform stores values
  with the sensitive argument in both state and plan files"; .../manage-sensitive-data/ephemeral —
  "Terraform does not store them in state or plan files" and "Use a version argument to trigger updates of
  write-only arguments"; `random_password` docs — use the ephemeral variant "to avoid storing the password
  in the plan or state file"; tflint rule `aws_write_only_arguments`

### TF-SEC-08 Public exposure switches

- **Look for:** `aws_s3_bucket_public_access_block` with any flag `false`, or missing on a new bucket where
  the project requires it; `0.0.0.0/0` or `::/0` ingress on 22, 3389, database or cache ports, or on all
  ports; `publicly_accessible = true`; `map_public_ip_on_launch = true`; `associate_public_ip_address =
  true` on private workloads
- **Why it matters:** the resource becomes reachable from the internet outside the documented entry points
  once a public address, an internet route and an open security group line up; one flag alone is a cue
- **Instead:** all four public access block flags `true`; ingress from security group IDs or prefix lists;
  private subnets for data stores
- **Severity:** Blocker for a data store or administration port shown reachable (address, route and
  security group visible); Major for a public address on a private workload or a flag set `false`; Minor
  for a missing block resource on a bucket nothing opens, Major where the project requires it
- **Source:** docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html — "By default, new
  buckets, access points, and objects don't allow public access"; Checkov `CKV_AWS_53`, `CKV_AWS_54`,
  `CKV_AWS_55`, `CKV_AWS_56`, `CKV2_AWS_6` (S3); `CKV_AWS_24`, `CKV_AWS_25`, `CKV_AWS_260`, `CKV_AWS_277`
  (security groups); `CKV_AWS_17` (RDS); `CKV_AWS_130` (subnets); `CKV_AWS_88` (EC2)

### TF-SEC-09 Encryption, logging and recovery arguments

- **Look for:** `storage_encrypted = false` or unset on RDS; a symmetric `aws_kms_key` without
  `enable_key_rotation = true` (asymmetric, HMAC and custom key store keys cannot rotate automatically); a
  log group without `kms_key_id` or retention where the specification asks for them; a data bucket without
  versioning; a removed `aws_cloudtrail`, flow log or access logging
- **Why it matters:** unencrypted data and its snapshots rest on access policies alone, and evidence is
  lost when it is needed
- **Instead:** the encryption, rotation, retention and versioning arguments the specification requires;
  check the service's current default before calling a resource unencrypted
- **Severity:** Major; Blocker when the change disables encryption or logging a documented invariant
  requires (`terraform-practices.md` section 5)
- **Source:** docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html — "not eligible for automatic
  or on-demand key rotation, including asymmetric KMS keys, HMAC KMS keys and KMS keys in custom key
  stores"; Checkov `CKV_AWS_16` (RDS encryption), `CKV_AWS_7` (KMS rotation),
  `CKV_AWS_158`, `CKV_AWS_338` (log groups), `CKV_AWS_21` (S3 versioning), `CKV2_AWS_11` (VPC flow logs)

## 10. Testing (TF-TST)

### TF-TST-01 New module logic without tests

- **Look for:** new or changed conditionals, `for` expressions, validations or naming rules in a reusable
  module that no existing or changed `run` block exercises (search the tests; another framework the
  project uses counts), in a project that tests its modules
- **Why it matters:** expression logic fails only when a caller hits the untested branch
- **Instead:** a `run` block per branch asserting the planned values
- **Severity:** Minor; Major when the project's rules require tests
- **Source:** developer.hashicorp.com/terraform/language/style — "We recommend that you write tests for your
  Terraform modules and run them just as you run your tests for your application code"

### TF-TST-02 Test runs that reach real infrastructure

- **Look for:** in unit tests, `run` blocks in apply mode against a real provider (no `command = plan`, no
  `mock_provider` for it); plan-mode tests that read live data sources or run `data "external"`; partial
  mocks that leave a real provider reachable; apply-mode tests without the project's sandbox account
- **Why it matters:** `terraform test` creates and destroys real resources by default (cost, credentials,
  orphans when cleanup fails); plan mode still configures providers and reads data sources, so it is not
  offline
- **Instead:** `mock_provider` for every provider in unit tests (apply with complete mocks is fine,
  `terraform-practices.md` section 4), or `command = plan` under the project's credentials policy; real
  apply-mode tests only where the project runs integration tests
- **Severity:** Major (`terraform-practices.md` section 4: written tests use `command = plan` or mocks)
- **Source:** developer.hashicorp.com/terraform/language/tests — "By default, each run block executes with
  command = apply instructing Terraform to execute a complete apply operation against your configuration";
  the plan-mode part is synthesis

### TF-TST-03 Mocks with too old a required_version

Retired 2026-10-16: merged into TF-PRV-01

### TF-TST-04 Validations untested or assertions that prove nothing

- **Look for:** new `validation`, `precondition` or `postcondition` blocks with no `run` block using
  `expect_failures`; assertions that compare a variable with the value the test just set; plan-mode
  assertions on attributes known only after apply
- **Why it matters:** a validation whose condition is inverted passes silently, and a tautological assertion
  is green whatever the module does
- **Instead:** one passing and one failing run per condition, `expect_failures` naming the object that
  reports it (`var.x` for a validation, the resource or data source address for its conditions,
  `output.x`, `check.x`); assertions on resource attributes the module derives
- **Severity:** Minor
- **Source:** developer.hashicorp.com/terraform/language/tests — "The test passes if the checkable objects
  you specify report an issue"; same page — checkable objects are "resources, data sources, check blocks,
  input variables, and outputs"; same page — "your assertions should only evaluate values that are certain
  to be computed before the checkable object is due to fail"; the tautology part is synthesis

## 11. Style (TF-STY)

### TF-STY-01 Names

- **Look for:** resource labels repeating the type (`aws_s3_bucket.s3_bucket_logs`), camelCase or hyphens,
  plural labels for single objects, `this` or `main` on a type with several instances, numeric inputs
  without units, negative boolean names (`disable_x`)
- **Why it matters:** addresses are permanent (renames need `moved`), so names are hard to fix later
- **Instead:** snake_case nouns (`aws_s3_bucket.logs`), `this` or `main` only for the only resource of its
  type in a module, `retention_days`, `enable_x`
- **Severity:** Nit
- **Source:** developer.hashicorp.com/terraform/language/style — "Do not include the resource type in the
  resource identifier since the resource address already includes it"; AWS Prescriptive Guidance,
  structure.html — "Add units to the names of inputs, local variables, and outputs that represent numeric
  values"; tflint rule `terraform_naming_convention`

### TF-STY-02 Deprecated and non-idiomatic syntax

- **Look for:** interpolation-only strings (`"${var.x}"`), legacy index syntax (`list.0`), two-argument
  `lookup()`, `//` or `/* */` comments, duplicate map keys, comparisons with `[]`
- **Why it matters:** noise in review, and two forms are bugs: duplicate keys keep one value, and
  `x == []` is always false for a typed collection, so the condition never matches
- **Instead:** `var.x`, `list[0]`, `var.m["k"]`, `length(x) == 0`, `#` comments
- **Severity:** Nit; Minor for duplicate map keys or a comparison with `[]`; Major when a comparison with
  `[]` gates a resource, validation or condition in the change
- **Source:** tflint rules `terraform_deprecated_interpolation`, `terraform_deprecated_index`,
  `terraform_deprecated_lookup`, `terraform_comment_syntax`, `terraform_map_duplicate_keys`,
  `terraform_empty_list_equality` — "a comparison with a single [] with the goal of checking if a
  collection is empty, will always return false"

### TF-STY-03 Layout, order and comments

- **Look for:** meta-arguments not first in a block (`count`/`for_each` first, `lifecycle` and
  `depends_on` last); data sources far from the resources that use them; a non-obvious `ignore_changes` or
  `count` toggle without a comment; new `override.tf` or `*_override.tf` files. File placement of variables
  and outputs is TF-MOD-10; an uncommented `depends_on` is TF-DEP-01
- **Why it matters:** readers find the interface and the unusual parts quickly; override files change
  resources from a distance
- **Instead:** the style guide's order; a one-line comment on each non-obvious meta-argument; no override
  files, or a comment on the original resource when one is unavoidable
- **Severity:** Nit; Minor for a new override file or an uncommented `ignore_changes`
- **Source:** developer.hashicorp.com/terraform/language/style — "If the effect of the meta-argument is not
  immediately obvious, use a comment for clarification"; same page — "Use them sparingly and add comments
  to the original resource definitions, as these overrides make your code harder to reason about"

## 12. Out of scope / handled elsewhere

- Formatting, validation and linters as tools: `terraform fmt -check`, `validate`, tflint and Checkov are
  run by the main conversation (`standalone-review.md` section 2); their output enters the triage tagged
  *(tool)*. The tflint and Checkov IDs above let a reviewer name the rule; a reviewer does not run them
- State files, real tfvars and `.terraform/` in the change: findings by path alone
  (`standalone-review.md` section 1)
- Specification fidelity and project invariants: `review.md` groups 1 and 6
- Whether an argument, resource or IAM action exists, and whether an argument forces replacement:
  `review.md` group 7; reviewers mark `unsure` and the main conversation verifies in the provider and AWS
  documentation
- Confused-deputy depth, encryption defaults per service, false positives on `Resource: "*"`:
  `implement-from-spec:reviewing-terraform-security`'s checklist
- Anything only a plan against live state or a deployed system settles: the report's *Needs runtime
  verification* section, run by the operator
- Policy-as-code engines (Sentinel, OPA) and cost: not reviewed here

## Sources

All read on 2026-10-16. HashiCorp pages are under developer.hashicorp.com/terraform/.

- HashiCorp language docs: `language/style`; `language/modules/develop` (and `/structure`, `/composition`,
  `/providers`, `/refactoring`); `language/providers/requirements`; `language/block/removed`,
  `language/block/check`, `language/block/variable`; `language/state/remove`, `/remote-state-data`,
  `/workspaces`, `/locking`; `language/import` (and `/generating-configuration`);
  `language/meta-arguments/count`, `/for_each`, `/depends_on`, `/lifecycle` (and `language/v1.5.x/meta-arguments/count`);
  `language/data-sources`; `language/values/locals`, `/outputs`, `/variables`;
  `language/expressions/type-constraints`, `/strings`, `/references`, `/dynamic-blocks`,
  `/version-constraints`; `language/validate`; `language/provisioners`; `language/manage-sensitive-data`
  (and `/ephemeral`); `language/backend` and `language/backend/s3`; `language/files/dependency-lock`;
  `language/tests` (and `/mocking`); `language/functions/timestamp`, `/uuid`, `/one`, `/try`,
  `/nonsensitive`
- HashiCorp CLI docs: `cli/workspaces`, `cli/commands/init`
- Terraform source and changelogs (github.com/hashicorp/terraform): `internal/initwd/module_install.go`,
  `internal/terraform/eval_count.go`, `CHANGELOG.md` on the v1.7, v1.9, v1.10 and v1.11 branches
- AWS Prescriptive Guidance, Best practices for using the Terraform AWS Provider:
  docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/ (structure.html,
  security.html, backend.html, version.html, community.html)
- AWS documentation (docs.aws.amazon.com): IAM `reference_policies_condition-keys.html`,
  `reference_policies_evaluation-logic_AccessPolicyLanguage_Interplay.html`, `id_roles_use_passrole.html`;
  KMS `rotate-keys.html`; S3 `create-bucket-overview.html`; EC2 `instancetypes/instance-types.html` and
  `UserGuide/finding-an-ami-parameter-store.html`
- Terraform AWS provider docs (github.com/hashicorp/terraform-provider-aws `website/docs/`):
  `index.html.markdown`, `r/iam_role`, `r/iam_policy_attachment`, `r/security_group`, `r/s3_bucket`,
  `r/db_instance`, `r/rds_cluster`, `r/dynamodb_table`, `r/launch_template`, `r/lambda_permission`,
  `r/ec2_tag`, `d/iam_policy_document`, `d/ami`, `d/partition`, `guides/resource-tagging`,
  `guides/enhanced-region-support`; random provider `docs/resources/password.md`
- TFLint rulesets: github.com/terraform-linters/tflint-ruleset-terraform (`docs/rules/`) and
  github.com/terraform-linters/tflint-ruleset-aws (`docs/rules/`)
- Checkov Terraform policy index: www.checkov.io/5.Policy%20Index/terraform.html
- OpenTofu documentation (opentofu.org/docs/): `language/ephemerality/`, `cli/commands/test/`,
  `language/state/encryption/`, `language/settings/backends/s3/`, `language/resources/syntax/`
- Shared principles and architecture smells: `${CLAUDE_PLUGIN_ROOT}/core/review/principles-and-architecture-smells.md`
