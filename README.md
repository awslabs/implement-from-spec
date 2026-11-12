# implement-from-spec

A Claude Code plugin with skills that implement code from specification items: Terraform, AWS CDK
(Python and Java apps), AWS CloudFormation, Java and Python. Each skill reads the items and the project's
rules, writes a code-free plan, and waits until you reply `approve`. A hook enforces the wait. Then it
builds the change test-first, runs the stack's own checks, has it reviewed by Claude and, if you enable
it, by an external model, and reports. It never deploys on its own: every deploy or live change asks you first.

Version 0.1.0.

## Disclaimer

This plugin is provided for non-production use. It is not a production-ready service and is provided "as
is", without warranties of any kind (see [LICENSE](LICENSE)). You should work with your security and
legal teams to meet your organizational security, regulatory and compliance requirements before
deployment. Do not deploy the code it generates to production environments without additional security
testing, and review every plan it writes and every line of code it generates first. You remain
responsible for anything you deploy, and for testing and supporting it.

Before using content in implement-from-spec, you should consider conducting your own independent assessment
to ensure that your use would comply with your own specific security and quality control practices and
standards, as well as the laws, rules, and regulations that govern you and your content.

## What the skills do

1. Read the specification items in scope, the project's `CLAUDE.md` or `AGENTS.md`, the neighbouring code
   and the documentation of every resource, construct or library the design uses
2. Write the plan to `ai-planning/<slug>.plan` in your repository: scope, constraints, tasks with the files
   each one owns, tests and waves. No code in the plan
3. Check the plan with `spec-trace.py plan`, a traceability check, and stop for your approval
4. After `approve`, keep a ledger (`ai-planning/<slug>.ledger.md`) and build the tasks in waves of
   subagents, each test-first
5. Run the stack's checks after every wave (for example `terraform validate` and a targeted plan,
   `cdk synth` and a change-set diff, `cfn-lint` and `cfn-guard`, the project's build or test gate)
6. Verify each item backwards from its acceptance criteria, then run `spec-trace.py code`
7. Review the change with Claude reviewer subagents and, when you enable it, an external reviewer in
   parallel (GPT-6 Astra on Amazon Bedrock or your own reviewer command; off by default)
8. Report what was built, every check with its result, the review outcome, and the exact command you run
   to deploy

## What the skills never do

- Deploy or change live state on their own. These commands always ask you first, before and after plan
  approval:
  - `terraform apply`, `destroy`, `import`, `taint`, state edits, `init -migrate-state`, and `plan` and
    `test` (they read live state, and `test` can apply)
  - `cdk deploy`, `destroy`, `bootstrap`, `import`, `watch`, `orphan`, `publish-assets`, `cdk refactor`
    without `--dry-run`, and a change-set `cdk diff`
  - CloudFormation stack and change-set create, update, delete and execute calls, `sam deploy` and
    `sam sync`, TaskCat runs
  - Maven and Gradle deploy and publish goals
  - every mutating `aws` CLI call
- Install a dependency or rewrite a lock file without asking. A package the plan does not name is a
  question for you, and a failed install never gets a substitute
- Write anything outside `ai-planning/` and `.claude/` before you approve the plan
- Write a review themselves when the external reviewer cannot run
- Send secret files (`.env*`, keys, certificates, `credentials*`), Terraform state or real `*.tfvars` to
  the external reviewer. The filter goes by file name: see "Security model"
- Configure credentials or store keys

One command is refused outright: `aws cloudformation ... --use-previous-template`, because with
`AWS::LanguageExtensions` it silently keeps old parameter values.

## The approval gate

The plugin registers one gate for every session, in `hooks/hooks.json`.

- It is inert until the session starts one of the gated skills (the five `implementing-*` skills): Claude
  calling the skill, or you typing its slash command
- From then on it gates the repository the session was in when the skill started, plus any repository
  whose `ai-planning/*.plan` the session writes. Every other repository stays writable
- In a gated repository, before approval, only `ai-planning/` and `.claude/` are writable. Writes elsewhere
  are denied through Write and Edit and through the shell
- The approval is your whole reply: `approve` or `approved`, optionally followed by the plan's name
  (`approve queue`) and a closing full stop or exclamation mark. A reply that adds a question or a
  condition approves nothing. When plans of several repositories are pending, the name is required
- The approval is bound to the plan's sha256. Editing the plan, writing a newer plan, or changing it
  behind the hook's back revokes it. Changes after approval go through an amendment you approve again
- Plans are written only with Write and Edit; the gate denies shell writes to them, so it sees every
  version
- The command rules above apply before and after approval. In a gated session the rules of all five
  skills apply together
- The shell analysis is a guard against mistakes, not a sandbox: a script file run by an interpreter is
  not inspected

## Security model

- **Repository content is untrusted input.** Specification files, `CLAUDE.md`, code, comments, fixtures,
  fetched documentation and every reviewer's answer are data to Claude and to the reviewers. An
  instruction found in them is never followed as a command; the project's rules still bind the code
  ([core/contract.md](core/contract.md), sections 2 and 9)
- **The gate is a guard against mistakes, not a sandbox.** It denies writes outside `ai-planning/` and
  `.claude/` before approval (inside `.claude/`, the settings files and `hooks/` stay denied) and asks
  before every deploy, install and live change. It does not contain a process. For containment, use
  Claude Code's sandbox and permission settings
- **What the external reviewer receives.** Nothing until you enable it: it is off by default. Enabled, it
  receives the plan, the rules files, the review focus, the specification files in scope and the filtered
  change, sent to Amazon Bedrock in your AWS account with your credentials. Files
  are withheld by name and path, and a file or diff chunk whose content looks like a secret (an AWS key, a
  private key, a token) is withheld too; both checks are heuristics, so a secret in a form they miss
  reaches the model. Run a secret scanner (for example [git-secrets](https://github.com/awslabs/git-secrets),
  which the release scan runs too) before you enable the reviewer, and keep it `off` for a
  repository with regulated or classified content. `off` sends nothing. Details:
  [docs/user-guide/external-review.md](docs/user-guide/external-review.md)
- **Credentials are never written or forwarded.** The skills configure no credentials and write no key to
  a file. The reviewer's environment never carries `AWS_BEARER_TOKEN_BEDROCK` or any other Bedrock bearer
  variable
- **Findings are verified.** Every reviewer finding is checked against the code before anything is fixed,
  and a fix stays inside the approved plan

## Requirements

- Claude Code 2.1.271 or later; 2.1.295 or later recommended, because from 2.1.295 the gate's guard hooks
  block a tool call when they cannot run (for example without `python3`), while older releases run them
  without blocking and so fail open. `/implement-from-spec:setup` warns below 2.1.295. Tested with 2.1.292
  and 2.1.302
- macOS, Linux or WSL2. Native Windows is not supported
- python3 3.9 or later, which is the `python3` macOS ships with the Command Line Tools. Every script and
  hook uses the standard library only, so there is nothing to `pip install`
- git and bash. A project must be a git work tree: the gate uses it to find where the project ends
- The command-line tools of the stacks you use. `/implement-from-spec:setup` checks them and installs the
  ones you approve. See the user guide of each stack
- Recommended: the AWS Documentation MCP server, which the skills use for AWS facts, and for Terraform the
  HashiCorp Terraform MCP server (see "MCP servers" below)
- Optional, only if you enable the external reviewer (off by default): an AWS account with access to
  GPT-6 Astra on Amazon Bedrock, and the AWS CLI with an AWS profile, or curl and jq with a Bedrock API key

Claude Code may run on a Claude subscription, an Anthropic API key or Amazon Bedrock. See
[docs/user-guide/providers.md](docs/user-guide/providers.md) for the Bedrock model pins.

## Install

From GitHub, inside Claude Code:

```
/plugin marketplace add awslabs/implement-from-spec
/plugin install implement-from-spec@implement-from-spec
```

The same from the shell:

```
claude plugin marketplace add awslabs/implement-from-spec
claude plugin install implement-from-spec@implement-from-spec
```

From a local copy of the repository, add the directory as the marketplace instead, from the directory
that holds the copy: `claude plugin marketplace add ./implement-from-spec`. The install command stays the
same.

`--scope project` on both commands records the plugin in the project's `.claude/settings.json`, to share it
with a team. Installed with `/plugin install` inside Claude Code, the plugin asks for its settings: the
external reviewer and how it authenticates. `claude plugin install` in the shell does not ask; it prints
that the options are not set yet, and their defaults apply until you set them with
`/plugin configure implement-from-spec@implement-from-spec` in a session or with `--config <key>=<value>`
on the install command (for example `--config external_review=bedrock-gpt` to enable the external
reviewer). The defaults keep the external reviewer off, so nothing is sent to a non-Claude model until you
enable it; see [docs/user-guide/external-review.md](docs/user-guide/external-review.md).

Then, in a new session:

```
/implement-from-spec:setup terraform
```

Name the stacks you use (`terraform`, `cdk`, `cloudformation`, `java`, `python`, `external-review` or
`all`). Setup shows each missing tool with its install commands, source and integrity check, installs only
what you approve, and never runs an administrator command itself. Each tool comes from its vendor under
that vendor's licence, not under this plugin's; see "Licence and support".

To update: `claude plugin update implement-from-spec@implement-from-spec`. The plugin's `version` pins
you until you update. A marketplace added from a local path is the exception: Claude Code reads the
plugin in place from your copy (`claude plugin list` shows "Read from: <the copy>"), so `version` pins
nothing and a `git pull` in the copy updates it for the next session.

## Getting started

One run end to end with the Python skill, on a specification of two items. It needs no AWS account and no
third-party package: python3, git, Claude Code, and uv or pipx (setup offers the missing one).

**1. Get the plugin.** From a local clone, which needs no marketplace:

```
git clone <repository URL> ~/implement-from-spec
```

You load it with `claude --plugin-dir ~/implement-from-spec` (step 3). The flag loads the plugin for that
session only and writes nothing to your settings, so start each session of this walkthrough with it.
Once the repository is published, install it instead with the two commands under "Install"
(`/plugin marketplace add awslabs/implement-from-spec`, then
`/plugin install implement-from-spec@implement-from-spec`) and leave the flag off.

**2. Create a tiny project.** A skill works in a git work tree with at least one commit:

```
mkdir textkit && cd textkit && git init
mkdir -p specification/functional
```

`CLAUDE.md`, the project's rules:

```markdown
# textkit

- Python 3.9 or later, standard library only: no third-party packages
- Code in `textkit/`, tests in `tests/`, one test module per code module
- Tests: `python3 -m unittest discover -s tests -v`
```

`.gitignore`, so test runs leave no untracked files:

```
__pycache__/
```

`specification/functional/slug.md`, the two items:

```markdown
# Functional spec: slugs

**SPEC-F001 — Slug from a title.** `textkit/slug.py` provides `slugify(title)`. It returns the title in
lower case, with every run of characters other than `a` to `z` and `0` to `9` replaced by one hyphen, and
no leading or trailing hyphen. `slugify("Hello, World!")` returns `hello-world`.

**SPEC-F002 — Nothing left.** `slugify` raises `ValueError` when no letter or digit remains, for example
for `slugify("!!!")`.
```

Then commit:

```
git add -A && git commit -m "Specification"
```

The commit needs a git identity. On a machine where git has none yet ("Author identity unknown"), set it
with `git config --global user.name "Your Name"` and `git config --global user.email you@example.com`, then
commit again.

[docs/spec-format.md](docs/spec-format.md) describes every input format the skills accept.

**3. Start Claude Code in the project.** The external reviewer is off by default, so nothing leaves your
machine for a non-Claude model:

```
claude --plugin-dir ~/implement-from-spec
```

Enabled later (`external_review = bedrock-gpt`), the review stage also calls GPT-6 Astra on Amazon Bedrock
with your AWS credentials ([docs/user-guide/external-review.md](docs/user-guide/external-review.md)).

**4. Check the tools.** In the session, type:

```
/implement-from-spec:setup python
```

Setup checks, read-only, what the Python skill needs, shows the install commands for anything missing,
and installs only what you approve. Only you can start it. Answer it like this:

- Setup reads the external reviewer's setting first and, since nothing is configured, says what the
  optional reviewer would send to Amazon Bedrock. When setup offers to enable the external reviewer,
  reply `no`: it stays off and needs no tools. Skipping the question leaves it off too
- When it lists `uv` as the required gap and asks what to install, reply `uv` (`all` does the same: it
  means the required gaps only). Setup installs an optional tool it mentions, such as the AWS CLI or the
  AWS SAM CLI, only when you name it, and neither is needed here
- Claude Code then asks permission to run setup's `install.py ... --apply` command, with the plan's
  summary. Allow it; declining installs nothing

When nothing required is missing, setup says so and installs nothing. Setup installs uv into
`~/.local/bin` and never edits your shell profile: when its report names a directory to add to PATH, add
it to your profile. The skills' own tool check looks in those directories anyway, and this project runs
nothing through uv, so you can go on in the same session; a project whose commands do (`uv run ...`)
needs the directory on PATH before its session starts.

**5. Implement.** Type:

```
/implement-from-spec:implementing-python-from-spec . specification/functional/slug.md
```

The skill reads the items and `CLAUDE.md`, posts a short "what I read", writes the plan to
`ai-planning/<slug>.plan`, checks it with `spec-trace.py plan`, and asks: *"Does this plan look right?
Reply approve (or approve <plan name>) to proceed, or tell me what to change."* Until you answer, the gate
denies every write outside `ai-planning/` and `.claude/`. Read the plan: its Scope is `SPEC-F001,
SPEC-F002`, and its tasks name the files each one owns and the tests that prove it.

**6. Approve.** Reply with one word:

```
approve
```

The skill keeps a ledger next to the plan, writes each test first and records its failing run, writes
`textkit/slug.py`, runs the tests from `CLAUDE.md`, verifies both items, runs `spec-trace.py code`, and
reviews the change with its Claude lens reviewers. It ends with a report headed
`## <Feature>: implemented (not deployed)`, with a line "External review: off (configuration)" after the
Review line, and whose last lines give the status (`implementation complete`) and the next steps.

**7. Check the result yourself:**

```
git status
python3 -m unittest discover -s tests -v
```

The changed files are the ones the plan's tasks own, plus `ai-planning/`. For a real stack, read its user
guide under [docs/user-guide/](docs/user-guide/) first; each guide describes the repository layout its
skill expects.

## Skills

- `implementing-terraform-from-spec`: Terraform modules, environment wiring, variables, outputs and IAM
  policy documents; ends at a targeted plan with zero destroys. Guide: [terraform.md](docs/user-guide/terraform.md)
- `implementing-cdk-from-spec`: AWS CDK v2 apps in Python or Java; ends at a change-set diff that replaces
  nothing that exists. Guide: [cdk.md](docs/user-guide/cdk.md)
- `implementing-cloudformation-from-spec`: CloudFormation YAML templates, Guard rules, template tests and
  parameter files; ends at validated templates. Guide: [cloudformation.md](docs/user-guide/cloudformation.md)
- `implementing-java-from-spec`: Java services, Lambda functions and libraries with JUnit tests, through the
  project's Maven or Gradle wrapper. Guide: [java.md](docs/user-guide/java.md)
- `implementing-python-from-spec`: Python Lambda handlers, Strands agents on AgentCore, libraries and
  scripts with their tests. Guide: [python.md](docs/user-guide/python.md)
- `reviewing-java-changes`: a two-stage review of any Java change, with or without a plan; also the review
  step of the Java skill
- `reviewing-python-changes`: a two-stage review of any Python change, with five Claude lenses; also the
  review step of the Python skill
- `reviewing-terraform-changes`, `reviewing-cloudformation-changes` and `reviewing-cdk-changes`: the same
  two-stage review for infrastructure code changed outside the implementing skills, with read-only checks
  (fmt and validate, cfn-lint and cfn-guard, synth) and no deploy
- `setup`: checks and installs the command-line tools, and offers to enable the optional external
  reviewer (it never turns it on itself); only you can start it
- Reviewer skills, loaded only inside a review: `code-reviewer` (any stack), `iac-security-reviewer`
  (CloudFormation and CDK), `reviewing-terraform-code` (Code Reviewer for HashiCorp Terraform),
  `reviewing-terraform-security` (Security Reviewer for HashiCorp Terraform) and
  `running-external-review` (runs the external review command and returns its output verbatim; while
  the reviewer is off, the command sends nothing and prints "External review: off (configuration)")

The second stage of every review is the external reviewer, which runs only when you enable it.

Each skill except the reviewer skills appears as `/implement-from-spec:<skill>`. Claude also starts the
implementing and reviewing skills on its own when a request matches ("implement SPEC-F012 in this repo").

The plugin ships no agents. Each review step dispatches one generic subagent per reviewer, all in one
message so they run in parallel, and each subagent first loads its reviewer skill with the Skill tool.
The reviewer skills are read-only, and the review-isolation hook enforces it with an allowlist: a subagent
that loaded a reviewer skill may use Read, Grep, Glob, read-only shell commands (`grep`, `rg`, `sort`, `wc`,
`file`, `diff` and `find` only with their listed read-only options) and a few bookkeeping tools (the task list, tool search, its hand-back), and
every other tool is denied, so it cannot edit, fetch, start
agents or run anything else, and it reads only the repository, the plugin and the review snapshot. The approval gate sees every subagent's tool
calls, and the orchestrator compares the work tree before and after the review. Each review is bound to
a snapshot of the change and opens with a state block (recommendation, verification, approval required,
risk, rollback); see `docs/user-guide/external-review.md`, "The review around it".

## Use

From a session inside the project repository:

```
/implement-from-spec:implementing-terraform-from-spec . specification/functional/queue.md
```

The arguments are the repository and the input: SPEC IDs, a specification file, or a feature spec under
`ai-planning/`. Plain words work too. The skills accept three input forms:

- Structured items `SPEC-<SVC>-n` under `docs/specifications/`
- `SPEC-Fxxx` (functional) and `SPEC-NFxxx` (non-functional) items under `specification/`, optionally
  with `TC-xxx` test cases
- A feature spec, `ai-planning/<feature>.md`, which says what to build, not how. The plan gives its
  requirements `SPEC-PLAN-n` IDs

Review the plan, reply `approve`, and the skill implements. Deploying stays yours: the report ends with
the exact command.

What a skill writes in your repository besides the change: `ai-planning/<slug>.plan`,
`ai-planning/<slug>.ledger.md`, and for an amendment `ai-planning/<slug>.r<N>.approved.md`, a snapshot of
the plan you approved before.

## MCP servers

Not bundled. Add them to your user or project MCP configuration, for example in `.mcp.json`:

```json
{
  "mcpServers": {
    "aws-documentation": {
      "command": "uvx",
      "args": ["awslabs.aws-documentation-mcp-server@1.2.3"],
      "env": {"FASTMCP_LOG_LEVEL": "ERROR", "AWS_DOCUMENTATION_PARTITION": "aws"}
    },
    "terraform": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "hashicorp/terraform-mcp-server:1.3.0"]
    }
  }
}
```

`uvx` comes with [uv](https://docs.astral.sh/uv/). Both servers are pinned to a released version (the
AWS Documentation server 1.2.3 is the PyPI release of 2026-10-13); raise a pin deliberately. Without the Terraform server the Terraform skill reads
the Terraform Registry documentation online. Without the AWS Documentation server the CloudFormation and
CDK skills fetch `docs.aws.amazon.com` pages directly; the other skills expect the server.

## Behaviour to know

- **The gate needs python3.** The plugin's hooks fail open when `python3` is missing or broken, so that
  an unrelated session is never blocked. Without `python3` there is no gate. Setup checks for it
- **Starting again.** After `claude --resume` or in a new session, start the skill again before it
  writes, so the gate knows the repository
- **Subagents.** Writing subagents are dispatched only after approval, and their brief carries the same
  restrictions
- **External review is off by default.** The report then says "External review: off (configuration)"
  and the Claude review runs alone. Enable it in `/config` (`external_review = bedrock-gpt`): every review
  then sends the plan, the rules files, the review focus, the specification files in scope and the
  filtered change to GPT-6 Astra on Amazon Bedrock, in your AWS account. Without access the report says
  "External review: not run (<reason>)" and the Claude review still runs. Details:
  [docs/user-guide/external-review.md](docs/user-guide/external-review.md)
- **Cost.** On a subscription the skills spend plan usage; with an API key or on Amazon Bedrock they are
  billed per token. When enabled, the external review is billed to the AWS account it runs in, at the
  model's Bedrock price
- **State outside your repository.** The gate keeps its state in the plugin's data directory
  (`~/.claude/plugins/data/<id>/spec-approval-gate/`). External reviews are saved in the review home:
  `$SPEC_REVIEW_HOME` when set, else `~/.local/state/spec-external-review/` (or under `$XDG_STATE_HOME`).
  Setup keeps its doctor result and install journal in `~/.local/state/implement-from-spec/` (or under
  `$XDG_STATE_HOME`). Nothing is written into the project except the files listed under "Use"

## Uninstall

Remove the tools setup installed first, if you want them gone: run `/implement-from-spec:setup` and ask
it to run `install.py --uninstall`, which removes only what setup installed in user scope, with the same
dry run and approval as an install. Its record lives in `~/.local/state/implement-from-spec/`, which
uninstalling the plugin does not delete.

```
claude plugin uninstall implement-from-spec@implement-from-spec
rm -r ~/.local/state/spec-external-review ~/.local/state/implement-from-spec
```

Uninstalling deletes the plugin's saved settings and its data directory, which holds the gate state
(`--keep-data` keeps the directory). The second line removes the saved external reviews and setup's state.

## Documentation

- Per-stack guides: [Terraform](docs/user-guide/terraform.md), [CDK](docs/user-guide/cdk.md),
  [CloudFormation](docs/user-guide/cloudformation.md), [Java](docs/user-guide/java.md),
  [Python](docs/user-guide/python.md)
- [External review](docs/user-guide/external-review.md): settings, states, credentials, what is sent
- [Model providers](docs/user-guide/providers.md): subscription, API key, Amazon Bedrock
- [Customer hand-off](docs/customer-handoff.md): one page for teams adopting the plugin
- [Design notes](docs/design-notes.md): decisions and the evidence behind them
- The shared workflow every skill follows: [core/contract.md](core/contract.md)

## Development

The unit tests, the skill evals, the security scans and the container tests are kept in the maintainers'
development repository and are not part of the released plugin. A maintainer runs all of them before
every release and before merging a pull request ([CONTRIBUTING.md](CONTRIBUTING.md)). The plugin's
manifests can be checked from a copy of the plugin with no AWS or model call:

```
claude plugin validate . --strict
```

## Maintainers

Owned and maintained by the AGS-NAMER-FSI-GF team. Owner: Denis Demichev.

## Licence and support

implement-from-spec is licensed under the Apache License 2.0, all of it: scripts, hooks, skills and
documentation. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The tools `/implement-from-spec:setup` installs are not part of the plugin. Each one, for example the AWS
CLI, Terraform, cfn-lint or Checkov, is downloaded from its vendor when you approve it and comes under
that vendor's licence, not under this plugin's; check it before you install. HashiCorp Terraform 1.6 and
later is licensed under the Business Source License 1.1, which is not an OSI-approved open-source licence.

The plugin is provided "as is". You remain responsible for testing, deploying and supporting what it
produces. Issues are answered on a best-effort basis.

- [Contributing](CONTRIBUTING.md): issues, pull requests and the local checks a change must pass
- [Security](SECURITY.md): report a vulnerability to AWS Security, never in a public issue
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## Acknowledgements

Four reviewer skills (`code-reviewer`, `iac-security-reviewer`, `reviewing-terraform-code` and
`reviewing-terraform-security`) first followed the structure of reviewer prompts in
[Everything Claude Code](https://github.com/affaan-m/everything-claude-code). They have since been
rewritten for this plugin.
