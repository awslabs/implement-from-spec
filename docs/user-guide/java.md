# Java

Two skills:

- `implement-from-spec:implementing-java-from-spec` implements Java code (Spring Boot services, AWS
  Lambda functions, shared libraries and their JUnit tests, built with Maven or Gradle) from
  specification items or a feature spec. It ends at a built, tested artifact and a local smoke check.
  Deploying stays with you or your pipeline
- `implement-from-spec:reviewing-java-changes` reviews any Java change, with or without a plan: two
  read-only Claude reviewers, a code reviewer (correctness, design, patterns, extensibility,
  maintainability, readability, the repository's contract files and documentation fidelity) and a
  security reviewer, and, when you enable it, the external reviewer (off by default), all in parallel,
  while the project's tests and a dependency audit run. It is also the Java skill's review step

## Requirements

- A JDK at the Java version the project targets. Setup offers Amazon Corretto
- The project's build wrapper (`./mvnw` or `./gradlew`); Maven or Gradle only when the project has none
- For the dependency audit: the project's dependencies already in the build tool's local repository or
  cache, in both when the project holds a `pom.xml` and a Gradle build (building the project once puts
  them there); for a Gradle project, Gradle 6.6 or later and, when
  the project has a wrapper, the wrapper's distribution in the Gradle user home (running `./gradlew` once
  puts it there); and network access to download public advisory data at most once a day, or a copy you
  import (see "The dependency audit")
- Optional: the AWS SAM CLI, for projects that build or test Lambda functions with SAM; the AWS CLI v2,
  for read-only checks of the target account
- The AWS Documentation MCP server, for AWS facts

Check and install with `/implement-from-spec:setup java`. Setup reads each tool's minimum version and
install recipes from [`core/deps/dependencies.json`](../../core/deps/dependencies.json), shows every gap
with its exact commands, and installs only what you approve. The skill checks the same tools, read-only,
at the start of every run, and stops before planning when a required one is missing.

When setup lists the gaps it asks what to install: name the required tools (the optional ones are not
needed to run the skill), then allow setup's `install.py ... --apply` command when Claude Code asks for
permission. Setup installs user-scope tools into directories such as `~/.local/bin` and never edits your
shell profile: add the directories its report names to PATH. The skill's tool check looks in them anyway,
but the project's own commands need them on PATH.

## What the project should have

- A `CLAUDE.md` or `AGENTS.md`. A project rule, for example "run builds only through `scripts/`",
  overrides every default of the skill
- The specification items. A common layout: `specification/SPECIFICATION.md` as the index,
  `functional/` (`SPEC-Fxxx`) and `non-functional/` (`SPEC-NFxxx`) topic files, `open-questions.md`, and
  `test-cases/TEST_CASES.md` with `TC-xxx` cases and a coverage matrix. A feature spec under
  `ai-planning/<feature>.md` works too. [spec-format.md](../spec-format.md) gives the rules for each
  format, including how a test cites a `TC-xxx`: the ID string itself in a comment or Javadoc, because a
  method name such as `tc003_searchesByStatus` does not count
- A `.gitignore` that covers `target/`, `build/` and `.gradle/`: after implementation every changed or
  untracked file must belong to a task (see "How a run goes", step 6)
- Optional: a design doc (for example `docs/DESIGN.md`) and `scripts/` wrappers for build, test, run and
  request calls, which the skill uses instead of raw commands

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

1. Ingest: the input, the specification tree, the build and its static analysis (Checkstyle, SpotBugs,
   PMD, Error Prone, Spotless), the design doc and two neighbouring classes per affected package, and for
   AWS work the SDK for Java 2.x modules and client setup. An open question the feature depends on is a
   blocker, never a default
2. Plan: `ai-planning/<slug>.plan`, with every class described in prose and no Java. Each new dependency
   names its version and where the version comes from: the specification, the project's own dependency
   management, or the plan's own choice
3. Analysis gate: `spec-trace.py plan` and `spec-layout.py check` (with `TC-xxx` IDs checked when the items
   cite test cases), then a self-review of pattern fit, Java idioms, layer fit, AWS client use, concurrency,
   testability, dependencies and scope, and the dependency check of every new dependency (see "The
   dependency check at plan time")
4. Your `approve`
5. Implementation in waves, test first with JUnit through the project's own build entry point. The
   implementing subagents start from the security defaults of the skill's
   [`java-practices.md`](../../skills/implementing-java-from-spec/references/java-practices.md), the
   form of the review's security rules that applies while code is written. The full build runs after
   every wave; the last wave syncs the specification and test-case files
6. Verification of each item, `spec-trace.py code`, the full build with the project's static analysis,
   the packaged artifact, and a smoke gate whenever request or output behaviour changed: start the
   application, call the endpoint (or invoke the Lambda handler locally), inspect the result, stop it.
   What only a deployed system can show is listed as "needs runtime verification". `spec-trace.py code`
   also fails every file changed against `HEAD` that no task owns and that is not under `ai-planning/`
   (`unowned-change`): a write outside the plan is an amendment you approve, never a ruling the skill
   makes alone
7. Review through `reviewing-java-changes`: its code reviewer applies
   [`reviewing-java-changes/references/review-dimensions.md`](../../skills/reviewing-java-changes/references/review-dimensions.md),
   its security reviewer
   [`reviewing-java-changes/references/security-dimensions.md`](../../skills/reviewing-java-changes/references/security-dimensions.md),
   and the dependency audit runs after the project's tests. Blockers and Majors are fixed; a vulnerable
   dependency the change introduced is fixed with the version change its finding names, unless you
   accept the advisory
8. The full build again, and a check that the review snapshot is still valid
9. The report, with each build command, the static analysis, the dependency audit and the smoke call,
   and the deploy command the skill did not run

A test that will not pass is debugged; it is never weakened, skipped or disabled.

## What asks first

The gate asks before each of these, before and after plan approval:

- Maven and Gradle dependency and version goals (`versions:*` other than `display-*` and `help`,
  `dependency:get`, `install:install-file`, `wrapper:wrapper`; Gradle `wrapper`, `useLatestVersions`,
  `dependencyUpdates`, `--write-locks` and `--update-locks`)
- Deploy and publish goals (`deploy`, `release:prepare`, `release:perform`, `jib:build`, Gradle `publish`
  tasks other than `publishToMavenLocal`, `jib`)
- `sam deploy`, `sync`, `delete`, `publish`, `pipeline bootstrap`, `remote invoke` and
  `remote test-event put` and `delete`
- Every mutating `aws` CLI call. Read-only calls, `events test-event-pattern` and `route53
  test-dns-answer` run without asking
- An import of advisory data, `dependency-audit.py refresh --from <path>`: the copy it publishes decides
  what the dependency audit can find (see "The advisory data"). A download (`refresh`), the plan's
  dependency check and the audit itself are not asked

In a gated session the rules of all five implementing skills apply together, so a `pip` or `brew` install
asks too. A dependency, plugin or build-tool version the plan does not name is an amendment you approve.

Before you approve the plan, the gate also denies every write in the repository outside `ai-planning/` and
`.claude/` (README, "The approval gate"). The plan's dependency check and a download or import of advisory
data are not denied: they write only to the advisory cache under `~/.local/state/implement-from-spec/`,
outside the project, and the import asks, as above. When the gate asks about a dependency step or a live
read the approved plan names, its prompt is the confirmation, and the skill does not ask again in the
conversation.
A step you decline is not retried and gets no substitute: the tasks that need it are marked `blocked` in
the ledger with the command for you to run, the others are finished, and the report's status is
"verification incomplete (<command> denied)" (contract section 12).

## The security reviewer

Security has its own reviewer on every Java review and every fix round. It is a second subagent on the
`code-reviewer` reviewer skill, always on Opus whatever the risk tier, dispatched in the same message as
the code reviewer, so it adds cost but no wall-clock time. It owns the Safety/security dimension for
every file of the change (Java sources, configuration and build files), including the security
consequence of a defect that one of the code reviewer's checks describes. The code reviewer reports a
security problem it notices as a one-line pointer, and the review merges the two into one finding.

Its rules are
[`reviewing-java-changes/references/security-dimensions.md`](../../skills/reviewing-java-changes/references/security-dimensions.md),
a catalogue for Java 17, 21 and 25, Spring Boot, AWS Lambda and Maven or Gradle builds, its facts read
on 2026-11-24. Its groups: injection; deserialisation and data binding; XML; cryptography, randomness,
TLS and secrets; authentication, sessions and tokens; authorisation; the web surface and Spring
configuration; files, resources and denial of service; input, outbound requests, logs and failure;
platform mechanisms; the AWS SDK and Lambda; known-vulnerable usage (the code patterns behind named CVEs
in widely used libraries); and dependencies and the build supply chain (the `JAVA-DEP` rules). Spring
rules cover Spring Boot 3.x (Security 6, Jackson 2) and 4.x (Security 7, Jackson 3), whose property
names, class names and removed APIs differ; the reviewer reads the Boot version from the build file
first. Each finding cites its rule: a `JAVA-SEC-nn` rule for code and configuration, the code patterns
behind named CVEs included, or a `JAVA-DEP-nn` rule for dependencies and the build.

How it works:

- It lists the entry points the change adds or alters first (controllers, message listeners, Lambda
  handlers, scheduled jobs, deserialisers, configuration and build files), then traces each untrusted
  value from its source to every sink as file and line steps, and looks for the guard (a filter chain, a
  validator, a framework default, a caller that never passes the value) before it reports
- It never looks anything up: it opens no page, runs nothing and never sees the dependency audit's
  report. A finding that depends on a version, a default or a date the repository does not show is
  marked `unsure: verify against the docs`, and the main conversation checks the documentation before
  it accepts the finding
- When the code calls an API that a rule ties to a named CVE, the finding names the library, so the
  review can merge it with the audit's entry for that library: one finding, with the code path as
  evidence
- The catalogue keeps no list of minimum versions, which would be out of date within weeks: versions
  are the audit's. It names a fixed release only inside a rule about a named CVE, as history
- Your project's rules, specification and approved plan choose among safe forms and override the
  catalogue's conventions; they cannot waive a hazard. Only you, in the conversation, can defer a
  security Blocker or Major

Each group of the catalogue carries a trigger, and the reviewer reads only the groups whose trigger the
change, the build files, the configuration or the code the change reaches meets; a trigger it cannot rule
out (a starter, parent or BOM whose contents it cannot see) counts as met, and a skipped group whose
trigger a traced path reaches is read after all. Five groups always apply: injection; cryptography,
randomness, TLS and secrets; files, resources and denial of service; input, outbound requests, logs and
failure; and dependencies and the build supply chain. The reviewer's `Groups:` line gives every group's
outcome: a finding count, `clean`, `not applicable (<the trigger not met>)`, `unsure (<the missing
context>)` or `needs runtime verification (<the check>)`. A group left `unsure` or needing runtime
verification, or a `Groups:` line that leaves a group out, makes verification incomplete.

Ask to "skip security" and the security reviewer is not dispatched: the report names the dimension as
skipped at your request and verification is incomplete, because no other reviewer covers it. The
dependency audit still runs.

## The dependency audit

Every Java review checks the project's dependencies for known vulnerabilities. After the project's
tests, the main conversation runs one command:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" audit --snapshot <snapshot DIR>
```

The review's preparation registers the gate `dependency-audit` as not run before any reviewer starts
(its line reads `Dependency audit: pending`), and only the audit's own result replaces that record: a
review whose audit was forgotten, crashed or could not run ends "verification incomplete", never clean.
Each attempt records the gate as pending again before it starts ("pending: an audit of this snapshot
started and has not recorded its result"), so an attempt that dies leaves no earlier result standing. A
pass or a fail also records its coverage as a second gate, `dependency-audit-coverage`: pass when the
inventory is complete, not run with the gap and its remedy when it is partial, so a fail found in a
partial inventory is a red gate and leaves verification incomplete too. The audit runs again in every fix
round, on the new snapshot.

Each run of a build tool may take 120 seconds (`--timeout`) and the whole audit 480 seconds
(`--total-timeout`), the wait for another refresh's lock, the download and every build-tool run
included; each run gets the smaller of its own limit and what is left of the whole. The total stays below the 10 minutes a Bash tool command may run
by default, so the audit ends with a result of its own, `not run (time limit: ...)` at worst,
instead of outliving its command with the gate still pending, except a git read or a network read that
keeps trickling: then the Bash command ends first and the gate stays pending, which reads as
verification incomplete. The skill passes another limit only when
you name one.

### How it works

1. **Resolution.** The build tool lists the dependencies, offline, from what is already on your machine:
   - Which build tool: the build files in the project directory decide. A `pom.xml` means Maven;
     `build.gradle`, `build.gradle.kts`, `settings.gradle` or `settings.gradle.kts` mean Gradle; a
     directory with both is resolved by both, because either may be the build that ships (one being
     migrated to the other, or one left behind). Each entry then names its build tool, and coverage is
     complete only when both resolve. When the project uses one of them only, name it in the
     conversation: the skill passes `--build-tool maven` or `--build-tool gradle`, and that tool
     resolves alone
   - Maven: `mvn -B -o -V -T 1 -Dstyle.color=never dependency:tree`, with the Maven distribution the
     project's `./mvnw` names when it is already under `~/.m2/wrapper/dists`, in the directory the
     wrapper names after that distribution's URL (a distribution of the same name from another URL is
     not used), else `mvn` from PATH;
     never a program inside the repository, so the wrapper script itself is not run. A Maven profile
     you name is resolved in a run of its own after the default build, because activating one can
     switch off the build's `activeByDefault` profiles. Every module of the build must give a
     dependency tree, and Maven must read the POM of every dependency (see "Maven")
   - Either build tool runs with your environment, `PATH` made absolute and without any entry inside
     the repository, so no program it looks up on `PATH` (`java`, for one) comes from the project
   - Gradle: Gradle itself resolves the build, offline, through an init script the plugin ships,
     `core/scripts/dependency-audit-graph.init.gradle`:
     `gradle --offline --no-daemon --no-configuration-cache -q --console=plain` with that script, whose
     one task prints the resolution result of every resolvable configuration of every project of the
     build. The Gradle
     that runs is the distribution the project's wrapper names, when the wrapper has already unpacked
     it into the Gradle user home (`GRADLE_USER_HOME`, else `~/.gradle`), in the directory named after
     that distribution's URL, with its completion marker left: once unpacked, the wrapper deletes the
     archive it checked, so a marker and an unpacked distribution with no archive beside them count as
     provisioned, and an archive still there must match the `distributionSha256Sum` the wrapper
     properties give, when they give one; with no wrapper, `gradle` from PATH. The `gradlew` script itself is never run, because it would download a missing
     distribution, and a project whose wrapper's distribution is not there is not audited, because
     another Gradle version may not configure the build. Gradle's project cache and every project's
     build directory go to a scratch directory that is removed afterwards, so nothing is written in
     the project. For the audit's run only, the script reads the build's Maven and Ivy repositories
     without their artefact-only metadata source (see "Gradle"). Lockfiles are honoured by Gradle
     itself. Supported: Gradle 6.6 and later, the first release whose command line takes
     `--no-configuration-cache`
   - A commit-range review audits the range's end commit, written out byte for byte from git into a
     scratch directory, not your working tree: its files, then its links that are relative and lead
     to a place inside it; any other link, and every submodule, is left out and makes the result
     partial. A pasted diff has no project, so the audit does not run, and a `--files` review stops
     before it runs when its snapshot leaves out a named build input; otherwise it runs, and its
     result is always partial, since the snapshot verifies only the files it holds and no list of files
     covers what a build reads: take the snapshot of the working tree or of a commit range instead
2. **Matching** against a local copy of public advisory data (below), with Maven's own version ordering
3. **Comparison with the review's base revision.** The base is always resolved, written out from its
   own revision as a commit range's end is: no list of file names covers everything a build reads to
   choose its dependencies (a script it applies, a file a profile's activation tests), so equal build
   files prove nothing. A vulnerable dependency the base
   lacks, or one whose scope widened from test to shipped, is the change's. The base's build tools are
   chosen by the same rule, from its own build files (and `--build-tool`, when given, applies to it
   too), so a build the change adds has nothing to compare with at the base and its entries count as
   the change's. When the base cannot be resolved, its entries are "attribution unknown" and count as
   the change's
4. **The report.** The status line; a `Data:` line (where the data came from, its dates, its advisory
   count and the attribution); a `Resolution:` line (the build tool or tools and why, then for each its
   version, path, build output and command, then profiles, modules, coverage and base); the inventory
   statement; then one line per vulnerable occurrence in four blocks, *Introduced by this change*,
   *Attribution unknown*, *Accepted by the user* and *Pre-existing*, and a last block, *Could not be
   evaluated*. Each line gives the module (followed by its build tool when both builds were resolved),
   the coordinates and version, the scope, the dependency path, each advisory id with its CVE alias,
   severity and review class, the basis of the match (`range`, `enumerated version`, `both`, or `not
   evaluable` for a range the audit cannot read one way only, a SEMVER range among them, which counts as
   a Major marked unsure) and the reported fix

The `Resolution:` line opens with the build tool or tools and why, in one of these forms; its `base:`
part, when the base was resolved, ends with the same words for the base's own build files
(`base: resolved from <revision> with build tool Maven (pom.xml found)`):

```
Resolution: build tool Maven (pom.xml found); ...
Resolution: build tool Gradle (build.gradle and settings.gradle found); ...
Resolution: build tools Maven and Gradle (pom.xml and build.gradle found; each is resolved, and coverage is complete only when both are); ...
Resolution: build tool Gradle (named with --build-tool gradle); ...
```

When both build tools were selected and one could not run, it reads `<tool> not run (<category>)` there
in place of its version and command; when the only one could not run, the line is
`Resolution: none (the audit stopped before the build tool ran)`. An entry reads as the first line
below, or, when both build tools were selected, as the second, whose `(Maven)` or `(Gradle)` after the
module says which build lists the dependency:

```
- module <module>; <group:artifact:version> (<scope>); path: <a> > <b> > <c>; advisories: <ID> (<CVE alias>) <SEVERITY> <class>[ unsure] [<basis>], ...; fix reported: <version>
- module <module> (Gradle); <group:artifact:version> (<scope>); path: ...
```

The review snapshot keeps both reports of each attempt, `gates/dependency-audit-<n>.txt` and
`input/dependency-audit-<n>.json` (schema `ifs-dependency-audit/1`, which binds the snapshot id, the
attempt, the dataset's digest and the SHA-256 of every build input read; its `resolution.selection` is
the build tools and why, as the `Resolution:` line words them, and `resolution.tools` holds one entry
per build tool, with its version, path, build output file and command, or the category that kept it
from running). The build tool's raw output goes to a file only you can read under
`~/.local/state/implement-from-spec/dependency-audit/` (the 20 newest are kept), whose path the
`Resolution:` line prints. No line of it is copied into a report, so a credential in a repository URL
or an error message never reaches the review. No advisory text reaches a report either: only
identifiers, coordinates, versions, severity words, dates and counts.

**The build tool runs with your permissions, as the project's tests do.** The offline switch is a
request to the build tool, not a sandbox: the project's build configuration, extensions and wrapper
settings execute as they do when you build. With Gradle, the plugin's init script runs inside that build,
and the build's own code could print lines shaped like the script's: the audit gives that output the
trust the tests have, no more. The audit asks for no trust that the tests did not already have.

To audit a project outside a review, ask Claude to run the same script with `audit --repo <path>
[--base <revision>]`: the report goes to standard output, and without `--base` every entry is
"attribution unknown" and counts against the result.

### The advisory data

The data is the OSV project's export of Maven advisories,
`https://osv-vulnerabilities.storage.googleapis.com/Maven/all.zip`, which carries GitHub Advisory
Database records and malicious-package records; withdrawn advisories are skipped.
The GitHub Advisory Database is licensed under CC-BY 4.0, and every report's `Data:` line carries the
attribution `OSV, GitHub Advisory Database, CC-BY 4.0`. Sources, read 2026-11-24: "Data sources"
(https://google.github.io/osv.dev/data/) and the GitHub Advisory Database repository
(https://github.com/github/advisory-database).

- It is kept in `~/.local/state/implement-from-spec/advisories/`, found from your home directory alone
  and readable only by you. The audit refuses that directory, and does not run, when it resolves inside
  the repository under audit, is a link or belongs to another user
- Data checked with the server within the last 24 hours is used as it is. Otherwise the audit asks the
  server whether the export changed and downloads it when it did: from one fixed HTTPS address, following
  no redirect, at most 128 MiB within 120 seconds
- Every record is parsed in memory before a copy is used (the archive is never unpacked to disk), and a
  copy with fewer than 5,000 usable advisories, or with two different records under one id, is
  refused, downloaded or imported, so an emptied, badly cut or small test copy never gives a clean
  result; a count cannot show that a large copy is whole. Its digest is checked again each time it is
  loaded, and the files of the cache must be yours, writable by no one else, with no second name
- When the server cannot be reached, data last checked within 7 days is used and the report says so,
  with both dates; with older data, or none, the audit does not run
- Nothing authenticates the export beyond HTTPS and its publisher

**The minimum does not stop a copy built on purpose.** A dataset made to pass the checks, 5,000 or more
well-formed records that leave out the advisories your dependencies match, gives a clean result. In a
gated session the approval gate denies the tool calls that would write, remove or replace the advisory
cache or the build-output directory directly, a Write or Edit or a shell command that names a path
under them (`core/gate/ifs_paths.py` lists both among its protected roots; reading them stays allowed),
and the documented route for a copy, the script's own `refresh --from`, asks you first, before and after
plan approval. Every report's `Data:` line then reads `import` and names the file it came from, and the
review report's *For the human reviewer* section ends with `Advisory data: imported from <path>,
published <date>, not downloaded from OSV`. Approve an import only for a copy you downloaded yourself from
the address above. The question guards that route only: a renamed copy of the script, or any program
whose writes the gate cannot see (it does not look inside a script that an interpreter runs), can still
write the cache without asking. Outside a gated session nothing asks, and against any other process
running as your user nothing protects the cache. Before you rely on a clean result, read its `Data:`
line: `download` from the address above, or `import` of a copy you made yourself.

### What leaves your machine

The plugin's own code makes one kind of network request: an anonymous HTTPS download of the public
export, at most once a day. It carries the user agent `implement-from-spec-dependency-audit` and, after
the first download, the date and tag the server gave the copy you hold, so an unchanged export is not
downloaded again. Nothing about the project is sent: no coordinate, no file, no name. The build tool
runs offline; anything your build configuration does on its own, it also does when the tests run.

### What the inventory is, and what an entry means

- With Maven, the inventory is the dependencies of every module of the build, in every scope, as Maven
  resolves them for the default build configuration and the profiles you name. Not in it: build
  plugins, annotation-processor paths configured in the compiler plugin (which resolves them on its
  own), shaded or relocated content. A dependency whose POM Maven cannot find offline, or cannot read,
  would show nothing below it although that POM declares dependencies; the audit reads Maven's warning
  for it and makes the result partial (see "Maven")
- With Gradle, it is every resolvable configuration of every project of the build, as Gradle resolves
  them, so annotation-processor paths, custom source sets and test fixtures are in it. Not in it: the
  buildscript classpath (build plugins), file dependencies (`files(...)` and `fileTree(...)`, which
  Gradle's resolution result does not hold), shaded or relocated content, and included builds, which
  make the result partial. A module without metadata counts as unresolved, never as a module with no
  dependencies (see "Gradle")
- With both builds in the project directory, it is both inventories, each entry labelled with its
  build tool; a vulnerable dependency that both builds list has an entry for each
- The security reviewer flags shading, which hides coordinates from the audit
- When the change adds or changes a coordinate the inventory leaves out (a Maven build plugin, an
  annotation-processor path in the compiler plugin, a Gradle buildscript dependency), the review runs
  the audit's `check` command on it, as at plan time; a match becomes a finding with the source
  `dependency audit`, and with no advisory data the coordinate is named under *Verification* as not
  checked
- An entry means that a version matching an advisory is in the inventory, not that the vulnerable code
  is called. The audit does no reachability analysis; the security reviewer's usage findings are the
  only evidence that the code is called, and the review words a dependency finding that way
- A result with no entry means "no matching advisory in this dataset", never "no vulnerabilities". A
  CVE the dataset does not carry (one that exists only in the NVD, for example) is not reported
- The class comes from the advisory's severity word: CRITICAL or HIGH, or a malicious-package record,
  is a Blocker; MODERATE (also written MEDIUM) a Major; LOW a Minor; anything else a Major marked
  unsure. The scope is reported and never lowers the class: a test-scope dependency keeps the class of
  its advisory
- The gate fails when an entry introduced by the change, or one whose attribution is unknown, is a
  Blocker or a Major you have not accepted. A failed audit is a red gate, so the review is Blocked
  until the dependency is fixed or you accept the advisory. *Pre-existing* entries go under
  *Pre-existing*, outside the recommendation, with an escalation note on a Blocker, unless the security
  reviewer shows that the change newly calls the vulnerable code
- `fix reported: <version>` is the version the advisories name, matched again against every advisory for
  that library; it ends with `(not checked against every advisory: one could not be evaluated)` when
  one of them could not be read for that version. It is not a claim that the release exists, can be
  downloaded or is the lowest safe one. `no fixed version in the advisory data` means none of the
  advisories names one

The status line, the first line of every report:

```
Dependency audit: pass (introduced: 0 Blocker, 0 Major, <n> Minor; attribution unknown: <n>; accepted: <n>; pre-existing: <n>; <n> dependencies in <n> modules; advisory data published <date>; coverage complete)
Dependency audit: fail (the same fields, the last coverage complete or coverage partial (<category>: <what to do>))
Dependency audit: not run (<category>: <what to do>)
Dependency audit: off (configuration: <source>)
Dependency audit: pending
```

Exit status: 0 pass or off; 2 fail; 69 not run; 3 the snapshot no longer matches the tree; 64 a usage
error, an invalid setting included; 1 an internal error. The review report's `Quality gate:` line ends
with the audit's status line, character for character, the off line included; when the audit printed
none, with the gate as recorded, `dependency-audit not run (<reason>)`. Every line of the four blocks
becomes a finding (rule `JAVA-DEP-01`, source `dependency audit`) or a pre-existing note; none is
dropped, and a partial result keeps what it found.

### Accepting an advisory

Only you accept an advisory, in the conversation: name its id (`GHSA-...`) or its CVE alias, for example
"accept GHSA-xxxx-xxxx-xxxx for this change". The skill runs the audit again with `--accept <id>` for
every advisory you have accepted so far. The new result supersedes the failed one, the entry moves to
*Accepted by the user*, and its finding is recorded as deferred with your words. The skill never accepts
one on its own judgment. An acceptance is an argument of that audit run: it holds for the review and its
fix rounds and is saved nowhere, so the next review reports the advisory again. An accepted id that
matches no entry is listed under *Could not be evaluated*.

### The `dependency_audit` setting

`dependency_audit`: `on` (default) or `off`. In `/config` it is the plugin's "Dependency audit" row
(`/plugin configure implement-from-spec@implement-from-spec` opens the same dialog). From the shell, with
Claude Code 2.1.285 or later:

```
echo '{"dependency_audit": "off"}' | claude plugin configure implement-from-spec@implement-from-spec --values-stdin
```

With `off`, the audit and the plan's dependency check do not run, nothing is recorded as missing, the
report's `Quality gate:` line ends with `Dependency audit: off (configuration: <source>)`, and a review
can be complete without the audit. The
review then no longer tells you about a vulnerable dependency a change adds: keep it on unless another
check of every change covers that.

The value comes from the first source that sets it:

1. A flag on the script, `--dependency-audit on|off`. The review skill adds `--dependency-audit on` only
   when you ask, in the conversation, for the audit of a review although your saved option is `off`; it
   never adds `off`
2. The environment: `IMPLEMENT_FROM_SPEC_DEPENDENCY_AUDIT`, `EVAL_IMPLEMENT_FROM_SPEC_DEPENDENCY_AUDIT` or
   `CLAUDE_PLUGIN_OPTION_DEPENDENCY_AUDIT`, which can switch the audit **on** only, over a saved `off`
   too, for example for one session
3. Your saved plugin options (`pluginConfigs`) in the managed settings file, else in your user
   `settings.json`. Like Claude Code, the script ignores `pluginConfigs` in project and local settings
4. The default, `on`

So only you switch the audit off: in your saved plugin options, or with the flag when you run the
script yourself. An `off` that arrives through the environment is not obeyed, because a repository's
committed `.claude/settings.json` can set variables in its `env` block once you trust the folder; the
audit is recorded as not run (`setting not obeyed`, naming the variable) and verification is
incomplete. The same holds for a saved `off` in a settings file that lies inside the repository under
audit. A value other than `on` or `off` is a usage error, never taken as either, and the audit is
recorded as not run.

To leave the audit out of one review, ask in the conversation ("skip the dependency audit"): it is not
run, the registration's not-run record stands, and the report says verification incomplete.

**Residual risk.** The advisory data is found from `HOME` alone, which a repository's settings cannot
move: Claude Code drops `HOME`, `TMPDIR` and the `XDG_*` variables from the `env` block of project and
local settings (settings reference, "Variables Claude Code ignores in `env`", read 2026-11-24). A
repository whose settings you trust can still define hooks, which run its own code with your
permissions and could write a copy into the cache; that is the trusted-folder risk of the threat model
(TM-45). The `Data:` line shows what the cache records about the data (where it says the data came
from, its publication date and its count); a process that can write the cache can write that record
too, so the line does not reveal such a copy, and the minimum advisory count alone does not stop one
built on purpose (see "The advisory data"). Read a repository's `.claude/settings.json` before you trust
it.

### Machines without internet access

Download `https://osv-vulnerabilities.storage.googleapis.com/Maven/all.zip` on a machine that can reach
it, copy the file across, and import it:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" refresh --from <path>/all.zip
```

`--from` also takes a directory of the export's JSON records; `--from` with no path is a usage error. In a gated session (one that started an
implementing skill), Claude Code asks you before the import (see "What asks first"). An import passes the
same checks as a download, the limits and the minimum included; its publication date is that of its
newest record, and the `Data:` line says `import` and names the file. An import counts as checked on the
day you make it: the audit uses it for 24 hours without contacting the server, then for up to 7 days with
a note that the server could not be reached, and after that it does not run until you import a newer copy. When you run the script
yourself, `--cached-data` keeps it from contacting the server at all. The build tool needs the project's
dependencies in its local repository or cache too, with Maven's dependency plugin, or with Gradle the
plugins the build applies and the wrapper's distribution: build the project once where they can be
downloaded.

### When the audit does not run

The status line names the category and the one action that remedies it, with your project's paths
filled in; the gate is recorded as not run and verification is incomplete. The skill never replaces a
not-run audit with another scanner or a web lookup: that result would not be this gate's.

Each category below is followed by its remedy as the line prints it, `<dir>` standing for the project
directory and `<log>` for the build output file. When the project has both builds, the remedy opens
with `the Maven build: ` or `the Gradle build: `, naming the build it is about, and ends with
``; if the project builds with Gradle only, `--build-tool gradle` audits that build alone`` (or the same
words for Maven), for a project that keeps the build files of a tool it no longer uses. A gap of the
other build is listed under *Could not be evaluated* as `the <tool> build: <category>: <remedy>`, with
the same ending.

Advisory data:

- `no advisory data`: `<reason>`; run `dependency-audit.py refresh` with network access, or
  `refresh --from <zip>` with a copy of the export. `<reason>` is `--cached-data` when the server was not
  to be asked, else `the refresh failed: <why>`
- `advisory data too old`: last checked `<date>`, more than 7 days ago (`<reason>`); run
  `dependency-audit.py refresh` with network access, or `refresh --from <zip>` with a copy of the export
- `advisory data missing`: the published dataset is gone: run refresh
- `advisory data unreadable`: run refresh
- `advisory data too small`: `<n>` advisories, fewer than the minimum of 5000 or than the cache records:
  run refresh
- `advisory data digest mismatch`: the dataset changed after it was validated: run refresh
- `advisory cache refused`, for the cache directory or a file in it:
  - `<path>` is a link or not a directory: remove it and run refresh (for a file: not a regular file)
  - `<path>` belongs to another user: remove it and run refresh
  - `<path>` can be written by other users: run `chmod go-w <path>`, then run refresh
  - `<path>` has another name (a hard link): remove it and run refresh (a file only)
  - `<path>` resolves inside the repository under audit: run the audit with HOME set to your own home
    directory
  - `<path>` cannot be created (`<reason>`): create it as a directory of your own, then run refresh
- `build output directory refused`: the same forms for the directory that holds the build tool's
  output, with run the audit again where the cache's end in run refresh
- `advisory cache busy`: another refresh holds its lock: run the command again
- `advisory data not refreshed`, from `refresh` only: `<why>`; the dataset published before, if any, is
  unchanged

`<why>`, here and after `the refresh failed: `, names what was refused, with sizes in MiB: for example
`the server answered with a redirect (302), which is never followed`, `the download is larger than 128
MiB`, `no complete answer within 120 seconds`, `HTTP 403`, `an entry larger than 4 MiB`, `more than 1024
MiB in all`, `a record that is not JSON` or `4980 usable advisories, fewer than the minimum of 5000`.

Build tool and project:

- `build tool missing`:
  - install Maven (/implement-from-spec:setup offers it), then run the audit again; for a Gradle build,
    install Gradle (/implement-from-spec:setup offers it), then run the audit again
  - the mvn on PATH (`<path>`) resolves inside the repository and is never run: install Maven outside
    it; for a Gradle build, the gradle on PATH (`<path>`) resolves inside the repository and is never
    run: install Gradle outside it
  - `<program>` did not start (`<reason>`): install the build tool again (/implement-from-spec:setup
    offers it), then run the audit again
- `wrapper not provisioned`, when the distribution the project's wrapper names is not on the machine:
  - Maven, only when there is no `mvn` on PATH to fall back to: run `./mvnw -v` in `<dir>` once with
    network access, then the audit again
  - Gradle, which does not fall back to PATH, because another Gradle version may not configure the
    build: run `./gradlew --version` in `<dir>` once with network access, then the audit again
- `plugin not in the local repository` (Maven's dependency plugin, or a Gradle plugin the build applies)
  and `artifacts not in the local repository` (a dependency, a parent or an imported BOM):
  - Maven: run `mvn -B dependency:tree` in `<dir>` once with network access, then the audit again
  - Gradle: run `./gradlew help` in `<dir>` once with network access, then the audit again
    (`gradle help` when the project has no wrapper)
  - Maven, `artifacts not in the local repository` only, when the build succeeded without the POM of a
    dependency: Maven could not find the POM of `<dependencies>` offline, so the dependencies declared
    there are not in the inventory: run `mvn -B dependency:tree` in `<dir>` once with network access,
    then the audit again
- `invalid project`:
  - Maven: the build tool could not read the project: fix it (its output is at `<log>`)
  - Gradle: Gradle could not configure the build: fix it (its output is at `<log>`)
- `build tool failed`:
  - mvn exited `<code>`: see its output at `<log>`; for a Gradle build, gradle exited `<code>`: see its
    output at `<log>`
  - its output passed 64 MiB: see `<log>`
  - this Gradle cannot run on the Java it started with: set JAVA_HOME to a Java it supports (its output
    is at `<log>`)
  - the plugin's `<path>` is missing: reinstall the plugin (its Gradle init script)
- `time limit`, both forms naming both limits (see "The dependency audit"):
  - the build tool did not finish within `<n>` seconds: raise --timeout, the limit of each build-tool
    run, or --total-timeout, the limit of the whole audit. `<n>` is the smaller of `--timeout` (120 by
    default) and what was left of `--total-timeout` (480 by default)
  - the audit reached its total limit of `<n>` seconds before `<tool>` resolved the candidate (or the
    base, or `with profile <id>`): raise --timeout, the limit of each build-tool run, or
    --total-timeout, the limit of the whole audit
  - the audit reached its total limit while another refresh held the advisory cache: raise --timeout,
    the limit of each build-tool run, or --total-timeout, the limit of the whole audit
  - when the time runs out while the base is resolved, the audit still ends with the candidate's
    result: the `Resolution:` line reads `base: not resolved from <revision> (time limit): every entry
    is attribution unknown`, and every entry counts as the change's
- `partial coverage`: the result does not cover the whole build. The vulnerabilities found are still
  reported, and still fail the gate: the status line is then `fail (...; coverage partial (partial
  coverage: <remedy>))` and the coverage gate is not run. The remedy names the gap:
  - Maven: Maven could not read the POM of `<dependencies>`, so the dependencies declared there are not
    in the inventory: its reason is in the build output at `<log>`; fix or replace that dependency, then
    run the audit again
  - Maven: not every module of the build has a parsed dependency tree: see `<log>`
  - Maven: `.mvn/maven.config` (or `MAVEN_ARGS`) passes `<option>`, which makes Maven build only part of
    the project, so the tree would cover only that part: remove it, then run the audit again. `<option>`
    is the long name (`--non-recursive`, `--projects`, `--resume-from` or `--file`); any form Maven
    reads is refused, short or long, one or two leading dashes, and with its value attached or after `=`
    (`-N`, `-pl`, `--pl=app`, `-ffoo.xml`, `--file=foo.xml`)
  - `snapshot does not cover the build`, every `--files` review: the snapshot holds the files named with
    --files only, and any other file of the working tree, one created later included, can change what the
    build resolves without the snapshot showing it: take a snapshot of the working tree or of a commit
    range to audit the dependencies. The vulnerabilities found are still reported and still fail the
    gate, and a clean result reads `not run`, never `pass`
  - Maven: the build has no profile `<profiles>`: name a profile it defines, then run the audit again
  - Maven: the build configures the dependency plugin's tree goal (`<parameters>`) for `<modules>`,
    which narrows what it lists: remove that configuration, then run the audit again
  - Maven: Maven printed no configuration of the tree goal for `<modules>`, so a filter on what it
    lists cannot be ruled out: see `<log>`
  - Maven, for a profile you named: the remedy opens with `with profile <id>: `
  - Gradle: the build includes other builds, which are not audited: audit each with
    `audit --repo <its directory>`
  - Gradle: `<n>` dependencies did not resolve offline: run `./gradlew <tasks>` in `<dir>` once with
    network access, then the audit again; one that still does not resolve is an error in the build.
    `<tasks>` is the `dependencies` task of up to five of the projects concerned (`:dependencies`,
    `:app:dependencies`), and the command is `gradle` when the project has no wrapper. When the audit
    read a repository without its artefact-only metadata source (see "Gradle"), the line goes on: or a
    module without metadata in a repository the audit reads without its artefact-only metadata source
    (`<repositories>`), whose dependencies no metadata lists: publish it with a POM or Gradle module
    metadata
  - Gradle: the resolution of `<n>` configurations failed: see `<log>`
  - Gradle: the build gives `<repositories>` its artefact-only metadata source back after the audit took it away,
    so a module without metadata may be listed without its dependencies: stop the build from adding
    artifact() to metadataSources, then run the audit again
  - Gradle: `<n>` configurations were resolved while the build had given a repository its artefact-only
    metadata source back, before the audit could take it back: stop the build from adding artifact()
    to metadataSources, then run the audit again
  - Gradle: `<n>` projects kept adding configurations while they were walked: see `<log>`
  - Gradle: `<n>` dependency results of a kind the audit cannot read were not walked: check those
    dependencies by hand (the build output at `<log>` names their configurations)
  - Gradle: the build declares the flat-directory repository `<repositories>`, whose artefacts have no
    metadata to list their dependencies: move them to a repository with POMs or Gradle module metadata,
    then run the audit again
  - Gradle: `<n>` components that are neither a module nor a project cannot be matched against
    advisories: check them by hand (the build output at `<log>` names them)
  - Gradle: `<n>` projects of the build reported no dependency graph: see `<log>`
  - Gradle: the build printed no complete dependency graph: see `<log>`
  - A written-out revision: `<n>` links that leave `<revision>` or cannot be written, and `<n>`
    submodules of it, were not written out, and the build could read them: check the revision out and
    run `audit --repo` on that working tree

  `<dependencies>` names up to three dependencies as Maven does,
  `group:artifact:type[:classifier]:version`, then `and <n> more`; `<repositories>` names repositories
  as `<name> of project <path>` or `<name> of the settings`. A Gradle build with several gaps gets the
  remedy of the first in the order above, and *Could not be evaluated* lists every gap (see "Maven" and
  "Gradle")
- `no build file`:
  - no pom.xml, no Gradle build and no Python lock, pin or dependency declaration file in `<dir>`: name
    the directory that holds one with --project-dir (a directory with neither Java build files nor Python
    sources; Python sources alone are audited as a Python project, see `docs/user-guide/python.md`)
  - no pom.xml in `<dir>`, which --build-tool maven names: name the build tool whose build files the
    project holds; for `--build-tool gradle`, no Gradle build in `<dir>`, which --build-tool gradle
    names: name the build tool whose build files the project holds

The review and the commit to audit:

- `pasted diff`: a pasted diff has no project to resolve: review a working tree or a commit range to
  audit its dependencies
- `revision too large`: `<n>` files and `<size>` at `<revision>`, over the limit of 100000 files or 256
  MiB: check it out and run `audit --repo` on that working tree (`<size>` in MiB, such as `301.4 MiB`)
- `revision cannot be read`:
  - git ls-tree cannot read `<revision>` (`<git's message>`): fetch that revision into the repository,
    then run the audit again
  - git cat-file did not return object `<object>` (`<reason>`): run `git fsck` in the repository, repair
    what it reports, then run the audit again
- `revision cannot be written`:
  - an entry of `<revision>` would leave the scratch directory: check it out and run `audit --repo` on
    that working tree, where git refuses such an entry
  - `<file>` of `<revision>` (`<reason>`): check it out and run `audit --repo` on that working tree
  - `<a>` and `<b>` of `<revision>` differ only in letter case or Unicode normalisation, which the
    scratch directory's file system does not tell apart: set TMPDIR to a directory on a case-sensitive
    volume, then run the audit again
- `snapshot does not cover the build`: the snapshot holds the files named with --files only, and the
  build also reads `<files>`, which could change without the snapshot showing it: take a snapshot of
  the working tree or of a commit range to audit the dependencies (the audit does not run); a snapshot
  that holds every build input still gives a partial result (above)
- `scratch directory refused`: the temporary directory resolves inside the repository: unset TMPDIR
- `setting not obeyed` (see "The `dependency_audit` setting"):
  - `<variable>=off` in the environment is not obeyed: unset it, or switch the audit off in your own
    plugin options
  - the settings file `<path>` lies inside the repository under audit, so its off is not obeyed: switch
    the audit off in your own plugin options
- `attachment failed` or `gate not recorded`: the report could not be attached to the review snapshot, or
  its result recorded; the line gives the reason. The skill runs the audit once more; when the tree
  changed, run the review again
- `registration failed`, on the preparation's line
  `Required gate: dependency-audit not run (registration failed: <why>)`: the script could not start or
  stopped with an error when the review was prepared

### Maven

The result is complete only when Maven ended successfully, every module of the build gave its
dependency tree and Maven read the POM of every dependency. When Maven cannot find a dependency's POM
offline, or finds it and cannot read it, it warns, and the build still succeeds, with the dependency in
the tree and nothing below it:

```
The POM for <dependency> is missing, no dependency information available
The POM for <dependency> is invalid, transitive dependencies (if any) will not be available
```

The audit reads those warnings, so what that POM declares counts as missing: a POM not found offline is
`artifacts not in the local repository`, one Maven could not read is `partial coverage` (see "When the
audit does not run"). *Could not be evaluated* names each such dependency, up to 20, then how many
more, and each module whose tree could not be read:

```
- module <module>: the POM of <dependency> was not found offline, so the dependencies declared there are not in the inventory
- module <module>: the POM of <dependency> could not be read, so the dependencies declared there are not in the inventory
- <n> more dependencies without dependency information (the build output names them)
- module <module>: no dependency tree was parsed
```

The `module <module>: ` part is left out when Maven warned before the first module's section of its
output.

When you name a profile, a dependency's scope names each build that held it, separated by commas, after
the Maven scope: `compile: default, profile-it` for a dependency the default build and the `it` profile
both resolve at the `compile` scope. A dependency only one of them resolves names only that one.

### Gradle

Gradle projects are audited on the same terms as Maven projects; "How it works" gives the command and
which Gradle runs. A wrapper that keeps its distribution anywhere but the Gradle user home (a
`distributionBase` or `zipStoreBase` other than `GRADLE_USER_HOME`) counts as not provisioned, because
that copy would be a program inside the project, and so does a distribution unpacked from another URL. With
a `distributionSha256Sum`, an archive still beside the completion marker must match that digest; once the
wrapper has unpacked the distribution it deletes the archive it checked, so a marker and an unpacked
distribution with no archive left count as provisioned without checking the digest again.

**Repositories, for the audit's run only.** A Maven or Ivy repository may resolve a module from its
artefact alone (`metadataSources { artifact() }`), and a module with no metadata then resolves as one
with no dependencies, which the resolution result does not show. So for the audit's run the init script
reads every Maven and Ivy repository of the build's projects, and from Gradle 6.8 those of the
settings' `dependencyResolutionManagement`, without that artefact-only source, keeping the POM, Ivy
descriptor and Gradle module metadata sources it had: such a module is unresolved, and the result
partial. A flat-directory repository (`flatDir`) holds artefacts only, so declaring one makes the result
partial. The `buildscript` and `pluginManagement` repositories stay as the build declares them: they
serve build plugins, which are outside the inventory, and without the artefact-only source a plugin held
as an artefact alone would stop the build. Your build files are not changed.

Each entry names its module as `project <path>` (`project :` for the root project) and its scope as a
context, followed by up to three of the configurations that hold the dependency. The context comes from
the configuration's name as Gradle's Java plugins form it:

- `test`: a name with the word test in it (`testRuntimeClasspath`, `integrationTestCompileClasspath`,
  `testFixturesRuntimeClasspath`)
- `build`: an annotation-processor path (`annotationProcessor`, `<source set>AnnotationProcessor`) or
  kapt
- `ship`: a runtime classpath (`runtimeClasspath`, `<source set>RuntimeClasspath`)
- `compile`: a compile classpath (`compileClasspath`, `<source set>CompileClasspath`)
- `other`: any other resolvable configuration

A dependency held in several configurations takes the most exposed context, in the order `ship`,
`other`, `compile`, `build`, `test`. `ship` and `other` count as shipping when the audit compares the
change with its base, so a configuration the naming conventions do not place is never taken for one
that stays out of the product: a dependency that moves into one of them from a compile, build or test
configuration is the change's. The context never lowers the class.

The result is complete only when Gradle ended successfully, every project of the build reported its
whole graph, no dependency stayed unresolved, no configuration failed to resolve, no dependency result
was of a kind the audit cannot read, every component was a module or a project, every line the init
script printed could be read, and the build declares no flat-directory repository and includes no
other build. Otherwise it is `partial coverage`: it keeps what it found and lists each gap under *Could
not be evaluated*, in these forms:

```
- included build <name>: not audited (the builds a composite includes are not)
- project <path>, <configuration>: <dependency> did not resolve
- <n> more unresolved dependencies (the build output names them)
- flat-directory repository <name> of <owner>, whose artefacts have no metadata to list their dependencies
- repository <name> of <owner> was read without its artefact-only metadata source, so a module it holds without metadata does not resolve in the audit
- project <path>: did not report its whole dependency graph
- project <path>, <configuration>: its resolution failed (<exception>)
- project <path>, <configuration>: a dependency result of a kind the audit cannot read (<class>) was not walked
- project <path>: <n> components that are neither a module nor a project could not be matched against advisories
- <n> lines of the init script's output could not be read
```

Unresolved dependencies are listed up to 20, then counted; repositories up to 20. The line for a
repository read without its artefact-only source comes only when a dependency did not resolve, since
it may explain why. `<owner>` is `project <path>` or `the settings`. An included build
(`includeBuild`, a composite build) is not audited: audit it on its own with
`audit --repo <its directory>`. `buildSrc`, which holds build logic as the buildscript classpath does,
is not audited either.

### Limits

- **No reachability.** An entry says a matching version is in the inventory; only the security
  reviewer's usage findings show that the vulnerable code is called
- **One dataset.** The GitHub Advisory Database records the OSV export carries; a clean result means "no
  matching advisory in this dataset"
- **What is resolved.** The default build configuration and the Maven profiles you name (ask in the
  conversation; the skill passes `--profile <id>`), each profile in a run of its own. Other profiles, and properties set only on a CI
  command line, are not audited; build plugins (Gradle's buildscript classpath included), Maven
  annotation-processor paths, Gradle file dependencies, shaded content and Gradle included builds are
  outside the inventory, and an included build or a flat-directory repository makes the result partial.
  A project holding a `pom.xml` and a Gradle build is resolved with both unless you name the build tool
- **Patched forks.** A library your organisation patched and republished with its own version suffix is
  matched by the advisory's range and may be reported although it is fixed. The report line gives the
  basis of the match, and you can accept the advisory
- **Release lines past their open-source support.** For such a line, the fixed release an advisory
  names may be published only to commercial support customers. On 2026-11-24 every Spring Boot 3.x line
  was past its open-source support (3.5.x ended in June 2026; the current line is 4.2), and recent
  advisories name fixes for 3.5.x that come with enterprise support only: CVE-2026-59414, for example,
  names 3.5.18, while the project page lists 3.5.16 as the newest 3.5 release (spring.io project and
  security pages, read 2026-11-24). The audit reports the fix the advisory names and cannot tell whether
  you can download it. When you cannot, or when it reports no fixed version, the choices are an upgrade to
  a supported line, a commercial support release, or accepting the advisory. The security reviewer
  flags a release line past its support from a dated table in its catalogue (`JAVA-DEP-02`), not from
  the advisory data
- **Authenticity.** Nothing authenticates the export beyond HTTPS and its publisher, and the minimum
  advisory count does not stop a copy built on purpose (see "The advisory data")

## The dependency check at plan time

Before it asks for your approval, the implementing skill matches the coordinates of every new dependency
and plugin the plan names against the same advisory data, in one call:

```
python3 -I "<plugin-root>/core/scripts/dependency-audit.py" check <group:artifact:version> ...
```

It resolves nothing and writes only to the advisory cache, outside the project, so it runs before
approval. It prints `Dependency check: <n> of <m> coordinates match an advisory (named coordinates only:
transitive dependencies are not seen)`, one line per coordinate and the `Data:` line, and exits 0 with no
match, 2 with a match and 69 when it could not check. The plan records each result beside its
dependency:

- No match: "no advisory matches this coordinate in the dataset of <date>"
- A match is never resolved silently. A version the specification or the project asked for stays in the
  plan, and the match becomes an open question with the reported fix as the recommended answer, which
  `approve` accepts; when the advisories name no fixed version, the options are another library or the
  version as asked, with a recommendation and its reason. When a specification item states the version,
  the draft under `ai-planning/<slug>.spec/` carries that item changed to the reported fix, recorded under
  `## Specification changes` and covered by the plan's draft digest, so `approve` accepts the answer and
  the item's change together (see "The specification"). A version the plan chose itself is replaced by
  the reported fix, on a `Needs your approval:` line that names the match
- "not checked", with the reason: no advisory data, the audit switched off, a version a BOM manages that
  no build file states, or your request to skip the check. The review's audit covers it after
  implementation

What a clean check does not show: that the version exists, is maintained or is compatible, or anything
about the library's own dependencies. A vulnerable transitive dependency of a new library is found by the
review's audit after implementation and fixed in a fix round, as an amendment you approve.

## The report

The run ends with the report of contract section 11: the items in scope and whether each was verified,
what changed, every check with its result, the `spec-trace code` counts, the review outcome (snapshot,
change digest, review state, findings fixed, rejected, covered by gate and open, fix rounds,
and the external reviewer's `External review: <state>
(<reason>)` line verbatim), files withheld from the external reviewer, findings that need runtime
verification, the rulings the skill made, amendments, deferred items, the status (`implementation
complete` or `verification incomplete (<what is missing>)`), and the next steps for the operator. For Java
the checks line names each build command, the static analysis and the smoke call with their results, and
the review's `dependency-audit` entry as its `Quality gate:` line gives it; the next steps give the deploy
command the skill did not run.

## Reviewing a change on its own

```
/implement-from-spec:reviewing-java-changes . main..HEAD
```

The arguments are the repository and a git range or a file list, optionally `--plan
ai-planning/<slug>.plan`. A pasted diff works too, without a dependency audit. The skill runs the
project's tests and then the dependency audit while the reviewers work, verifies every finding against
the code, sets severity itself, and returns one Blocker, Major, Minor and Nit report with a concrete fix
per finding, opening with the review state block (snapshot, recommendation, verification, approval
required, risk, rollback; see
[external-review.md](external-review.md#the-review-around-it-snapshot-isolation-state-and-fix-rounds)).

## Out of scope

- Infrastructure templates and CDK apps: [cloudformation.md](cloudformation.md), [cdk.md](cdk.md)
- A security audit of a whole code base: the security reviewer covers the change and what it makes
  reachable, and the dependency audit matches versions against one advisory dataset
- Open-ended design discussion: write a spec first
- Deploying
