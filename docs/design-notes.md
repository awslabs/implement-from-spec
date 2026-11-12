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

`hooks/hooks.json` starts every hook as `python3 -I`. Since 2026-10-27 every PreToolUse call runs one
dispatcher, `core/gate/ifs-pretool.py` (`python3 -I -S`, exec form, `onFailure: block`), which runs the
gate's guards, the reviewer-isolation hook and the install ask in-process, with decisions identical to
the separate hooks it replaced; the gate's other registrations and the two setup hooks
(`core/deps/install-ask-hook.py`, `core/deps/session-notice.py`) start as before. `session-notice.py`
loads its sibling `depslib.py` by file path and adds nothing to `sys.path`.

Security changes of 2026-11-12, after the PR 1 triage and an independent review of its fixes (the threat
model's TM-47, TM-55, TM-57 to TM-62):

- **Fail closed for every tool, deliberately.** The dispatcher stays one registration on matcher `*` with
  `onFailure: block`, so a `python3` that cannot run blocks every tool call of every session with the
  plugin, reads included, until it is fixed or the plugin is turned off in `enabledPlugins`. The
  maintainer chose this over availability for reads on 2026-11-12: the reviewer isolation is an
  allowlist and needs every tool hooked, and a non-blocking registration for reads would let a
  registered reviewer use any tool unchecked whenever the hook cannot start
- **One definition of the state locations.** `core/gate/ifs_paths.py` locates the gate's and the
  isolation hook's state for the dispatcher, the gate and the isolation hook alike, loaded by path through
  one identical `load_paths` function. The dispatcher used to mirror those locations, and a mirror that
  drifted would have skipped the guards of a gated session; a paths module that cannot load makes the
  dispatcher run the full selection
- **No variable a repository can set moves the state, and losing it fails closed.** `SPEC_GATE_STATE_DIR`
  is gone (a repository's settings `env` block could set it and so move the gate's state between two calls,
  which made the session read as ungated); the state follows only `CLAUDE_PLUGIN_DATA`, `XDG_STATE_HOME` and
  `HOME`, which project and local settings cannot set, and the tests move it through the environment they
  start the hooks with. Starting a gated skill, and registering a reviewer, also writes an activation record
  in `~/.local/state/implement-from-spec/active/`, located from `HOME` alone: while it exists, a state that is
  missing, unreadable or elsewhere denies every write and shell command of the session (the reviewer: every
  call), instead of reading as never activated. A lost session is not repaired; the user starts a new one.
  In a gated session the gate protects these records, the reviewer registrations, the review snapshots and
  the timing log like its own state
- **No bytecode cache.** The dispatcher's checks and `ifs_paths.py` are compiled from source on every call
  that loads them and no `.pyc` is read or written for those modules; the former cache under the plugin data
  directory let a planted `.pyc` run inside every hook call in a session the gate did not protect. The
  modules a check loads itself (`depslib.py`, `install.py`) and the standard library keep Python's normal
  loader. The price is the compile time of the checks on the calls that load them; calls no check can
  decide still load nothing
- **The timing log stays in the hooks, hardened.** The eval runner's per-check timeline needs each check's
  duration from inside the dispatcher, which an external runner cannot measure, so the log was kept rather
  than removed. It is confined to `~/.local/state/implement-from-spec/hook-timing/` (a bare `<name>.tsv` or an
  absolute path in it), reached from `HOME` through directory descriptors with no symlink followed, and
  written only to a private regular file of the user with one link, under 64 MiB, opened non-blocking.
  `HOME` is one of the variables Claude Code does not take from project or local settings
  (https://code.claude.com/docs/en/settings-reference, "Variables Claude Code ignores in `env`")

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


## Review model: snapshots, isolation, states and fix rounds (decided 2026-10-26)

The maintainer compared the review skills with Anthropic's published review practice (the Claude Code
team's six layers with fix-round caps, and the Code Review documentation at
code.claude.com/docs/en/code-review, code-review-customize and code-review-pull-requests, read
2026-10-26) and had GPT-6 Astra assess ten proposals. Decisions, 2026-10-26: risk tiers only escalate;
the recurrence ledger is dropped (confirmed misses become eval cases instead); the four foundations
GPT-6 Astra ranked first are in scope (review snapshot, enforced reviewer isolation, a fail-closed
review state, a security hand-off rule); new eval cases cover each change once, on the Python stack,
plus a Java clean change. This section is the interface every file below implements; contract
section 9 states the normative rules.

### 1. Review snapshot (`core/scripts/review-snapshot.py`)

Findings, gate results, fix rounds and the review state bind to one immutable description of what was
reviewed. Standard library only, Python 3.9.

- `create --repo R --base REV [--range A..B | --files P... | --diff-file F] [--plan P] [--context P...]
  [--policy-rev REV] [--out DIR]`: writes `DIR/manifest.json`, schema `ifs-review-snapshot/1`, and
  prints `Review snapshot: <id12> (<n> files, policy at <rev12>)`. The manifest holds: `id` (sha256 of
  the canonical JSON of everything below), `repo`, `base`, `mode`, `candidate` (one entry per changed
  path, tracked changes staged or not plus untracked files git does not ignore: `path`, `status`
  added/modified/deleted, `sha256` of the candidate bytes or null when deleted), `policy` (the policy
  revision and, per policy file, `path`, `sha256` at that revision or null when absent), `policy_changed`
  (policy files whose candidate bytes differ from the policy revision), `plan` and `context` (`path`,
  `sha256` of the candidate bytes) and `created_at`. Policy files are `CLAUDE.md`, `AGENTS.md` and
  `REVIEW.md` at the root and in every parent directory of a changed path. Their policy-revision bytes
  are copied to `DIR/policy/<path>`; a file absent at that revision is not copied and the manifest says
  null, never falls back to the candidate. `--policy-rev` defaults to `--base` (in `--range` mode, to
  `A`). Default `DIR`: `<state>/review-snapshots/<id12>`, `<state>` being `$CLAUDE_PLUGIN_DATA` when set,
  else `$XDG_STATE_HOME/implement-from-spec`, else `~/.local/state/implement-from-spec`
- `verify DIR`: recomputes the candidate; exit 0 unchanged, exit 3 changed with one `changed: <path>`
  line per difference
- `delta OLD NEW [--json]`: paths added, removed or changed between two snapshots of the same repository
  and base: the scope of a fix round
- `record-gate DIR --name NAME --status pass|fail|not-run --command CMD [--reason TEXT]` (`not-run` needs `--reason`): appends to `DIR/gates.json` with the
  snapshot id; refused (exit 3) when `verify` fails, so a gate result never outlives its snapshot.
  `gates DIR` prints them
- `attach DIR --to synth/<name>.out|gates/<name>.txt|input/<name> --from PATH|-`: copies an output the
  reviewers read into the snapshot, write-once: a synthesised cloud assembly (regular files and
  directories, no symlinks, no CDK `asset.<sha256>` staging), a gate command's output, or an input from outside
  the repository (a change set, a pasted plan output; standard input with `-`). Added after the PR 1 code
  review: the IaC reviewing skills synthesised and redirected straight into `DIR`, which the approval gate
  denies in an implementing skill's gated session (the snapshot roots are among
  `ifs_paths.state_write_roots`, denied with or without approval), so the security reviewer of an
  implementing CDK review never got its templates. The producing command writes to a scratch directory
  and the script, which the gate does not see, copies the result; this keeps the gate's protection whole
  instead of opening subdirectories of the snapshot to tool calls. It writes nowhere else: only those three
  subdirectories of a snapshot directly under a default snapshot root (the only ones reviewers may read)
  that still verifies (exit 3 otherwise), never `input/change.diff` (the preparation's), never through a
  symlink, never over a name already attached, from no source that is or holds a credential path (every
  entry of a directory checked), within 256 MiB and 20,000 files.
  Reviewers may not run it (the isolation hook allows `verify`, `delta` and `gates` only)
- Exit status: 0 done, 1 error, 3 snapshot changed, 64 usage

### 2. Risk classification (`core/scripts/review-risk.py`)

`classify DIR [--json]` reads a snapshot and prints the tier and why. It only adds scrutiny: it never
lowers lens coverage, never reads author labels or commit messages, and never changes an external-review
setting. Output (JSON with `--json`): `tier` `standard|high`, `reasons` (one per matched rule, with the
path), `approval_required` (reasons a human must approve this snapshot), `security_handoff` (reviewer
skills that must be dispatched, each with its reason) and `lens_model` (`sonnet`, or `opus` on `high`).
Rules, by path and by added or removed lines:

- Policy files changed (`policy_changed`), CI and automation files (`.github/`, `.gitlab-ci.yml`,
  `buildspec*.yml`, `Jenkinsfile`, `.claude/`, `hooks/`, `*settings*.json`, `.claude-plugin/`):
  `approval_required` and `high`
- Specification files changed without an approved plan in the snapshot: `approval_required`
- Security-relevant content: IAM policy documents or statements, `Principal`, `sts:AssumeRole`, auth,
  token, password, secret, crypto or TLS handling, network exposure (`0.0.0.0/0`, public access
  settings): `high`
- Destructive data changes: migrations, `DeletionPolicy`/`UpdateReplacePolicy` changes, a removed or
  replaced stateful resource (tables, buckets, databases, queues, file systems): `high`
- Weakened tests: a deleted test file, a removed assertion, an added `skip`, `xfail`, `@Disabled` or
  `pytest.mark.skip`: `high`
- Infrastructure files inside an application-code review: CloudFormation or CDK templates and constructs
  add `implement-from-spec:iac-security-reviewer`, Terraform files add
  `implement-from-spec:reviewing-terraform-security` to `security_handoff`
- A path no rule recognises is listed under `reasons` as `unrecognised file type` and never lowers the
  tier

### 3. Reviewer isolation (`core/gate/review-isolation.py`, hooks.json `PreToolUse` on every tool)

Plugin hooks run inside subagents, and their input carries `agent_id` and `agent_type`
(code.claude.com/docs/en/hooks, "Common input fields", read 2026-10-26). The hook enforces the read-only
rule the reviewer skills used to state only as an instruction:

- **Registration**: a `Skill` call made inside a subagent (input has `agent_id`) that loads one of the
  reviewer skills (`implement-from-spec:code-reviewer`, `iac-security-reviewer`,
  `reviewing-terraform-code`, `reviewing-terraform-security`, `running-external-review`) records the
  `agent_id` and its role in `<state>/review-isolation/<session_id>.json` (same `<state>` as above,
  written atomically under a lock). The main conversation and unregistered subagents (implementation
  waves) are never affected
- **For a registered reviewer**, an allowlist (changed from a denylist on 2026-11-12, after the PR 1
  triage: a tool the denylist did not name, a new Claude Code tool included, was allowed): `Read`, `Grep`,
  `Glob` and `Bash` as limited below, plus bookkeeping that writes no file and starts nothing (`TodoWrite`,
  `TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate`, `ToolSearch`, `SubagentHandback`). Everything else is
  denied with `permissionDecision: "deny"` and a reason that tells the reviewer to list the denied call
  under the parts it could not complete:
  - Every other tool: `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `WebFetch`, `WebSearch`, `Agent`,
    `Task`, any `mcp__*` tool, and any further `Skill` call among them
  - `Read`, `Grep` and `Glob` outside the allowed roots (the git top level of the hook input's `cwd`,
    `$CLAUDE_PLUGIN_ROOT`, the review-snapshot directory) or on a credential path anywhere (`~/.aws`,
    `~/.ssh`, `~/.config/gcloud`, `~/.azure`, `~/.docker/config.json`, `~/.netrc`, `.env` and `.env.*`)
  - `Bash` unless every command of the line (split on `|`, `&&` and `||`) is on the read-only allowlist:
    `git` with `diff`, `log`, `show`, `status`, `ls-files`, `blame`, `rev-parse`, `cat-file`,
    `merge-base` (never `-c`, `--output`, `--ext-diff`, `--exec`, `--upload-pack`); `ls`, `cat`, `head`,
    `tail`, `wc`, `grep`, `rg`, `sort`, `uniq`, `cut`, `tr`, `diff`, `stat`, `file` (`grep` and `rg` with
    an allowlist of read-only options, `SEARCH_SPECS`, each matched by its full name: since the PR 1 code
    review, because `rg --hostname-bin` runs a program and getopt reads an abbreviation such as `--regex`
    as `--regexp`; an option that runs or loads something, follows a symlink out of the paths given, or
    takes a value in one of BSD grep, GNU grep and ugrep but not in another, is left out); `find` without
    `-exec`, `-execdir`, `-ok`, `-delete`, `-fprint*`; `sed -n` without `-i` or a `w` command;
    `python3 -I <PLUGIN_ROOT>/core/scripts/review-snapshot.py verify|delta|gates`; and, for the
    `running-external-review` role only, `python3 -I <PLUGIN_ROOT>/core/scripts/spec-external-review.py`.
    Any `>`, `>>`, `<(`, `$(`, backtick, `;`, `&` (background), leading variable assignment, `env`,
    `sudo` or test runner denies the line. Reviewers no longer run tests; the orchestrator's quality gate
    does
- Each denial is appended to the session's state file. Limitation, stated in the user guide: this is
  enforcement inside Claude Code's tool layer, not an operating-system sandbox; the external-review
  script still sends what it documents, and the before-and-after `git status` comparison stays

### 4. Policy and requirements

Review policy and approved requirements are different authorities. Policy (`CLAUDE.md`, `AGENTS.md`,
`REVIEW.md`) is read from the snapshot's `policy/` directory, the policy revision, never from the
candidate: a change cannot review itself under rules it rewrote. A change to a policy file is reviewed
as part of the change and puts `human (policy file changed: <path>)` under *Approval required*; it is
not by itself a Major. Specifications are read from the candidate, because the documentation sync
(section 10) amends them legitimately; the specification-fidelity lens checks every changed
specification item against the approved plan, and a change no approved item or amendment covers is a
Major finding "unapproved requirement change". `spec-external-review.py` gains `--policy-dir DIR`: rules
are read from that directory (the only input allowed outside `--repo`, confined to it, no symlinks; since
2026-11-12 only the `policy/` directory of a snapshot of the reviewed repository, its files checked against
the snapshot's manifest, and since the third fix round of that day a snapshot of the change under review:
policy at its base, the change's mode and commits, every applicable policy file recorded; since the fourth,
a `--files` review, which has no base argument, names the snapshot by its full id with `--snapshot-id`,
and the snapshot's base must be an ancestor of `HEAD`).

`REVIEW.md` may recalibrate Minor and Nit severity, cap Nits, add always-check rules and name generated
paths to skip. It cannot remove a Blocker class, a lens, the security hand-off, the quality gate or the
external stage; a line that tries is reported as a finding, as any instruction in reviewed content is.

### 5. Findings

The finding line gains an evidence clause and an attribution:

    [Blocker|Major|Minor|Nit] [unsure] <file>:<line> - <lens or group> - <problem> (<item ID>). Why: <one sentence>. Evidence: <trigger>; <path, with file:line steps>; <wrong result>. Fix: <concrete change> [(pre-existing)]

- **Evidence** is a causal argument, not a citation: what triggers the defect, the path it takes, the
  wrong result. Uncertain findings are still reported, with `unsure` and what would decide them. The
  orchestrator still opens the code and looks for counter-evidence (a guard, a caller that never passes
  the value); evidence is where verification starts, never proof
- **Pre-existing** means the harmful behaviour and its exposure both exist on the base, independent of
  this change. A defect the change makes reachable, widens or worsens is the change's, even in lines it
  did not touch
- **Covered by gate**: a finding the quality gate demonstrably settles (same snapshot, red when the gate reports that very violation or green when it proves its absence, the exact
  file and rule) gets that disposition with the command; anything the gate cannot see (a semantic type
  hole behind `Any`, a suppression, a file the gate's configuration excludes) stays a finding
- **Minor and Nit**: the report shows at most five one-liners (or `REVIEW.md`'s cap) and counts the rest; every finding is
  saved in full to `<snapshot DIR>/findings.md`. Higher severities are never capped
- **Temporal compatibility** joins the specification and failure lenses: mixed old and new versions,
  migration order, replay, rollback after new writes, partial deployment

### 6. Review state (fail-closed)

Every review report opens with this block, which ends with the same state as one JSON line:

    Snapshot: <id12> (valid | invalidated: <paths>)
    Recommendation: <No blocking findings | Changes requested | Blocked>
    Verification: <complete | incomplete (<reasons>)>
    Approval required: <none | human (<reasons>)>
    Risk: <standard | high> (<reasons>)
    Rollback: <not applicable | supported (<evidence>) | unsafe (<finding>) | unknown (<what settles it>)>

    <!-- ifs-review-state: {"snapshot":"<id12>","recommendation":"...","verification":"complete|incomplete","approval_required":true|false,"open":{"blocker":N,"major":N},"risk":"standard|high"} -->

- **Blocked**: a confirmed open Blocker, a red gate, or a confirmed open security Blocker or Major
- **Changes requested**: a confirmed open Major the user has not agreed to defer
- **No blocking findings**: neither of the above. It is a recommendation, never an approval: the
  person who ran the review approves
- **Verification incomplete** when any of: a lens or reviewer failed or skipped part of its brief (even
  when the orchestrator covered it, which is named), the external review was required by policy and did
  not run, a security hand-off was required and did not run, a high-risk claim needs runtime
  verification, the snapshot was invalidated, an isolation denial left a reviewer's brief incomplete
- A review is **complete** only with *No blocking findings*, *Verification: complete* and *Approval
  required: none*. The implementing skills read the JSON line; anything else means their report states
  what remains, and a later edit invalidates the snapshot and therefore the state

The old verdicts map as Approve and Approve with comments to *No blocking findings*, Request changes to
*Changes requested*, Block to *Blocked*.

After the state block the report adds `### For the human reviewer`: two or three sentences on what the
change does and why, written from the traced code (the author's narrative is testimony), and the hunks a
human should read, as many as the risk warrants, each with its reason, highest blast radius first. A
`### Pre-existing (not caused by this change)` section keeps those findings with their severity, outside
the recommendation, with an escalation note on any Blocker. `### Covered by gate` lists those
dispositions.

### 7. Fix rounds

A fix is reviewed like the change it fixes. After the fixes, take a new snapshot and its `delta` against
the reviewed one; that delta is the round's scope, with the whole repository readable for context.

- Lenses: every lens whose domain the delta touches, plus every lens with a finding the fix claims to
  close; the security hand-off reviewers when the delta touches their paths; the external stage on the
  delta's files (`--files`, with the new snapshot's `--policy-dir` and `--snapshot-id`)
- The brief carries the earlier findings, numbered F1, F2 and so on. Each is reported `closed`
  (evidence), `open` or `regressed`; an open finding keeps its number and is not notified again as new.
  For every fixed pattern the reviewer searches the repository for sibling instances
- Round cap: two fix rounds after the first review. At the cap, automatic fixing stops; the report lists
  the open findings and asks the user whether the approach itself should change. Reaching the cap is
  never a clean result
- A fix applied outside the plan's *Owns* is an amendment (section 5), as before

### 8. Security hand-off

`review-risk.py`'s `security_handoff` list is mandatory: each named reviewer is dispatched with the
other reviewers, and when one cannot run, verification is incomplete. A confirmed security Blocker or
Major can be deferred only by the user in the conversation, recorded in the ledger when a plan exists.
On `high`, the application lenses run on Opus.

### 9. Order of reading

Approved requirements (the plan's items, the specification) are read first: they define the target. The
author's claims of completion (commit message, implementer report, the plan's completion notes) are read
last, after tracing, as testimony to confirm.

## Review speed and the eval loop (decided 2026-10-26)

Measured on the branch's first eval round (23 review cases, 2 runs each, concurrency 3, 7,236 s): wall time
is the summed run time divided by the concurrency; Bedrock did not throttle; the first reviewer was
dispatched 64 s (Python) to 201 s (CDK) into a run, after many separate setup calls; the reviewer
dispatches left 10 s apart because the orchestrator wrote each long brief inline. The maintainer chose
(2026-10-26): a single preparation call, compact dispatch, no runner subagent when the external review
is off, tighter turn budgets on the review cases; the eval loop gets one run per case while developing
(two at release), regrading of kept transcripts, change-impact case selection, and parallel fix agents;
the Finch VM grows to 8 CPUs and 10 GiB and evals run at concurrency 8.

### 1. `core/scripts/review-prepare.py`

One call replaces the setup steps of every reviewing skill. Standard library only, Python 3.9.

    python3 -I "<PLUGIN_ROOT>/core/scripts/review-prepare.py" --stack python|java|cdk|cloudformation|terraform \
        --repo R --base REV [--range A..B | --files P... | --diff-file F] [--plan P] [--context P...] \
        [--external-review off] [--json]

It runs `review-snapshot.py create` and `review-risk.py classify` in process (import, not a subprocess,
where the modules allow it), reads the stack's dispatch manifest, writes one brief per reviewer to
`<snapshot DIR>/briefs/<reviewer>.md`, and decides the external stage: it runs
`spec-external-review.py --show-config` with the same settings flags the user gave; when the effective
mode is `off`, it runs the external-review script itself with the review's arguments (which then prints
`External review: off (configuration)` and sends nothing) and saves stdout, stderr and the exit code to
`<snapshot DIR>/external.txt`; otherwise the runner subagent is dispatched as before. Output (text; the
same as JSON with `--json`):

    Review snapshot: <id12> (<n> files, policy at <rev12>)
    Snapshot directory: <DIR>
    Risk: <standard|high> (<reasons>)
    Approval required: <none | human (<reasons>)>
    Dispatch: <reviewer> skill=implement-from-spec:<skill> model=<sonnet|opus> brief=<DIR>/briefs/<reviewer>.md
    Dispatch: ...                                  (one line per reviewer, security hand-off included)
    External review: <the script's status line, when it ran here> | runner (dispatch the runner)
    Runner: skill=implement-from-spec:running-external-review model=<m> policy=<optional|required|unknown> brief=<DIR>/briefs/external-review.md

Exit status: 0 done, 1 error, 3 snapshot changed during preparation, 64 usage.

### 2. Dispatch manifest `skills/reviewing-<stack>-changes/references/dispatch.json`

Schema `ifs-review-dispatch/1`: `{"schema": ..., "reviewers": [{"name": "failure-handling", "skill":
"code-reviewer", "model": "lens" | "sonnet" | "opus", "brief": [{"file": "<path relative to the skill
dir or PLUGIN_ROOT-relative core/...>", "section": "<exact heading text, or null for the whole
file>"}], "assign": "<the lens or check groups, one line>"}], "runner": {"skill":
"running-external-review", "model": "sonnet", "focus": "<review-focus.md path>"}}`. `"model": "lens"`
takes the risk script's `lens_model`. A brief is the brief template plus the referenced sections
verbatim, with the repository path, change mode, plan, specification files, `<DIR>/policy/`, the
precedence rule, the read-only rule and the findings format filled in; nothing is paraphrased.

### 3. Dispatch from the skills

Every Agent prompt is short: `First load the skill implement-from-spec:<skill> with the Skill tool,
then read the brief at <path> and follow it.` All Agent calls go in one message. The runner subagent is
dispatched only when the preparation line says `External review: runner`; otherwise the status line in
`external.txt` is the external stage's result and goes into the report as before. Contract section 9's
"dispatched on every review" becomes "run on every review: by the preparation script when the setting is
off, by the runner subagent otherwise".

### 4. Turn budgets

`max_turns` of each review case: the larger of 30 and 1.5 times the highest main-session turn count of
its passing runs on the branch, rounded up to a multiple of 5; a case with no passing run keeps its
value.

### 5. The eval loop

One run per case while developing and in fix rounds, two for release evidence; change-impact case
selection (a change to shared review files selects every review case); regrading of kept runs with the
current graders, cross-checked in the eval runner's own regular-expression engine; one fix agent per
failing case. The harness that implements it ships with the test suite, not with the plugin; its README
gives the commands.

### 6. Scripted state block and findings (added 2026-10-26)

The second branch eval round showed models cutting snapshot ids to 7 or 10 characters, writing "id -> id"
on fix-round Snapshot lines, and being refused a Write of `findings.md` outside the project. The state
block and JSON line are therefore printed by `review-snapshot.py state DIR` from validated arguments and
the snapshot's `risk.json` (written by `review-prepare.py`); in a fix round the first line reads
`Snapshot: <id12> (valid; fix round <K> of 2, previous <old id12>)`. Findings are saved with
`review-snapshot.py save-findings DIR` from a quoted heredoc. `open` counts confirmed Blockers and Majors
of the change that are neither fixed nor deferred with the user's agreement, in every stack. Terraform
validate first runs `init` against a local provider mirror with a CLI configuration that has no `direct`
method, and asks for a download only when no mirror holds the providers. Reviewer briefs say one plain
command per Bash call, because designed isolation denials cost 4.1 retries per run.

### 7. External stage fail-closed (added 2026-10-26)

The third eval round found `spec-external-review.py` crashing on an unreadable untracked file without a status
line, and a review then reporting itself complete. The script now skips non-regular and unreadable files
(listed as not sent) and prints `External review: failed (<Type>: <message>)` on any unexpected error, with
the `; required by policy` tail under policy `required`. The preparation prints `policy=` on the Runner line;
a missing status line is recorded as `External review: failed (no status line; ...)`, and under policy
`required` or `unknown` any outcome other than a passed review makes verification incomplete. The main
conversation writes nothing in the project during a review, in every stack.

## Local eval runs (decided 2026-10-26)

The maintainer decided on 2026-10-26 that evals run on the macOS host, in separate processes with
separate, empty Claude Code configurations, instead of in the Finch container: the time of a review run
is model-bound, and the host allows more concurrent runs without the container's memory ceiling. Each
process gets a fresh copy of the plugin, an empty configuration, an empty home directory and a cleared
environment, so nothing installed for the user's own sessions loads, and the eval sandbox denies the
user's real home to every run. The tools the cases need come from a prepared offline cache. Terraform's
`validate` cannot run under the macOS eval sandbox, which blocks the provider plugin's local socket; the
Terraform review records it as not run with that reason (the maintainer, 2026-10-26). The test harness's
README describes the isolation, the toolchain cache, sharding and the smoke evidence.
