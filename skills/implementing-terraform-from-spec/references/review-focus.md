Terraform for an AWS stack (modules under modules/ or the project's documented layout, wiring in the environment root), implementing specification items. Look hardest at:
- Fidelity to the specification items and the plan's Global constraints: names, values, outputs exactly as stated; anything missing, stubbed or not wired into the environment root
- Anything that would destroy or replace an existing resource: forced-replacement arguments, resource address renames without a moved block, changed lifecycle blocks
- IAM: every action named and minimal, resource ARNs scoped (bucket ARN plus /* for objects; * only for actions without resource-level permissions, with a comment), no broad managed policies, no Principal "*" without a tightening Condition; roles and attachments only at the documented attachment point
- S3 and exposure: the project's naming pattern, public access block with all four flags true, nothing newly reachable from the internet outside the existing entry points
- Data protection: prevent_destroy and deletion_protection where data lives; encryption settings
- Secrets in .tf or example tfvars; variables without type or description; outputs without description; sensitive outputs not marked sensitive
- Resource arguments or IAM action names that may not exist: say "verify against the provider docs" rather than asserting
- Temporal compatibility: a consumer root reading an output before its producer root is applied, roots applied in another order, a partial apply, a revert after new writes that loses or strands data written under the new configuration
- Precedence: the repository rules, the specification items and the approved plan override these defaults; a deviation the project prescribes is not a finding
