# Java review: the dependency audit's entries

Read this when the audit's report lists an entry, or when the user accepts an advisory (SKILL.md step 4,
item 5). Running the audit, its status lines and what each one means for the review state are SKILL.md
step 3; the report's `Quality gate:` entry is SKILL.md step 5. This file does not restate them.

## Contents

1. Reading the report
2. Entries become findings
3. Accepting an advisory
4. Fix rounds

## 1. Reading the report

The report is the text the audit printed. On a snapshot each attempt attaches
`<DIR>/gates/dependency-audit-<n>.txt`, with `input/dependency-audit-<n>.json` binding the same facts for
scripts; the authoritative one is the report the latest `dependency-audit` result names in its recorded
command (`(report gates/dependency-audit-<n>.txt)`, shown by `review-snapshot.py gates <DIR>`), never
simply the highest `<n>`: an attempt that stopped before recording leaves a report no result names, and
the gate then stays pending. A fail found in a partial inventory also records `dependency-audit-coverage`
as not run, so verification stays incomplete.

After the status line and its `Data:`, `Resolution:` and `Inventory:` lines come five blocks, each headed
`<name> (<count>):` with one `- ` line per entry or `- none`. The `Resolution:` line opens with the
build tool or tools and why, in one of these forms, the third for a project holding both builds:

    Resolution: build tool Maven (pom.xml found); ...
    Resolution: build tool Gradle (<files> found); ...
    Resolution: build tools Maven and Gradle (<files> found; each is resolved, and coverage is complete only when both are); ...
    Resolution: build tool Maven (named with --build-tool maven); ...

The line ends with the base, which every run resolves from its own revision: `base: resolved from
<rev12> with <build tool clause>`, or `base: not resolved from <rev12> (<category>): every entry is
attribution unknown`.

An entry of the first four blocks is one vulnerable occurrence, on one line:

    - module <module>; <group:artifact:version> (<scope>); path: <a> > <b> > <c>; advisories: <ID> (<CVE alias>) <SEVERITY> <class>[ unsure] [<basis>], ...; fix reported: <version>[ (not checked against every advisory: one could not be evaluated)]

with `no fixed version in the advisory data` in place of `fix reported: <version>` when the advisories
name none. When both build tools were selected, the module is followed by the tool that listed the
occurrence, `- module <module> (Maven); ...` or `- module <module> (Gradle); ...`: it says which
build declares the dependency, and the same library listed by both builds is two entries, one per build.
For Maven the module is its `group:artifact` and the scope the Maven scope; when the audit ran a
`--profile`, each profile in a run of its own beside the default build, the scope is followed by the
builds that listed the occurrence, `default` and `profile-<id>` (`compile: default, profile-it`). For Gradle the
module is `project <path>` (`project :` for the root project) and the scope is a context, then up to
three of the configurations that hold the dependency: `ship` (a runtime classpath), `compile` (a compile
classpath), `test` (a test configuration), `build` (an annotation-processor path) or `other` (any other
configuration, which counts as shipping). The class (Blocker, Major or Minor) is the script's, from the
advisory's severity word, and is not re-graded: the scope or context is reported and never lowers it.
`unsure` (a severity word the script does not know, or an advisory it could not evaluate against the
version, both Major) stays on the finding. The reported fix is the version the advisories name, checked again against
every advisory for that artifact; it does not show that the release exists or is the lowest safe one, so
a Fix never claims either. When an advisory for the artifact could not be evaluated at that version, the
fix carries `(not checked against every advisory: one could not be evaluated)`: the version may still
match that advisory, and the Fix says so.

An entry means a version matching an advisory is in the inventory, not that the vulnerable code is
called: the audit has no reachability analysis. Only a usage finding shows a call, so word the finding
that way.

## 2. Entries become findings

Every entry of the four blocks becomes one finding, a not-run result's included (a partial result keeps
what it found); none is dropped:

- *Introduced by this change* and *Attribution unknown*: a finding of the change, dimension
  Safety/security, check JAVA-DEP-01, source `dependency audit`, with the class the report gives. An
  unknown attribution counts as the change's because nothing shows the base had it, which is also why it
  fails the gate. Its `<file>:<line>` is the build-file line that declares the dependency at the root of
  the path, or the parent or BOM import that manages it (for Gradle, the project's `build.gradle` or
  `build.gradle.kts`, the version catalogue entry it names or the platform that manages it; the tool
  after the module, when there is one, says which build to read), found by reading the build file,
  never invented; its Evidence is that line and the report line; its Fix is the
  reported fix (with its not-checked note, when the line carries one) or, on "no fixed version in the
  advisory data", a specific question: replace or remove the library, or accept the advisory (section 3)
- Search the change for calls into the library. A reviewer's usage finding merges into the entry's
  finding only when it shows a call into the code the advisory describes, not merely the same
  `group:artifact`: one finding, the code path in its Evidence, source `dependency audit, Claude`, and
  the class the higher of the two. Accepting the advisory (section 3) defers only the advisory part; a
  usage defect that is not a call into the described code keeps its own finding and disposition
- *Pre-existing*: under *Pre-existing*, with an escalation note on a Blocker, unless a usage finding shows
  the change newly calls the vulnerable code. Exposure the change creates is the change's (SKILL.md step
  4, attribution), so the usage finding is then a finding of the change
- *Accepted by the user*: disposition `deferred: <the user's words>`, its class kept

An entry is never `covered by gate`: the gate is where it comes from, and that disposition would take a
known vulnerability out of the report. The report shows these findings under its usual caps; findings.md
holds every one.

## 3. Accepting an advisory

Accepting is the user's alone, in this conversation, never your judgment, because it keeps a known
vulnerability in the change. When the user accepts one, run the audit again with `--accept <advisory id>`
(the id or its CVE alias) for every advisory the user has accepted so far in this review: acceptance is
an argument of each run, not a record, so a fix round's audit carries them too. The new result
supersedes the failed one, which no deferral could lift, since a failed gate keeps the review Blocked.
The entry moves to *Accepted by the user* and its finding is deferred with the user's words. Then save
the findings, print the state block and send the report again, its `Quality gate:` line carrying the new
status line. A *Could not be evaluated* line `accepted id <id> matches no entry of this audit` goes to the
user: the advisory they meant is still open, under another id.

## 4. Fix rounds

A dependency finding's fix is the version change its Fix names; the user may accept the advisory
instead (section 3). Each round's audit runs on `<NEW>` with every `--accept` the user gave and any
`--profile` or `--build-tool` the user named, against the same base, since the preparation's arguments
are the same. A dependency finding is `closed` only when the round's report has complete coverage (its
status line ends `coverage complete`) and no longer lists it: a partial result, a fail ending `coverage
partial (...)` included, cannot show it is gone, and a not-run result never has complete coverage.
Compare the
`dataset sha256` on the two reports' `Data:` lines: the
script does not compare them itself. When they differ, the advisory data changed between the rounds:
say so in the round's section, and an entry the earlier report did not list is a new finding under the
next F-number. When the digests differ, the audit's own comparison between the two reports closes an
earlier entry on absence alone, coordinate and version unchanged included: the later report simply no
longer lists it, with no re-check against the previous dataset (a known limitation; see CHANGELOG). The
review does not take that at face value: keep such an entry `open` in the review, noted "advisory no
longer in the dataset (dataset changed)", for the user to accept or confirm — this is a manual rule of
the review, not something the audit enforces. A finding is confirmed closed in the review only when the
version itself changed, or the fix is otherwise confirmed.
