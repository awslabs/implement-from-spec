# Design notes

Decisions with the evidence behind them. Newest decisions first within each topic.

## Approval gate placement (decided 2026-10-16)

The gate is registered once, by the plugin's `hooks/hooks.json`, and runs in plugin mode
(`--skills-dir`). It is inert in every session until that session starts one of the plugin's gated
skills, a skill whose directory holds a `gate_rules.json`. From then on it gates the repository the
session was in when the skill started, plus any repository whose `ai-planning/*.plan` the session
writes. Every other repository stays writable.

Why not the skills' own `hooks` frontmatter, as the vault skills use:

- A skill's frontmatter hooks stay registered for the rest of the session, and in skill mode every git
  work tree is a project repository. After one implementing skill ran, every other repository was gated
  until it had an approved plan
- In a plugin skill's frontmatter hook, `CLAUDE_PLUGIN_DATA` is empty, so the gate's state could not
  live in the plugin's data directory

How activation is detected, without a step the model could skip:

- When Claude starts the skill, `PreToolUse` with matcher `Skill` fires, with
  `tool_input.skill = "<plugin>:<skill>"`. The gate's `activate` event registers the repository
- When the user types the slash command, `UserPromptSubmit` receives `prompt = "/<plugin>:<skill> …"`
  and no Skill tool call follows. The gate's `record` event registers the repository, then handles
  approval words as before

Failure policy:

- The plugin-level hooks keep the default `onFailure: continue`. They run in every session, so a
  missing or broken `python3` must not block every tool in every session
- Inside the script, an ungated session never blocks, even on a malformed payload. A gated session
  fails closed: a guard error denies the write
- `setup` (planned) checks that `python3` is present, so the gate is not silently absent

Evidence: probes run with Claude Code 2.1.301 on macOS 27.0.1, loading a throwaway plugin with
`claude -p --plugin-dir`, model `sonnet`, Amazon Bedrock:

- **Skill content:** `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_SKILL_DIR}` are substituted.
  `${user_config.KEY}` is not substituted when no value has been saved, even with a `default`
- **What the documentation says (read 2026-10-16):** the skills page
  (https://code.claude.com/docs/en/skills) lists `${CLAUDE_PLUGIN_DATA}` among the string substitutions,
  "Substituted only in plugin skills", and says "In a plugin skill, Claude Code substitutes
  `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` in the same two places": the skill's Markdown
  content and Bash rules in `allowed-tools`. The plugins reference
  (https://code.claude.com/docs/en/plugins-reference, "Where each variable resolves") resolves `${...}`
  in skill content "Anywhere in the Markdown body", exports `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`,
  `CLAUDE_PROJECT_DIR` and `CLAUDE_PLUGIN_OPTION_<KEY>` to hook commands, and says "The variables aren't
  present in the environment of commands Claude runs through the Bash tool". Neither page says which
  variables a skill's frontmatter hook receives. The probe above did not test `${CLAUDE_PLUGIN_DATA}` in
  skill content, so whether 2.1.301 substitutes it there is not measured
- **Skill frontmatter hook in a plugin skill:** `CLAUDE_PLUGIN_ROOT` is exported to the process, and
  `CLAUDE_PLUGIN_DATA` is empty
- **Plugin `hooks/hooks.json` hook:** both `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are exported
  (`~/.claude/plugins/data/<plugin>-inline` for a `--plugin-dir` load)
- **Quoting:** in both hook types, `${…}` inside single quotes reached the shell literally. Hook
  commands therefore use `"$CLAUDE_PLUGIN_ROOT"` in double quotes
- **Visible events:** `PreToolUse` matcher `Skill` and `UserPromptSubmit` were both seen by the plugin
  hook, with the payloads described above
- **Live check:**
  - with the gate's hooks loaded from this repository and a temporary gated skill, the session that
    started the skill was denied a write outside `ai-planning/`
  - a second session that never started the skill wrote its file, and created no gate state

Consequence for configuration: because `${user_config.KEY}` is not substituted without a saved value,
the scripts read the plugin's settings themselves and apply their own defaults. Skill text does not
pass settings through.

## Gate interpreter (decided 2026-10-16)

`hooks/hooks.json` starts every hook as `python3 -I`: the gate in each of its five registrations and the
two setup hooks (`core/deps/install-ask-hook.py`, `core/deps/session-notice.py`). `session-notice.py`
loads its sibling `depslib.py` by file path and adds nothing to `sys.path`.

Why: the gate runs on every Write, Edit, Bash and Skill call of every session, so any code Python loads
before the gate's own runs inside every hook call. In isolated mode "`sys.path` contains neither the
script's directory nor the user's site-packages directory. All `PYTHON*` environment variables are
ignored, too" (https://docs.python.org/3/using/cmdline.html, `-I`, "Added in version 3.4", so the
Python 3.9 floor has it). A `json.py` written next to the script, a `PYTHONPATH` or `PYTHONSTARTUP`
value, or a package in the user's site-packages is therefore never imported by the gate. The script
also drops its own directory from `sys.path` before its first import, for any registration that starts
it without `-I`, such as a skill's frontmatter hook in skill mode.

The scripts the skills start through the Bash tool run the same way: every documented invocation is
`python3 -I "<path>"` (`spec-trace.py`, `spec-external-review.py`, `doctor.py`, `install.py` and the
`--apply` command `install.py` prints), and the setup bootstrap calls python3 with `-I`. A Bash
command inherits the session's environment, and a settings file's `env` block sets "environment
variables for every session and its subprocesses", from any settings file including a trusted
repository's `.claude/settings.json` (https://code.claude.com/docs/en/settings-reference, `env`), so a
`PYTHONPATH`, `PYTHONHOME` or `PYTHONSTARTUP` value there would otherwise reach the scripts. The setup
scripts find `depslib.py` by file path through one `_depslib` function and their other siblings
through `depslib.load_sibling`, adding nothing to `sys.path`.

## Setup state directory (decided 2026-10-16)

Setup's scripts (the doctor, `install.py`, the install ask hook and the session-start notice) keep their
state in one directory, `${XDG_STATE_HOME:-~/.local/state}/implement-from-spec/setup/`, and do not read
`CLAUDE_PLUGIN_DATA`. `--data-dir` overrides the location for one run.

Why:

- The doctor runs from a skill's preflight through the Bash tool, and the notice runs as a SessionStart
  hook. Claude Code exports `CLAUDE_PLUGIN_DATA` to hook commands but not to commands run through the
  Bash tool (plugins reference, "Where each variable resolves"), so a resolution that read the variable
  saved the doctor's result in one directory and had the notice look in another
- `HOME` and `XDG_STATE_HOME` are the same for a hook and a Bash tool command, so every script resolves
  the same directory with no flag, and skill text never has to pass a directory

Cost: the directory is not removed when the plugin is uninstalled. Claude Code deletes
`${CLAUDE_PLUGIN_DATA}` when the plugin is uninstalled from the last place it is installed (plugins
reference, "Environment variables"); this directory stays until the user removes it. The approval gate's
state is unaffected: the gate runs only as a hook, where `CLAUDE_PLUGIN_DATA` is exported, and keeps its
state there.

## Test environment (decided 2026-10-16)

Skills and the core are tested in an isolated Finch container: Amazon Linux 2023 (`python3` 3.9.25)
with Claude Code from Anthropic's signed dnf repository, latest channel by default with a 2.1.295 floor
(the stable channel was at 2.1.292 on 2026-10-18; `CLAUDE_CODE_CHANNEL` selects it). The
container sees only the plugin, mounted read-only at `/plugin`; no host home directory, no `~/.claude`,
no `~/.aws`. Live runs authenticate Claude Code on Amazon Bedrock with `AWS_BEARER_TOKEN_BEDROCK`,
`CLAUDE_CODE_USE_BEDROCK`, `AWS_REGION` and the model pins passed by variable name (`-e NAME`), so no
value appears in a command line or a file. The container runner is part of the maintainers' development
repository, not of the released plugin.

Results on 2026-10-16:

- `core`: gate, spec-trace and external-review suites pass on Python 3.9.25
- `gate-live`:
  - the session that started a gated skill was denied a write outside `ai-planning/`
  - the session that never started it wrote its file
  - exactly one session's gate state existed afterwards

## Python minimum (decided 2026-10-16)

The minimum is the `python3` that macOS ships by default: on macOS 27.0.1 that is the Command Line
Tools' Python 3.9.6, behind `/usr/bin/python3`. The core's test suites pass on it.

Note for development shells running under Rosetta: `/usr/bin/python3` fails there because the Command
Line Tools are arm64-only. Run `arch -arm64 /Library/Developer/CommandLineTools/usr/bin/python3` to test
on the default interpreter.

## Deploys (decided 2026-10-16)

Deploys and live state changes (`terraform apply`, `cdk deploy`, change-set execution, stack
create/update/delete, state edits) always ask the user for explicit approval through the gate's command
rules. They are not hard-denied: an operator may approve one in the session. The skills still stop at
the plan, diff or change set and hand the operator the exact command.

## External reviewer default (decided 2026-10-19)

Off by default: `external_review = off`. Nothing goes to a non-Claude model until the user enables the
reviewer, and the report says "External review: off (configuration)" while the Claude review runs alone.
It stays available as an opt-in: `external_review = bedrock-gpt` (OpenAI GPT-6 Astra on Amazon Bedrock in
the user's account, `external_review_auth = aws-profile` by default) or `command`. Setup offers to enable
it, says what it sends, and leaves it off when the user declines or does not answer; it never turns it on
itself. Enabled but unable to run, it reports "External review: not run (<reason>)" and the Claude review
still runs; `external_review_policy = required` makes a missing review a failure. A misspelt mode is not
taken as off: the stage is reported as not run and nothing is sent. The earlier decision of 2026-10-16 had
the reviewer on by default (`bedrock-gpt` with `aws-profile`); it was reversed so that no repository
content leaves for another provider without the user's choice.

## No CI (decided 2026-10-16)

The repository has no CI/CD pipeline and no GitHub Actions. Every quality and security check runs on
the maintainer's laptop: the Python suites on python3 and macOS's built-in Python, component and
scan-scope checks, `claude plugin validate --strict` and a static code scan on every change; before a
release also the full code, dependency and secret scans and a security review; and the isolated Linux
container for Linux and live runs. These checks are kept in the maintainers' development repository and
are not part of the released plugin. The hosting service carries the published repository only.

## New code (decided 2026-10-16)

Everything is ported from existing sources, recorded in the maintainers' provenance map. Where no
source exists, new code may be written; each such file is marked "new" in the provenance map.

## Standard library only (decided 2026-10-16)

Every script and hook in the plugin (`core/gate/`, `core/scripts/`, `core/deps/`, the setup bootstrap)
imports only the Python standard library and runs on Python 3.9, the `python3` macOS ships. The plugin
itself has no install step: installing the plugin installs everything it runs. Only the stacks' own
command-line tools (terraform, the CDK CLI, cfn-lint, a JDK, uv or pipx) come from the user's machine,
and `/implement-from-spec:setup` installs those only with the user's approval.

Why:

- **No install hook exists to run one.** The plugin manifest reference lists no field that runs a
  command when a plugin is installed. The nearest documented pattern, installing dependencies into
  `${CLAUDE_PLUGIN_DATA}` from a hook, would download and install packages in a user's session, at a
  time the user did not choose. A stdlib-only plugin needs neither
- **The gate must start in every session.** `hooks/hooks.json` runs the gate on every Write, Edit,
  Bash and Skill call in every session. A third-party import would make the gate depend on a virtual
  environment or a site-packages state that differs per machine; when the import failed, the hook would
  fail open and the gate would be silently absent. With the standard library, the only precondition is
  `python3` itself, which setup checks
- **Python 3.9 as the floor.** It is the interpreter a Mac has without any install, so a customer can try
  the plugin on a stock machine. Code therefore avoids newer syntax and modules (`match`, `tomllib`, the
  `X | Y` union at run time; `from __future__ import annotations` keeps annotations unevaluated), and
  the maintainers' local checks run every suite on both the newest `python3` and the 3.9 interpreter
- **Supply chain.** Nothing in the plugin is fetched from a package index at run time, so there is no
  dependency to pin, audit, typosquat or compromise, and a release is exactly the files in the
  repository. The same reasoning keeps MCP servers out of the bundle: they are other projects' code, and
  the README recommends them with pinned versions instead. Inside the skills, a package the approved plan
  does not name is a question for the user, and a failed install never gets a substitute, because the
  name may be hallucinated or squatted (contract section 7)

Cost: no third-party YAML, HTTP or CLI libraries. The scripts parse what they need with `json` and
`re`, call AWS through the AWS CLI rather than an SDK, and the Bedrock API-key path is a bash script
(`core/scripts/bedrock-gpt`) over curl and jq.

Evidence: the core suites pass on Python 3.9.6 (macOS Command Line Tools) and 3.9.25 (Amazon Linux 2023,
in the maintainers' test container); the "Plugin manifest reference" page of the Claude Code documentation, read
2026-10-16, lists the manifest fields and the `${CLAUDE_PLUGIN_DATA}` directory "for installed
dependencies such as `node_modules`".

## Two reviewers: Claude, and an external model of another family (decided 2026-10-16)

Every implementing skill reviews its change in two stages that run in parallel on the same change and
the same base commit (contract section 9):

- **Claude stage, always.** Generic subagents loading the plugin's read-only reviewer skills, or the
  reviewing skill of the stack,
  walk the stack's check groups and review dimensions against the code. They report every finding they
  see; the orchestrator sets severity from the code
- **External stage, opt-in.** `core/scripts/spec-external-review.py` sends nothing by default (`off`).
  When the user enables it, it sends the plan, the rules files, the review focus, the specification files
  in scope and the filtered change to a model of a different family: OpenAI GPT-6 Astra on Amazon Bedrock
  or any reviewer command the organisation already uses

Why two, and why a different family:

- **Shared blind spots.** A model reviewing code it may have written shares that code's blind spots: the
  same misreading of a requirement, the same remembered-but-wrong API default, the same pattern it finds
  plausible. A reviewer from another model family fails differently, so the overlap of what both miss is
  smaller than either alone
- **The Claude stage stays because it has the tools.** It reads the repository, runs the stack's
  read-only checks and verifies a finding against the code before it is reported. The external stage sees
  only the payload it is sent. Each covers what the other cannot
- **Findings are evidence to check, not verdicts.** Both reviewers' output is data. Every finding is
  opened in the code and ends fixed, rejected with one line of evidence, deferred with the user's
  agreement, or open; claims about AWS or library behaviour are checked in the documentation first,
  because the external model's knowledge is dated
- **Optional, because it is a choice, not a dependency.** The second-family review sends repository
  content to another provider, so it is off until a team enables it. While it is off, the
  report says "External review: off (configuration)" and nothing leaves the machine for a non-Claude
  model. When the reviewer is enabled but cannot run, the report gives the exact reason and the Claude
  stage still runs. The skill never writes an external review itself, because an invented second opinion
  is worse than none. Teams that need the review set `external_review_policy = required`, which turns a
  missing review into "verification incomplete"
- **Separate credentials.** The external reviewer never receives `AWS_BEARER_TOKEN_BEDROCK` or any other
  Bedrock bearer variable, and its API-key mode reads its own variable, so enabling it can never change
  how Claude Code itself authenticates

The default (off; opt-in through Bedrock with the user's AWS profile) is recorded above under
"External reviewer default". Settings, states and what is sent: [user-guide/external-review.md](user-guide/external-review.md).

## Reviewers are skills (decided 2026-10-19)

The plugin ships no agents. The five reviewers (`code-reviewer`, `iac-security-reviewer`,
`reviewing-terraform-code`, `reviewing-terraform-security` and `running-external-review`, formerly the
`spec-review-runner` agent) are skills, and every review step dispatches one generic subagent per
reviewer (`subagent_type: "general-purpose"`), all in one message, each told to load its reviewer skill
with the Skill tool before it follows its brief (contract section 9). The two Terraform reviewers were
named `terraform-code-reviewer` and `terraform-security-reviewer` until 2026-10-22, when the AWS Trademark
Team asked that no skill name lead with a third-party name.

Why:

- **A generic subagent already gives what the agents were for.** Each reviewer still runs in its own
  context, sees only its brief and the skill, and runs in parallel with the others; the review steps
  keep setting the model per call. A custom agent added a file per reviewer, a tool list and an agent
  namespace to keep in step with the skills, and nothing a skill cannot carry
- **The hard tool list is replaced by instructions plus the gate.** An agent's `tools` field removed
  Write and Edit from the reviewer; a generic subagent has them. The reviewer skills now say what the
  list enforced (Read, Grep, Glob and read-only shell commands; no edit tool, no further agent or skill),
  the approval gate still sees and gates every subagent tool call, and the orchestrator compares
  `git status --porcelain` and `git diff` before and after the review, undoing and reporting any change
  a reviewer made. This is weaker than a tool list against a reviewer that ignores its instructions, and
  is accepted because the reviewers treat everything they read as data and the before-and-after
  comparison catches a write in the work tree
- **Loadable by instruction, not by accident.** Each reviewer skill sets `user-invocable: false`, which
  hides it from the `/` menu while Claude can still load it, and its description says it is loaded only
  inside a dispatched review. It does not set `disable-model-invocation: true`: the Claude Code skills
  documentation (code.claude.com/docs/en/skills, read 2026-10-19) says that with that field "Claude can't
  invoke the skill on its own" and that "Claude Code blocks the call", which would block the subagent's
  Skill tool call. The maintainers' component check holds both rules

