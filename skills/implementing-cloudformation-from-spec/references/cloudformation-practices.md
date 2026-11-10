# CloudFormation practices

Rules for authoring and validating templates, each with the documentation that supports it (quotations
read on 2026-10-14, data protection, change sets and the validation toolchain re-read on 2026-10-16). The
project's own conventions win where they are stricter. Re-read a cited page when
a decision depends on it: limits and tool versions change.

## Contents

1. Organisation
2. Quotas
3. Parameters, conditions and pseudo parameters
4. Cross-stack values
5. AWS::LanguageExtensions and Fn::ForEach
6. Data protection
7. Naming and logical IDs
8. IAM and secrets
9. Lambda versions and aliases
10. Change sets
11. Validation toolchain
12. Tools not to adopt

## 1. Organisation

- One template per stack, YAML, under the project's template directory. Group resources by lifecycle
  and ownership: "By grouping resources with common lifecycles and ownership, owners can make changes to
  their set of resources by using their own process and schedule without affecting other resources"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- Layer stacks so each depends only on layers below it ("A layered architecture organizes stacks into
  multiple horizontal layers that build on top of one another", same page)
- Follow the section order and comment style the project's existing templates use; a new template copies
  a sibling's skeleton (description, parameters, conditions, resources, outputs)
- Keep design rationale next to the resource it explains, in a YAML comment or `Metadata`, not in the
  description

## 2. Quotas

From https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-limits.html: 500
resources, 200 parameters, 200 outputs and 200 mappings per template; a template body of 51,200 bytes
inline or 1 MB from S3. The quotas apply after expansion: "Using the Fn::ForEach intrinsic function does
not change the quotas, which apply to the resultant template"
(https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/intrinsic-function-reference-foreach.html).
A template over 51,200 bytes is deployed from S3 (`--template-url`).

## 3. Parameters, conditions and pseudo parameters

- Use AWS-specific parameter types where they exist; "CloudFormation can quickly validate values for
  AWS-specific parameter types before creating your stack" (best-practices page)
- Constrain every string parameter (`AllowedValues` or `AllowedPattern`); validate parameter
  combinations in a `Rules` section, which validates "parameter values before CloudFormation creates or
  updates any resources" (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/rules-section-structure.html)
- In YAML, quote `'Yes'` and `'No'` in `AllowedValues` (parameters section reference)
- SSM parameter types: "CloudFormation validates them against the parameter keys you specify, but not
  their values", and values "might change in Parameter Store between the time that you create the change
  set and run it" (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-supplied-parameter-types.html)
- Build ARNs from `AWS::Partition`, `AWS::Region` and `AWS::AccountId`; never hard-code them (cfn-lint
  I3042 reports it)

## 4. Cross-stack values

- Use the mechanism the project already uses (for example an SSM parameter registry declared in one
  file, or stack exports). Do not introduce a second one
- Exports are a contract: "After another stack imports an output value, you can't delete the stack that
  is exporting the output value or modify the exported output value"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html). Prefix
  export names with the stack name
- An SSM dynamic reference does not take part in drift detection, and one in the Parameters section
  "must include a version number" (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-ssm.html)

## 5. AWS::LanguageExtensions and Fn::ForEach

From https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/transform-aws-languageextensions.html:

- The declaration "must use the literal string `AWS::LanguageExtensions`"
- **Never update a LanguageExtensions stack with `--use-previous-template`** (or UsePreviousTemplate):
  "The `AWS::LanguageExtensions` transform resolves parameters to literal values during processing. When
  you use `--use-previous-template`, CloudFormation uses this processed template with the old literal
  values, preventing new parameter values and Systems Manager parameter updates from being applied.
  Instead, provide the original template". A parameter-only change set (moving a Lambda alias, for
  example) must re-submit the template. K22 denies the flag
- "Short-form YAML syntax isn't supported" for its functions: write `Fn::Length`, `Fn::ForEach`,
  `Fn::ToJsonString` in long form
- Its functions are "only supported in the `Resources`, `Conditions`, and `Outputs` sections"
- "The AWS SAM CLI currently doesn't support the `Fn::ForEach` intrinsic function"
- A loop's logical name must be unique and must not collide with a logical ID (Fn::ForEach reference);
  the collection may be a `Ref` to a `CommaDelimitedList` parameter
- "If you want to create a stack from a stack template that contains macros *and* nested stacks, you must
  create or update the stack directly from the template using the CreateStack or UpdateStack action"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateChangeSet.html, Capabilities,
  read 2026-10-14). A pipeline that deploys only through change sets therefore keeps nested stacks out of
  templates that use a transform (inference from that sentence; confirm in dev before relying on the
  opposite)

## 6. Data protection

- **DeletionPolicy** defaults to `Delete`: "If a resource has no `DeletionPolicy` attribute,
  CloudFormation deletes the resource by default". The one exception: "The default policy is `Snapshot`
  for `AWS::RDS::DBCluster` resources and for `AWS::RDS::DBInstance` resources that don't specify the
  `DBClusterIdentifier` property". The policy "doesn't apply to resources whose physical instance is
  replaced during stack update operations"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html,
  read 2026-10-16)
- **UpdateReplacePolicy** defaults to `Delete` for every resource type, RDS included: "By default, if you
  don't specify an `UpdateReplacePolicy`, CloudFormation deletes your resources". It "is only executed if
  you update a resource property whose update behavior is specified as **Replacement**", and `Snapshot`
  on a type that does not support snapshots "reverts to the default option, which is `Delete`"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html,
  read 2026-10-16). The RDS `Snapshot` default is a DeletionPolicy rule only; an RDS instance replaced by
  an update is deleted unless UpdateReplacePolicy says otherwise
- So every stateful resource sets both `DeletionPolicy` and `UpdateReplacePolicy` explicitly (cfn-lint
  W3011 and I3011 report gaps), to `Retain` or, where the type supports it, `Snapshot`
- `RetainExceptOnCreate`: "new, empty, and unused resources are deleted, while in-use resources and their
  data are retained" (same page)
- Set the resource's own deletion protection where it has one (DynamoDB `DeletionProtectionEnabled`, off
  by default; Cognito user pools; RDS)
- "Termination protection on stacks is disabled by default"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html); it is
  set by the pipeline or bootstrap, outside the template

## 7. Naming and logical IDs

- "You can't perform an update that causes a custom-named resource to be replaced. If you must replace
  the resource, specify a new name" (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-name.html)
- Changing a logical ID creates a new resource and deletes the old one. That includes the logical IDs a
  `Fn::ForEach` loop generates: changing a collection value or the `OutputKey` pattern renames a
  resource. The loop's own logical name does not appear in the transformed output
- Names the project pins (stack names, function names, registry keys) are copied verbatim from the items

## 8. IAM and secrets

- Least privilege: "avoid using wildcard permissions whenever possible" (best-practices page)
- Custom-named IAM resources need `CAPABILITY_NAMED_IAM` in the pipeline's change-set call
- Secrets never appear in parameters, defaults, literals, `Metadata` or `Outputs`; use dynamic
  references ("use dynamic references", best-practices page). `NoEcho` "does not mask any information
  stored in" Metadata or Outputs (parameters section reference). Secrets Manager references are
  versionless, and "Updating only the secret value in Secrets Manager doesn't automatically cause
  CloudFormation to retrieve the new value"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html)
- Verify every action name in the service authorization reference; the IAM policy validator
  (`cfn-policy-validator`) checks policies against IAM Access Analyzer when credentials are available

## 9. Lambda versions and aliases

- `AWS::Lambda::Version` "creates a version from the current code and configuration of a function"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-version.html);
  read each property's update behaviour on that page rather than assuming one rule for all. Set
  `CodeSha256` so a version is published only for the expected code
- "Lambda never reuses version numbers" (https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html),
  and the PublishVersion API "doesn't publish a version if the function's configuration and code haven't
  changed since the last version" (https://docs.aws.amazon.com/lambda/latest/api/API_PublishVersion.html).
  What CloudFormation does when a new `AWS::Lambda::Version` resource meets unchanged code is not stated
  there: test it in dev before a design depends on it

## 10. Change sets

- `ResourceChange.Replacement` is `True | False | Conditional` and `PolicyAction` is `Delete | Retain |
  Snapshot | ReplaceAndDelete | ReplaceAndRetain | ReplaceAndSnapshot`
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ResourceChange.html). The User
  Guide's samples spell the middle value `Conditionally`: "the `Replacement` field would be
  `Conditionally`", and explain that "if only one of the many changes requires a replacement,
  CloudFormation must replace the resource and, therefore, sets the `Replacement` field to `True`"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-samples.html,
  read 2026-10-16). Treat both spellings as a replacement
- The rule of this skill: an existing resource whose change shows `Replacement` `True` or `Conditional`
  stops the run unless a ruling the user agreed to, recorded in the ledger, covers its logical ID. The
  per-change cause is in `Details[].Target.RequiresRecreation` (`Never`, `Conditionally`, `Always`)
- The check is mechanical: `rules/change-set-replacement.guard` over the `describe-change-set --output
  json` document fails on such a replacement and on a `Remove` whose `PolicyAction` deletes. It is adapted
  from the Guard guide's deployment-safety use case: "validate CloudFormation change sets against policy
  rules to prevent changes that result in resource replacement, such as renaming an Amazon DynamoDB table"
  (https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html, read 2026-10-16)
- "Change sets don't guarantee that CloudFormation will successfully update a stack"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- Pre-deployment validation results come from `describe-events` on the change set, not
  `describe-stack-events` (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/validate-stack-deployments.html)
- The processed template (`get-template --template-stage Processed`) shows what the transform produced,
  which is what Guard and the policy validator should see for generated resources
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_GetTemplate.html)

## 11. Validation toolchain

- **cfn-lint** (v1.57.2 on 2026-10-16; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lint.html):
  checks templates "against the CloudFormation resource provider schemas and additional rules", and
  applies the SAM transform before checking. Configure it in `.cfnlintrc` (templates,
  regions, parameter files so `Fn::ForEach` collections get real values, include `I` checks for I3011
  and I3042). Exit code is a bitmask (2 errors, 4 warnings, 8 informational). Rules worth requiring: W3011,
  I3011, I3042, W1011 (secret parameters), E3510 and W3037 (IAM), W2001 and W8001 (unused parameters and
  conditions)
- **cloudformation-validate** (`cfn-validate`, release 1.12.1 of 2026-09-25;
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html): offline
  checks that resolve intrinsic functions, then run "Schema checks", built-in "Rules" and state machine
  checks; it "runs without network access or AWS credentials after installation". Run it beside cfn-lint
  (`cfn-validate infra/ --region <region>`, `--parameter Key=Value` for parameter-dependent checks,
  `--strict` to fail on warnings). Exit codes: `0` no errors, `1` errors (or warnings under `--strict`),
  `2` usage error. Custom rules in CEL or Rego (`--rule-source`) or Guard (`--guard-rule-source`, "a
  subset of the Guard language"; an unsupported construct is rejected at load, not ignored). Installed as
  a single downloaded binary, so its install is the user's decision like any other
- **cfn-guard** (v3.2.1 on 2026-08-25): rules under the project's rule directory, each with a
  `*_tests.yaml` of PASS and FAIL cases run by `cfn-guard test`
  (https://docs.aws.amazon.com/cfn-guard/latest/ug/testing-rules.html), and `cfn-guard validate` over every
  template with JUnit output for the pipeline. Guard does not resolve parameters or transforms
- **Template tests** (pytest or the project's runner): assertions on parsed templates that Guard cannot
  express, such as counts after expansion or cross-template consistency
- **Managed rule sets**: the User Guide's Guard page points to the AWS Guard Rules Registry "For
  ready-to-use rules that cover common security and compliance controls"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html). Its last
  release is 1.0.2 of 2022-09-02 (GitHub releases API, checked 2026-10-16), so its rules are a starting
  point, not a live feed: copy the rules the project adopts into its rule directory with the release they
  came from, give each a `*_tests.yaml`, and keep project rules for whatever the items require
- **validate-template** checks syntax only: "These service-side checks don't run the additional
  property, security, or best-practice checks"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-guide.html)
- Optional, when the project adopts them: Checkov, cfn-policy-validator

## 12. Tools not to adopt

- **Rain**: its README says "Rain is no longer actively maintained and has been deprecated" and the
  repository is archived (checked 2026-10-14)
- **cfn-nag**: last release v0.8.10 in June 2022
- **AWS Guard Rules Registry as a live dependency** (pulling its latest rules at validation time): it has
  had no release since 1.0.2 (2022-09-02); vendor and pin the rules instead (section 11)
