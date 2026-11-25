# Python

Two skills:

- `implement-from-spec:implementing-python-from-spec` implements Python code (AWS Lambda handlers,
  Strands agents on AgentCore, shared libraries, scripts and their tests) from specification items. It
  ends at a green quality gate, a built artifact and a local smoke check. Deploying stays with you or your
  pipeline
- `implement-from-spec:reviewing-python-changes` reviews any Python change: four read-only Claude lens
  reviewers (specification fidelity, failure handling with the AWS runtime and logging, types and design,
  tests), a security reviewer and, when you enable it, the external reviewer (off by default), all in
  parallel, while the project's tests and a dependency audit run. It is also the Python skill's review step

## Requirements

- python3 3.9 or later for the plugin itself, and a Python that matches the project's target runtime
- pipx or uv, to install command-line tools without touching the project's environment
- The project's own toolchain: uv, pip or poetry with its lock files, and its linter, type checker and
  test runner. These are project dependencies, never installed by setup
- For the dependency audit: python3 3.11 or later as the `python3` the plugin runs when the project has a
  TOML lock file, a `Pipfile` or a `pyproject.toml` that declares dependencies, because only 3.11 and later
  read TOML (`tomllib`); requirements files, `Pipfile.lock` and `setup.cfg` are read on 3.9 too; a committed lock file or requirements
  files pinned with `==` when the project declares dependencies (see "The dependency audit"); and network
  access to download public advisory
  data at most once a day, or a copy you import. On python3 3.9 or 3.10 the rest of the plugin works and
  the audit is recorded as not run (`interpreter`)
- Optional: the AWS SAM CLI; the AWS CLI v2, for read-only checks of the target account
- The AWS Documentation MCP server, for AWS facts

Check and install with `/implement-from-spec:setup python`. Setup reads each tool's minimum version and
install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every gap
with its exact commands, and installs only what you approve. The skill checks the same tools, read-only,
at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A `CLAUDE.md` or `AGENTS.md` with the project's rules
- The specification items, with the `Interface:` names the code must use exactly. A common layout is a
  `specification/` tree with `functional/` (`SPEC-Fxxx`) and `non-functional/` (`SPEC-NFxxx`) topic files;
  structured `SPEC-<SVC>-n` items under `docs/specifications/` and a feature spec under `ai-planning/`
  work too. [spec-format.md](../spec-format.md) gives the rules for each
- A `.gitignore` that covers `__pycache__/`, virtual environments, `.pytest_cache/` and build output:
  after implementation every changed or untracked file must belong to a task (see "How a run goes",
  step 6)
- `pyproject.toml`, lock files and the CI job that runs the checks. A repository with no code or test
  toolchain yet gets a package skeleton and test setup proposed in the plan
- A lock file in the project directory (`uv.lock`, `poetry.lock`, `pdm.lock`, `pylock.toml`,
  `Pipfile.lock`), or requirements files with every requirement pinned with `==`: the dependency audit
  reads only those, and a project that declares dependencies without one is recorded as not run (`no lock
  file`). A project
  that declares no third-party package at all (a standard-library script, a Lambda function on the
  runtime's packages) needs none

## The specification

Every run starts by finding the project's specification (`spec-layout.py detect`): `specification/`,
`docs/specifications/` or `docs/SPECIFICATION.md`, or a file elsewhere that you confirm when detect names
it as a candidate. The skill follows it as written and extends it in place, in its own layout and
format: a requirement it lacks becomes a new item with the next free ID, and an item the change must
alter or reverse is changed or struck through, never silently. Only a project with no specification
gets a first one in `specification/`, derived from the existing code. Every specification file the
change adds or changes is drafted under `ai-planning/<slug>.spec/`, recorded in the plan's
`## Specification changes` with the draft's digest, and written into place first after your `approve`;
the last wave then brings the living documents and the generated traceability report in line with the
code. The `spec-handling` skill does this work: see [specification.md](specification.md).

## How a run goes

1. Ingest: the items and every interface they rely on (event envelopes, table items, error codes, shared
   modules), the toolchain and the Lambda runtime it targets, two neighbouring modules, and the
   documentation of every library and AWS API the design calls
2. Plan: `ai-planning/<slug>.plan`, with every module, function and handler described in prose and no
   Python. Each new dependency names its version and where the version comes from: the specification,
   the project's lock file, or the plan's own choice
3. Analysis gate: `spec-trace.py plan` and `spec-layout.py check`, then a self-review of pattern fit,
   boundaries (every external input parsed into a model, every failure mapped to the item's error code),
   idempotency, AWS clients, observability, testability, dependencies and scope, and the dependency check
   of every new dependency (see "The dependency check at plan time")
4. Your `approve`
5. Implementation in waves, test first. The implementing subagents start from the security defaults of
   the skill's
   [`python-practices.md`](../../skills/implementing-python-from-spec/references/python-practices.md)
   (section 12), the form of the review's security rules that applies while code is written. After each
   wave the project's full gate runs, typically
   `uv run --locked ruff format --check .`, `ruff check`, `mypy` and `pytest`, or the project's own
   wrapper or CI command. `--locked` makes a stale lock fail instead of being rewritten
6. Verification of each item, `spec-trace.py code`, the artifact build for each touched Lambda function or
   agent, and an import and entrypoint smoke check with stubbed AWS clients. What only a deployed system
   can show is listed as "needs runtime verification". `spec-trace.py code` also fails every file changed
   against `HEAD` that no task owns and that is not under `ai-planning/` (`unowned-change`): a write
   outside the plan is an amendment you approve, never a ruling the skill makes alone
7. Review through `reviewing-python-changes`: its lens reviewers apply
   [`reviewing-python-changes/references/review-lenses.md`](../../skills/reviewing-python-changes/references/review-lenses.md)
   and
   [`reviewing-python-changes/references/review-dimensions.md`](../../skills/reviewing-python-changes/references/review-dimensions.md),
   its security reviewer
   [`reviewing-python-changes/references/security-dimensions.md`](../../skills/reviewing-python-changes/references/security-dimensions.md),
   and the dependency audit runs after the quality gate. Blockers and Majors are fixed; a vulnerable
   dependency the change introduced is fixed with the version change its finding names, unless you
   accept the advisory
8. The quality gate again, then a documentation sync
9. The report, with each gate command, the build, the smoke check and the dependency audit

## What asks first

The gate asks before each of these, before and after plan approval:

- Package installs: `pip`, `pip3`, `pipx`, `uv`, `poetry`, `pdm`, `conda` and `pipenv` `install`, `add`
  and `inject`, and `--with` options
- Lock file changes: `uv lock`, `uv sync`, `remove` and `update`, `pip-compile`, unless run with
  `--locked`, `--frozen`, `--check` or `--dry-run`
- `sam`, `cdk` and `serverless` deploy, destroy, bootstrap, watch, sync, delete and remove commands
- Every mutating `aws` CLI call
- An import of advisory data, `dependency-audit.py refresh --ecosystem pypi --from <path>`: the copy it
  publishes decides what the dependency audit can find (see "The advisory data"). A download (`refresh
  --ecosystem pypi`), the plan's dependency check and the audit itself are not asked

Read-only `aws` calls, `events test-event-pattern` and `route53 test-dns-answer` run without asking. In a
gated session the rules of all five implementing skills apply together.

A package the plan does not name, a lock change it does not describe, or a substitute for a package that
failed to install, is a question for you.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate"). The plan's dependency check and a download or import of advisory
data are not denied: they write only to the advisory cache under `~/.local/state/implement-from-spec/`,
outside the project, and the import asks, as above. When the gate asks about an install or lock change the approved
plan names, its prompt is the confirmation, and the skill does not ask again in the conversation. A step
you decline (or one a non-interactive session cannot answer) is not retried and gets no substitute: the
tasks that need it are marked `blocked` in the ledger with the command for you to run, the others are
finished, and the report's status is "verification incomplete (<command> denied)" (contract section 12).

## The security reviewer

Security has its own reviewer on every Python review and every fix round. It is a subagent on the
`code-reviewer` reviewer skill, always on Opus whatever the risk tier, dispatched in the same message as
the lens reviewers, so it adds cost but no wall-clock time. It owns the Safety/security dimension for
every file of the change (Python sources, configuration, and dependency, lock and installer files),
including the security consequence of a defect that a lens reviewer's check describes: the lens reports
the mechanics (a broad `except`, an `assert`, a string-built DynamoDB expression), the security reviewer
the consequence under its own rule, and the review merges the two into one finding. A lens reviewer that
notices a security problem reports it as a one-line pointer.

Its rules are
[`reviewing-python-changes/references/security-dimensions.md`](../../skills/reviewing-python-changes/references/security-dimensions.md),
a catalogue for CPython 3.11 to 3.15 (the releases the Python developer guide listed as supported on
2026-11-25), AWS Lambda, Strands agents on AgentCore, Django, Flask, FastAPI and other web services,
libraries and scripts, and their dependency, lock and installer files, its facts read on 2026-11-25. Its
103 rules sit in 14 groups: injection; deserialisation and data binding; XML; cryptography, randomness,
TLS and secrets; authentication, sessions and tokens; authorisation; the web surface and framework
configuration; files, resources and denial of service; input validation, outbound requests, logs and
failure; platform mechanisms (in-process sandboxes, `assert`, import paths and start-up hooks, `ctypes`,
request state in globals); AI agents and model output; the AWS SDK and Lambda; known-vulnerable usage
(the code patterns behind named CVEs in the interpreter and in widely used libraries); and dependencies
and the build supply chain (the `PY-DEP` rules). Each finding cites its rule: a `PY-SEC-nn` rule for code
and configuration, or a `PY-DEP-nn` rule for dependencies, indexes, lock files and installers.
`PY-SEC-01` to `PY-SEC-11` keep the numbers they had as group 8 of `review-dimensions.md`, so earlier
findings still resolve.

How it works:

- It lists the entry points the change adds or alters first (Lambda handlers and their events, HTTP
  routes and views, message and stream consumers, scheduled jobs, agents and the tools they hold, MCP
  servers, deserialisers and parsers, configuration and dependency files), then traces each untrusted
  value from its source to every sink as file and line steps, and looks for the guard (a middleware, a
  framework default, an authoriser, a pydantic model, a caller that never passes the value) before it
  reports
- It reads the interpreter release (`requires-python`, `.python-version`, a `FROM python:` or Lambda
  base image tag, a Lambda runtime, a CI pin) and the locked library releases before applying a rule
  whose answer depends on them. The interpreter is not in the dependency audit's inventory, so for the
  standard-library rules the release the repository pins is part of the finding
- It never looks anything up: it opens no page, runs nothing and never sees the dependency audit's
  report. A finding that depends on a version, a default or a date the repository does not show is
  marked `unsure: verify against the docs`, and the main conversation checks the documentation before
  it accepts the finding
- When the code calls an API that a rule ties to a named CVE, the finding names the distribution by its
  PyPI name, so the review can merge it with the audit's entry for that package: one finding, with the
  code path as evidence
- The catalogue keeps no list of minimum versions, which would be out of date within weeks: versions are
  the audit's. It names a fixed release only inside a rule about a named CVE, as history, and keeps dated
  support tables for the interpreter, frameworks and SDKs only for `PY-DEP-02` (a release line past its
  support)
- Your project's rules, specification and approved plan choose among safe forms and override the
  catalogue's conventions; they cannot waive a hazard. Only you, in the conversation, can defer a
  security Blocker or Major

Each group of the catalogue carries a trigger, and the reviewer reads only the groups whose trigger the
change, the dependency files, the configuration or the code the change reaches meets; a trigger it
cannot rule out (a framework or meta-package whose dependencies it cannot see, a handler whose event
source is outside the repository) counts as met, and a skipped group whose trigger a traced path reaches
is read after all. Four groups always apply: injection; cryptography, randomness, TLS and secrets; files,
resources and denial of service; and input validation, outbound requests, logs and failure. The
reviewer's `Groups:` line gives every group's outcome: a finding count, `clean`, `not applicable (<the
trigger not met>)`, `unsure (<the missing context>)` or `needs runtime verification (<the check>)`. A
group left `unsure` or needing runtime verification, or a `Groups:` line that leaves a group out, makes
verification incomplete.

Ask to "skip security" and the security reviewer is not dispatched: the report names the dimension as
skipped at your request and verification is incomplete, because no other reviewer covers it. The
dependency audit still runs.

## The dependency audit

Every Python review checks the project's dependencies for known vulnerabilities. After the project's
quality-gate commands, the main conversation runs one command:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" audit --snapshot <snapshot DIR>
```

It is the same script, with the same gate, records and report as the Java review's dependency audit
([java.md, "The dependency audit"](java.md#the-dependency-audit)): the review's preparation registers the
gate `dependency-audit` as not run before any reviewer starts (`Dependency audit: pending`), only the
audit's own result replaces that record, each attempt records the gate as pending again before it
starts, and a pass or a fail also records its coverage as the gate `dependency-audit-coverage`. A review
whose audit was forgotten, crashed or could not run ends "verification incomplete", never clean. The
audit runs again in every fix round, on the new snapshot, within the same limit of 480 seconds for the
whole audit (`--total-timeout`), the wait for another refresh's lock and the download included.

### How it works

1. **The inventory is read, never resolved.** The audit reads the project's lock and pin files as data.
   No installer, resolver or build backend runs, and nothing from the project is imported or executed:
   building a source distribution, or running a `setup.py`, runs the repository's code, and the
   repository under review is untrusted. Which files it reads:
   - Lock files in any directory of the project (virtual environments, installed or vendored package
     trees, caches and build output left out), each its own module: `uv.lock` (version 1), `poetry.lock` (lock-version
     1.x or 2.x), `pdm.lock` (lock_version 4.x), `pylock.toml` and `pylock.<name>.toml` (PEP 751,
     lock-version 1.x) and `Pipfile.lock` (pipfile-spec 6)
   - Requirements files: `requirements*.txt`, `*-requirements.txt`, `*_requirements.txt` and
     `requirements/*.txt` in any directory of the project, and every file they name with `-r` or `-c`,
     relative to the naming file as pip reads it, and only when it is one of the candidate's files (never
     a git-ignored file or anything inside `.git`). A requirement counts only
     when it is pinned to one version: exactly one `==<version>` clause without `*`, or `===<version>`.
     `--hash` and `--config-settings` (`-C`) are allowed after a requirement, any other option there
     makes the file not read whole, as pip refuses it, and global options such as `--index-url`,
     `--extra-index-url`, `--find-links`, `--trusted-host` and `--require-hashes` are skipped with their
     values wherever they stand on a line (the security reviewer's `PY-DEP` rules judge them); of the
     `-r` and `-c` on one line the first `-r`, else the first `-c`, is followed, as pip does. A requirement
     left unpinned that a constraint file of the same install pins with `==` and no marker is covered by
     that pin; a constraint to a URL, a VCS or a local path for a package the install installs makes it
     `packages not evaluated`, since pip then takes the package from there; a file two installs reach is
     judged in each. One package at one version is one entry
   - Declarations, which are never a module but decide coverage: `pyproject.toml` (`[project]`
     dependencies and optional dependencies, `[dependency-groups]`, and Poetry's, PDM's and uv's
     dependency tables), `setup.cfg` (`install_requires`, `extras_require`), `setup.py` (never run: the literal
     `install_requires` and `extras_require` lists of its one `setup()` call are read with Python's `ast`,
     anything built in code is unknown), setuptools' dynamic `dependencies = {file = [...]}` files, read as
     requirement lines, and `Pipfile` (every package category). A `pyproject.toml` that does not parse is
     `declarations not read`. A declaration is covered by
     the lock and pin files of its own directory, or of the nearest directory above it that holds any (a
     uv or Poetry workspace locks its members at its root), and each dependency it declares must be
     listed there: the main dependencies always, one an environment marker narrows included, the groups'
     and extras' only against a lock file, which locks every group, since a requirements file may be
     compiled from the main set alone. Only the project of the declaration's own directory and the
     workspace members of the lock file covering it count as listed by their own name. A declaration the
     audit cannot read is `declarations not read` unless a lock file that locks every group covers it
   - Each lock or pin file is one module of the report. A `pyproject.toml` or `setup.cfg` that configures
     tools only (formatter or linter settings) does not make the project a Python one
   - No dependency file at all: Python sources (`.py` files outside virtual environments, installed or
     vendored package trees, caches and build output) with no Python lock, pin or dependency declaration
     file anywhere in the repository mean a project that declares no third-party package. Its PyPI part
     is complete with nothing to match and passes, and the status line's coverage reads `coverage
     complete (no third-party Python dependency declared)`. No advisory data is needed, so none is
     downloaded: the status line reads `advisory data not needed (no package to match)` and the report
     `Data: none needed (no package to match)`, unless a copy of the PyPI data is already cached, which is
     then named without a refresh; the case never downloads PyPI data. Beside a Java build the PyPI side
     adds only the coverage note, `coverage complete (PyPI: no third-party Python dependency declared)`,
     and no PyPI `Data:`, `Resolution:` or `Inventory:` line, so the report otherwise reads as a Java-only
     audit's; when the Java side is partial, its partial coverage stands with no note. An import of a package nothing declares, and a package the Lambda runtime or a layer
     provides, are the security reviewer's to find (`PY-DEP-10`, `PY-DEP-11`); when the change removed
     every Python dependency file the base had, the `base:` part says how many dependencies the base
     listed, and the removal is the reviewer's to judge (`PY-DEP-04`)
   - Which ecosystems: the files in the project directory decide, as its build files decide between Maven
     and Gradle. Python lock, pin or declaration files, or Python sources with no dependency file, make
     the PyPI audit run; a `pom.xml` or Gradle
     build makes the Maven audit run; a directory holding both is audited for both, each with its own
     data, and coverage is complete only when both are. When the project uses one of them only, name it
     in the conversation: the skill passes `--ecosystem pypi` (or `maven`), and that ecosystem is audited
     alone
2. **Matching** against a local copy of the OSV PyPI export (below), with PEP 440's version ordering,
   package names compared in their normalised form (PEP 503: `Demo_Http` and `demo-http` are one
   package). Environment markers are never evaluated: a package locked for one platform, one Python
   release or one extra counts everywhere, because a marker narrows where a package installs, not whether
   the project ships it. Every group, the development groups included, is in the inventory, and every
   entry counts as shipping
3. **Comparison with the review's base revision.** The base revision's own lock, pin and declaration
   files are read the same way, from git, module by module: an occurrence is the change's when its
   module, package and version are not in the same module at the base. A module of the base that could
   not be read whole leaves only its own entries "attribution unknown"; the base's other modules still
   attribute theirs. A base with no Python dependency file has none of the candidate's occurrences, which
   are then the change's. Without a base every entry is "attribution unknown" and counts as the change's
4. **The report**, in the Java audit's form: the status line; one `Data:` line per ecosystem used; for
   PyPI a `Resolution:` line naming the files read, the project directory, the candidate, the modules with
   their coverage, and the base; the inventory statement; then the five blocks *Introduced by this
   change*, *Attribution unknown*, *Accepted by the user*, *Pre-existing* and *Could not be evaluated*

A commit-range review audits the range's end commit, and its base, read from git with `git ls-tree` and
`git cat-file`: nothing is written out or checked out, and a link is followed only inside the revision.
A pasted diff has no project, so the audit does not run, and a `--files` review stops before it runs when
its snapshot leaves out a lock, pin, declaration or `constraints*.txt` file, or a file under
`requirements/`, and otherwise reads partial (see "When the audit does not run").

The PyPI lines of a report read:

```
Resolution: PyPI: lock and pin files uv.lock, requirements-dev.txt read as data (no tool runs); project: <dir>; candidate: the working tree; modules (2, coverage complete): uv.lock, requirements-dev.txt; base: read from <revision>
- module requirements.txt; pypi:demo-http==1.0.0 (pin); path: requirements.txt > demo-http==1.0.0; advisories: GHSA-xxxx-xxxx-xxxx (PYSEC-2099-1, CVE-2099-1001) HIGH Blocker [both]; fix reported: 1.2.0
- module uv.lock; pypi:demo-yaml==5.3 (lock: dev); path: uv.lock > demo-yaml==5.3; advisories: PYSEC-2099-2 (CVE-2099-1002) CRITICAL (from CVSS 3.1 9.8) Blocker [range]; fix reported: 5.4
```

The scope is `lock`, `pin` or `constraint`, followed by the groups, extras or sections that list the
package when the file names them. An entry lists at most 10 advisories, the most severe first, then `and
<n> more advisories (the JSON report lists up to 100)`, and a block at most 500 entries, then `- <n> more
entries, not listed here: the JSON report lists up to 5000`; the JSON report records what it left out
(`advisories_not_listed`, `not_listed`), and the status line's counts are always of every entry. The `base:` part reads `none given (every entry is attribution
unknown)`, `read from <revision>`, `read from <revision>; <n> of its modules not read whole, whose
entries are attribution unknown`, `read from <revision>: no Python lock, pin or declaration file there`,
or `not read from <revision> (<category>): every entry is attribution unknown`; for a project that
declares nothing whose base did, it ends `; the base listed <n> dependencies in <m> modules, and the
change removed every Python dependency file`. A PyPI side whose files list no package to match loads no
advisory data; when no side loaded any, the status line reads `advisory data not needed (no package to
match)` for a complete result and `advisory data published none (no package to match)` for a partial
one. With two ecosystems the status line counts both,
names both dates as `advisory data published <date> (Maven), <date> (PyPI)`, and a partial remedy names
its side (`the PyPI dependencies: ...`).

The review snapshot keeps both reports of each attempt, `gates/dependency-audit-<n>.txt` and
`input/dependency-audit-<n>.json` (schema `ifs-dependency-audit/1`, which binds the snapshot id, the
attempt, the dataset's digest and the SHA-256 of every lock, pin and declaration file read). No advisory
text and no free text from a lock file reaches a report: only identifiers, package names and versions that
pass a grammar, severity words, dates, counts and escaped paths.

To audit a project outside a review, ask Claude to run the same script with `audit --repo <path>
[--base <revision>]`: the report goes to standard output, and without `--base` every entry is
"attribution unknown" and counts against the result.

### The advisory data

The data is the OSV project's export of PyPI advisories,
`https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip`, the same host as the Maven export,
which carries PyPI Advisory Database (`PYSEC-`), GitHub Advisory Database (`GHSA-`) and OpenSSF malicious
package (`MAL-`) records; withdrawn advisories are skipped. Every PyPI `Data:` line carries the
attribution `OSV, PyPI Advisory Database and GitHub Advisory Database, CC-BY 4.0; OpenSSF Malicious
Packages, Apache 2.0`. Source, read 2026-11-25: "Data sources" (https://google.github.io/osv.dev/data/).

- It is kept in `~/.local/state/implement-from-spec/advisories/pypi/`, below the Maven cache, with its
  own dataset, metadata and lock, and every rule of the Java audit's cache applies to it unchanged:
  found from your home directory alone, readable only by you, refused when it resolves inside the
  repository under audit, is a link or belongs to another user, used as it is for 24 hours after a
  server check, refreshed with a conditional request from one fixed HTTPS address with no redirect
  followed (at most 128 MiB within 120 seconds), used with a note for up to 7 days when the server
  cannot be reached, and not used after that ([java.md, "The advisory data"](java.md#the-advisory-data))
- A PyPI dataset must hold at least 10,000 usable advisories, downloaded or imported (the export held
  26,440 on 2026-11-25, 12,095 of them malicious-package records, so the minimum stays below the count of
  the others), and no two different records under one id. As for Maven, the minimum does not stop a copy
  built on purpose: before you rely on a clean result, read its `Data:` line, `download` from the address
  above or `import` of a copy you made yourself
- In a gated session the approval gate denies the tool calls that would write the cache directly (the
  `pypi/` directory lies inside the protected `advisories/`), and `refresh --from` asks you first, before
  and after plan approval; a review whose data was imported says so for the human reviewer. Outside a
  gated session, and against another process running as your user, nothing protects the cache
- Nothing authenticates the export beyond HTTPS and its publisher

### What leaves your machine

The plugin's own code makes one kind of network request: an anonymous HTTPS download of each public
export it needs, at most once a day, with the user agent `implement-from-spec-dependency-audit` and,
after the first download, the date and tag the server gave the copy you hold. A PyPI side with no package
to match downloads nothing, so a project that declares no third-party package, a Java project with a
helper script among them, makes no PyPI request. Nothing about the project
is sent: no package name, no file, no version. Nothing runs: the PyPI audit starts no installer and no
other program, so, unlike the Java audit, nothing it does can reach the network on the project's behalf.

### What the inventory is, and what an entry means

- The inventory is every package version the lock files and the pinned requirements files list, in
  every group, extra and environment marker. Not in it: the project's own packages (its workspace
  members), what a package from a VCS, a URL or a local path holds (each is listed under *Could not be
  evaluated*), vendored or copied code, packages a Lambda layer or a container image provides, and the
  interpreter itself
- An entry means that a version matching an advisory is in the inventory, not that the vulnerable code
  is called. The audit does no reachability analysis; the security reviewer's usage findings are the only
  evidence that the code is called, and the review words a dependency finding that way
- A result with no entry means "no matching advisory in this dataset", never "no vulnerabilities"
- The class comes from the advisory's severity word: CRITICAL or HIGH, or a malicious-package record, is
  a Blocker; MODERATE (also written MEDIUM) a Major; LOW a Minor; anything else a Major marked unsure.
  PyPI Advisory Database records carry no severity word, so a `PYSEC-` record takes the strongest word of
  the GitHub advisories it is an alias of (`HIGH (from GHSA-...)` on the report line), else the rating of
  its CVSS 3.0 or 3.1 base score, computed by the audit with the FIRST 3.1 equations (9.0 or more
  CRITICAL, 7.0 HIGH, 4.0 MEDIUM, else LOW, shown as `CRITICAL (from CVSS 3.1 9.8)`); a record with
  neither, a CVSS 4.0 vector only for one, is a Major marked unsure
- Advisories of one occurrence that are aliases of each other (the PyPI export carries most
  vulnerabilities twice, as a `PYSEC-` and a `GHSA-` record) are one entry: the id shown is the member
  that decides the class, the others follow as its aliases, and accepting any of their ids accepts the
  entry
- An advisory range with a bound PEP 440 cannot parse, or a `SEMVER` range, is "not evaluable" for the
  package (basis `not evaluable`), a Major marked unsure, never unaffected. A local version
  (`2.5.1+cpu`) is matched as itself and as its public version (`2.5.1`), and every advisory it matches
  is marked unsure, because a local build may carry a backported fix; its class is not lowered
- The gate fails when an entry introduced by the change, or one whose attribution is unknown, is a
  Blocker or a Major you have not accepted, as for Java. *Pre-existing* entries stay outside the
  recommendation, with an escalation note on a Blocker, unless the security reviewer shows that the
  change newly calls the vulnerable code
- `fix reported: <version>` is the version the advisories name, matched again against every advisory for
  that package; it is not a claim that the release exists or is the lowest safe one

The status line, the first line of every report, and the exit status are the Java audit's:

```
Dependency audit: pass (introduced: 0 Blocker, 0 Major, <n> Minor; attribution unknown: <n>; accepted: <n>; pre-existing: <n>; <n> dependencies in <n> modules; advisory data published <date>; coverage complete)
Dependency audit: fail (the same fields, the last coverage complete or coverage partial (<category>: <what to do>))
Dependency audit: not run (<category>: <what to do>)
Dependency audit: off (configuration: <source>)
Dependency audit: pending
```

Exit status: 0 pass or off; 2 fail; 69 not run; 3 the snapshot no longer matches the tree; 64 a usage
error, an invalid setting included; 1 an internal error. The review report's `Quality gate:` line ends
with the audit's status line, character for character. Every line of the four blocks becomes a finding
(rule `PY-DEP-01`, source `dependency audit`) or a pre-existing note; none is dropped, and a partial result
keeps what it found.

### Accepting an advisory

Only you accept an advisory, in the conversation: name its id (`GHSA-...`, `PYSEC-...`) or its CVE alias,
for example "accept GHSA-xxxx-xxxx-xxxx for this change". The skill runs the audit again with
`--accept <id>` for every advisory you have accepted so far; the new result supersedes the failed one, the
entry moves to *Accepted by the user*, and its finding is recorded as deferred with your words. The skill
never accepts one on its own judgment. An acceptance holds for the review and its fix rounds and is saved
nowhere, so the next review reports the advisory again. An accepted id that matches no entry is listed
under *Could not be evaluated*.

### The `dependency_audit` setting

The setting is the Java audit's, one value for both ecosystems: `on` (default) or `off`, in `/config` the
plugin's "Dependency audit" row. Only you switch it off, in your saved plugin options; an `off` that
arrives through the environment, or from a settings file inside the repository under audit, is not
obeyed and is recorded as not run (`setting not obeyed`). To leave the audit out of one review, ask in the
conversation ("skip the dependency audit"): the report then says verification incomplete. The full rules:
[java.md, "The `dependency_audit` setting"](java.md#the-dependency_audit-setting).

### Machines without internet access

Download `https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip` on a machine that can reach
it, copy the file across, and import it:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" refresh --ecosystem pypi --from <path>/all.zip
```

Plain `refresh` and `refresh --from` stay the Maven forms. `--from` also takes a directory of the export's
JSON records. In a gated session Claude Code asks you before the import (see "What asks first"). An import
passes the same checks as a download, the 10,000-advisory minimum included, counts as checked on the day
you make it, and is then used as a download is: 24 hours without contacting the server, up to 7 days with
a note. When you run the script yourself, `--cached-data` keeps it from contacting the server at all.
Nothing else is needed offline: the PyPI audit reads files and runs no tool.

### When the audit does not run

The status line names the category and the one action that remedies it, with your project's paths filled
in; the gate is recorded as not run and verification is incomplete. The skill never replaces a not-run
audit with another scanner, `pip-audit` included, or a web lookup: that result would not be this gate's.

Four categories stop the PyPI audit as not run, with no partial result:

- `interpreter`: the Python dependency audit needs python3 3.11 or later, which reads TOML lock files
  (tomllib), and this is python3 `<x.y.z>`: run the audit with python3.11 or later. Only a project that
  holds a TOML lock file, a `Pipfile` or a declaring `pyproject.toml` stops so; one of requirements
  files, `Pipfile.lock` or `setup.cfg` alone is audited on 3.9 and 3.10. With two ecosystems
  the Maven side still runs, and the PyPI side is listed under *Could not be evaluated* as `the PyPI
  dependencies were not audited: interpreter: ...`, so the result is incomplete until a newer python3 runs
  it. Without `tomllib` a `pyproject.toml` is judged by its table headers: a `[project]`,
  `[dependency-groups]`, `[tool.poetry...]` or `[tool.pdm...]` table, a `[tool.uv]` `dev-dependencies`
  or `sources` key, or a line it cannot judge (a quoted key, an inline table at `tool`, a file of more than
  100,000 lines) declares, and a file of other tool tables alone does not, so a Java project with
  formatter settings is audited as a Java one only
- `no Python dependency file`, with `--ecosystem pypi` only: no Python lock, pin or dependency declaration
  file in `<dir>`: name the directory that holds one with --project-dir. Without the flag, a directory
  with neither Java build files nor Python sources is `no build file`: no pom.xml, no Gradle build and no
  Python lock, pin or dependency declaration file in `<dir>`: name the directory that holds one with
  --project-dir. A dependency file in a subdirectory (a `tools/requirements.txt`, say) is audited as a
  module of the project; one outside the directory `--project-dir` names is not that project's
- `too many Python dependency files`: more than 200 lock, pin and declaration files or 64 MiB in all, at
  `<file>`: audit a smaller project directory with --project-dir. The files read to decide whether the
  project is a Python one, and to record the digests of its inputs, count too, each file once
- `time limit`: the audit reached its total limit while it read the Python dependency files (or while it
  matched the dependencies against the advisory data, for either ecosystem): raise --timeout, the limit of
  each build-tool run, or --total-timeout, the limit of the whole audit

Every other gap makes the result partial: the vulnerabilities found are still reported and still fail
the gate, the status line is then `fail (...; coverage partial (<category>: <remedy>))`, and a result
with nothing found reads `not run (<category>: <remedy>)`, never `pass`. A project that declares no
third-party package has no gap: it passes (see "How it works"). The first gap names the status
line's category; *Could not be evaluated* lists every one (up to 20, then how many more):

- `no lock file`: `<files>` declares (or declare) dependencies and no lock or pin file covers them: commit
  a lock file (uv lock, poetry lock, pdm lock, pipenv lock, or pip-compile with every requirement pinned),
  then run the audit again
- `lock file empty`: the lock and pin files list no package while `<files>` declare dependencies:
  regenerate the lock file, then run the audit again
- `lock file out of date`: `<file>` declares `<n>` dependencies that `<lock and pin files>` do not list:
  regenerate the lock or pin file (uv lock, poetry lock, pdm lock, pipenv lock, or pip-compile with every
  requirement pinned), then run the audit again. *Could not be evaluated* names up to three of them. When
  a missing main dependency carries an environment marker and only pin files cover it, the remedy adds
  `; a dependency an environment marker narrows needs one pin file per platform or a lock file that
  records every platform` before `, then run the audit again`
- `declarations not read`: `<file>` declares dependencies this audit cannot read (`<why>`): declare them
  as literal lists in pyproject.toml or setup.cfg, or commit a lock file (uv lock, poetry lock, pdm lock,
  pipenv lock, or pip-compile with every requirement pinned), then run the audit again. `<why>` is
  `setup.py builds them in code`, `it is not valid Python`, `a dynamic field this audit does not read`,
  `a file it names is not read`, `a field of an unexpected type`, `setup.cfg names them with file: or
  attr:` or `it is not a valid setup.cfg`. A `pyproject.toml` that does not parse reads `<file> cannot be
  read as a declaration file (it is not valid TOML): fix it, then run the audit again`, whatever covers it
- `lock file of another project`: `<file>` does not hold the project its pyproject.toml names: run
  `uv lock` in the project directory, then run the audit again (checked for `uv.lock` only)
- `lock file not read`: `<file>` cannot be read as a `<uv|Poetry|PDM|Pipenv|pylock.toml>` lock file
  (`<why>`): regenerate it with the tool that wrote it, then run the audit again. `<why>` is `it is not
  valid TOML`, `it is not valid JSON`, a lock version this audit does not read (`its version is not 1,
  the uv.lock version this audit reads`, and the same for the other formats), or `its <section> section
  is not a table of packages`
- `packages not evaluated`: `<name>` in `<file>` cannot be checked against the advisory data (`<why>`):
  pin it to a released version from an index, or review it yourself; the result stays partial while it is
  there. `<why>` names the source by a fixed phrase, never the lock file's own text (`from git`, `from hg`,
  `from svn`, `from bzr`, `from a URL`, `from a file`, `from a path`, `from a directory`, `from a VCS`,
  `from an archive`, `an editable install`, `a virtual project`, and `from an unrecognised source kind`
  for any other kind, a Poetry source type outside git, directory, file and url included), or
  `no version`, `not pinned with ==` (`Pipfile.lock`), `a package without a valid name`, `a version PEP
  440 cannot parse`, and for a constraint file's line about a package the install installs `a constraint
  to a URL, a VCS or a local path` or `a constraint this audit cannot read`
- `lock file too large`: `<file>` lists more than 100000 packages: audit a smaller project; or the lock
  and pin files list more than 100000 packages in all, at `<file>`: audit a smaller project directory with
  --project-dir
- `requirements not pinned`: `<name>` in `<file>` (or line `<n>` of `<file>`) is `<why>`: pin every
  requirement with == (pip-compile writes such a file) or commit a lock file, then run the audit again.
  `<why>` is `not pinned to a version`, `a version range`, `a URL, a VCS or a local path`, `an editable
  install (-e), which names no version`, `pinned with === to a version PEP 440 cannot order`, `pinned to
  a version PEP 440 cannot parse`, `names an environment variable, which is not expanded here` or `not a
  requirement this audit can read`
- `requirements not read`: line `<n>` of `<file>` holds an option this audit does not read (on its own
  line, or after a requirement, where pip reads only `--hash` and `--config-settings`): remove it or
  commit a lock file, then run the audit again
- `include not followed`: the requirement (or constraint) file on line `<n>` of `<file>` names a URL, a
  path outside the repository or nothing (or names a file that is not one of the candidate's files, such
  as a git-ignored file or one inside `.git`, which is never read; or nests deeper than the audit follows,
  16 levels): name a file inside the repository, then run the audit again
- `requirements file too large`: `<file>` has more than 100000 lines: split it, then run the audit again
- `file not read`: `<file>` is missing, is a link that leaves the repository, is not a regular file of at
  most 16 MiB, is over 16 MiB, or is a chain of links longer than the audit follows: replace it with a
  regular file inside the repository, then run the audit again; or `<file>` is not UTF-8 (or names an
  encoding other than UTF-8): save it as UTF-8, then run the audit again
- `snapshot does not cover the build`, for a `--files` review: take a snapshot of the working tree or of
  a commit range instead

The advisory data categories are the Java audit's, with the PyPI remedies: `no advisory data` and
`advisory data too old` end with run `dependency-audit.py refresh --ecosystem pypi` with network access,
or `refresh --ecosystem pypi --from <zip>` with a copy of the OSV PyPI export; `advisory data missing`,
`advisory data unreadable`, `advisory data too small` (fewer than the minimum of 10000) and `advisory data
digest mismatch` end with run refresh --ecosystem pypi. `advisory cache refused`, `advisory cache busy`,
`time limit`, `pasted diff`, `revision cannot be read`, `setting not obeyed`, `attachment failed`, `gate
not recorded` and `registration failed` read as the Java page lists them
([java.md, "When the audit does not run"](java.md#when-the-audit-does-not-run)).

### Limits

- **No reachability.** An entry says a matching version is in the inventory; only the security
  reviewer's usage findings show that the vulnerable code is called
- **One dataset.** The OSV PyPI export; a clean result means "no matching advisory in this dataset"
- **Lock files as written.** The audit reads what the lock file says, not what is installed or what the
  declarations would resolve to today: it checks that each declared dependency is listed by name, not
  that the version locked satisfies the declared range (the security reviewer's `PY-DEP-04` does), and a
  `uv.lock` must hold the project its `pyproject.toml` names. A requirements file under another name than the patterns above
  is read only when a requirements file names it with `-r` or `-c`
- **Markers are not evaluated.** A package locked for another platform or another Python release is
  reported too; accept its advisory when it never installs where you deploy
- **Every directory of the project.** Lock and pin files anywhere in the project directory are read,
  docs and tooling requirements included, since each is installed somewhere; to audit one service of a
  larger repository alone, name its directory with `--project-dir`
- **What is outside the inventory.** Build-time requirements (`[build-system] requires`), the
  interpreter, a Lambda layer, a container image's packages, native libraries inside wheels, and code
  copied into the repository; the security reviewer's `PY-DEP-02`, `PY-DEP-08` and `PY-DEP-11` flag some
  of it
- **Patched and local builds.** A local version is reported, marked unsure; accept the advisory when the
  build carries the fix
- **Authenticity.** Nothing authenticates the export beyond HTTPS and its publisher, and the minimum
  advisory count does not stop a copy built on purpose (see "The advisory data")

## The dependency check at plan time

Before it asks for your approval, the implementing skill matches every new dependency the plan names, at
the version the plan states, against the same advisory data, in one call:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" check pypi:<name>==<version> ...
```

Each argument is `pypi:` (any case), a valid PyPI name and exactly `==` with a PEP 440 version; anything
else is a usage error (exit 64). It reads no lock file, resolves nothing, writes only to the advisory
cache, outside the project, so it runs before approval, and it needs no TOML, so it runs on python3 3.9
too. It prints `Dependency check: <n> of <m> coordinates match an advisory (named coordinates only:
transitive dependencies are not seen)`, one line per argument as you typed it (`pypi:<name>==<version>:
no matching advisory in this dataset`, or `<k> matching advisories: ...; fix reported: <version>`) and the
`Data:` line, and exits 0 with no match, 2 with a match and 69 when it could not check. The plan records
each result beside its dependency:

- No match: "no advisory matches this coordinate in the dataset of <date>"
- A match is never resolved silently: a version the specification or the project asked for stays in the
  plan and the match becomes an open question with the reported fix as the recommended answer; a version
  the plan chose itself is replaced by the reported fix, on a `Needs your approval:` line that names the
  match. The rules are the Java skill's ([java.md, "The dependency check at plan
  time"](java.md#the-dependency-check-at-plan-time))
- "not checked", with the reason: no advisory data, the audit switched off, a version the plan does not
  pin, or your request to skip the check. The review's audit covers it after implementation

What a clean check does not show: that the version exists, is maintained or is compatible, or anything
about the package's own dependencies. A vulnerable transitive dependency of a new package is found by the
review's audit, from the regenerated lock file, and fixed in a fix round, as an amendment you approve.

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (snapshot,
change digest, review state, findings fixed, rejected, covered by gate and open, fix rounds,
and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For
Python the checks line names each quality-gate command, the artifact build and the smoke check with their
results, and the review's `dependency-audit` entry as its `Quality gate:` line gives it. The review
skill's own report feeds into it; it is not the final reply.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-python-changes . main..HEAD
```

The arguments are the repository and a git range or a file list, optionally `--plan
ai-planning/<slug>.plan`. A pasted diff works too, without a dependency audit. The skill runs the
project's quality gate and then the dependency audit while the reviewers work, verifies every finding against
the code, sets severity itself, and returns one Blocker, Major, Minor and Nit report with a concrete fix
per finding, opening with the review state block (snapshot, recommendation, verification, approval
required, risk, rollback; see
[external-review.md](external-review.md#the-review-around-it-snapshot-isolation-state-and-fix-rounds)).

## Out of scope

- CloudFormation ([cloudformation.md](cloudformation.md)), CDK apps, also in Python ([cdk.md](cdk.md)),
  and Terraform ([terraform.md](terraform.md))
- A security audit of a whole code base: the security reviewer covers the change and what it makes
  reachable, and the dependency audit matches locked versions against one advisory dataset
- Deploying
