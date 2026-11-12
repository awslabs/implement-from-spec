# Changelog

Versions follow semantic versioning: a major version changes the gate's approval grammar or the
specification input formats, a minor version adds a stack or a check, a patch fixes or updates facts.

## Unreleased

### Changed

- Eval speed and review cost (2026-10-27, analysis in the maintainer's timing report): one PreToolUse
  dispatcher hook instead of five registrations (hook CPU per call 48–96 ms instead of 162–520 ms);
  Python review lenses on Opus (the critical lens 357 s to 129 s at the same cost); lane discipline
  and a capped finding line, with findings written once in findings.md; CDK reviewers dispatched in
  parallel with `cdk synth`; fix rounds re-dispatch only the lens that owns a finding; a local eval
  runner with one longest-first queue
- Review model (decided 2026-10-26, `docs/design-notes.md`): every review is bound to a snapshot of the
  change (`core/scripts/review-snapshot.py`), classified by an escalation-only risk script
  (`core/scripts/review-risk.py`) that adds Opus lenses, a human-approval requirement and a mandatory
  security hand-off, and read under the review policy (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`) of the base
  revision, never the change's own. Reviewer subagents are held read-only by a new hook,
  `core/gate/review-isolation.py`. Findings carry an Evidence clause and a causal pre-existing
  attribution; the report opens with a fail-closed state block (recommendation, verification, approval
  required, risk, rollback) and a JSON state line the implementing skills read; fixes are re-reviewed on
  the snapshot delta, at most two fix rounds. Ten new review eval cases, tagged `review-model`

### Fixed

- A plan approved in an earlier session: the approval message now opens by saying why that approval does
  not unlock this session (approval is per session and bound to the plan's exact content), in all five
  implementing skills
- CDK: a request that renames or moves an existing resource gets an approval message that opens by
  saying a plain `cdk deploy` would replace it (both logical IDs named), then offers the safe paths (keep
  the construct ID, keep the logical ID, or a separate `cdk refactor` with its `--dry-run` mapping)

## 0.1.0 — 2026-11-25

### Added

- Skills
  - `implementing-terraform-from-spec`: Terraform modules and wiring; fmt, validate and a targeted plan
    with zero destroys
  - `implementing-cdk-from-spec`: AWS CDK v2 apps in Python or Java; synth, assertion tests, cdk-nag and
    a change-set diff with no replacement of existing resources
  - `implementing-cloudformation-from-spec`: CloudFormation templates, Guard rules and template tests;
    cfn-lint, cfn-guard, cloudformation-validate and a change-set replacement rule
  - `implementing-java-from-spec`: Java services, Lambda functions and libraries, test-first through the
    project's build wrapper, with a local smoke gate
  - `implementing-python-from-spec`: Python Lambda handlers, Strands agents, libraries and scripts,
    test-first, with the project's lint, type and test gates
  - `reviewing-terraform-changes`, `reviewing-cdk-changes`, `reviewing-cloudformation-changes`,
    `reviewing-java-changes` and `reviewing-python-changes`: reviews of a change in two parallel stages
    (Claude reviewers and the external reviewer) over the stack's review dimensions
  - `setup`: checks and installs the stacks' command-line tools, only with your approval
- Review dimensions: a `references/review-dimensions.md` per stack (Terraform, CloudFormation, CDK, Java,
  Python), each building on the shared principles and architecture smells in
  `core/review/principles-and-architecture-smells.md`; used by the review skills, the implementing
  skills' review step and the reviewer skills
- Reviewer skills: `reviewing-terraform-code`, `reviewing-terraform-security`, `iac-security-reviewer`
  (CloudFormation and CDK), `code-reviewer` and `running-external-review`, all read-only, each loaded by
  a generic subagent that a review step dispatches; the plugin ships no agents
- Shared core
  - The approval gate (`core/gate/spec-approval-gate.py`), registered once in `hooks/hooks.json`, inert
    until a gated skill starts, gating only that repository. Deploys and live changes always ask
  - `spec-trace.py`: plan and code traceability checks
  - `spec-external-review.py`: the external review stage, configured by the plugin's settings; off by
    default, opt-in as GPT-6 Astra on Amazon Bedrock, through an AWS profile or a Bedrock API key, or a
    custom command
  - `core/scripts/bedrock-gpt`: the Responses API client for API-key authentication, kept off the Bash
    tool's PATH (a plugin's `bin/` is on it)
  - `core/deps/`: the dependency manifest, the read-only doctor and the installer behind `setup`
  - Python 3.9 or later, standard library only
- Setup
  - An optional SessionStart notice: one line when setup never ran or last found a missing required
    tool, silent otherwise; turned off with the `setup_session_notice` option
  - One state directory for the doctor, the installer, the install ask hook and the notice,
    `${XDG_STATE_HOME:-~/.local/state}/implement-from-spec/setup/` (`--data-dir` overrides it for one
    run); it is not removed on uninstall, see the README
  - A clean-container install check on five Linux images (Amazon Linux 2023, Debian 12, Ubuntu 24.04,
    Fedora 44, Red Hat UBI 9), run in the maintainers' test container
- Documentation
  - README, per-stack user guides, external review and model provider guides, the specification input
    format, customer hand-off, design notes
  - README: the licences of the tools setup installs (each from its vendor under the vendor's licence;
    Terraform 1.6 and later under the Business Source License 1.1) and an acknowledgement of Everything
    Claude Code
  - `docs/security/threat-model.md`: a threat model on the Four Question Frame, with a data-flow diagram
    and every control cited by file and line
  - `LICENSE` (Apache License 2.0, for the whole repository),
    `NOTICE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`; a copyright line and
    `SPDX-License-Identifier: Apache-2.0` header on every script
- Tests and release records, kept in the maintainers' development repository and not part of the
  released plugin
  - Unit tests for the gate (every `gate_rules.json` example), spec-trace, the external review script
    and the dependency tools; a component check; 37 eval cases, with results kept per version; per-stack
    sample projects
  - A container runner with smoke, live gate, end-to-end, install check and eval runs; every check runs
    locally, including the security scans (no CI)
  - A documentation walkthrough: a newcomer follows the README's Install and Getting started literally in
    a clean container, with live sessions, and the findings are written out
  - An eval summary that combines the latest saved result of each case per model, the pass rate of each
    skill against the 80% bar and a freshness flag per result (`current`, `stale`, `same-commit`)
  - A release checklist, a provenance record of every file, the scan procedure and the triage record of
    every finding
  - A release export: only the shipped files, checked for missing paths, broken links and internal names,
    into a fresh repository with one commit

### Changed

- External reviewer off by default (decided 2026-10-19, reversing the on-by-default decision of
  2026-10-16): `external_review` defaults to `off` in `plugin.json` and in `spec-external-review.py`, and
  the doctor and `install.py` default to `--review-auth off`. Nothing goes to a non-Claude model until
  the user sets `external_review = bedrock-gpt` (or `command`); the report then says "External review:
  off (configuration)". Setup offers to enable the reviewer, saying what it would send to Amazon
  Bedrock, and leaves it off when the user declines or does not answer; it checks the AWS CLI for the
  reviewer only when the user enables it with `aws-profile`. A misspelt mode is reported as not run,
  never taken as off
- Contract rules every implementing skill follows
  - A read of live state the plan names (a targeted plan, a diff, a change set) runs under the gate's
    approval prompt, with no second question in the conversation; denied or not possible, it is
    recorded as not run with the operator's command, and verification and review go on
  - A dependency step the plan names and the user denies is not retried or substituted; the tasks that
    need it are marked blocked and the report says "verification incomplete"
  - Same-change files (a specification topic file, a registry, a coverage matrix, the living documents)
    are in a task's Owns from the start; one found after approval is an amendment
  - After approval the plan is read-only: status and notes go in the ledger, an edit revokes the
    approval, and a correctly amended plan is approved again in a new turn
  - The final report gives the external review result on its own line, quoted literally
  - A user instruction that a binding project rule forbids (an install, a test framework, a dependency
    under approval) is not a stop: the plan follows the rule, records the conflict under its open
    questions with the rule quoted as the recommended answer, and the approval message asks once
- Skill triggering: every skill description leads with its triggers, and a `when_to_use` field adds
  the requests that used to be missed (a waived plan, a plan resumed from an earlier session, a
  dependency or resource added to a specification project, a diff to review, a review that keeps the
  external reviewer out, a terse question about a commit). A waived plan still gets a plan, and an
  earlier approval does not carry over
- Approval: the planning turn ends with one fixed plain-text message: the plan line, a mandatory
  `Design:` line (two to four sentences of prose on what the plan builds and how it is wired), the
  no-write line, what runs after approve, and the approval question word for word
- Deploy and apply requests: the skill runs nothing and does not answer with a refusal alone; the reply
  gives the operator's exact commands for the project's profile and root, and the pre-deploy or
  pre-apply checks the plan and ledger record
- Plans: Java and Python plans have an open questions section and list the dependencies that need
  approval, each open question with its source, options and recommended answer
- Reviews: what the approved plan explicitly leaves out (a stated exclusion, a deferred item, an
  operator check) is the agreed scope, not a finding; a binding rule the plan cannot waive is still
  reported, with the rule quoted
- Setup: "all" installs the required gaps only; optional tools and the alternative member of a pair
  only when named
- Evals: the judge model defaults to Sonnet
- spec-trace
  - `unowned-change`: a write outside every task's Owns FAILs, judged from the approval baseline commit
    as well as the working tree; amendment and baseline paths WARN
  - `tests-unowned`: a test path that does not exist yet and that no task owns FAILs at plan time
  - Task fields may wrap onto following lines; a backticked Tests entry that is prose FAILs
  - `outside-repo`: an owned file or test that resolves outside the repository through a symlink FAILs
  - A path owned in several waves is judged by its last owner
- Terraform: `terraform init` asks unless the backend is disabled; state migration flags ask
- Setup: cfn-lint requires 1.47.0 or later (Python 3.10 or later), installed through uv with a matching
  Python
- Reviewer agents rewritten in original wording; their output contracts are unchanged
- Java fixture on Spring Boot 3.5.16; CDK Java dependencies pinned to their newest releases

### Fixed

- spec-trace: code quoted in a `Tests: none — <reason>` entry is no longer read as a test path;
  `src/test/` and `*Test.java`-style names count as tests
- Setup: a skill's preflight and the SessionStart notice read the same saved doctor result (they used
  to resolve different directories)
- Setup reads the external reviewer's configuration (`spec-external-review.py --show-config`) before
  asking, and asks about the reviewer only when nothing is configured
- Reviews: the review runner is dispatched on every review, also when the external review is off or
  the user keeps the change away from the external reviewer (`--external-review off`), and the
  report's External review line is the one the runner returned
- Reports: every line below the heading is plain text, with no bold labels, and the External review
  line is the script's line with no bold, quotation marks or code span

### Security

- The approval gate now also analyses here-documents and here-strings fed to a shell, `eval`,
  `env -S`/`env -C` and `bash -c` option clusters, `find -exec` bodies, function bodies, inline
  interpreter code that runs commands or writes files, in-place `sed` and `perl` edits, archive
  extraction (`tar`, `unzip`), symbolic and hard links, git global options and `--work-tree`, and a `cd`
  that may not run
- The gate protects its own script, directory and state and the plugin's hooks from shell commands,
  and guards the user's Claude settings and hooks as well as the project's, also through symlinks
- The gate fails closed: a malformed or missing `gate_rules.json` makes every shell command ask, a gated
  skill the gate cannot record is refused, and an edit of an approved plan revokes the approval
- The gate runs as `python3 -I`, with its own directory removed from the import path
- The gate treats a tool's side effects in the project as writes, denied before approval: `terraform
  init`, `get` and `providers lock`, a saved `terraform plan -out`, `cdk synth`, Maven and Gradle
  builds, `pip` into a project virtual environment and `python -m venv`, `npm install`, `sam build` and
  `cloudformation package`. Planning reads provider schemas through the MCP server or the Registry,
  or works in a copy under `${TMPDIR:-/tmp}`
- The gate no longer lets an unquoted command substitution cut a write target short, a bypass found
  in an end-to-end run
- External review: more sensitive files are withheld (`.envrc`, kube and Docker configs,
  `.git-credentials`, `.pgpass` and others), plain diffs are parsed hunk by hunk and a malformed hunk is
  withheld, `git diff` runs without text conversion, and the reviewer command is logged by program name
  and argument count only
- git-secrets runs in the release scan alongside ASH, Semgrep and Bandit
