# AWS CDK practices

Rules for designing, writing and checking CDK v2 apps, each with the documentation that supports it. CDK
quotations were read on 2026-10-16; CloudFormation quotations carried over from the CloudFormation skill
were read on 2026-10-14. The project's own conventions win where they are stricter. Re-read a cited page
when a decision depends on it: CLI flags, defaults and tool versions change.

## Contents

1. Organisation
2. Quotas
3. Logical IDs and construct IDs
4. Removal policies and data protection
5. Cross-stack values
6. IAM and secrets
7. Checks: synth, tests, cdk-nag, template tools
8. Python CDK apps
9. Java CDK apps
10. Change sets and replacement evidence
11. Tools not to adopt

## 1. Organisation

- Group resources into stacks by lifecycle and ownership: "By grouping resources with common lifecycles
  and ownership, owners can make changes to their set of resources by using their own process and
  schedule without affecting other resources"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- Layer stacks so each depends only on layers below it ("A layered architecture organizes stacks into
  multiple horizontal layers that build on top of one another", same page)
- Follow the app's existing layout: where stacks and constructs live, how stacks receive configuration
  (props, context), how tests build a stack. A new stack copies a sibling's skeleton
- Supported languages: "TypeScript, JavaScript, Python, Java, C#, Go"
  (https://docs.aws.amazon.com/cdk/v2/guide/languages.html). This skill writes Python and Java apps; for
  any other language it applies only the template-level checks of section 7

## 2. Quotas

The CloudFormation quotas apply to each synthesised template: 500 resources, 200 parameters, 200 outputs
and 200 mappings per template, and a template body of 51,200 bytes inline or 1 MB from S3
(https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-limits.html). L2 and L3
constructs often synthesise several resources each: count the resources in `cdk.out`, not the constructs
in the code.

## 3. Logical IDs and construct IDs

From https://docs.aws.amazon.com/cdk/v2/guide/identifiers.html:

- The logical ID is generated from the construct path: "Concatenate the path components from the
  construct tree, excluding the stack itself", apply the readability heuristics, and "Append an
  8-character hash of the full path to ensure uniqueness"
- "If you change a construct ID after deployment, the logical ID changes, which causes AWS CloudFormation
  to replace the resource. Use `cdk diff` to verify changes before you deploy"
- "if you change the logical ID of a resource, AWS CloudFormation creates a new resource with the new
  logical ID, then deletes the existing one. Depending on the type of resource, this might cause service
  interruption, data loss, or both"
- Moving a resource into a new construct changes its path too. The `Default` heuristic keeps the logical
  ID: "If a path component is `Default`, the CDK removes it from both the human-readable portion and the
  hash input", so "wrapping an existing construct inside a new construct — and naming the inner construct
  `Default` — produces the exact same logical ID". Only one child per scope may have the ID `Default`
- "For cases where logical IDs have already changed, you can use the `cdk refactor` command to map old
  logical IDs to new ones" (same page; section 10)
- A characterisation test pins the logical ID of every stateful resource the plan touches (assert the key
  in the synthesised template's `Resources`), so a rename fails a test before it reaches a change set

## 4. Removal policies and data protection

From https://docs.aws.amazon.com/cdk/v2/guide/resources.html, "Removal policies":

- "Resources that maintain persistent data, such as databases, Amazon S3 buckets, and Amazon ECR
  registries, have a *removal policy*". `RemovalPolicy.RETAIN` keeps the resource "when destroying the
  stack (default)"; `RemovalPolicy.DESTROY` destroys it with the stack
- "The AWS CDK's `RemovalPolicy` translates to AWS CloudFormation's `DeletionPolicy`. However, the
  default in AWS CDK is to retain the data, which is the opposite of the AWS CloudFormation default"
- Some stateful resources have no `removalPolicy` prop on their L2; for those, `applyRemovalPolicy()` on
  the underlying CloudFormation resource sets it (the page lists, among others, Cognito user pools, SQS
  queues, OpenSearch Service domains and EC2 volumes)
- "a Lambda function version uses a `removalPolicy` attribute to determine whether a given version is
  retained when a new version is deployed. These have different meanings and defaults"
- CloudFormation does not delete an S3 bucket that contains objects even under `DESTROY`; `autoDeleteObjects`
  empties it first. Never set either on data the items keep

Rules that follow, because the defaults differ by construct and version:

- Set the removal policy explicitly on every stateful resource, to `RETAIN` or the value the items
  require, and assert in a test that the synthesised template carries both `DeletionPolicy` and
  `UpdateReplacePolicy` with that value. CloudFormation's own rule still applies to the template: "If a
  resource has no DeletionPolicy attribute, CloudFormation deletes the resource by default", and the
  policy "doesn't apply to resources whose physical instance is replaced"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html)
- Set the resource's own deletion protection where it has one (DynamoDB tables, Cognito user pools, RDS)
- Physical names: "any changes to deployed resources that require a resource replacement ... will fail if
  a resource has a physical name assigned" (resources.html, "Resource physical names"). Assign one only
  when the items pin it

## 5. Cross-stack values

- Use the mechanism the project already uses (construct references passed as props, SSM parameters,
  explicit exports); do not introduce a second one
- Exports are a contract: "After another stack imports an output value, you can't delete the stack that
  is exporting the output value or modify the exported output value"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html)
- A construct passed to a stack in the same environment becomes an export: the CDK "automatically
  synthesizes AWS CloudFormation exports in the producing stack and an `Fn::ImportValue` in the consuming
  stack", a strong reference and "the default behavior"
  (https://docs.aws.amazon.com/cdk/v2/guide/resources.html, "Referencing resources in a different stack").
  Removing or restructuring a shared resource can then deadlock ("CloudFormation cannot remove an export
  while another stack still imports it"); the page's two-phase migration through `ReferenceStrength.BOTH`
  to `WEAK` is a plan with two deploys, never one change
- `fromLookup` methods query the account at synthesis and cache the result in `cdk.context.json`; "Commit
  this file to version control" (same page)
- Names the project pins (stack IDs, resource names, parameter keys) are copied verbatim from the items

## 6. IAM and secrets

- Least privilege: "avoid using wildcard permissions whenever possible" (best-practices page). Prefer the
  constructs' `grant*` methods, which scope actions and resources to the construct; hand-written
  statements name each action, verified in the service authorization reference
- Build ARNs from the stack's partition, Region and account tokens; never hard-code them
- Secrets never appear in context, props, environment variables, literals or Outputs; reference Secrets
  Manager or Parameter Store. Secrets Manager dynamic references are versionless, and "Updating only the
  secret value in Secrets Manager doesn't automatically cause CloudFormation to retrieve the new value"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references-secretsmanager.html)

## 7. Checks: synth, tests, cdk-nag, template tools

- **`cdk synth`**: `--validation` "Validate the generated CloudFormation templates after synthesis by
  performing additional checks", default `true` (https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-synth.html).
  The synth command has no `--strict` option of its own; the global `--strict`, "Do not construct stacks
  that contain warnings", works with every command (https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd.html).
  `--lookups` defaults to `true`; with it false, "Synthesis will fail if ... context lookups need to be
  performed" (same page): a lookup missing from `cdk.context.json` reads the account and writes that file,
  so it is a question for the user, not a silent step
- **Validation plugins**: templates "are validated immediately after synthesis ... If there are any
  violations, the synthesis will fail and a report will be printed to the console", and "A default plugin
  that uses a comprehensive rule set for AWS resources is automatically added to your application, based on
  @aws/cloudformation-validate" (https://docs.aws.amazon.com/cdk/v2/guide/policy-validation-synthesis.html).
  It "is a best-effort validation ...; it is not a full standards compliance mechanism by itself" (same
  page). Acknowledge a finding with `Validations.of(scope).acknowledge` with an `id` and a `reason`;
  "Suppression is scope-based, and applies to all constructs under the given scope", so acknowledge on the
  narrowest construct
- **Fine-grained assertions** with the `assertions` module: `Template.from_stack` / `Template.fromStack`,
  `has_resource_properties` / `hasResourceProperties` ("performs a partial match"), `resource_count_is` /
  `resourceCountIs`, `Match` matchers from `Match.anyValue` to `Match.objectEquals`, and `Capture`
  (https://docs.aws.amazon.com/cdk/v2/guide/testing.html). These are the proof type for test-first work
- **Snapshot tests** compare the whole template with a stored baseline; "snapshot testing isn't useful in
  catching regressions", but "Snapshot tests can be of great help in refactoring" (same page). Use them
  where the project keeps them, never as the only proof of an item
- **cdk-nag** (cdklabs): rule packs such as `AwsSolutionsChecks`. "Version 3.x of cdk-nag integrates with
  the standardized Validations mechanism in CDK" (policy-validation-synthesis.html); its README shows
  `Validations.of(app).addPlugins(new AwsSolutionsChecks(app))` and acknowledgement through
  `Validations.of(construct).acknowledge({ id, reason })` with ids such as `AwsSolutions-S1`
  (https://github.com/cdklabs/cdk-nag, read 2026-10-16). Apps on cdk-nag v2 apply the pack as an Aspect;
  follow the version the app uses. Adding cdk-nag is a new dependency the plan names with its version
  (Python `cdk-nag`, Maven `io.github.cdklabs:cdknag`)
- **Template-level tools on `cdk.out/*.template.json`**: cfn-lint (v1.57.2 on 2026-10-06) and cfn-guard
  (v3.2.1 on 2026-08-25) with the project's rule files, exactly as the CloudFormation skill runs them; Guard
  does not resolve parameters or transforms. The standalone validator `cfn-validate TEMPLATE_OR_DIRECTORY`
  checks templates locally, exit "`0` when it finds no errors, `1` when it finds errors, and `2` for a usage
  or initialization error", and `--strict` makes warnings fail
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html). In a CDK
  app "you don't need to install the validator separately", because the default plugin runs the same checks
  in `cdk synth` (same page)
- **`cdk validate`**: the CloudFormation best-practices page says "For CDK projects, `cdk validate` runs
  CloudFormation pre-deployment validation against your synthesised templates", a service-side check; the
  CDK CLI command reference read on 2026-10-16 does not list a `validate` command. Run it only when
  `cdk --help` lists it and the user approves the account access (the gate asks)
- Tests run with the language's runner: "`python -m pytest`" for Python and "`mvn compile && mvn test`" for
  Java (testing.html, "Running tests"), or the project's wrapper scripts when it has them

## 8. Python CDK apps

From the Python skill's practices and https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html:

- "Python AWS CDK applications require Python 3.9 or later". Code runs on the project's pinned version and
  on 3.9: no `match`, no `X | Y` types at runtime without `from __future__ import annotations`
- Activate the project's virtual environment before any command ("Otherwise, you won't have access to the
  modules installed there")
- Dependencies: "we recommend that you use the == operator to specify exact versions for all dependencies",
  and "Installing a module with `pip install` does not automatically add it to `requirements.txt`". Lock
  files are the project's choice; never edit a lock by hand, regenerate it with the project's tool
- Imports: "import individual classes from top-level `aws_cdk`" or alias it as `cdk`, "Avoid doing both";
  construct libraries with short aliases (`import aws_cdk.aws_s3 as s3`); `lambda_` because `lambda` is a
  keyword
- Test first: a test for new behaviour must fail before the code exists, or it does not test that
  behaviour; a characterisation test for preserved behaviour passes before and after, by design
- Lambda handler code bundled by the app follows the Python skill's handler rules (separate the handler
  from the logic, bundle dependencies); it is that skill's work when the items are about the handler
- Toolchain: the project's ruff, mypy and pytest commands. "Ruff 0.17.0 (2026-10-09) changed its default
  rule set: projects pin ruff and list `select` explicitly" (Python skill, read 2026-10-14)

## 9. Java CDK apps

From the Java skill's build rules and https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-java.html:

- "Java AWS CDK applications require Java 8 (v1.8) or later" and "Apache Maven 3.5 or later"; "the
  application skeletons generated by the AWS CDK Toolkit are Maven projects". The project's pinned Java
  release is the one to use
- Build and test through the project's wrapper scripts when it has them, never around them; otherwise
  `mvn compile && mvn test`. If the gate denies a direct `mvn` (a project or plugin rule), report it and use
  the wrapper or ask; never route around it
- Dependencies live in `pom.xml`: "Maven does not support dependency locking ... we recommend you always
  use exact versions to keep your builds repeatable", and "Maven automatically installs or updates your
  dependencies whenever you build (`mvn compile`) or package (`mvn package`) your project. The CDK Toolkit
  does this automatically every time you run it". So a `pom.xml` dependency edit is the install: it happens
  only in a task the approved plan names
- Props use the builder pattern: `Bucket.Builder.create(this, "Id")...build()`; missing values are
  `null` and are tested before use
- Tests: JUnit 5 with AssertJ, one behaviour per test, each citing its item ID in its name or Javadoc; the
  test is written and seen failing before the construct exists
- Records for value types, no checked exceptions in construct code, one class per file; avoid wildcard
  imports ("We recommend writing a separate Java `import` statement for each AWS Construct Library class")
- No Java in the plan: describe each construct and class in prose

## 10. Change sets and replacement evidence

- `cdk diff --method`: "`auto` – Default. Creates an AWS CloudFormation change set to display accurate
  replacement information. If the change set can't be created ... falls back to a template-only diff. Uses
  the deploy role"; "`change-set` – Always creates a change set and fails if it can't be created. Use this
  when you need guaranteed accuracy. Uses the deploy role"; "`template` – Compares CloudFormation templates
  directly. Faster, but less accurate. Any change detected to properties that require resource replacement
  is displayed as a resource replacement, even if the change is purely cosmetic. Uses the lookup role"
  (https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-diff.html). `auto` can fall back silently, so the
  evidence command is always `--method change-set`; `--exclusively` diffs only the named stacks, and
  `--fail` exits 1 when differences are detected
- `ResourceChange.Replacement` is `True | False | Conditional` and `PolicyAction` is `Delete | Retain |
  Snapshot | ReplaceAndDelete | ReplaceAndRetain | ReplaceAndSnapshot`
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ResourceChange.html); a change set
  that still exists can be read with `aws cloudformation describe-change-set` (read-only)
- "Change sets don't guarantee that CloudFormation will successfully update a stack"
  (https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- `cdk refactor` (https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-refactor.html and refactor.html):
  in preview, and "You must provide the `--unstable=refactor` option"; it "verifies that your CDK
  application contains exactly the same set of resources as the deployed state, differing only in their
  locations in the construct tree", and rejects any addition, deletion or modification. "Refactoring
  operations must be performed alone, separately from other actions". `--dry-run` "Print[s] the mapping to
  the console without applying it"; `--override-file` resolves ambiguous mappings; `--revert` needs an
  override file and "doesn't completely undo a previous refactor operation". "In non-interactive
  environments such as CI/CD pipelines, the CDK CLI automatically proceeds without prompting", which is why
  the gate asks before any refactor without `--dry-run`. It needs the latest bootstrap template, and
  Lambda `Version` and API Gateway `Deployment` constructs "are automatically excluded from refactoring"

## 11. Tools not to adopt

- **cfn-nag**: last release v0.8.10 in June 2022; cdk-nag is the CDK-level rule engine
- **Rain**: its README says "Rain is no longer actively maintained and has been deprecated" and the
  repository is archived (checked 2026-10-14)
- **AWS Guard Rules Registry** as a rule source: last release 1.0.2 in September 2022; write project rules
