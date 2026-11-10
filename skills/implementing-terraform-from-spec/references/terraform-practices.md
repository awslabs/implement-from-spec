# Terraform practices

The defaults this skill applies when the project's CLAUDE.md documents nothing stricter. The project's
documented pattern always wins; record any deviation as a ruling in the ledger.

## Contents

1. Layout
2. Module pattern and checklist
3. State safety
4. Validation
5. Review classes
6. Sources these defaults follow

## 1. Layout

The default layout, the one the plugin's Terraform test fixture uses: `bootstrap/` (state bucket
and lock table, local state; recent Terraform versions lock S3 state with a lock file instead of a DynamoDB
table, so follow what the project's pinned version and backend config use), `environment/` (the root module and its wiring), `envs/` (tfvars and backend
config per environment, with a commented `*.tfvars.example`), `modules/<name>/`. A project with another
layout states it in CLAUDE.md; use that.

## 2. Module pattern and checklist

Every new module has `main.tf` (resources, data sources, IAM policy documents), `variables.tf` (every
input with a `type` and a `description`), `outputs.tf` (at least name, ARN and the policy JSON its
consumers need) and `versions.tf` (`required_version` and the provider constraint).

IAM flows one way: resource modules export policy JSON from `aws_iam_policy_document` data sources; only
the compute module (or the project's documented attachment point) creates roles, policies and
attachments. That keeps a role's whole grant reviewable in one file.

Checklist (phase 3 and the review):

- each new module is about 300 lines of HCL or less
- resource modules create no roles or attachments
- new attachment-point variables follow the existing names (for example `<resource>_rw_policy_json`,
  `<resource>_enabled`)
- every new module has a `versions.tf` with a constraint compatible with the root's
- the only existing resource the change modifies is the attachment point, receiving new inputs
- every variable has a `type` and a `description`; every output has a `description`
- tags come from provider `default_tags`

## 3. State safety

- A targeted plan (`-target=module.<new>`) shows the targeted part of the graph is additive (zero destroys,
  zero changes outside the attachment point); only a full plan of the root shows nothing else changes
- Data-holding resources carry `lifecycle { prevent_destroy = true }` and the resource's own deletion
  protection argument where it has one
- Renaming a resource address destroys and recreates it unless a `moved` block records the rename; a
  rename without one is a Blocker
- An argument that forces replacement on an existing resource is a stop-and-ask
- No secrets in `.tf` or `*.tfvars.example`; secrets live in Secrets Manager or SSM and are read at run
  time, and sensitive outputs are marked `sensitive = true`
- `apply`, `destroy`, `import`, `taint`, `state` edits and `init -migrate-state` are the operator's; the plugin's approval gate (K22)
  asks before any of them, and before an `init` with the backend enabled (`init -backend=false` is enough
  for `fmt` and `validate`)

## 4. Validation

    AWS_PROFILE=<profile> terraform -chdir=<root> fmt -recursive
    AWS_PROFILE=<profile> terraform -chdir=<root> validate
    AWS_PROFILE=<profile> terraform -chdir=<root> plan -var-file=<tfvars> -target=module.<new_a> -target=module.<new_b>

`fmt` and `validate` need no confirmation. The plan reads live state, so K22 asks. When the project uses
`terraform test`, tflint, Checkov or a policy engine, run them as its CI does and report each.

Tests: the native framework (`*.tftest.hcl` files, `terraform test`) exists since Terraform v1.6.0, and
mock providers (`mock_provider` blocks) since v1.7.0 ("Test mocking is available in Terraform v1.7.0 and
later"). A `run` block executes `command = apply` unless it says `command = plan`, so a test file the
skill writes uses `command = plan` or mock providers, and K22 asks before `terraform test` either way.
Check the project's `required_version` before relying on mocks.

Static analysis: tflint and Checkov are optional. Run them when installed or when the project's CI does,
and report each; a missing tool is reported as not run, never as clean.

## 5. Review classes

- **Blocker**: a destroy or replacement of an existing resource; a rename without `moved`; a secret in HCL
  or example tfvars; `Principal: "*"` without a tightening condition; `"*"` in an IAM resource without a
  justified comment; a role or attachment inside a resource module; an architecture invariant broken; red
  fmt, validate or plan
- **Major**: a variable without type or description; an output without description; missing
  `prevent_destroy` or deletion protection where data lives; per-resource tags instead of `default_tags`;
  an operator variable missing from the example tfvars; a module over about 300 lines
- **Minor** and **Nit**: naming polish, comment rot, redundant `depends_on`

## 6. Sources these defaults follow

Read these for the detail; this file does not restate them, and the project's rules override them:

- HashiCorp's agent skills (github.com/hashicorp/agent-skills, MPL-2.0): `terraform-style-guide`
  (`plugins/terraform/skills/terraform-style-guide`: file organisation, formatting, naming, variables,
  outputs, version pinning, review checklist) and `terraform-test`
  (`plugins/terraform/skills/terraform-test`: test files, run blocks, mocking, running tests)
- AWS Prescriptive Guidance, "Best practices for using the Terraform AWS Provider"
  (docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/): security
  (least privilege, remote state encryption, "Perform static analysis"), backends, code base structure,
  provider version management, community modules
- Terraform's testing documentation (developer.hashicorp.com/terraform/language/tests and
  .../tests/mocking): the version facts in section 4
