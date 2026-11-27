# Changelog

Versions follow semantic versioning: a major version changes the gate's approval grammar or the
specification input formats, a minor version adds a stack or a check, a patch fixes or updates facts.

## 0.4.0 — 2026-11-25

### Added

- Python security reviewer (decided 2026-11-25, `docs/design-notes.md`, "Python security review"): a
  dedicated Claude reviewer on every Python review and every fix round, the `code-reviewer` skill on Opus
  (`security` in the dispatch manifest), which owns the Safety/security dimension for every file of the
  change, Python sources, configuration and dependency, lock and installer files alike, including the
  security consequence of a defect a lens reviewer's check describes. It works from a new catalogue,
  `skills/reviewing-python-changes/references/security-dimensions.md` (CPython 3.11 to 3.15; AWS Lambda,
  Strands agents on AgentCore, Django, Flask, FastAPI; facts read 2026-11-25): 103 rules in 14 groups,
  injection, deserialisation and data binding, XML, cryptography and TLS, authentication and tokens,
  authorisation, the web surface, files and denial of service, input and outbound requests, platform
  mechanisms, AI agents and model output, the AWS SDK and Lambda, the code patterns behind named CVEs in
  the interpreter and widely used libraries, and the `PY-DEP` rules for dependencies, indexes, lock files
  and installers. It reads the groups whose trigger the change meets (four always apply), gives every
  group's outcome on its `Groups:` line, and looks nothing up: a finding that depends on a version, a
  default or a date is marked "verify against the docs" and checked by the main conversation
- Dependency audit for Python reviews, in `core/scripts/dependency-audit.py`: the project's lock and pin
  files (`uv.lock`, `poetry.lock`, `pdm.lock`, `pylock.toml` and `pylock.<name>.toml`, `Pipfile.lock`, and
  requirements files pinned with `==` or `===`, with the files they name with `-r` and `-c`) are read as
  data, never resolved: no installer, resolver or build backend runs and nothing from the project is
  imported, since building a source distribution runs the repository's code. Every package version, in
  every group and extra, whatever its environment marker, is matched with PEP 440 ordering against a local
  copy of the public OSV PyPI export (PyPI Advisory Database and GitHub Advisory Database records, CC-BY
  4.0; OpenSSF Malicious Packages, Apache 2.0), downloaded at most once a day into
  `~/.local/state/implement-from-spec/advisories/pypi/`, and compared with the base revision's files,
  module by module. The same gates, status lines, report blocks, acceptance and setting as the Java audit;
  `skills/reviewing-python-changes/references/dispatch.json` lists the gate under `required_gates`, so the
  preparation registers it as pending. Declarations without a lock or pin file, an unpinned requirement
  and a package from a VCS, a URL or a local path make the result partial, each with its remedy; Python
  sources with no Python lock, pin or declaration file anywhere in the repository pass with nothing to
  match, `coverage complete (no third-party Python dependency declared)`, undeclared imports and
  runtime-provided packages being the security reviewer's (PY-DEP-10, PY-DEP-11).
  `PYSEC` records, which carry no severity word, take the word of the GitHub advisory they are an alias
  of, else the rating of their CVSS 3.x base score; aliased advisories of one occurrence are one entry; a
  local version is matched as its public version too and marked unsure. A project with both Java build
  files and Python dependency files is audited for both, each with its own data
- `dependency-audit.py`: `audit --ecosystem maven|pypi` audits one ecosystem alone; `refresh --ecosystem
  pypi [--from <zip or directory>]` fills the PyPI cache (plain `refresh` stays Maven's); `check` takes
  `pypi:<name>==<version>` beside `GROUP:ARTIFACT:VERSION`
- `implementing-python-from-spec`: a dependency check at plan time (`dependency-audit.py check
  pypi:<name>==<version> ...`): every new dependency the plan names is matched before approval, and a
  match becomes an open question or an approval line with the reported fix, never changed silently, as
  for Java; security defaults in `references/python-practices.md` for the implementing subagents, the
  generation-time form of the catalogue's rules
- `implementing-python-from-spec/gate_rules.json`: the rule `python-advisory-data-import` asks before
  `dependency-audit.py refresh --from`, for either ecosystem

### Changed

- `reviewing-python-changes`: the Claude stage is four lens reviewers (specification fidelity, failure
  handling, types and design, tests) and the security reviewer; the lens "security and AWS runtime" is
  gone, and its AWS runtime and logging groups (7 and 9) and PY-ARC-03 belong to the failure-handling
  lens. Group 8 of `references/review-dimensions.md` is a pointer to the new catalogue, whose rules
  `PY-SEC-01` to `PY-SEC-11` keep their numbers. The review runs the dependency audit after the quality
  gate, its `Quality gate:` line ends with the audit's status line, and `dependency audit` is a finding
  source (rule `PY-DEP-01`, `references/dependency-audit.md`). Asking to "skip security" leaves
  verification incomplete; the audit still runs
- `dependency-audit.py`: the ecosystem-neutral half (the advisory store, matching, classes, attribution
  and reports) moved to `core/scripts/dependency_audit_osv.py`, and the PyPI inventory and PEP 440 are
  `core/scripts/dependency_audit_pypi.py`, both loaded by path. Java reports are unchanged, except that
  the not-run line of a directory with no build file of any kind, and the usage line of `check`, now name
  the Python files too
- A Java project that also holds Python lock, pin or dependency declaration files is now audited for both
  ecosystems; a `pyproject.toml` that configures tools only does not count, on python3 3.9 and 3.10 too,
  where its table headers decide
- `reviewing-java-changes/references/security-dimensions.md`: JAVA-SEC-35 maps CWE-378 in place of
  CWE-377, which CWE 5.0 deprecated (CWE-379 it mapped already)
- `implementing-java-from-spec/gate_rules.json`: `java-advisory-data-import` no longer matches an import
  naming `--ecosystem pypi`, which the Python rule asks for

### Fixed

- `reviewing-java-changes` and `reviewing-python-changes`: a fix round's re-run of the dependency audit
  now repeats every option the review's first audit run carried (`--accept`, `--profile`, `--build-tool`,
  `--project-dir`, `--timeout`, `--total-timeout` and `--dependency-audit on`), with the same interpreter.
  A round that dropped them could read the audit as `off` or `not run` with the fix left unaudited, even
  though the user had asked for it on the first run

### Known limitations

- The PyPI audit needs python3 3.11 or later (`tomllib`) only to read a TOML lock file, a Pipfile or a
  declaring `pyproject.toml`; on an older interpreter that side is recorded as not run, while requirements
  files, `Pipfile.lock`, `setup.cfg` and the rest of the plugin, the Java audit and `check
  pypi:<name>==<version>` keep the 3.9 minimum. There, a `pyproject.toml` is judged by its table headers,
  so one of tool settings alone leaves a Java project's audit as it was
- The PyPI audit now checks the lock file against the declarations: an uncovered or out-of-date lock file
  (a dependency declared but not listed, a main dependency an environment marker narrows included) is
  reported as `lock file out of date` rather than trusted as written, and a declaration it cannot read (a
  `setup.py` list built in code, a `setup` that is wrapped or rebound or a file that reaches names
  dynamically, the file being read with `ast` and never run, a dynamic field other than setuptools' `file =`
  list, a `pyproject.toml` that does not parse) as `declarations not read` unless a lock file that locks
  every group covers it, whose names it shows are then still compared with that lock file. The check is by name, not by version range. Lock and pin files in every directory under the project directory are modules, not only the
  top; a directory outside the project is still found only by naming it with `--project-dir`
- Environment markers are not evaluated, so a package locked for another platform or Python release is
  reported too
- A `setup.py` that reaches names dynamically (`exec`, `eval`, `globals`, `importlib` and the like) is not
  read, so one that reads its version with `exec(open(...).read())` gives `declarations not read` unless a
  lock file that locks every group covers it

### Security

- The PyPI audit runs nothing of the project: lock, pin and declaration files are read as data, a
  `setup.py` is never run, and a revision's files are read through `git ls-tree` and `git cat-file`
  without being written out
- Lock and pin files are hostile input: a per-run budget of at most 16 MiB a file, 200 files and 64 MiB in
  all, a per-side cap of 100,000 packages or requirements kept, 100,000 packages or lines read from a
  single file, and a deadline checked before each file so the audit ends within one file's reading of
  `--total-timeout`, and the same deadline checked while the dependencies are matched; reports are bounded
  (10 advisories an entry and 500 entries a block in the text report, 100 and 5,000 in the JSON report,
  each cut said where it applies); an option pip does not read, on its own line or after a requirement,
  makes the file not read; a constraint to a URL, a VCS or a path makes the package not evaluated; a file
  is opened without following a link, must be a regular file, and a link, `-r`
  or `-c` is followed only to a file inside the repository (at most 8 links in a revision, 16 levels of
  includes); only UTF-8 is read; versions are parsed by a scanner with no regex and a length cap; every
  package name and version a report prints passes a grammar
- The PyPI advisory data is downloaded from the same host as the Maven export and kept under the
  protected `advisories/` directory, so the gate's protection, the cache checks and the limits apply to it
  unchanged; a PyPI dataset must hold at least 10,000 usable advisories
- Threat model: TM-80 (lock and pin files as hostile input), TM-81 (the audit executing the project's
  code), TM-82 (the PyPI audit reading clean when it is not), data flow 28; TM-71 to TM-79 and data flows
  26 and 27 extended to the second ecosystem and re-cited after the script's split

## 0.3.0 — 2026-11-24

### Added

- Specification handling (decided 2026-11-24, `docs/design-notes.md`): a new skill, `spec-handling`, and
  a new read-only checker, `core/scripts/spec-layout.py`. Every implementing skill now finds the
  project's specification first (`specification/`, `docs/specifications/` or `docs/SPECIFICATION.md`),
  follows it as written and extends it in place, in its own layout and format; only a project that has
  none gets a first specification derived from its code, in `specification/`: an index, functional and
  non-functional item files, and architecture, deployment, feature-list, test-case, traceability
  (generated) and open-question documents. Migration into `specification/` happens only on request.
  The skill also runs on its own (`/implement-from-spec:spec-handling`). Guide:
  `docs/user-guide/specification.md`
- `spec-layout.py` subcommands `detect`, `check`, `digest`, `survey` and `traceability`, and the options
  `--draft`, `--plan`, `--base`, `--spec` (repeatable: a specification kept elsewhere, layout `named`),
  `--id-regex` and `--json`
- `detect` names candidate specification files outside the recognised places; with layout `none` and a
  candidate, the plan asks before any baseline, recommending the candidate as the existing specification
- Plans carry a `## Specification changes` section: one record per item the change adds, changes or
  strikes (or "none"), `deleted` records for a requested migration, and exactly one
  `Draft digest: sha256 <hex>` line from `spec-layout.py digest`. Every specification file the change
  adds or changes is drafted under `ai-planning/<slug>.spec/`, so approving the plan binds the exact
  draft. After approval a first-wave task re-runs the check, copies the draft into place and runs the
  check again; a resumed run after a partial copy passes. Verification, after the sync, runs
  `check --plan --base`. Drafted files are frozen at approval; a last-wave sync task, planned
  whenever the layout keeps a generated `TRACEABILITY.md`, updates only the generated report and the
  living documents the draft does not contain
- `spec-layout.py check` joins the analysis gate and the verification: it fails a draft that no longer
  matches the plan's digest, a difference between the item delta and the plan's records, an ID that is
  no longer defined, a drafted file not written byte for byte, a specification file that matches a
  secret pattern (every text file of a draft is scanned), a draft file that is sensitive
  (`draft-sensitive`) or binary and unnamed (`draft-binary`), a record that is duplicated
  (`record-duplicate`) or names the wrong file (`record-file`), a format defect in the layout the skill
  creates, and a generated traceability report that is out of date
- A repository with more than one recognised specification place fails `layout-ambiguous` until
  `--spec` or the plan's ``Specification root: `<place>` `` line names one. `detect` lists every item
  with its file and line. `--spec` takes existing Markdown files only (exit 2 otherwise)
- A symlink anywhere in the specification places, the traceability report's path and its parents
  included, stops `detect`, `check` and `traceability` with exit 2. The draft digest is computed by
  `core/gate/draft_digest.py`, shared with the approval gate; without it every `spec-layout.py` command
  exits 2
- A plan drafted before specification handling (no `## Specification changes`) still passes: each item
  it changed is a WARN `change-legacy` for the user to confirm, as 0.2.0's contract section 10 required
- Four eval cases for the new behaviour (a project without a specification, an extension in place, a
  post-approval run, and the skill on its own)
- Java security reviewer (decided 2026-11-24, `docs/design-notes.md`, "Java security review"): a second
  Claude reviewer on every Java review and every fix round, the `code-reviewer` skill on Opus, which owns
  the Safety/security dimension for every file of the change, including the security consequence of a
  defect the code reviewer's checks describe. It works from a new catalogue,
  `skills/reviewing-java-changes/references/security-dimensions.md` (Java 17, 21 and 25; Spring Boot 3.x
  and 4.x; AWS Lambda and the SDK for Java 2.x; Maven and Gradle builds; facts read 2026-11-24): injection,
  deserialisation and data binding, XML, cryptography and TLS, authentication and tokens, authorisation,
  the Spring web surface, files and denial of service, logs and failure, platform mechanisms, AWS, the
  code patterns behind named CVEs, and the `JAVA-DEP` rules for dependencies and the build supply chain.
  It reads the groups whose trigger the change meets (five always apply, and a trigger it cannot rule out
  counts as met), reports the others as `not applicable (<reason>)`, and gives every group's outcome on
  its `Groups:` line; a group left unsure makes verification incomplete. It looks nothing up: a finding
  that depends on a version, a default or a date is marked "verify against the docs" and checked by the
  main conversation
- Dependency audit for Java reviews, `core/scripts/dependency-audit.py`: the build tool lists the
  project's dependencies offline (Maven `dependency:tree`; Gradle through the init script below), and
  the script matches them against a local copy of the public OSV Maven export (GitHub Advisory
  Database records, CC-BY 4.0), downloaded at most once a day; the plugin sends nothing about the project.
  The preparation registers the gate `dependency-audit` as pending, and each attempt records it as pending
  again before it starts, so a review without the audit's result is incomplete; a pass or a fail also
  records its coverage as the gate `dependency-audit-coverage`, and its status line ends with `coverage
  complete` or `coverage partial (...)`, so a fail found in a partial inventory is a red gate and an
  incomplete verification. The base revision is always resolved from its own files, and each Maven profile
  named is resolved in a run of its own, each dependency scope naming every build that resolved it. An
  advisory range whose events can be read more than one way, or a SEMVER range, whose ordering is not
  Maven's, is not matched and counts as a Major marked unsure, never by a guess; a reported fix checked
  against every advisory for that artifact says so, else it is marked not checked against every advisory.
  The report lists each vulnerable occurrence as introduced by the change, attribution
  unknown, accepted by the user or pre-existing, with the advisory ids, the class and the fix the
  advisories report; a Blocker or Major the change introduced fails the gate, and the review is Blocked
  until the dependency is fixed or the user accepts the advisory. `refresh --from` imports a copy of the
  export on a machine without internet access; `audit --repo` audits a project outside a review. A
  build plugin, compiler-plugin processor path or Gradle buildscript dependency the change adds or
  changes, which the inventory leaves out, is matched with `check`.
  `--timeout` limits each build-tool run (default 120 seconds) and `--total-timeout` the whole audit, the
  lock wait and the download included (default 480 seconds), so the audit ends with a result of its own
  within one Bash tool command, except a git read or a network read that keeps trickling: then the Bash
  command ends first and the gate stays pending, which reads as verification incomplete
- Gradle projects in the dependency audit: Gradle itself resolves every resolvable configuration of every
  project, offline, through the plugin's init script `core/scripts/dependency-audit-graph.init.gradle`
  (Gradle 6.6 and later), with the distribution the project's wrapper names when it is in the Gradle user
  home under that distribution's URL with its completion marker left (an archive still beside the marker
  must match the `distributionSha256Sum` the wrapper's properties give, when they give one; the wrapper
  deletes the archive once it unpacks the distribution, so a marker and an unpacked distribution with no
  archive left count as provisioned), never the `gradlew` script, and writes nothing in the project; for the run, the Maven and Ivy
  repositories of the projects and of the settings' `dependencyResolutionManagement` are read without
  their artefact-only metadata source, so a module without metadata counts as unresolved, while the
  `buildscript` and `pluginManagement` repositories stay as declared; each entry's context is ship,
  compile, test, build or other (other counts as shipping); the buildscript classpath, file dependencies,
  shaded content and included builds are outside the inventory, and an included build, a flat-directory
  repository or a dependency result of an unknown kind makes the result partial
- Build tool selection in the dependency audit: a `pom.xml` is resolved by Maven, Gradle build files by
  Gradle, and a project directory holding both by both, each occurrence labelled with its tool and
  coverage complete only when both resolve; `--build-tool maven|gradle` names the one the project uses,
  and the base revision follows the same rule on its own files
- Setting `dependency_audit`: `on` (default) or `off`. Only the user's saved plugin options or a flag on
  the script switch it off; an environment variable can only switch it on, and an `off` from the
  environment, or from a settings file inside the repository under audit, is recorded as not run
- `implementing-java-from-spec`: a dependency check at plan time (`dependency-audit.py check`). Every new
  dependency and plugin the plan names is matched against the same advisory data before approval; a
  match becomes an open question, or an approval line when the plan chose the version, with the reported
  fix as the recommendation, and is never changed silently. When a specification item states the
  version, the draft carries that item changed to the reported fix, recorded under
  `## Specification changes`, so `approve` accepts both. The plan states where each version comes from,
  and a version the plan chose itself is marked as such
- `implementing-java-from-spec`: security defaults in `references/java-practices.md` for the implementing
  subagents, the generation-time form of the catalogue's rules

### Changed

- A requirement with no specification item (a feature spec under `ai-planning/`, a request in plain
  words) becomes a new item of the project's specification, with the next free ID. Plan-local
  `SPEC-PLAN-n` IDs are superseded: plans drafted earlier still pass, and `spec-trace.py plan` fails
  `plan-local-id` for one in a plan with `## Specification changes`
- The strict format rules apply only to a specification whose index carries
  `Format: implement-from-spec specification format 1`; older layouts get warnings, and only for new or
  changed items
- The traceability report is regenerated only when it carries the plugin's generated mark; a project's
  own report is never overwritten. `traceability` prints to stdout only on a clean run, and the skill
  writes it through a temporary file under `ai-planning/` that it moves into place on success
- The approval gate (K22) binds a plan's specification draft: on `approve` it computes the draft's
  digest and approves only when it equals the plan's `Draft digest:` line, refusing when they differ,
  when one exists without the other, or when the draft cannot be digested ("Nothing was approved: have
  the plan and its draft re-checked …"). While the approval holds, a write into the draft or naming
  `ai-planning/` revokes it; before a write to a drafted path (or naming the repository root) the gate
  re-checks the digest, and on a mismatch revokes the approval and denies the write. A missing
  `core/gate/draft_digest.py` fails closed. Residuals: location-only writes (git, formatters, inline
  code, unresolvable targets) revoke only inside the draft; changes behind the hook's back or between the
  re-check and a copy's read are caught at the next drafted write or by the skill's check; written bytes
  are judged only by `spec-layout.py check`. Plans without a draft behave as in 0.2.0, and the approval
  grammar is unchanged; nothing outside `ai-planning/` and `.claude/` is written before approval,
  specification files included
- `spec-trace.py code` no longer prints the `unwired` hint for an owned Markdown file: a document is
  never imported
- The report has a `Specification:` line (contract section 11)

- `reviewing-java-changes`: the Claude stage is two reviewers, the code reviewer (correctness, design,
  patterns, extensibility, maintainability, readability, contract files and documentation fidelity) and
  the security reviewer, where one reviewer covered seven dimensions. The report's `Quality gate:` line
  ends with the audit's status line (`Dependency audit: pass (...)`, `fail (...)`, `not run (<category>:
  <what to do>)` or `off (configuration: <source>)`), `dependency audit` is a finding source, and the
  `Reviewers:` line takes Safety/security from the security reviewer. "Skip security" leaves the security reviewer out and
  makes verification incomplete; the audit still runs
- `reviewing-java-changes/references/review-dimensions.md`: its security group is a pointer to the new
  catalogue, whose rules `JAVA-SEC-01` to `JAVA-SEC-12` keep their numbers; JAVA-CTR-03 no longer counts
  the AWS Encryption SDK for Java (`com.amazonaws:aws-encryption-sdk-java`) as the AWS SDK for Java 1.x
- `core/scripts/review-prepare.py`: a dispatch manifest may name `required_gates`, each with the plugin
  script that registers it; the preparation runs its `register` command and prints the line it returns,
  and records the gate as not run ("registration failed") when the script cannot run. The schema id is
  unchanged
- `implementing-java-from-spec`: the report's `Checks:` line carries the review's `dependency-audit`
  entry; the external stage's review focus follows the catalogue's groups

### Fixed

These also affect 0.2.0 users:

- On a case-insensitive volume (the macOS default), a write through a differently cased path (for
  example `PROJ/src/a.py` for `proj/src/a.py`) to a gated project, its `ai-planning/` folder, its plan,
  its `.claude` settings or the plugin's own files was allowed before approval. The gate now compares
  every path as the file system spells it; on a case-sensitive volume nothing changes
- A firmlink alias of a project path (on macOS, `/System/Volumes/Data/<path>` for `<path>`) was allowed
  before approval. The gate now resolves it to the project's own path, on a case-insensitive system
  volume (the default)
- A shell command whose program name was in upper case (`RM`, `CP` and others, which a case-insensitive
  volume runs as `rm` and `cp`) was not analysed as a write. Such a name is now read as the program the
  shell finds on the hook's `PATH`; one found only on the Bash tool's `PATH` is not
- `spec-external-review.py` took a quoted value of 16 or more characters made only of letters, digits
  and underscores for an identifier and did not withhold it, so such a secret value was sent to the
  reviewer. Only capital words joined by underscores (`API_TOKEN_NAME`) are now treated as identifiers
- Repository file names in the external reviewer's terminal output, status lines and saved review
  record are escaped (backslash doubled, controls, separators and bidi characters as `\n`, `\xNN`,
  `\uNNNN`), so a file name can no longer forge or restyle a line
- Inline interpreter code (`python3 -c`, a here-document fed to an interpreter) was not seen as a write
  before approval when the interpreter's name was quoted, in upper case, an absolute path, versioned
  (`python3.12`) or behind a wrapper (`env`, `nice`); it is now analysed like the plain name
- Reviewer isolation compared paths, roots and credential names as text, so on a case-insensitive volume
  a reviewer could read a repository's `.env` as `.ENV`, and on macOS `~/.aws/credentials` through its
  firmlink alias under `/System/Volumes/Data`. Every path and root it compares is now spelled as the file
  system holds it, the gate's own way, and credential directories, `.env` names and the credential
  patterns of Glob, Grep and the shell are compared in any letter case and normalisation
- The setup ask hook matched `install.py` as typed, so `INSTALL.PY --apply`, which a case-insensitive
  volume runs as `install.py`, installed without its permission prompt. The installer's name is now
  matched in any letter case and with format characters dropped, and the dispatcher passes such a
  command to the ask hook

### Known limitations

- No runnable eval proves the post-approval apply step live: the post-approval eval needs gate state a
  resumed run lacks. The script side is covered by a host integration test in the maintainers' test
  suite
- The dependency audit's inventory leaves out local file and file-tree dependencies (Gradle `files()`
  and `fileTree()`, `flatDir`, Maven system-scope dependencies): they are never resolved against the
  advisory dataset, so a vulnerable jar brought in this way is not reported
- The dependency audit's download deadline does not bound a response that keeps trickling bytes: the
  attempt is recorded as pending before the run starts, so a hang leaves the gate not run rather than
  wrongly passed, but the audit does not always end within its stated total timeout
- A dependency finding closes when the current report's advisory dataset no longer lists it, which is
  also true when the advisory was simply dropped from the dataset rather than fixed; the coordinate and
  version are not re-checked against the previous dataset before closing
- Running a gate script through a symlink has not been checked against the gate's rule for its own
  scripts
- The approved draft is guarded only as far as the gate sees each write: a shell or NotebookEdit write
  into the draft that lands after approval gets no after-the-fact check, a symlink re-pointed after
  approval escapes the paths the gate recorded, and `node -p` and `node --eval` are not recognised as
  inline code
- The gate's shell analysis is best effort: it does not catch inline interpreter code it cannot read
  (strings split up, other languages' file APIs, code an interpreter reads from stdin), treats neither
  `link` nor rsync's `--link-dest` as making hard links, and misparses the wrapper options `command -p`
  and `exec -a`, besides the residuals above. Run the agent in a sandbox when you need a hard boundary

### Security

- Threat model: TM-63 (repository text promoted into a specification the plugin derives, and read back
  by later runs), TM-64 (an existing item reworded, renumbered or dropped without the user's approval)
  and TM-65 (`spec-layout.py` reading outside the repository through a symlink or a draft path), and
  TM-66 to TM-70 (a written specification that is not the approved draft, the traceability report's
  target and content, a new skill and the gate, specification files reaching the external reviewer, and
  a specification kept where detect does not recognise it)
- Credential values stay out of specification items: the baseline survey skips the files the external
  review treats as sensitive, and `spec-layout.py check` fails a specification file that matches a
  secret pattern

- The audit's reports carry no advisory text and no line of the build tool's output: only advisory ids,
  coordinates, versions, severity words, dates and counts that pass a grammar; the build tool's raw
  output stays in a file only the user can read under `~/.local/state/implement-from-spec/dependency-audit/`
- The advisory data lives in `~/.local/state/implement-from-spec/advisories/`, found from the home
  directory alone, and is refused when it lies inside the repository under audit, is a link, belongs to
  another user or can be written by others. Every dataset, downloaded or imported, must hold at least 5,000
  usable advisories and no two different records under one id, its digest is checked on every load, and
  data last checked more than 7 days ago is not used. The download
  comes from one fixed HTTPS address, follows no redirect and is read within size and time limits
- The build tool runs with the user's permissions, as the project's tests do: its offline switch is a
  request, not a sandbox. It is started with an argument list, no shell and closed standard input, in
  its own process group that is ended at the time limit, and never from a program inside the repository;
  `PATH` reaches it absolute and without the repository's directories
- The approval gate protects the dependency audit's directories: in a gated session it denies the tool
  calls that would write, remove or replace the advisory cache or the build-output directory
  (`~/.local/state/implement-from-spec/advisories/` and `.../dependency-audit/`, listed in
  `core/gate/ifs_paths.py`); only the script writes them, and reads stay allowed. In that session an
  import of advisory data (`dependency-audit.py refresh --from`) asks you first, before and after plan
  approval, since the copy it publishes decides what the audit can find; a download, `check` and `audit`
  do not ask. A review whose advisory data was imported says so in its section for the human reviewer
- Threat model: TM-71 and TM-72 (the advisory download and the advisory cache), TM-73 to TM-77 (advisory
  and build-tool text reaching a model, the project's build running at review time, a repository switching
  the audit off, a revision written out from git, and a secret in the build tool's output), and TM-78 and
  TM-79 (an audit that reads clean when it is not, and a review that reads complete without the audit),
  with data flows 26 and 27

## 0.2.0 — 2026-11-13

### Changed

- Eval speed and review cost (2026-10-27, analysis in the maintainer's timing report): one PreToolUse
  dispatcher hook, `core/gate/ifs-pretool.py`, in place of the four PreToolUse registrations of 0.1.0. It is
  registered on every tool (matcher `*`, `onFailure: block`), Read, Grep and Glob included, because the
  reviewer isolation needs every tool call; calls no check can decide load nothing beyond the dispatcher;
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

### Security

Fixes from the triage of pull request 1, from three independent reviews of those fixes and from the pull
request's code review (two rounds), in the unreleased changes above (2026-11-12):

- The PreToolUse dispatcher's failure policy is fail-closed for every tool, by decision: when `python3`
  cannot run, every tool call of a session with the plugin is blocked, reads included, until it is fixed
  or the plugin is turned off; documented in the threat model (TM-47) and tested
- The dispatcher no longer keeps its own copy of the gate's and the isolation hook's state locations: all
  three use `core/gate/ifs_paths.py`, and a paths module that cannot load fails closed
- `SPEC_GATE_STATE_DIR` is removed: it took precedence over the plugin data directory, a repository's settings
  `env` block could set it, and moving the gate's state between two calls made an activated session read as
  ungated. Starting a gated skill now also writes an activation record under
  `~/.local/state/implement-from-spec/active/`; while it exists, a gate state that is missing, unreadable or
  somewhere else denies every write and shell command of the session (start a new session to continue), and
  a registered reviewer whose registration is lost is denied every call (TM-61). A state file or record that
  cannot be read or even checked (mode 000, a directory above it the hooks may not search, a dangling symlink
  in its place) counts as present: the session's guards and the reviewer's isolation then deny with a message
  naming the directories, where an unreadable state and record used to read as "no state" and lifted both
  (TM-55, TM-61). While the plugin's state directories cannot be reached, this denies the writes and shell
  commands of every session and the calls of every subagent. The hooks' failure handlers build their messages
  best-effort, so a deny is printed even when the error came from `core/gate/ifs_paths.py` itself: until the
  fourth fix round the gate's guard handler and the isolation hook's (naming the activation records, the
  state directory, or checking a reviewer's raw records) could raise there, and the deny was lost to a
  traceback
- Reviewer isolation is an allowlist: a registered reviewer may use Read, Grep, Glob, read-only Bash and a
  few bookkeeping tools; every other tool is denied, a new Claude Code tool included
- A reviewer's `grep` and `rg` take only an allowlist of read-only options, each matched by its full name, with
  `--opt=value` and `--opt value` both checked; an abbreviation, an unlisted option and a value given to an
  option that takes none are denied. Until the code review, `rg` forbade only `--pre` and `--pre-glob`:
  `rg --hostname-bin=<program>` ran a program (a script in the change under review, an instruction planted in
  it could ask for), and its spaced form was taken for the pattern and never checked; and BSD grep took
  `--regex=` for `--regexp=`, so the hook took the next word, a file outside the allowed roots, for the
  pattern. Options that run or load something (`rg --pre`, `--hostname-bin`, `--hyperlink-format`, `-z`,
  `--ignore-file`, `--type-add`; ugrep's `--filter`, `--pager`, `--view`, `--config`, `--exclude-from`), that
  follow symbolic links out of the paths given (`grep -R`, `-S`, `rg -L`) or whose value kind differs between
  BSD grep, GNU grep and ugrep (`-O`, `-J`, `-M`) are not on it (TM-55)
- A reviewer's `sort`, `wc`, `file` and `diff` take an allowlist of read-only options too, and `find` an
  allowlist of tests and actions. Until the seventh round, `sort --files0-from=<list>`, `wc --files0-from`,
  `file -f <list>` and GNU and bfs `find -files0-from <list>` read the files or starting points that a list
  committed in the change names, outside the allowed roots, while only the list itself was checked; `find -L`,
  `-H` and `-follow` and `ls -L` followed a committed symbolic link out of the roots, and bfs `find -rm`
  (Claude Code's `find`) deleted. `diff` of two directories, or of a directory and an absent path or a
  dangling symbolic link (which `-N` and `-P` turn into an empty directory), now needs `--no-dereference`, since GNU and Apple's diff follow
  a committed link inside them with or without `-r`, and for a directory and a file the file diff reads in
  the directory is checked like any path (TM-55)
- One reading of the Skill tool's `skill` input for the gate, the dispatcher and the reviewer isolation
  (`ifs_paths.skill_parts`): the surrounding whitespace and a leading `/` are dropped, as Claude Code's Skill
  tool drops them. The isolation hook already did; the gate did not, so `/implementing-python-from-spec` or
  a padded name could start a gated skill with no activation and no gate (TM-08)
- The CDK, CloudFormation and Terraform reviews no longer write into the review snapshot directory: in an
  implementing skill's gated session the gate denies every tool-call write there, so `cdk synth --output
  <DIR>/synth/change.out`, the gate outputs redirected to `<DIR>/gates/` and the change set or plan output
  copied to `<DIR>/input/` were denied, and the IaC security reviewer of an implementing CDK review got no
  synthesised template. The command now writes to a scratch directory, and the new
  `review-snapshot.py attach` copies the result in: write-once, only to `synth/<name>.out`, `gates/<name>.txt`
  or `input/<name>` (never `input/change.diff`) of a snapshot directly under the default snapshot roots that
  still verifies, never through a symlink on either side, from no source that is or holds a credential path
  (every entry of a directory checked), without CDK's `asset.<sha256>`
  staging, within 256 MiB and 20,000 files. Reviewers cannot run it, and the gate still denies the direct
  writes. A new eval case, `cloudformation-review-gated-session`, runs the review step of
  `implementing-cloudformation-from-spec` in the session its command gates (TM-58)
- In a gated session the gate also denies tool writes, deletions and renames of the other hooks' state: the
  reviewer registrations, the activation records, the review snapshots and the timing log; a shell command
  may not name the registrations or the records
- No bytecode cache under the plugin data directory: the dispatcher's checks and `ifs_paths.py` are compiled
  from source and the dispatcher writes no `.pyc`, so a file planted in the former cache directory can no
  longer run inside the hooks. The modules a check loads itself (`depslib.py` and `install.py` on the setup
  ask path) and the standard library still use Python's normal loader (TM-40). The price, measured on
  macOS's built-in Python 3.9 (2026-11-12, median of 15 calls, wall time with interpreter start): a gated
  Bash call 98 to 148 ms, a gated Write 98 to 172 ms, a registered reviewer's Read 86 to 162 ms; a call no
  check can decide is unchanged at 58 ms
- The opt-in hook timing log (`IFS_HOOK_TIMING_LOG`, `EVAL_IFS_HOOK_TIMING_LOG`) is written only in
  `~/.local/state/implement-from-spec/hook-timing/`, reached from `HOME` through directory descriptors with
  no symlink followed, and only to a private (0600) regular file of the user with one link that the record
  keeps within 64 MiB (a soft cap: hooks writing at the same moment can pass it by one record each), opened
  non-blocking; anything else is skipped. A repository's settings `env` block can still switch it on,
  which writes timestamps, tool names and ids to that directory (TM-57)
- Terraform review: `terraform validate` in a scratch copy runs `init` without a question only when the root
  has no `module` block and no JSON configuration at all (no `.tf.json` or `.tftest.json` file in the root or
  a directory directly below it, whatever it holds, since a JSON key can be escaped past a text search; no
  `.tf` or `.tftest.hcl` file there holds the word `module`; no symlink; no error from the search, whose
  errors are no longer discarded) and a local provider mirror holds the providers; otherwise the user is
  asked before `init`. The search's `grep` exits 1 when nothing matches, and `find` with it, so the text now
  reads "no module" from no output at all with exit 0 or 1, and asks on any path, any error message or any
  other exit; until the fourth fix round it asked on every non-zero exit, so every module-free root asked.
  This is skill text the orchestrator follows; nothing enforces it (TM-59)
- `spec-external-review.py --policy-dir` accepts only the `policy/` directory of a snapshot of the change under
  review (`<snapshot home>/<id12>/policy`, `<id12>` in the id's exact form, its manifest naming `--repo`, its
  policy at its base, the same mode and commits as the change arguments, and every policy file that applies
  to a changed path recorded), with no symlink from the state directory down (each component opened with
  `O_NOFOLLOW` through the one above it); each policy file is read once and the bytes sent are the bytes
  checked against the manifest's sha256, and without `--rules` every recorded file must be there and readable;
  a directory inside the repository is no longer accepted. A `--files` review (a fix round's delta), which
  names no base, also needs `--snapshot-id`, the round's snapshot's full id, equal to its manifest's, and the
  snapshot's base must be an ancestor of `HEAD`; before, it was bound by coverage only, so an older snapshot
  of another base was accepted. `review-prepare.py`'s runner command carries the id, and the reviewing
  skills' fix rounds keep it (TM-15)
- Review records: a record whose `.sha256` sidecar is missing counts as changed outside its writer, so
  deleting `risk.json.sha256` and editing `risk.json` invalidates the snapshot and keeps human approval
  required. A record deleted together with its sidecar still reads as never recorded (TM-58)
- Review policy copies: `verify`, `state` and a reused snapshot check `policy/` against the manifest (every
  recorded file present with its sha256, nothing else there). Until the seventh round nothing but the
  external stage checked them, so a `policy/REVIEW.md` edited after the snapshot steered the Claude reviewers
  while `state` still printed valid; now the snapshot reads invalidated, and `create` refuses to reuse such a
  directory (TM-58)
- `review-snapshot.py state` refuses (exit 64) "No blocking findings" with an open Blocker or Major and
  "Changes requested" with an open Blocker: such a block read as a complete review to the implementing skills
- `review-prepare.py` prints repository-derived names with control characters, newlines and bidi controls
  escaped, so a file name cannot add or restyle an output line, and writes them escaped into the reviewer
  briefs too, where a model would read a forged heading or rule as part of the brief; when such a name would
  have to go into the external runner's command, the external stage reports `not run` instead (TM-62)

### Fixed

- A plan approved in an earlier session: the approval message now opens by saying why that approval does
  not unlock this session (approval is per session and bound to the plan's exact content), in all five
  implementing skills
- CDK: a request that renames or moves an existing resource gets an approval message that opens by
  saying a plain `cdk deploy` would replace it (both logical IDs named), then offers the safe paths (keep
  the construct ID, keep the logical ID, or a separate `cdk refactor` with its `--dry-run` mapping)
- Documentation: the README and the customer hand-off no longer say the hooks fail open without `python3`
  (on Claude Code 2.1.295 or later every tool call blocks until it is fixed or the plugin is turned off);
  the README's "Security model" lists the residual risks the threat model names; the threat model's
  citations were re-read and re-pointed for every row, with data flows for the review snapshots, the
  activation records and the timing log; the design notes and the user guides state the current Terraform
  `init` rule, the report's sections (covered-by-gate findings are counts only), the documentation sync
  before the review in the infrastructure skills, and the `--files` limit of the external review's
  snapshot binding

## 0.1.0 — 2026-11-12

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
