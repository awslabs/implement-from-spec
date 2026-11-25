# Python review: the dependency audit's entries

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

The audit reads the project's lock and pin files as data: `uv.lock`, `poetry.lock`, `pdm.lock`,
`pylock.toml` (and `pylock.<name>.toml`), `Pipfile.lock`, and the requirements files in every directory
under the project directory, with every file they name through `-r` or `-c` — each lock or pin file is a
module, not only the ones at the top. A requirement counts when it is pinned with `==` or `===` or a
constraint file of the same install pins it with `==` and no marker; a constraint to a URL, a VCS or a local
path makes it `packages not evaluated`, and an option pip does not read, on its own line or after a
requirement (where only `--hash` and `--config-settings` are allowed), makes the file `requirements not
read`. No installer, resolver or build backend runs and nothing is
imported, so the inventory needs no environment. Every package of every group, extra and platform counts,
because environment markers are not evaluated. Not in it: the interpreter, the project's own packages,
what a package from a VCS, a URL or a local path holds (each is listed under *Could not be evaluated*),
and vendored or copied code. `pyproject.toml`, `setup.cfg`, `setup.py` and `Pipfile` are declarations:
they never become a module, but decide coverage. A declaration with no lock or pin file covering its
directory (or the nearest one above it) keeps the audit from running (`no lock file`); a declaration whose
covering lock or pin file does not list it reads `lock file out of date` instead (every main dependency,
one an environment marker narrows included, whose remedy then names one pin file per platform or a lock file
for every platform; groups and extras only against a lock file), and also marks the covering modules'
coverage partial. A `setup.py` is read with `ast`, never run: its literal `install_requires` and
`extras_require` are compared, and one that builds them in code, a dynamic field the audit does not read or
a `pyproject.toml` that does not parse reads `declarations not read` (the first two only when no lock file
that locks every group covers the declaration). python3 3.11 or later (`tomllib`) is needed only to read a TOML lock
file, a `Pipfile`, or a declaring `pyproject.toml`; on an older interpreter that side alone is not run
(category `interpreter`), while requirements files, `Pipfile.lock` and a `setup.cfg` are still read. A
repository with Python sources and none of these files passes with no module and a coverage field naming
the absence (`coverage complete (no third-party Python dependency declared)`) and loads no advisory data
(without a cache the data field reads `advisory data not needed (no package to match)`); every block is
then `- none`, which says only that nothing is declared. Beside a Java build the PyPI side adds only the
note `(PyPI: no third-party Python dependency declared)` to the Java result. The security reviewer covers
what such a project can still ship: third-party imports nothing declares (PY-DEP-10) and packages the
runtime or a layer provides (PY-DEP-11); a lock or pin file the change removes is in the diff (PY-DEP-04).

The audit's own limits can also leave the result partial or not run: `lock file too large` (more than
100,000 packages in one file, or in all, of the per-side cap), `requirements file too large` and `too many
Python dependency files` (the per-run budget of 200 files and 64 MiB), `file not read` (a file missing,
outside the candidate, over 16 MiB, a broken or too-long link, or not UTF-8), `include not followed` (an
`-r` or `-c` line naming a URL, a path outside the repository, a file not in the candidate, or nesting
past 16 levels), and `time limit` (the audit's deadline reached, checked before each file is read and while the
dependencies are matched, so the run ends close to `--total-timeout`). The text report lists at most 10
advisories an entry and 500 entries a block, the JSON report 100 and 5,000, each cut said where it applies;
the status line's counts are of everything, so a finding is never dropped by the cut. Each gives its remedy on the
report's `not run` or `coverage partial` line (SKILL.md step 3); their *Could not be evaluated* notes name
the file and, where it applies, the line.

After the status line come one `Data:` line per ecosystem used (Maven first when the repository also has
a Maven or Gradle build, which the audit then resolves as well), each ecosystem's `Resolution:` and
`Inventory:` lines, then five blocks, each headed `<name> (<count>):` with one `- ` line per entry or
`- none`. The PyPI `Resolution:` line names the lock and pin files read, the project directory, the
candidate (the working tree or a revision) and the modules with their coverage, and ends with the base:
`base: read from <rev>`, `base: read from <rev>; <n> of its modules not read whole, whose entries are
attribution unknown`, `base: read from <rev>: no Python lock, pin or declaration file there` (every entry
introduced), or `base: not read from <rev> (<category>): every entry is attribution unknown`.

An entry of the first four blocks is one vulnerable occurrence, on one line:

    - module <file>; pypi:<name>==<version> (<scope>[: <groups>]); path: <file> > <name>==<version>; advisories: <ID> (<aliases>) <SEVERITY> <class>[ unsure] [<basis>], ...; fix reported: <version>[ (not checked against every advisory: one could not be evaluated)]

with `no fixed version in the advisory data` in place of `fix reported: <version>` when the advisories
name none. The module is the lock or pin file's repository-relative path; the scope is `lock`, `pin` or
`constraint`, followed by the groups, extras or Pipfile sections the file names. Advisories that are
aliases of each other are one entry: the id shown is the one that decides the class, the others follow it
in parentheses. A PYSEC record without a severity word takes the word of the GHSA record it is aliased
with (`HIGH (from GHSA-...)`), else the rating of its CVSS v3 base score (`CRITICAL (from CVSS 3.1 9.8)`).
The class (Blocker, Major or Minor) is the script's, from that word, and is not re-graded: the scope or
group (`dev`, `test`) is reported and never lowers it. `unsure` stays on the finding: a severity word the
script does not know, an advisory it could not evaluate against the version (a range PEP 440 cannot
order), or a local version (`2.5.1+cpu`), which is matched as itself and as its public version because a
local build may carry a backported fix. The reported fix is the version the advisories name, checked again
against every advisory for that package; it does not show that the release exists or is the lowest safe
one, so a Fix never claims either. When an advisory for the package could not be evaluated at that
version, the fix carries `(not checked against every advisory: one could not be evaluated)`: the version
may still match that advisory, and the Fix says so.

An entry means a version matching an advisory is in the inventory, not that the vulnerable code is
called: the audit has no reachability analysis. Only a usage finding shows a call, so word the finding
that way. A `MAL-` record (a malicious package) is a Blocker whether or not it is called, because a
package can run code while it is built and after it is installed (PY-DEP-01).

## 2. Entries become findings

Every entry of the four blocks becomes one finding, a not-run result's included (a partial result keeps
what it found); none is dropped:

- *Introduced by this change* and *Attribution unknown*: a finding of the change, dimension
  Safety/security, check PY-DEP-01, source `dependency audit`, with the class the report gives. An
  unknown attribution counts as the change's because nothing shows the base had it, which is also why it
  fails the gate. Its `<file>:<line>` is the line that brings the package in, found by reading the files,
  never invented: the requirement line of a pin file, or for a lock file the declaration in
  `pyproject.toml` (or `Pipfile`, `setup.cfg`) of the direct dependency that pulls it in, else the lock
  file's entry for the package. Its Evidence is that line and the report line; its Fix is the reported
  fix through the project's mechanism (the version in the declaration or constraint and the lock
  regenerated with the project's tool, with its not-checked note when the line carries one) or, on "no
  fixed version in the advisory data", a specific question: replace or remove the library, or accept the
  advisory (section 3). A `MAL-` entry's Fix removes the package and says that every machine that
  installed it is exposed
- Search the change for imports of and calls into the package. A reviewer's usage finding merges into
  the entry's finding only when it shows a call into the code the advisory describes, not merely an
  import of the same distribution: one finding, the code path in its Evidence, source `dependency audit,
  Claude`, and the class the higher of the two. Accepting the advisory (section 3) defers only the
  advisory part; a usage defect that is not a call into the described code keeps its own finding and
  disposition
- *Pre-existing*: under *Pre-existing*, with an escalation note on a Blocker, unless a usage finding shows
  the change newly calls the vulnerable code. Exposure the change creates is the change's (SKILL.md step
  4, attribution), so the usage finding is then a finding of the change
- *Accepted by the user*: disposition `deferred: <the user's words>`, its class kept

Lines under *Could not be evaluated* are notes, never findings: a package from git, a URL or a path, a
requirement that is not pinned, a file the audit could not read; each has already kept the result from
passing with complete coverage. An entry is never `covered by gate`: the gate is where it comes from, and
that disposition would take a known vulnerability out of the report. The report shows these findings
under its usual caps; findings.md holds every one.

## 3. Accepting an advisory

Accepting is the user's alone, in this conversation, never your judgment, because it keeps a known
vulnerability in the change. When the user accepts one, run the audit again with `--accept <advisory id>`
(the id or any of its aliases) for every advisory the user has accepted so far in this review: acceptance
is an argument of each run, not a record, so a fix round's audit carries them too. The new result
supersedes the failed one, which no deferral could lift, since a failed gate keeps the review Blocked. The
accepted advisories move to *Accepted by the user*, deferred with the user's words; any other advisory of
the same package stays an entry of its block in the new report and stays a finding (the old F-number kept
open, or a new one), so an acceptance never defers more than the ids the user named. Then save the
findings, print the state block and send the report again, its `Quality gate:` line carrying the new
status line. A *Could not be evaluated* line `accepted id <id> matches no entry of this audit` goes to the
user: the advisory they meant is still open, under another id.

## 4. Fix rounds

A dependency finding's fix is the version change its Fix names, with the lock file regenerated by the
project's tool; the user may accept the advisory instead (section 3). Each round's audit runs on `<NEW>`
with every option this review's first audit run carried (every `--accept` the user gave, and any
`--project-dir`, `--ecosystem`, `--dependency-audit on` and `--total-timeout`) and by the same
interpreter, against the same base, since the preparation's arguments are the same. A dependency finding
is `closed` only when the round's report has complete coverage (the last field of its status line begins
`coverage complete`, which includes `coverage complete (no third-party Python dependency declared)` once
the last dependency is removed) and no longer lists it: a partial result, a fail ending `coverage partial
(...)` included, cannot show it is gone, and a not-run result never has complete coverage. Compare the
`dataset sha256` on the two reports' PyPI `Data:` lines: the script does not compare them itself. When
they differ, the advisory data changed between the rounds: say so in the round's section, and an entry the
earlier report did not list is a new finding under the next F-number. When the digests differ, the audit's
own comparison between the two reports closes an earlier entry on absence alone, package and version
unchanged included: the later report simply no longer lists it, with no re-check against the previous
dataset. The review does not take that at face value: keep such an entry `open` in the review, noted
"advisory no longer in the dataset (dataset changed)", for the user to accept or confirm; this is a rule
of the review, not something the audit enforces. A finding is confirmed closed in the review only when the
version itself changed, or the fix is otherwise confirmed.
