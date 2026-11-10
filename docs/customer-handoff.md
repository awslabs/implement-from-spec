# implement-from-spec: customer hand-off

One page for a team adopting the plugin. The full documentation is the [README](../README.md) and the
[user guides](user-guide/).

## What it does

Claude Code skills that implement Terraform, AWS CDK (Python and Java apps), CloudFormation, Java and
Python from your specification items. Each skill writes a code-free plan to `ai-planning/` in your
repository and waits until you reply `approve`. Then it builds the change test-first, runs the stack's
checks, has the change reviewed by Claude and, if you enable it, by an external model, and reports with
the exact deploy command.

## What it never does

- Deploy or change live state on its own. Deploys, stack and change-set operations, `terraform apply`,
  state edits and mutating `aws` calls always ask you first, before and after plan approval
- Write product code before you approve the plan
- Install a dependency the plan does not name without asking
- Configure credentials or store keys
- Send secrets, Terraform state or real `*.tfvars` to the external reviewer

## What the gate blocks, and why

A model coding straight from a spec takes the first plausible design. The plan is where you redirect it
cheaply, so the gate holds the repository until you approve.

- Inert until a session starts one of the five implementing skills; then it gates that repository, and
  any other whose plan the session writes. Every other repository stays writable
- Before approval, only `ai-planning/` and `.claude/` are writable, through file tools and the shell
- The approval is your whole reply, `approve`, and it is bound to the plan's content: editing the plan
  revokes it
- The gate needs `python3`. Without it, Claude Code 2.1.295 or later blocks every Write, Edit and Bash
  call until `python3` is fixed; older releases let the calls run ungated
- It is a guard against mistakes, not a sandbox

## Prerequisites

- Claude Code 2.1.271 or later, on macOS, Linux or WSL2; 2.1.295 or later recommended (below it the
  gate's guard hooks fail open when `python3` cannot run, and setup warns)
- python3 3.9 or later (the `python3` macOS ships), git and bash
- Per stack, checked and installed by `/implement-from-spec:setup <stack>`:
  - Terraform: terraform 1.6.0 or later; TFLint and Checkov optional
  - CDK: Node.js 22 or later, the CDK CLI, the AWS CLI v2, and Python 3 with pip or a JDK with Maven or
    Gradle; AWS credentials for the change-set diff
  - CloudFormation: cfn-lint, cfn-guard and the AWS CLI v2; cloudformation-validate recommended
  - Java: a JDK and the project's Maven or Gradle wrapper
  - Python: pipx or uv, and the project's own toolchain
- Recommended: the AWS Documentation MCP server

## External reviewer

Optional and off by default: nothing goes to a non-Claude model, and the report says "External review:
off (configuration)" while the Claude review runs alone. Enabled, it is GPT-6 Astra on Amazon Bedrock in
your AWS account, through the AWS CLI with your AWS profile, and each review sends the plan, the rules
files, the review focus, the specification files in scope and the filtered change. Without access, the
report says "External review: not run (<reason>)" and the Claude review still runs.

- Turn it on: set the plugin's "External reviewer" row in `/config` to `bedrock-gpt`, after a secret scan
  of the repository; set it back to `off` to stop. `/implement-from-spec:setup` offers this and checks the
  tools, but never turns it on itself
- Authenticate with an AWS profile (`aws-profile`, the default; SSO works), or with a short-term Amazon
  Bedrock API key exported as `IMPLEMENT_FROM_SPEC_BEDROCK_API_KEY` (`api-key`). Claude Code's own
  `AWS_BEARER_TOKEN_BEDROCK` is never used
- The account needs `bedrock:InvokeModel` on the model and its inference profile, and AWS Marketplace
  permissions for the one-time subscription to the model
- `external_review_policy = required` makes a missing review a failure

Details: [user-guide/external-review.md](user-guide/external-review.md).

## Model providers

A Claude subscription, an Anthropic API key and Amazon Bedrock all work. On Bedrock, pin
`ANTHROPIC_DEFAULT_OPUS_MODEL` and `ANTHROPIC_DEFAULT_SONNET_MODEL`, or run `/setup-bedrock`: without the
pin, the `sonnet` alias resolves to an older default model. WebSearch is not available on Bedrock; the
skills do not need it. Details: [user-guide/providers.md](user-guide/providers.md).

## Install

Until the repository is published, you receive a copy of it from your AWS contact. Add that directory as
the marketplace, then install:

```
claude plugin marketplace add ./implement-from-spec
claude plugin install implement-from-spec@implement-from-spec
```

Then run `/implement-from-spec:setup` in a new session.

## Support

The plugin is provided "as is". You remain responsible for testing, deploying and supporting what it
produces. Issues are answered on a best-effort basis. The plugin is licensed under the Apache License 2.0
(`LICENSE`). The tools setup installs come from their vendors under the vendors' licences; HashiCorp
Terraform 1.6 and later is under the Business Source License 1.1, which is not an OSI-approved
open-source licence.

For the trust boundaries (what the gate does and does not stop, what the external reviewer receives,
how credentials are handled), see the README's [Security model](../README.md#security-model).
