#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
dependency-audit.py — says, for the dependencies a Java or Python project resolves or locks, which match a
known advisory, how severe, which fix the advisories report, and whether the change under review introduced
them.

Owner: the implement-from-spec plugin. Owns one thing: the dependency audit of a Java or Python review and its
gate record `dependency-audit`. For Java the build tool lists the dependencies offline; for Python the lock and
pin files are read as data and nothing runs (dependency_audit_pypi.py). The script matches them against a local
copy of the public OSV export of each ecosystem (Maven, PyPI) and sends nothing about the project anywhere: its
only network use is one anonymous HTTPS download of each export, from one host. It never writes in the project.
In a review it attaches its two reports and records its gate through core/scripts/review-snapshot.py (loaded by
path), never by writing into a snapshot directory itself. What is not Maven's or Gradle's (the advisory data and
its store, matching, the classes, attribution and the reports) is dependency_audit_osv.py's, loaded by path.

Ecosystems. The files of the project directory choose them, as its build files choose Maven or Gradle: Maven for
a pom.xml or Gradle build files, PyPI for Python lock, pin or dependency declaration files in any of its
directories (dependency_audit_pypi.py names them; a pyproject.toml or setup.cfg that configures tools only
selects nothing), both when the directory holds both, each with its own data; --ecosystem maven|pypi audits one alone; --build-tool, which is Maven's, makes the project a
Java one as well, and --profile applies to the Maven build only. Python source files (.py, outside virtual
environments, installed or vendored package trees and build output) with no Python lock, pin or dependency
declaration file anywhere in the repository also select PyPI: such a project declares no third-party package (a
standard-library script, a Lambda function on the runtime's packages), so its PyPI part is complete with nothing to
match and never needs the PyPI data: nothing is downloaded and missing data cannot make it partial. Alone, it reads
"coverage complete (no third-party Python dependency declared)", with the cached PyPI data's date when a cache
exists, else "advisory data not needed (no package to match)" and "Data: none needed (no package to match)"; a base
that listed dependencies is named with its counts. Beside a Java build it adds only "(PyPI: no third-party Python
dependency declared)" after "coverage complete": the Java report is otherwise the one 0.3.0 printed. A directory with
neither Java build files nor Python sources stays not run (no build file). With two ecosystems, one that cannot
run counts as an incomplete result and the other's findings stay. A TOML lock file, a Pipfile and a declaring
pyproject.toml need python3 3.11 or later (tomllib); on an older interpreter a PyPI part that holds one is not run
(interpreter), while requirements files, Pipfile.lock and setup.cfg are read there, and the Java audit runs on
python3 3.9 as before.

Commands:
    register --snapshot DIR
        Called by review-prepare.py for a stack whose dispatch manifest lists the gate under required_gates.
        Records the gate as not run, "pending: the audit has not run for this snapshot", and prints
        "Dependency audit: pending"; a review with no later result is therefore incomplete. With the audit
        switched off by the user it records nothing and prints the off line.
    audit --snapshot DIR [--accept ID ...] [--profile ID ...] [--timeout SECONDS] [--total-timeout SECONDS]
          [--cached-data] [--project-dir PATH] [--build-tool maven|gradle] [--ecosystem maven|pypi]
        The review form. Verifies the snapshot, resolves the candidate (the working tree, or for a
        commit-range review the range's end commit written out from git), matches, compares with the base,
        attaches gates/dependency-audit-<n>.txt and input/dependency-audit-<n>.json (n is the attempt on
        this snapshot) and only then records the gate, naming the attempt's report in the recorded command.
        --accept takes an advisory id (or its CVE alias) the user accepted in this conversation, never one
        chosen on the caller's own judgment. --profile names a Maven profile to audit as well (Gradle has
        none). --timeout is the time limit of each build-tool run (default 120), --total-timeout that of the
        whole audit (default 480), below the longest a Bash tool command may run by default, so the audit
        always ends with a result: each run gets the smaller of --timeout and what is left, and once nothing is left
        the audit is not run (time limit). --cached-data never contacts the server. --project-dir is the
        directory holding the build file when it is not the repository root. --build-tool names the build
        tool the project uses, which then resolves it alone; without it a pom.xml is resolved by Maven, Gradle
        build files by Gradle, and a directory with both by both.
    audit --repo PATH [--base REV] [the options above]
        The same audit with no snapshot, report on standard output. Without --base nothing can be compared,
        so every entry is "attribution unknown" and counts against the result.
    check GROUP:ARTIFACT:VERSION|pypi:NAME==VERSION ... [--cached-data]
        The plan-time form: matches the named coordinates or PyPI pins only, with no resolution, one line
        each, then the data line of each ecosystem named. It does not show that a version exists or is
        maintained, and it cannot see transitive dependencies.
    refresh [--ecosystem maven|pypi] [--from ZIP-OR-DIRECTORY]
        Downloads the advisory data of the ecosystem (default maven), or imports a local copy of its export,
        and prints the data line.
Every command but refresh takes --dependency-audit on|off: the user's explicit setting for this run. off is for
a user who has switched the audit off, never a way to skip it for one review: a review whose audit is skipped
has a check that did not run, so the audit is not started and verification stays incomplete.

The setting dependency_audit (userConfig in .claude-plugin/plugin.json, default on) is read from the flag,
then from the user's saved plugin options (as core/scripts/spec-external-review.py reads them), then the
default. IMPLEMENT_FROM_SPEC_DEPENDENCY_AUDIT, EVAL_IMPLEMENT_FROM_SPEC_DEPENDENCY_AUDIT and
CLAUDE_PLUGIN_OPTION_DEPENDENCY_AUDIT can switch the audit on, never off: a repository's committed settings
can set the environment, so an off found there, or in a settings file inside the repository under audit, is
reported as not run and never obeyed (threat model TM-45, TM-46).

Status line, the first line of every report (a threshold result with every count, never a claim of absence):
    Dependency audit: pass (introduced: 0 Blocker, 0 Major, <n> Minor; attribution unknown: <n>; accepted: <n>;
        pre-existing: <n>; <n> dependencies in <n> modules; advisory data published <date>; coverage complete)
        (with two ecosystems: "advisory data published <date> (Maven), <date> (PyPI)")
        (Python sources and no Python dependency file: "coverage complete (no third-party Python dependency declared)",
        and "advisory data not needed (no package to match)" when no PyPI data is cached)
    Dependency audit: fail (the same fields, the last coverage complete or coverage partial (<category>: <what
        to do>))
    Dependency audit: not run (<category>: <what to do>)
    Dependency audit: off (configuration: <source>)
    Dependency audit: pending
fail: an occurrence the change introduced, or whose attribution is unknown, matches an advisory of class
Blocker or Major that the user has not accepted. A result that does not cover every module keeps what it
found (it still fails on such an occurrence) and is otherwise not run, so it never reads as clean. On a
snapshot an attempt first records the gate dependency-audit as not run ("pending: an audit of this snapshot
started and has not recorded its result"), so an attempt that dies leaves no earlier result standing; a pass
or a fail then records its coverage as the gate dependency-audit-coverage (pass when complete, not run with
the category and remedy when partial) before its own result, so a fail found in a partial inventory is a red
gate and leaves verification incomplete. A --files snapshot that does not hold every build file the project
reads is not run: the snapshot would not show a later change to one.

The text report: the status line; "Data:" (source, the three dates, the advisory count, the dataset digest,
the attribution of the ecosystem's sources: ATTRIBUTION here for Maven, dependency_audit_pypi.py's for PyPI), one
Data line per ecosystem; then for each ecosystem
its Resolution and Inventory lines (PyPI: "Resolution: PyPI: <files read>; project; candidate; modules; base");
"Resolution:" (the build tool or tools and why:
the build files found or --build-tool; then each tool's path, versions, build output and command; profiles,
modules, the base); "Inventory:" (what was listed and what was not); then five blocks, each headed
"<name> (<count>):" with one "- " line per vulnerable occurrence or "- none": Introduced by this change,
Attribution unknown, Accepted by the user, Pre-existing, Could not be evaluated. An occurrence line reads
    - module <module>; <group:artifact:version> (<scope>); path: <a> > <b> > <c>;
      advisories: <ID> (<CVE alias>) <SEVERITY> <class>[ unsure] [<basis>], ...; fix reported: <version>[ (not
      checked against every advisory: one could not be evaluated)]
on one line (a PyPI one reads "- module <lock or pin file>; pypi:<name>==<version> (<lock|pin|constraint>[: <groups>]);
path: <file> > <name>==<version>; ..."), the fix being "no fixed version in the advisory data" when the advisories
name none; a PyPI advisory whose severity word was taken from an aliased GHSA record or scored from its CVSS v3
vector says so ("HIGH (from CVSS 3.1 7.5)"), and advisories that are aliases of each other are one; when two
build tools resolved the project, "module <module> (<tool>)" names the one that listed the occurrence. A Maven
module is its group:artifact and its scope the Maven scope; a Gradle module is "project <path>" and its scope
the context of the configurations that hold the dependency (ship for a runtime classpath, compile for a compile
classpath, test for a test configuration, build for an annotation-processor path, other for any other), then
those configurations. The fix is the one the advisories report, matched again against every advisory for that
artifact; it is not a claim that the release exists or is the lowest safe one. The JSON report (schema
ifs-dependency-audit/1) carries the same facts and binds them: snapshot id, attempt, the dataset's digest and
the SHA-256 of every resolution input.

The inventory. Maven: the dependencies of every module of the build in every scope; not build plugins, not
annotation-processor paths configured in the compiler plugin, not shaded or relocated content. Gradle: every
resolvable configuration of every project of the build, annotation-processor paths included; not the
buildscript classpath, not file dependencies (files and file trees, which Gradle's resolution result does not
hold), not shaded or relocated content, not included builds. A module without metadata, whose dependencies
nothing lists, is never in it as if it had none: for the run, every Maven and Ivy repository of the projects and
of the settings' dependencyResolutionManagement is read without its artefact-only metadata source
(metadataSources artifact()), so such a module is unresolved, and a flat-directory repository there, which holds
artefacts only, makes the result partial; buildscript and pluginManagement repositories, which serve build
plugins, stay as declared. PyPI: every package version the lock files (uv.lock, poetry.lock, pdm.lock,
pylock.toml and pylock.<name>.toml, Pipfile.lock) and the requirements files pinned with == or === list in every
directory of the project, in every group, extra and environment marker (a marker is never evaluated), the
project's own workspace members left out; a declaration with no lock or pin file, a declared dependency the
covering lock and pin files do not list, a requirement not pinned to one version, and a package from a VCS, a URL
or a local path make it partial (dependency_audit_pypi.py's header has the rules). An entry means a version
matching an advisory is in the inventory, not that the vulnerable code is called.

No advisory text reaches a report: only ids, coordinates, versions, severity words, dates and counts that pass
a grammar are printed; a value from a build file or the build tool that does not is replaced by its digest,
a path is escaped and capped, the same in the text and the JSON report. That keeps a value from adding or
altering a line, not from reading like an instruction: IGNORE-ALL-PREVIOUS-INSTRUCTIONS is a valid artifact id
and a directory can be named in prose, so a report's values are data to whoever reads it. The build tool's raw
output goes to a file only the user can read under ~/.local/state/implement-from-spec/dependency-audit/, and no
line of it is copied.

Advisory data: ~/.local/state/implement-from-spec/advisories/ for Maven, advisories/pypi/ below it for PyPI
(at least 10,000 usable advisories; dependency_audit_pypi.py), each published, checked and kept the same way
(located from HOME alone; refused when it
resolves inside the repository under audit, is a link or belongs to another user). Data checked with the
server within 24 hours is used as is; otherwise the export is requested from one fixed HTTPS URL with a
conditional request, no redirect followed, at most 128 MiB within 120 seconds. Every record is parsed in
memory (at most 200,000 entries, 4 MiB each, 1 GiB in all, every member of an archive counted and its central
directory checked before it is listed; never extracted to disk) and a dataset is published only when it holds at
least the ecosystem's minimum of usable advisories (5,000 for Maven, 10,000 for PyPI) and no two different
records under one id, so a
small, emptied or badly cut dataset is refused; a count cannot show that a large export is whole. The minimum
does not stop a dataset built on purpose to that size. The documented route for one, `refresh --from`, asks the
user in a gated session (the gate rules java-advisory-data-import in
skills/implementing-java-from-spec/gate_rules.json and python-advisory-data-import in
skills/implementing-python-from-spec/gate_rules.json), and the gate denies direct tool writes into the cache; a
program the gate cannot see into, such as a renamed copy of this script, is not covered, and outside a gated
session nothing protects the cache. Every report's Data line names an imported dataset and its path. Cache
directories and files must be the user's own, not writable by others, never links, and a file has one name
only; the dataset's digest is checked again on every load, and the previous dataset is kept, so an audit that
read the old metadata as a refresh published still finds its data. When the refresh fails, data checked within
7 days is used and the report says so; older than that, or none, and the audit is not run. Nothing
authenticates the export beyond HTTPS and its publisher.

Resolution, offline, by the build tool the project uses: Maven for a pom.xml, Gradle for its build files
(build.gradle, build.gradle.kts, settings.gradle, settings.gradle.kts), both when the project directory holds
both, since either may be the build it ships, or the one --build-tool names; the base revision by the same rule
on its own files, so a build the change adds is the change's. Maven: `mvn -B -o -V -T 1 -Dstyle.color=never
dependency:tree` with the two logger levels MAVEN_ARGS names, once for the default build and once per profile
named, read from standard output, with the Maven distribution the project's wrapper names when it is already
under ~/.m2/wrapper/dists (MAVEN_USER_HOME honoured) in the directory named after its URL, else mvn from PATH
(made absolute); a .mvn/maven.config or MAVEN_ARGS that builds part of the project only (-N, -pl, -rf, -f) is
not run, and a tree goal the build configures to list less (scope, includes, excludes, an output file), or
whose configuration Maven does not print, makes the result partial. Gradle: `gradle --offline
--no-daemon --no-configuration-cache -q --console=plain` with dependency-audit-graph.init.gradle (beside this script),
which prints the resolution result of every resolvable configuration of every project in lines carrying a
nonce of the run and, for the run only, reads the Maven and Ivy repositories of the projects and the settings
without their artefact-only metadata source, and with the project cache directory and every project's build
directory in a scratch directory, so
Gradle writes nothing in the project. It runs the distribution the project's wrapper names when
that is already in the Gradle user home (GRADLE_USER_HOME, else ~/.gradle), and with no wrapper gradle from
PATH; a project whose wrapper's distribution is not there is not run, since another Gradle version may not
configure the build. Never a program inside the repository: a wrapper script is never run, because it would
download a missing distribution. The child gets an argument list and no shell, closed standard input and its
own process group, ended as a group at its time limit (the smaller of --timeout and what is left of
--total-timeout); the build tool and the project's build configuration run with the user's permissions,
exactly as the project's tests do: offline is a request, not a sandbox. A
result is complete only when every build tool that ran ended successfully and every module (Maven) or project
(Gradle) reported, with no unresolved dependency: for Maven no dependency whose POM it did not find offline or
could not read (its warnings "The POM for <artifact> is missing, no dependency information available" and
"... is invalid, transitive dependencies (if any) will not be available", where the build still succeeds),
for Gradle no unresolved dependency, no configuration whose resolution failed, no dependency result of a kind
the walk cannot follow, no component that is neither a module nor a project, no flat-directory repository and no
included build. A revision is written out with git ls-tree and
git cat-file (no attribute or filter applies; links and submodules are not written; at most 256 MiB and
100,000 files).

Usage:
    python3 -I <plugin-root>/core/scripts/dependency-audit.py register --snapshot <DIR>
    python3 -I <plugin-root>/core/scripts/dependency-audit.py audit --snapshot <DIR>
    python3 -I <plugin-root>/core/scripts/dependency-audit.py audit --snapshot <DIR> --accept GHSA-xxxx-xxxx-xxxx
    python3 -I <plugin-root>/core/scripts/dependency-audit.py audit --repo ~/src/app --base main
    python3 -I <plugin-root>/core/scripts/dependency-audit.py check org.yaml:snakeyaml:2.4
    python3 -I <plugin-root>/core/scripts/dependency-audit.py check pypi:requests==2.32.4
    python3 -I <plugin-root>/core/scripts/dependency-audit.py refresh
    python3 -I <plugin-root>/core/scripts/dependency-audit.py refresh --ecosystem pypi
    python3 -I <plugin-root>/core/scripts/dependency-audit.py refresh --from ~/Downloads/all.zip

Exit status: 0 pass, a check with no match, refresh done, register done, or off; 2 fail, or a check with a
match; 69 not run; 3 the snapshot no longer verifies; 64 usage, an invalid setting included; 1 internal error.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import functools
import glob
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import secrets
import shutil
import signal
import subprocess  # nosec B404 - git and the project's build tool run as child processes, by design
import sys
import posixpath
import tempfile
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - not POSIX; the plugin runs on macOS and Linux
    fcntl = None  # type: ignore[assignment]

SETTING = "dependency_audit"
SCRIPTS_DIR = os.path.dirname(os.path.realpath(__file__))
EXPORT_URL = "https://osv-vulnerabilities.storage.googleapis.com/Maven/all.zip"
ATTRIBUTION = "OSV, GitHub Advisory Database, CC-BY 4.0"
EXIT_OK, EXIT_ERROR, EXIT_FAIL, EXIT_CHANGED, EXIT_USAGE, EXIT_NOT_RUN = 0, 1, 2, 3, 64, 69

# The Maven dataset's minimum (documented above): it refuses a small, emptied or badly cut dataset, a test
# dataset included; it is a constant, with no flag and no environment variable behind it.
MIN_ADVISORIES = 5000
# Resolution limits. TOTAL_TIMEOUT_SECONDS bounds one whole audit (the download, and every build-tool run of
# candidate and base): it stays below the most Claude Code lets one Bash tool command run by default
# (BASH_MAX_TIMEOUT_MS, "default: 600000, or 10 minutes", code.claude.com/docs/en/env-vars, read 2026-11-24), so
# the audit ends itself with a not-run result instead of being killed with nothing recorded.
BUILD_TIMEOUT_SECONDS = 120
TOTAL_TIMEOUT_SECONDS = 480
MAX_BUILD_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_REVISION_BYTES = 256 * 1024 * 1024
MAX_REVISION_FILES = 100_000
KEPT_BUILD_LOGS = 20
PENDING_REASON = "pending: the audit has not run for this snapshot"
ATTEMPT_REASON = "pending: an audit of this snapshot started and has not recorded its result"
# The coverage of an attempt that ran, recorded apart from its result: a fail found in a partial inventory is a
# red gate and still leaves verification incomplete, which one gate's pass, fail or not-run cannot say at once.
COVERAGE_GATE = "dependency-audit-coverage"


def load_sibling(filename: str, module_name: str, directory: str = SCRIPTS_DIR, inject=None):
    """A script of this directory (or of `directory`), loaded by its path: hyphenated names cannot be imported,
    and under python3 -I this directory is not on sys.path, so a planted module cannot stand in for it.
    `inject` names modules set in the new module before its code runs, so two modules loaded here share one
    instance of a third (one NotRun class, one registry of ecosystems) instead of each loading its own copy."""
    path = os.path.join(directory, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(inject or {})
    # No __pycache__ in the plugin's directory: an installed plugin is read-only content.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


# The ecosystem-neutral half of the audit (the advisory data and its store, matching, classes, attribution and
# the reports) and the PyPI inventory, each loaded once by path; the PyPI module is given this same shared module.
osv = load_sibling("dependency_audit_osv.py", "ifs_dependency_audit_osv")
pypi = load_sibling("dependency_audit_pypi.py", "ifs_dependency_audit_pypi", inject={"osv": osv})
# The shared names this script's own Maven and Gradle code and its commands call, bound once; every other shared
# name is used as osv.<name>, tests included, so each has one binding and a patch of it reaches every caller.
Stop, NotRun, RefreshFailed = osv.Stop, osv.NotRun, osv.RefreshFailed
GATE_NAME, INPUT_LIMIT, ID_GRAMMAR, WORD_RE = osv.GATE_NAME, osv.INPUT_LIMIT, osv.ID_GRAMMAR, osv.WORD_RE
sha256, mib, shown, withheld, safe, safe_path, named_list, time_limit_remedy = \
    osv.sha256, osv.mib, osv.shown, osv.withheld, osv.safe, osv.safe_path, osv.named_list, osv.time_limit_remedy
inside, fold, nfd, name_rules, read_small, file_sha256 = \
    osv.inside, osv.fold, osv.nfd, osv.name_rules, osv.read_small, osv.file_sha256
state_home, default_cache_dir, private_dir = osv.state_home, osv.default_cache_dir, osv.private_dir
data_record, data_line, match_package, INVENTORY_MEANING, CLASS_ORDER = \
    osv.data_record, osv.data_line, osv.match_package, osv.INVENTORY_MEANING, osv.CLASS_ORDER
base_occurrences, gate_status, empty_result = osv.base_occurrences, osv.gate_status, osv.empty_result
one_line, not_run_line, off_line, status_line, occurrence_line, render_text, render_json = \
    osv.one_line, osv.not_run_line, osv.off_line, osv.status_line, osv.occurrence_line, osv.render_text, \
    osv.render_json


# ---------------------------------------------------------------- what may appear in a report
# The grammars of what Maven, Gradle and their build files name; the shared ones (advisory ids, paths) and the
# rule for a value that fails its grammar are dependency_audit_osv.py's.
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")  # a groupId or an artifactId
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}\Z")
TOOL_VERSION_RE = re.compile(r"^[0-9][A-Za-z0-9_.+-]{0,31}\Z")
PROFILE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\Z")


def safe_coordinate(package: str) -> str:
    group, sep, artifact = package.partition(":") if isinstance(package, str) else ("", "", "")
    if sep and NAME_RE.match(group) and NAME_RE.match(artifact):
        return package
    return withheld("coordinate", package)


# ---------------------------------------------------------------- the setting
ENV_PREFIXES = ("IMPLEMENT_FROM_SPEC_", "EVAL_IMPLEMENT_FROM_SPEC_", "CLAUDE_PLUGIN_OPTION_")
VALUES = ("on", "off")


class Setting:
    """The resolved dependency_audit setting. state: on; off (the user's own, obeyed); refused (an off that
    came through the environment or a settings file inside the repository: reported, never obeyed)."""

    def __init__(self, state: str, source: str) -> None:
        self.state, self.source = state, source


def saved_setting():
    """(value or None, where it was read, the settings files read): the user's saved plugin options, read as
    spec-external-review.py reads its own, so both scripts agree on which file counts."""
    try:
        ext = load_sibling("spec-external-review.py", "ifs_spec_external_review")
        cfg = ext.Config()
        saved = ext.saved_options(cfg)
    except Exception:  # noqa: BLE001 - unreadable saved options leave the default, on: never a silent off
        return None, "", []
    if saved and str(saved[0].get(SETTING, "")).strip():
        return str(saved[0][SETTING]), saved[1], list(cfg.files)
    return None, "", list(cfg.files)



def resolve_setting(flag, environ, repo, saved=saved_setting) -> Setting:
    """Flag, then the environment for on only, then the saved options, then the default. An environment
    variable outranks a saved off because a user may switch the audit back on for one run; it never switches
    the audit off, since a trusted repository's settings can set it for every command (TM-45)."""
    if flag is not None:
        return Setting(flag, "flag --dependency-audit")
    for prefix in ENV_PREFIXES:
        var = prefix + SETTING.upper()
        raw = environ.get(var, "").strip()
        if not raw:
            continue
        value = raw.lower()
        if value not in VALUES:
            raise Stop(EXIT_USAGE, f"{SETTING} = {shown(raw)!r} (environment {var}) is not one of {', '.join(VALUES)}")
        if value == "on":
            return Setting("on", f"environment {var}")
        return Setting("refused", f"{var}=off in the environment is not obeyed: unset it, or switch the audit "
                                  "off in your own plugin options")
    raw, where, files = saved()
    if raw is None:
        return Setting("on", "default")
    value = raw.strip().lower()
    if value not in VALUES:
        raise Stop(EXIT_USAGE, f"{SETTING} = {shown(raw)!r} ({shown(where)}) is not one of {', '.join(VALUES)}")
    planted = [f for f in files if repo and inside(f, repo)]
    if value == "off" and planted:
        return Setting("refused", f"the settings file {shown(planted[0])} lies inside the repository under "
                                  "audit, so its off is not obeyed: switch the audit off in your own plugin options")
    return Setting(value, where)


# ---------------------------------------------------------------- Maven version ordering
# The reference is Maven's own org.apache.maven.artifact.versioning.ComparableVersion: the same tokenisation,
# nesting, qualifier aliases and normalisation, checked against a corpus of pairs that class ordered
# (tests/fixtures/dependency-audit/version-order.json, which names the maven-artifact release that ordered it).
# An item is ("n", width, value) for a number, ("s", qualifier) for a string, ("l", [items]) for a sublist.
# width keeps Maven's three number classes apart (up to 9 digits, up to 18, longer): Maven orders them by class
# before value.
QUALIFIERS = ("alpha", "beta", "milestone", "rc", "snapshot", "", "sp")
QUALIFIER_ALIASES = {"ga": "", "final": "", "release": "", "cr": "rc"}
SHORT_QUALIFIERS = {"a": "alpha", "b": "beta", "m": "milestone"}
ZERO = ("n", 0, 0)


def _is_digit(ch: str) -> bool:
    # Java's Character.isDigit on one UTF-16 unit: a decimal digit of the basic plane.
    return ch.isdecimal() and ord(ch) < 0x10000


def _number(text: str) -> tuple:
    stripped = text.lstrip("0") or text  # Maven keeps a run of zeros whole, so its length decides the class
    width = 0 if len(stripped) <= 9 else 1 if len(stripped) <= 18 else 2
    return ("n", width, int(stripped))


def _string(text: str, followed_by_digit: bool) -> tuple:
    if followed_by_digit and len(text) == 1:
        text = SHORT_QUALIFIERS.get(text, text)
    return ("s", QUALIFIER_ALIASES.get(text, text))


def _qualifier_key(text: str) -> bytes:
    """Maven compares qualifiers as strings: the index of a known one, else "7-<text>". Java orders strings
    by UTF-16 unit, which the big-endian encoding preserves bytewise."""
    known = str(QUALIFIERS.index(text)) if text in QUALIFIERS else f"{len(QUALIFIERS)}-{text}"
    return known.encode("utf-16-be", "surrogatepass")


RELEASE_KEY = _qualifier_key("")


def _is_null(item: tuple) -> bool:
    if item[0] == "n":
        return item[2] == 0
    if item[0] == "s":
        return _qualifier_key(item[1]) == RELEASE_KEY
    return not item[1]


def _normalise(items: list) -> None:
    """Drops trailing null items (0, a release qualifier, an empty sublist), looking past a sublist that is
    not empty, as ListItem.normalize does."""
    for i in range(len(items) - 1, -1, -1):
        if _is_null(items[i]):
            del items[i]
        elif items[i][0] != "l":
            break


@functools.lru_cache(maxsize=65536)
def parse_version(version: str) -> tuple:
    """A version as Maven's nested item list (treated as immutable once returned)."""
    text = version.lower()
    root: list = []
    current, stack = root, [root]
    is_digit, start = False, 0

    def nest():
        nonlocal current
        child: list = []
        current.append(("l", child))
        stack.append(child)
        current = child

    for i, ch in enumerate(text):
        if ch in ".-":
            token = text[start:i]
            current.append(ZERO if i == start else _number(token) if is_digit else _string(token, False))
            start = i + 1
            if ch == "-":
                nest()
        elif _is_digit(ch):
            if not is_digit and i > start:
                if current:
                    nest()  # Maven reads ".X1" as "-X1": a qualifier before a digit opens its own sublist
                current.append(_string(text[start:i], True))
                start = i
                nest()
            is_digit = True
        else:
            if is_digit and i > start:
                current.append(_number(text[start:i]))
                start = i
                nest()
            is_digit = False
    if len(text) > start:
        if not is_digit and current:
            nest()  # and a closing ".X" as "-X"
        current.append(_number(text[start:]) if is_digit else _string(text[start:], False))
    while stack:
        _normalise(stack.pop())
    return ("l", root)


def _sign(a, b) -> int:
    return (a > b) - (a < b)


def _compare_item(item: tuple, other) -> int:
    """item against other, which is None where the other version has no item at this position."""
    kind = item[0]
    if kind == "n":
        if other is None:
            return 0 if item[2] == 0 else 1
        if other[0] != "n":
            return 1  # a number is newer than a qualifier or a sublist
        return _sign(item[1], other[1]) or _sign(item[2], other[2])
    if kind == "s":
        if other is None:
            return _sign(_qualifier_key(item[1]), RELEASE_KEY)
        if other[0] == "s":
            return _sign(_qualifier_key(item[1]), _qualifier_key(other[1]))
        return -1  # a qualifier is older than a number or a sublist
    if other is None:
        return next((r for r in (_compare_item(x, None) for x in item[1]) if r), 0)
    if other[0] == "n":
        return -1
    if other[0] == "s":
        return 1
    for left, right in itertools.zip_longest(item[1], other[1]):
        result = -_compare_item(right, None) if left is None else _compare_item(left, right)
        if result:
            return result
    return 0


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1, as Maven orders a against b."""
    return _compare_item(parse_version(a), parse_version(b))


# ---------------------------------------------------------------- the Maven forms of the shared functions
# The advisory data, its store and matching are dependency_audit_osv.py's, given an ecosystem; these are their
# Maven forms, which the Java path and its tests use. MAVEN itself is defined with the report wording below.
def normalise_entry(affected) -> dict | None:
    return osv.normalise_entry(affected, MAVEN)


def normalise_record(raw) -> dict | None:
    return osv.normalise_record(raw, MAVEN)


def build_dataset(records, minimum: int = MIN_ADVISORIES) -> dict:
    return osv.build_dataset(records, MAVEN, minimum)


def match_entry(entry: dict, version: str) -> tuple:
    return osv.match_entry(entry, version, MAVEN)


class Index(osv.Index):
    """The Maven dataset by `group:artifact`."""

    def __init__(self, dataset: dict) -> None:
        super().__init__(dataset, MAVEN)


class Store(osv.Store):
    """The Maven advisory cache, the cache directory itself."""

    def __init__(self, directory: str, repo=None, fetch=None, now=time.time,
                 minimum: int = MIN_ADVISORIES, limits=osv.Limits, deadline=None) -> None:
        super().__init__(directory, MAVEN, repo=repo, fetch=fetch, now=now, minimum=minimum, limits=limits,
                         deadline=deadline)


# ---------------------------------------------------------------- materialisation and resolution
SHIPPED_SCOPES = ("compile", "runtime")  # the Maven scopes whose dependencies ship with the module
GRADLE_BUILD_FILES = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
WRAPPER_NAMES = ("mvnw", "mvnw.cmd", "gradlew", "gradlew.bat")
PRUNED_DIRS = (".git", "target", "build", "node_modules", ".gradle")
# Beyond batch, offline and one thread: two loggers at the level the audit reads. Maven prints its warnings about
# a dependency's POM through org.codehaus.plexus.PlexusContainer, and prints the configuration of the mojo it
# runs at debug level through DefaultMavenPluginManager; a -D option on the command line is set after the
# project's .mvn/jvm.config, so a project cannot turn either off.
MAVEN_ARGS = ("-B", "-o", "-V", "-T", "1", "-Dstyle.color=never",
              "-Dorg.slf4j.simpleLogger.log.org.codehaus.plexus.PlexusContainer=info",
              "-Dorg.slf4j.simpleLogger.log.org.apache.maven.plugin.internal.DefaultMavenPluginManager=debug")
# The tree goal's configuration as Maven prints it before the tree, one "(f) name = value" line per parameter.
CONFIG_START_RE = re.compile(r"^\[DEBUG\] Configuring mojo execution "
                             r"'[^':]+:maven-dependency-plugin:[^':]+:tree:[^']*'")
CONFIG_PARAM_RE = re.compile(r"^\[DEBUG\]   \([a-z]\) ([A-Za-z]+) = (.*)$")
CONFIG_END = "[DEBUG] -- end configuration --"
# Parameters of the tree goal that narrow or move what it prints, with the value that does neither (None: any
# value narrows). A build that sets one lists less than it resolves.
TREE_FILTERS = {"scope": None, "includes": "[]", "excludes": "[]", "outputFile": None, "outputType": "text",
                "skip": "false", "verbose": "false", "tokens": "standard"}
MISSING_PROFILE_RE = re.compile(r'The requested profile "([^"]*)" could not be activated because it does not exist')
# Options that make Maven build part of the project only, in .mvn/maven.config or MAVEN_ARGS, by every name
# Maven 3.9's command line takes, with the long name each is reported by. Maven 3.9's CLIManager parses the
# options with commons-cli's GnuParser: a word names an option after one or two leading dashes, by its short or
# its long name (-file, --pl and --N are options too), with
# its value in the next word or after "=" (-f=x, --projects=x), and a one-letter short option also takes its value
# attached (-fx; -Nclean is -N and the goal clean).
MAVEN_NARROWING = {"N": "--non-recursive", "non-recursive": "--non-recursive", "pl": "--projects",
                   "projects": "--projects", "rf": "--resume-from", "resume-from": "--resume-from", "f": "--file",
                   "file": "--file"}
# The one-letter options above, which take an attached value, and the other options whose names start with one of
# those letters, by their short and their long names (a long name takes one dash as well as two): -fae and
# -fail-at-end are --fail-at-end, -ffoo is --file foo.
MAVEN_ATTACHED = ("f", "N")
MAVEN_NOT_NARROWING = ("fae", "ff", "fn", "fail-at-end", "fail-fast", "fail-never")
BANNER_RE = re.compile(r"^\[INFO\] -+< ([^\s:]+:[^\s:]+) >-+$")
GOAL_RE = re.compile(r"^\[INFO\] --- (?:maven-)?dependency(?:-plugin)?:(\S+):tree \([^)]*\) @ .+ ---$")
# The tree's root line, GROUP:ARTIFACT:TYPE[:CLASSIFIER]:VERSION; the fields are counted after the split
# (root_fields), not by a quantified group in the regex.
ROOT_RE = re.compile(r"^\[INFO\] (\S+)$")
NODE_RE = re.compile(r"^\[INFO\] ((?:\|  |   )*)(?:\+- |\\- )(\S+)( \(optional\))?$")
TREE_LINE_RE = re.compile(r"^\[INFO\] (?:\|  |   )*(?:\+- |\\- )")  # anything shaped like a line of a tree
ORDER_ENTRY_RE = re.compile(r"^\[INFO\] \S.*\[[A-Za-z0-9._-]+\]$")
WRAPPER_DIST_RE = re.compile(r"^apache-maven-([0-9][A-Za-z0-9.-]{0,31})-bin\.(?:zip|tar\.gz)$")
# Colour codes, which -Dstyle.color=never should keep out but a build's own logging settings could bring back: the
# parser reads every line without them.
COLOUR_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# The two warnings Maven prints when it reads no dependency information for a dependency (LoggingRepositoryListener
# in maven-core and DefaultArtifactDescriptorReader in maven-resolver-provider, read in Maven's 3.8.x, 3.9.x and 4
# sources on github.com/apache/maven on 2026-11-24): its POM was not found, or it was found and could not be read,
# and the dependencies declared there are dropped. Either way the build succeeds and the tree shows the dependency
# with no children, so the part of the graph below it is not in the inventory. Searched for anywhere in a line,
# whatever its level label or colour: a line taken for one by mistake makes the result partial, never clean. A
# relocation is not among them: Maven follows it and reads the POM at the new coordinates, and a relocation cycle
# is reported as a POM that could not be read.
DESCRIPTOR_RE = re.compile(r"The POM for (\S+) is (?:(missing), no dependency information available|"
                           r"(invalid), transitive dependencies \(if any\) will not be available)")
# The lines that follow an unreadable-POM warning when Maven adds the reasons: one "[<severity>] <problem>" line
# per problem of that POM, then an empty line.
PROBLEM_LINE_RE = re.compile(r"^\[(?:FATAL|ERROR|WARNING)\] ")


def is_resolution_input(rel: str, project: str = "") -> bool:
    """Whether a repository-relative path can change what the build resolves, so that a --files snapshot
    must hold it and the JSON report records its digest: every pom.xml, .mvn/, the wrappers, Gradle build,
    settings and properties files, lockfiles (Gradle honours them when it resolves), and gradle/ and
    buildSrc/ at the root of the repository or of the project."""
    parts = rel.split("/")
    name = parts[-1]
    if name == "pom.xml" or ".mvn" in parts[:-1] or name in WRAPPER_NAMES:
        return True
    if name in GRADLE_BUILD_FILES or name == "gradle.properties" or name.endswith(".lockfile"):
        return True
    inner = parts[project.count("/") + 1:] if project and rel.startswith(project + "/") else parts
    return any(len(p) > 1 and p[0] in ("gradle", "buildSrc") for p in (parts, inner))


def list_tree(snap, root: str, rev: str) -> list:
    """(mode, object id, size, path) of every entry of a revision, read with git ls-tree: no attribute,
    filter or export rule applies to it."""
    try:
        out = snap.git(root, ["ls-tree", "-r", "-z", "-l", "--full-tree", rev])
    except snap.Failure as exc:
        raise NotRun("revision cannot be read", f"git ls-tree cannot read {shown(rev[:12])} ({shown(exc.message)}): "
                                                "fetch that revision into the repository, then run the audit again")
    entries = []
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _tab, path = record.partition(b"\t")
        mode, _kind, oid, size = meta.split()
        entries.append((mode.decode("ascii"), oid.decode("ascii"), 0 if size == b"-" else int(size), os.fsdecode(path)))
    return entries


class BlobReader:
    """git cat-file --batch: the bytes of blobs exactly as git stores them, one process for a whole revision."""

    def __init__(self, snap, root: str) -> None:
        self.proc = subprocess.Popen(  # nosec B603 B607 - argument list, fixed git subcommand, git from user PATH
            ["git", *snap.GIT_OPTS, "-C", root, "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=snap.git_env())

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        with contextlib.suppress(OSError):
            self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.wait()

    def read(self, oid: str) -> bytes:
        try:
            self.proc.stdin.write(oid.encode("ascii") + b"\n")
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().split()
            if len(header) != 3 or header[1] != b"blob":
                raise ValueError("not a blob")
            data = self.proc.stdout.read(int(header[2]))
            if len(data) != int(header[2]) or self.proc.stdout.read(1) != b"\n":
                raise ValueError("short read")
        except (OSError, ValueError) as exc:
            raise NotRun("revision cannot be read", f"git cat-file did not return object {oid[:12]} ({exc}): run "
                                                    "`git fsck` in the repository, repair what it reports, then run "
                                                    "the audit again")
        return data


def name_clash(paths: list, dest: str):
    """Two paths of a revision that the file system under `dest` would take for one (they differ in letter
    case or Unicode normalisation only, at any depth), as (one, other), or None: written out, the second would
    merge into the first, and the tree built would not be the revision's."""
    case, normalisation = name_rules(dest)
    if case is False and normalisation is False:
        return None
    key_of = fold if case is not False else nfd
    seen: dict = {}
    for path in paths:
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            spelling = "/".join(parts[:depth])
            other = seen.setdefault("/".join(key_of(p) for p in parts[:depth]), spelling)
            if other != spelling:
                return other, spelling
    return None


def materialise(snap, root: str, rev: str, dest: str, max_bytes: int = MAX_REVISION_BYTES,
                max_files: int = MAX_REVISION_FILES) -> dict:
    """Writes the files and links of `rev` under `dest`, byte for byte. A link is written when it is relative
    and resolves inside `dest` once every link is written (a link through another link included); any other,
    and every submodule, is counted and not written, which makes the result partial (resolve_tree): the build
    could read what is missing. An entry that would leave `dest`, or two entries `dest` cannot keep apart, stop
    the audit; a revision over the limits is not written at all."""
    entries = list_tree(snap, root, rev)
    files = [e for e in entries if e[0] in ("100644", "100755")]
    links = [e for e in entries if e[0] == "120000"]
    total = sum(size for _mode, _oid, size, _path in files + links)
    if len(files) + len(links) > max_files or total > max_bytes:
        raise NotRun("revision too large", f"{len(files) + len(links)} files and {mib(total)} at {rev[:12]}, over "
                                           f"the limit of {max_files} files or {mib(max_bytes)}: check it out and run "
                                           "`audit --repo` on that working tree")
    for _mode, _oid, _size, path in files + links:
        parts = path.split("/")
        if os.path.isabs(path) or any(p in ("", ".", "..") for p in parts):
            raise NotRun("revision cannot be written", f"an entry of {rev[:12]} would leave the scratch directory: "
                                                       "check it out and run `audit --repo` on that working tree, "
                                                       "where git refuses such an entry")
    clash = name_clash([e[3] for e in files + links], dest)
    if clash:
        raise NotRun("revision cannot be written", f"{safe_path(clash[0])} and {safe_path(clash[1])} of {rev[:12]} "
                                                   "differ only in letter case or Unicode normalisation, which the "
                                                   "scratch directory's file system does not tell apart: set TMPDIR "
                                                   "to a directory on a case-sensitive volume, then run the audit "
                                                   "again")
    written, omitted = [], 0
    with BlobReader(snap, root) as blobs:
        for mode, oid, _size, path in files:
            target = os.path.join(dest, *path.split("/"))
            try:
                os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                             0o700 if mode == "100755" else 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(blobs.read(oid))
            except OSError as exc:
                raise NotRun("revision cannot be written", f"{safe_path(path)} of {rev[:12]} ({exc.strerror}): check "
                                                           "it out and run `audit --repo` on that working tree")
        # Links after every file: a link written first could turn a directory of a later file into a way out.
        for _mode, oid, _size, path in links:
            pointer = os.fsdecode(blobs.read(oid))
            place = os.path.join(dest, *path.split("/"))
            if not pointer or os.path.isabs(pointer) or "\0" in pointer:
                omitted += 1
                continue
            try:
                os.makedirs(os.path.dirname(place), mode=0o700, exist_ok=True)
                if not inside(os.path.dirname(place), dest):
                    omitted += 1
                    continue
                os.symlink(pointer, place)
                written.append(place)
            except OSError:
                omitted += 1
    kept = 0
    for place in written:
        if inside(os.path.realpath(place), dest):
            kept += 1
        else:
            os.unlink(place)
            omitted += 1
    return {"files": len(files), "bytes": total, "links": kept, "links_omitted": omitted,
            "submodules": sum(1 for e in entries if e[0] == "160000")}


def worktree_files(snap, root: str, git: bool) -> list:
    """The repository-relative paths of the working tree: tracked files and untracked ones git does not
    ignore (the same rule a snapshot's candidate follows); a directory that is no work tree is walked."""
    if git:
        return snap.split_z(snap.git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]))
    found = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in PRUNED_DIRS)
        rel = os.path.relpath(current, root)
        found += [name if rel == "." else f"{rel}/{name}".replace(os.sep, "/") for name in sorted(files)]
    return found


def worktree_inputs(root: str, names: list, project: str) -> dict:
    """{path: sha256} of the resolution inputs in a working tree; a link or an unreadable file is recorded by
    what it is, so it never equals a regular file at the base."""
    found = {}
    for rel in names:
        if is_resolution_input(rel, project) and os.path.lexists(os.path.join(root, rel)):
            data = read_small(os.path.join(root, rel))
            found[rel] = sha256(data) if data is not None else "not a readable regular file"
    return found


def revision_inputs(snap, root: str, entries: list, project: str) -> dict:
    """{path: sha256} of a revision's resolution inputs, read with the limit worktree_inputs reads files with;
    a larger one is recorded by its size, never read."""
    wanted = [e for e in entries if is_resolution_input(e[3], project)]
    found = {}
    with BlobReader(snap, root) as blobs:
        for mode, oid, size, path in wanted:
            if mode not in ("100644", "100755"):
                found[path] = "not a readable regular file"
            elif size > INPUT_LIMIT:
                found[path] = f"over {mib(INPUT_LIMIT)}, not read"
            else:
                found[path] = sha256(blobs.read(oid))
    return found


def new_node(group: str, artifact: str, kind: str, classifier: str, version: str, scope: str, optional: bool,
             path: list, ships=None) -> dict:
    """One dependency of a module. `ships` says whether the module ships it, which attribution needs; for a
    Maven scope it follows from the scope, a Gradle node passes it from its configuration's context."""
    return {"package": f"{group}:{artifact}", "type": kind, "classifier": classifier, "version": version,
            "scope": scope, "optional": optional, "path": path,
            "ships": scope in SHIPPED_SCOPES if ships is None else ships}


def parse_maven_output(text: str) -> dict:
    """The dependency trees in the standard output of `mvn dependency:tree`: one module per build banner
    ("---< group:artifact >---"), its tree after the goal's header line. modules carry `parsed`; the result is
    complete only when the build ended successfully and every module it named has a parsed tree whose root is
    that module. Anything between trees is noise and is skipped; nothing here is trusted beyond its shape. A
    line shaped like a tree line that is not read as one (an unknown suffix, a line after the tree was taken
    to have ended) makes the module unparsed: dropping it would shorten the inventory without a trace.

    A warning that Maven read no dependency information for a dependency (DESCRIPTOR_RE) is taken wherever it
    stands, the lines of reasons that follow it included, without ending a tree; it goes to `descriptors` with
    the module whose section printed it (None before the first module) and makes the result partial."""
    modules: list = []
    info = {"maven": None, "java": None, "plugin": None, "success": False, "expected": None}
    current = tree = None
    stack: list = []
    descriptors: list = []
    missing_profiles: list = []
    ordering = reasons = False
    config = None
    for raw in text.split("\n"):
        line = COLOUR_RE.sub("", raw.rstrip("\r"))
        if config is not None:
            param = CONFIG_PARAM_RE.match(line)
            if param:
                config[param.group(1)] = param.group(2)
                continue
            if line == CONFIG_END and current is not None:
                current["tree_config"] = config
            config = None
        if CONFIG_START_RE.match(line):
            config = {}
            continue
        absent = MISSING_PROFILE_RE.search(line)
        if absent:
            missing_profiles.append(absent.group(1))
            continue
        warned = DESCRIPTOR_RE.search(line)
        if warned:
            entry = {"module": current["id"] if current else None, "kind": warned.group(2) or warned.group(3),
                     "artifact": warned.group(1)}
            if entry not in descriptors:
                descriptors.append(entry)
            reasons = entry["kind"] == "invalid"
            continue
        if reasons and (line == "" or PROBLEM_LINE_RE.match(line)):
            continue
        reasons = False
        if info["maven"] is None and line.startswith("Apache Maven "):
            info["maven"] = line.split()[2] if len(line.split()) > 2 else None
        elif info["java"] is None and line.startswith("Java version: "):
            info["java"] = line[len("Java version: "):].split(",")[0].strip()
        if line == "[INFO] Reactor Build Order:":
            ordering, info["expected"] = True, 0
        elif ordering and ORDER_ENTRY_RE.match(line):
            info["expected"] += 1
        elif ordering and info["expected"]:
            ordering = False
        if line == "[INFO] BUILD SUCCESS":
            info["success"] = True
        banner = BANNER_RE.match(line)
        if banner:
            current, tree = {"id": banner.group(1), "version": None, "nodes": [], "parsed": False}, None
            modules.append(current)
            continue
        goal = GOAL_RE.match(line)
        if goal:
            info["plugin"] = info["plugin"] or goal.group(1)
            tree = "root" if current is not None and not current["parsed"] and not current["nodes"] else None
            continue
        if tree == "root" and line.startswith("[DEBUG] "):
            continue  # what Maven logs at debug level between the goal's header and the tree
        if tree == "root":
            root = ROOT_RE.match(line)
            fields = root.group(1).split(":") if root else []
            fields = fields if 4 <= len(fields) <= 5 and all(fields) else []
            if fields and f"{fields[0]}:{fields[1]}" == current["id"]:
                current["version"], current["parsed"] = fields[-1], True
                stack, tree = [(current["id"], fields[-1])], "nodes"
            else:
                tree = None
        elif tree == "nodes":
            node = NODE_RE.match(line)
            if not node:
                tree = None
                if TREE_LINE_RE.match(line):
                    current["parsed"] = False
                continue
            depth = len(node.group(1)) // 3 + 1
            fields = node.group(2).split(":")
            if depth > len(stack) or len(fields) not in (5, 6):
                current["parsed"], tree = False, None  # a tree this parser cannot follow is no tree
                continue
            classifier = fields[3] if len(fields) == 6 else ""
            stack = stack[:depth] + [(f"{fields[0]}:{fields[1]}", fields[-2])]
            current["nodes"].append(new_node(fields[0], fields[1], fields[2], classifier, fields[-2], fields[-1],
                                             bool(node.group(3)), list(stack)))
        elif current is not None and current["parsed"] and TREE_LINE_RE.match(line):
            current["parsed"] = False
    filtered = {m["id"]: tree_filters(m.get("tree_config")) for m in modules if m["parsed"]}
    filtered = {module: params for module, params in filtered.items() if params}
    return {"modules": modules, "info": info, "descriptors": descriptors, "filtered": filtered,
            "missing_profiles": list(dict.fromkeys(missing_profiles)),
            "complete": bool(info["success"] and modules and all(m["parsed"] for m in modules)
                             and info["expected"] in (None, len(modules)) and not descriptors and not filtered
                             and not missing_profiles)}


def tree_filters(config) -> list:
    """The parameters of a module's tree goal that narrow what it prints; ["its configuration was not printed"]
    when Maven printed none, so no filter is ruled out."""
    if config is None:
        return ["its configuration was not printed"]
    return [name for name, plain in TREE_FILTERS.items()
            if name in config and (plain is None or config[name] != plain)]


def safe_artifact(text: str) -> str:
    """An artifact as Maven's resolver names it in a warning: group:artifact:extension[:classifier]:version."""
    parts = text.split(":")
    if len(parts) in (4, 5) and NAME_RE.match(parts[0]) and NAME_RE.match(parts[1]) \
            and all(WORD_RE.match(p) for p in parts[2:-1]) and VERSION_RE.match(parts[-1]):
        return text
    return withheld("dependency", text)


DESCRIPTOR_NOTES = {"missing": "the POM of {} was not found offline",
                    "invalid": "the POM of {} could not be read"}


def maven_notes(parsed: dict) -> list:
    """What the report lists under Could not be evaluated for a Maven run: each dependency Maven read no
    dependency information for, with the module whose section named it."""
    notes = []
    for entry in parsed["descriptors"][:MAX_UNRESOLVED_NOTES]:
        where = f"module {module_label(entry['module'])}: " if entry["module"] else ""
        notes.append(where + DESCRIPTOR_NOTES[entry["kind"]].format(safe_artifact(entry["artifact"]))
                     + ", so the dependencies declared there are not in the inventory")
    if len(parsed["descriptors"]) > MAX_UNRESOLVED_NOTES:
        notes.append(f"{len(parsed['descriptors']) - MAX_UNRESOLVED_NOTES} more dependencies without dependency "
                     "information (the build output names them)")
    return notes


def descriptor_problem(descriptors: list, online: str, log: str) -> tuple:
    """(category, remedy) of a build that succeeded with dependencies Maven read no dependency information for.
    A POM not found offline is an artefact missing from the local repository, remedied as one; a POM found and
    unreadable is not fixed by a download, so its remedy is the dependency itself."""
    missing = [safe_artifact(d["artifact"]) for d in descriptors if d["kind"] == "missing"]
    if missing:
        return "artifacts not in the local repository", (f"Maven could not find the POM of {named_list(missing)} "
                                                         "offline, so the dependencies declared there are not in the "
                                                         f"inventory: {online}")
    invalid = [safe_artifact(d["artifact"]) for d in descriptors]
    return "partial coverage", (f"Maven could not read the POM of {named_list(invalid)}, so the dependencies declared "
                                f"there are not in the inventory: its reason is in the build output at {shown(log)}; "
                                "fix or replace that dependency, then run the audit again")


def _java_hash(value: int, text: str) -> int:
    """Java's `31 * h + c` over the UTF-16 code units of `text`, as a 32-bit value."""
    data = text.encode("utf-16-be")
    for i in range(0, len(data), 2):
        value = (value * 31 + int.from_bytes(data[i:i + 2], "big")) & 0xFFFFFFFF
    return value


def java_uri_hash(url: str) -> str:
    """java.net.URI.hashCode of an http or https distribution URL, in hexadecimal: the name the Maven wrapper's
    Java launcher gives the directory of that URL (PathAssembler, apache/maven-wrapper; URI.hashCode,
    openjdk/jdk; both read 2026-11-24). Components are hashed raw, the scheme and host without case."""
    parts = urllib_parse().urlsplit(url)
    h = _java_hash(0, parts.scheme.lower())
    for component, present in ((parts.fragment, "#" in url), (parts.path, True), (parts.query, "?" in url)):
        if present and component is not None:
            h = (h * 127 + _java_hash(0, component)) & 0xFFFFFFFF if "%" not in component else \
                (h * 127 + _java_hash(0, re.sub(r"%(..)", lambda m: "%" + m.group(1).upper(), component))) \
                & 0xFFFFFFFF
    userinfo, _at, hostport = parts.netloc.rpartition("@")
    if userinfo:
        h = (h * 127 + _java_hash(0, userinfo)) & 0xFFFFFFFF
    h = _java_hash(h, (parts.hostname or "").lower())
    h = (h + 1949 * (parts.port if parts.port is not None else -1)) & 0xFFFFFFFF
    return f"{h:x}"


def shell_hash(url: str) -> str:
    """The hash the Maven wrapper's mvnw script names a distribution URL's directory with (hash_string,
    apache/maven-wrapper, read 2026-11-24): `h * 31 + byte` modulo 2^32 over the URL's bytes, in hexadecimal."""
    value = 0
    for byte in url.encode("utf-8"):
        value = (value * 31 + byte) % 4294967296
    return f"{value:x}"


def urllib_parse():
    import urllib.parse  # here, not at the top, as the network modules are
    return urllib.parse


def wrapper_distribution(project_dir: str, repo, environ) -> str | None:
    """The mvn of the Maven distribution the project's wrapper names, when that distribution is already under
    the user's ~/.m2/wrapper/dists (MAVEN_USER_HOME honoured), in the directory the wrapper names after this
    distribution URL by the Java launcher (java_uri_hash) or the mvnw script (shell_hash): a distribution of
    the same file name downloaded from another URL is another distribution and is not used. The wrapper
    script itself is never run: it would download a missing distribution, and it is a program inside the
    repository. The wrapper deletes the archive after unpacking, so a distributionSha256Sum cannot be checked
    again here."""
    data = read_small(os.path.join(project_dir, ".mvn", "wrapper", "maven-wrapper.properties"), 65536)
    url = _read_property(data.decode("utf-8", "replace"), "distributionUrl") if data else None
    name = WRAPPER_DIST_RE.match(url.rsplit("/", 1)[-1]) if url else None
    if not name:
        return None
    version = name.group(1)
    home = environ.get("MAVEN_USER_HOME") or os.path.join(os.path.expanduser("~"), ".m2")
    dists = os.path.join(home, "wrapper", "dists")
    try:
        launcher = os.path.join(dists, f"apache-maven-{version}-bin", java_uri_hash(url), f"apache-maven-{version}",
                                "bin", "mvn")
    except ValueError:  # a URL Python cannot split, for instance a bad port: no directory is named after it
        launcher = None
    for path in (launcher, os.path.join(dists, f"apache-maven-{version}", shell_hash(url), "bin", "mvn")):
        if path is None:
            continue
        if os.path.isfile(path) and os.access(path, os.X_OK) and not (repo and inside(path, repo)):
            return path
    return None


def find_maven(project_dir: str, repo, environ) -> tuple:
    """(path, where it came from): the wrapper's distribution when it is on the machine, else mvn from PATH,
    never a program that resolves inside the repository."""
    has_wrapper = any(os.path.lexists(os.path.join(project_dir, *p))
                      for p in (("mvnw",), (".mvn", "wrapper", "maven-wrapper.properties")))
    distribution = wrapper_distribution(project_dir, repo, environ) if has_wrapper else None
    if distribution:
        return distribution, "the wrapper's distribution"
    found = shutil.which("mvn", path=absolute_path(environ))
    if found and repo and inside(found, repo):
        raise NotRun("build tool missing", f"the mvn on PATH ({shown(found)}) resolves inside the repository and is "
                                           "never run: install Maven outside it")
    if found:
        return found, "PATH"
    if has_wrapper:
        raise NotRun("wrapper not provisioned", f"run `./mvnw -v` in {shown(project_dir)} once with network access, "
                                                "then the audit again")
    raise NotRun("build tool missing", "install Maven (/implement-from-spec:setup offers it), then run the audit again")


def absolute_path(environ) -> str:
    """PATH with every entry made absolute against this process's directory, an empty one included, as a
    shell here resolves it: a relative entry would otherwise name one directory when the tool is looked up
    and another once the build tool runs in the project."""
    entries = [os.path.abspath(entry or os.curdir) for entry in environ.get("PATH", os.defpath).split(os.pathsep)]
    return os.pathsep.join(dict.fromkeys(entries))


def tool_environ(environ, repo) -> dict:
    """The build tool's environment: PATH absolute and without the entries inside the repository under audit,
    so no program the build tool or its launcher looks up on PATH (java, for one) comes from the project."""
    entries = [e for e in absolute_path(environ).split(os.pathsep) if not (repo and inside(e, repo))]
    return dict(environ, PATH=os.pathsep.join(entries))


def build_log(repo, label: str) -> str:
    """A new file only the user can read for the build tool's raw output, under the plugin's state directory;
    the oldest are removed so the directory does not grow."""
    directory = private_dir(os.path.join(state_home(), GATE_NAME), repo, "build output directory")
    old = sorted(n for n in os.listdir(directory) if n.startswith("build-") and n.endswith(".log"))
    for name in old[:max(0, len(old) - KEPT_BUILD_LOGS + 1)]:
        with contextlib.suppress(OSError):
            os.unlink(os.path.join(directory, name))
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    fd, path = tempfile.mkstemp(dir=directory, prefix=f"build-{stamp}-{label}-", suffix=".log")  # 0600, a new name
    os.close(fd)
    return path


def run_build_tool(argv: list, cwd: str, timeout: float, log: str, environ) -> tuple:
    """(exit code, output): the child gets an argument list and no shell, closed standard input and its own
    process group, and writes to `log`, never to a pipe a surviving grandchild could hold open. At the time
    limit, or when the output passes its limit, the whole group is killed and the code is 'time limit' or
    'output limit'."""
    fd = os.open(log, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            # Argument list of the build tool's absolute path outside the repository and fixed arguments, no shell
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            proc = subprocess.Popen(  # nosec B603 - argument list, absolute tool path outside the repo, fixed args
                argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT, env=dict(environ),
                start_new_session=True)
        except OSError as exc:
            raise NotRun("build tool missing", f"{shown(argv[0])} did not start ({exc.strerror}): install the build "
                                               "tool again (/implement-from-spec:setup offers it), then run the audit "
                                               "again")
        deadline, code = time.monotonic() + timeout, None
        while code is None:
            try:
                code = proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                over = "output limit" if os.fstat(fd).st_size > MAX_BUILD_OUTPUT_BYTES else \
                    "time limit" if time.monotonic() > deadline else None
                if over:
                    # Not yet reaped, so its id is still its group's: the kill cannot reach another process.
                    with contextlib.suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    code = over
        # What the build left running in its group is ended before its output is read: it could go on writing
        # the output or the project. The leader is reaped, but a group's id is not reused while a member of
        # the group remains (POSIX), so the kill reaches only those; with none left it finds no group.
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        if code not in ("time limit", "output limit") and os.fstat(fd).st_size > MAX_BUILD_OUTPUT_BYTES:
            code = "output limit"  # written faster than the checks above ran, and read only in part
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), "rb") as fh:
            text = fh.read(MAX_BUILD_OUTPUT_BYTES).decode("utf-8", "replace")
    finally:
        os.close(fd)
    return code, text


def tree_problem(parsed: dict, online: str, log: str):
    """(category, remedy) of a build that succeeded with a tree that cannot stand for its inventory, None when
    nothing here applies: a dependency Maven read no dependency information for, a profile the build lacks, a
    tree goal configured to list less, or a tree goal whose configuration Maven did not print."""
    if parsed.get("descriptors"):
        return descriptor_problem(parsed["descriptors"], online, log)
    if parsed.get("missing_profiles"):
        names = named_list([safe(p, PROFILE_RE, "profile") for p in parsed["missing_profiles"]])
        return "partial coverage", (f"the build has no profile {names}: name a profile it defines, then run the "
                                    "audit again")
    filtered = parsed.get("filtered") or {}
    unprinted = [m for m, params in filtered.items() if params == tree_filters(None)]
    configured = {m: params for m, params in filtered.items() if m not in unprinted}
    if configured:
        params = sorted({p for found in configured.values() for p in found})
        return "partial coverage", (f"the build configures the dependency plugin's tree goal ({', '.join(params)}) "
                                    f"for {named_list([safe_coordinate(m) for m in configured])}, which narrows "
                                    "what it lists: remove that configuration, then run the audit again")
    if unprinted:
        return "partial coverage", (f"Maven printed no configuration of the tree goal for "
                                    f"{named_list([safe_coordinate(m) for m in unprinted])}, so a filter on what it "
                                    f"lists cannot be ruled out: see {shown(log)}")
    return None


def maven_problem(code, text: str, parsed: dict, project: str, log: str, timeout: float) -> tuple:
    """(category, remedy) of a Maven run that gave no complete result. The category comes from fixed phrases
    of Maven's messages, or for a build that succeeded from the dependencies it read no dependency information
    for, before any phrase (the reasons Maven gives for an unreadable POM hold phrases of a broken project); no
    line of the output is copied (a repository URL in it may carry a credential)."""
    online = f"run `mvn -B dependency:tree` in {shown(project)} once with network access, then the audit again"
    if code == "time limit":
        return "time limit", time_limit_remedy(f"the build tool did not finish within {int(timeout)} seconds")
    if code == "output limit":
        return "build tool failed", f"its output passed {mib(MAX_BUILD_OUTPUT_BYTES)}: see {shown(log)}"
    if code == 0:
        found = tree_problem(parsed, online, log)
        if found:
            return found
    plugin = "No plugin found for prefix 'dependency'" in text or \
        re.search(r"maven-dependency-plugin\S* or one of its dependencies could not be resolved", text)
    if plugin:
        return "plugin not in the local repository", online
    if any(phrase in text for phrase in ("offline mode", "has not been downloaded from it before",
                                          "Could not resolve dependencies", "Non-resolvable parent POM",
                                          "Non-resolvable import POM")):
        return "artifacts not in the local repository", online
    if any(phrase in text for phrase in ("Non-parseable POM", "The build could not read", "Malformed POM",
                                          "project build error")):
        return "invalid project", f"the build tool could not read the project: fix it (its output is at {shown(log)})"
    if code != 0:
        return "build tool failed", f"mvn exited {code}: see its output at {shown(log)}"
    return "partial coverage", f"not every module of the build has a parsed dependency tree: see {shown(log)}"


def run_limit(timeout: float, deadline, total, what: str) -> float:
    """The time limit of one build-tool run: the smaller of --timeout and what is left of the audit's total
    limit; NotRun once nothing is left, so the tool is not started."""
    if deadline is None:
        return timeout
    left = int(deadline - time.monotonic())
    if left < 1:
        raise NotRun("time limit", time_limit_remedy(f"the audit reached its total limit of {total} seconds "
                                                     f"before {what}"))
    return min(timeout, left)


def maven_narrowing(project_dir: str, environ) -> None:
    """NotRun when the project's .mvn/maven.config (found as Maven finds it, in the nearest directory at or
    above the project that holds .mvn) or MAVEN_ARGS passes an option that makes Maven build part of the
    project only: the reactor Maven prints is then the part, so the parser could not tell."""
    sources = []
    directory = os.path.abspath(project_dir)
    while True:
        if os.path.isdir(os.path.join(directory, ".mvn")):
            data = read_small(os.path.join(directory, ".mvn", "maven.config"), 65536)
            if data:
                sources.append((".mvn/maven.config", data.decode("utf-8", "replace")))
            break
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    if environ.get("MAVEN_ARGS"):
        sources.append(("MAVEN_ARGS", environ["MAVEN_ARGS"]))
    # Split at any white space, although Maven 3.9 takes each line of maven.config as one word: an option's name
    # is always in the first piece of its word, so this refuses whatever either rule would pass, and more only
    # where a value holds a space followed by a dash.
    for where, text in sources:
        for token in text.split():
            option = maven_narrowing_option(token)
            if option:
                raise NotRun("partial coverage", f"{where} passes {option}, which makes Maven build only part of the "
                                                 "project, so the tree would cover only that part: remove it, then "
                                                 "run the audit again")


def maven_narrowing_option(token: str):
    """The long name of the MAVEN_NARROWING option that one word of Maven's command line passes, None when it
    passes none. Any number of leading dashes is read as Maven reads one or two, and a word that starts with
    -pl or -rf, which Maven 3.9 refuses as an unknown option, is refused here too: no word passes because the
    parser of another Maven version might read it otherwise."""
    name = token.lstrip("-")
    if not name or name == token:
        return None  # a value, a goal, or "-" or "--" alone
    key = name.split("=", 1)[0]
    if key in MAVEN_NARROWING:
        return MAVEN_NARROWING[key]
    if token.startswith("--") or key in MAVEN_NOT_NARROWING:
        return None
    if name[0] in MAVEN_ATTACHED:
        return MAVEN_NARROWING[name[0]]
    return next((MAVEN_NARROWING[p] for p in ("pl", "rf") if name.startswith(p)), None)


def merge_module(merged: dict, module: dict, configuration) -> None:
    """A module of one Maven run into the inventory of all runs: one node per coordinate, version, type,
    classifier and scope, carrying the configurations (the default build, a profile) that list it when the
    audit ran more than one."""
    target = merged.setdefault(module["id"], dict(module, nodes=[]))
    index = {(n["package"], n["version"], n["type"], n["classifier"], n["scope"]): n for n in target["nodes"]}
    for node in module["nodes"]:
        key = (node["package"], node["version"], node["type"], node["classifier"], node["scope"])
        if key not in index:
            index[key] = dict(node, configurations=[])
            target["nodes"].append(index[key])
        if configuration and configuration not in index[key]["configurations"]:
            index[key]["configurations"].append(configuration)


def maven_inventory(project_dir: str, repo, profiles: list, timeout: float, environ, label: str, deadline=None,
                    total=None) -> dict:
    """The inventory of a Maven build: the default build, and each profile the user named in a run of its own,
    since activating a profile can switch off the build's activeByDefault ones ("This profile will
    automatically be active for all builds unless another profile in the same POM is activated using one of
    the previously described methods", Maven's Introduction to Build Profiles, read 2026-11-24)."""
    tool, source = find_maven(project_dir, repo, environ)
    maven_narrowing(project_dir, environ)
    child = tool_environ(environ, repo)
    merged: dict = {}
    complete, notes, problem, unparsed, info, logs = True, [], None, [], None, []
    for profile in [None, *profiles]:
        what = f"Maven resolved the {label}" + (f" with profile {profile}" if profile else "")
        try:
            limit = run_limit(timeout, deadline, total, what)
        except NotRun as exc:
            if profile is None:
                raise
            complete, problem = False, problem or (exc.category, exc.remedy)
            break
        log = build_log(repo, label)
        logs.append(log)
        argv = [tool, *MAVEN_ARGS, *(["-P", profile] if profile else []), "dependency:tree"]
        code, text = run_build_tool(argv, project_dir, limit, log, child)
        parsed = parse_maven_output(text)
        info = info or parsed["info"]
        if not (parsed["complete"] and code == 0):
            complete = False
            if problem is None:
                category, remedy = maven_problem(code, text, parsed, project_dir, log, limit)
                problem = (category, remedy if profile is None else f"with profile {profile}: {remedy}")
        notes += [n for n in maven_notes(parsed) if n not in notes]
        unparsed += [m["id"] for m in parsed["modules"] if not m["parsed"] and m["id"] not in unparsed]
        for module in parsed["modules"]:
            if module["parsed"]:
                merge_module(merged, module, (f"profile-{profile}" if profile else "default") if profiles else None)
    command = " ".join(["mvn", *MAVEN_ARGS, "dependency:tree"])
    if profiles:
        command += " (then once with -P " + ", once with -P ".join(profiles) + ")"
    return {"modules": [dict(m, tool="Maven") for m in merged.values()], "complete": complete, "notes": notes,
            "problem": problem, "unparsed": unparsed,
            "info": {"tool": "Maven", "path": tool, "source": source, "log": ", ".join(logs),
                     "version": safe(info["maven"], TOOL_VERSION_RE, "version"),
                     "plugin": safe(info["plugin"], TOOL_VERSION_RE, "version"),
                     "java": safe(info["java"], TOOL_VERSION_RE, "version"), "command": command}}


# Gradle. The plugin's init script prints the resolution result of every resolvable configuration of every
# project; see its header for what each line holds and which Gradle versions it supports.
GRADLE_INIT_SCRIPT = os.path.join(SCRIPTS_DIR, "dependency-audit-graph.init.gradle")
GRADLE_TASK = ":ifsDependencyAuditGraph"
GRADLE_ARGS = ("--offline", "--no-daemon", "--no-configuration-cache", "-q", "--console=plain")
GRADLE_MARK = "IFS-DEPENDENCY-AUDIT"
NONCE_PROPERTY = "ifs.dependencyAudit.nonce"
SCRATCH_PROPERTY = "ifs.dependencyAudit.scratch"
GRADLE_WRAPPER_PROPERTIES = os.path.join("gradle", "wrapper", "gradle-wrapper.properties")
GRADLE_RECORDS = {"gradle": 3, "project": 2, "included": 2, "configuration": 3, "resolved": 4, "unresolved": 5,
                  "failed": 4, "unknown": 4, "narrowed": 3, "flatdir": 3, "early": 3, "restored": 3, "unfinished": 2,
                  "done": 3}  # kind: length
GRADLE_PATH_RE = re.compile(r"^:(?:[A-Za-z0-9_.-]{1,64}(?::[A-Za-z0-9_.-]{1,64}){0,15})?$")
CLASS_NAME_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$.]{0,199}$")
DIST_ZIP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\.zip$")
CAMEL_WORD_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")
# A component the init script prints as neither a module nor a project. Gradle's public ComponentIdentifier has
# two more kinds (its Javadoc at docs.gradle.org, read 2026-11-24): LibraryBinaryIdentifier, a native library of
# Gradle's software model, and RootComponentIdentifier, the root a resolution starts from, which the walk never
# reaches again. Any other is a type Gradle does not document. None has coordinates to match an advisory with, so
# one makes the result partial.
OTHER_COMPONENT = "other component"
# A Gradle configuration's context, most exposed first. ship and other ship for attribution's sake: a
# configuration the naming conventions do not place is never taken for one that stays out of the product.
GRADLE_CONTEXTS = ("ship", "other", "compile", "build", "test")
SHIPPING_CONTEXTS = ("ship", "other")
MAX_UNRESOLVED_NOTES = 20


def gradle_context(name: str) -> str:
    """What a configuration is for, from its name as Gradle's Java plugins form it (<source set><Kind>, the
    main source set unprefixed): test when a word of it is test (testRuntimeClasspath, integrationTest...,
    testFixtures...), build for an annotation-processor path or kapt, ship for a runtime classpath, compile for a
    compile classpath, other for anything else. It is reported and decides whether a dependency ships; it never
    lowers a class."""
    words = [w.lower() for w in CAMEL_WORD_RE.findall(name)]
    if "test" in words or "tests" in words:
        return "test"
    if name == "annotationProcessor" or name.endswith("AnnotationProcessor") or words[:1] == ["kapt"]:
        return "build"
    if name == "runtimeClasspath" or name.endswith("RuntimeClasspath"):
        return "ship"
    if name == "compileClasspath" or name.endswith("CompileClasspath"):
        return "compile"
    return "other"


def _gradle_element(item):
    """(package, version) of one path element, version None for a project or another kind of component; None
    when the element is not one the init script prints."""
    if not isinstance(item, list) or not all(isinstance(v, str) for v in item):
        return None
    if len(item) == 4 and item[0] == "module":
        return f"{item[1]}:{item[2]}", item[3]
    if len(item) == 2 and item[0] == "project":
        return f"project {item[1]}", None
    if len(item) == 2 and item[0] == "other":
        return OTHER_COMPONENT, None
    return None


def _gradle_record(text: str):
    """One line of the init script as (kind, fields, path), None when it is not one it prints: a line that
    carries the nonce but cannot be read makes the result partial rather than being dropped unseen."""
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, list) or not value or not isinstance(value[0], str) \
            or GRADLE_RECORDS.get(value[0]) != len(value):
        return None
    has_path = value[0] in ("resolved", "unresolved")
    fields = value[1:-1] if has_path else value[1:]
    if not all(isinstance(v, str) for v in fields):
        return None
    path = None
    if has_path:
        if not isinstance(value[-1], list) or not value[-1]:
            return None
        path = [_gradle_element(item) for item in value[-1]]
        if None in path:
            return None
    return value[0], fields, path


def _gradle_project(projects: dict, path: str) -> dict:
    return projects.setdefault(path, {"id": f"project {path}", "version": None, "nodes": [], "parsed": False,
                                      "configurations": [], "unresolved": [], "failed": [], "unknown": [],
                                      "early": [], "unfinished": False, "projects": [], "others": 0, "index": {}})


def _add_resolved(module: dict, configuration: str, path: list) -> None:
    """A resolved component into the project's inventory: one node per coordinate and version, whatever number
    of configurations holds it, with the most exposed context and that configuration's path; a project
    dependency is kept by its path only, as Maven keeps a sibling module."""
    package, version = path[-1]
    if version is None:
        if package == OTHER_COMPONENT:
            module["others"] += 1
        elif package not in module["projects"]:
            module["projects"].append(package)
        return
    context = gradle_context(configuration)
    node = module["index"].get((package, version))
    if node is None:
        group, _sep, artifact = package.partition(":")
        node = new_node(group, artifact, "", "", version, context, False, path, ships=context in SHIPPING_CONTEXTS)
        node["configurations"] = []
        module["index"][(package, version)] = node
        module["nodes"].append(node)
    elif GRADLE_CONTEXTS.index(context) < GRADLE_CONTEXTS.index(node["scope"]):
        node.update(scope=context, ships=context in SHIPPING_CONTEXTS, path=path)
    if configuration not in node["configurations"]:
        node["configurations"].append(configuration)


def parse_gradle_output(text: str, nonce: str) -> dict:
    """The resolved graph in the output of a run of the init script: only the lines that carry this run's
    nonce are read. complete only when the root project listed the projects of the build, every one of them
    said it was done after the number of configurations it walked, no dependency is unresolved, no
    configuration failed, no dependency result is of a kind the walk cannot follow, no component is one the
    audit cannot match, the build declares no flat-directory repository, gave no repository its artefact-only
    metadata source back (early, restored), stopped adding configurations (unfinished), includes no other
    build, and every marked line could be read; the build's exit status is checked by the caller. `narrowed` lists the
    repositories the init script read without their artefact-only metadata source, which can explain an
    unresolved dependency."""
    prefix = f"{GRADLE_MARK} {nonce} "
    info = {"gradle": None, "java": None}
    expected, included, done, narrowed, flatdirs, restored = [], [], {}, [], [], []
    projects: dict = {}
    malformed = 0
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        if not line.startswith(prefix):
            continue
        record = _gradle_record(line[len(prefix):])
        if record is None:
            malformed += 1
            continue
        kind, fields, path = record
        if kind == "gradle":
            if info["gradle"] is None:
                info.update(gradle=fields[0], java=fields[1])
        elif kind == "project":
            expected.append(fields[0])
        elif kind == "included":
            included.append(fields[0])
        elif kind == "done":
            done[fields[0]] = fields[1]
        elif kind == "configuration":
            _gradle_project(projects, fields[0])["configurations"].append(fields[1])
        elif kind == "failed":
            _gradle_project(projects, fields[0])["failed"].append((fields[1], fields[2]))
        elif kind == "unknown":
            _gradle_project(projects, fields[0])["unknown"].append((fields[1], fields[2]))
        elif kind in ("narrowed", "flatdir", "restored"):
            {"narrowed": narrowed, "flatdir": flatdirs, "restored": restored}[kind].append(tuple(fields))
        elif kind == "early":
            _gradle_project(projects, fields[0])["early"].append(fields[1])
        elif kind == "unfinished":
            _gradle_project(projects, fields[0])["unfinished"] = True
        elif kind == "unresolved":
            _gradle_project(projects, fields[0])["unresolved"].append((fields[1], fields[2]))
        else:
            _add_resolved(_gradle_project(projects, fields[0]), fields[1], path)
    expected = list(dict.fromkeys(expected))
    order = expected + sorted(p for p in projects if p not in expected)
    for name in expected:
        _gradle_project(projects, name)
    modules = [projects[name] for name in order]
    for module in modules:
        name = module["id"][len("project "):]
        module["parsed"] = done.get(name) == str(len(module["configurations"]))
        del module["index"]
        for node in module["nodes"]:
            node["configurations"].sort(key=lambda c: (GRADLE_CONTEXTS.index(gradle_context(c)), c))
    restored = list(dict.fromkeys(restored))
    complete = bool(info["gradle"] and expected and not malformed and not included and not flatdirs and not restored
                    and all(m["parsed"] and not m["unresolved"] and not m["failed"] and not m["unknown"]
                            and not m["others"] and not m["early"] and not m["unfinished"] for m in modules))
    return {"modules": modules, "info": info, "included": included, "malformed": malformed, "complete": complete,
            "narrowed": list(dict.fromkeys(narrowed)), "flatdirs": list(dict.fromkeys(flatdirs)),
            "restored": restored}


def gradle_project_label(path: str) -> str:
    return "project " + (path if GRADLE_PATH_RE.match(path) else withheld("project path", path))


def gradle_owner_label(owner: str) -> str:
    """Who declares a repository: a project, or the settings."""
    return "the settings" if owner == "settings" else gradle_project_label(owner)


def repository_names(entries: list) -> list:
    return [f"{safe(name, NAME_RE, 'repository name')} of {gradle_owner_label(owner)}" for owner, name in entries]


def safe_requested(text: str) -> str:
    """An unresolved request as Gradle names it: a coordinate with or without its version, or a project."""
    if text.startswith("project "):
        return gradle_project_label(text[len("project "):])
    parts = text.split(":")
    if len(parts) in (2, 3) and NAME_RE.match(parts[0]) and NAME_RE.match(parts[1]) \
            and (len(parts) == 2 or VERSION_RE.match(parts[2])):
        return text
    return withheld("dependency", text)


def gradle_notes(parsed: dict) -> list:
    """What the report lists under Could not be evaluated for a Gradle run, every value through its grammar."""
    notes = [f"included build {safe(name, NAME_RE, 'build name')}: not audited (the builds a composite includes "
             "are not)" for name in parsed["included"]]
    unresolved = [(m, configuration, requested) for m in parsed["modules"]
                  for configuration, requested in m["unresolved"]]
    notes += [f"{module_label(m['id'])}, {safe(configuration, WORD_RE, 'configuration')}: "
              f"{safe_requested(requested)} did not resolve" for m, configuration, requested in
              unresolved[:MAX_UNRESOLVED_NOTES]]
    if len(unresolved) > MAX_UNRESOLVED_NOTES:
        notes.append(f"{len(unresolved) - MAX_UNRESOLVED_NOTES} more unresolved dependencies (the build output "
                     "names them)")
    notes += [f"flat-directory repository {name}, whose artefacts have no metadata to list their dependencies"
              for name in repository_names(parsed["flatdirs"][:MAX_UNRESOLVED_NOTES])]
    if unresolved:
        notes += [f"repository {name} was read without its artefact-only metadata source, so a module it holds "
                  "without metadata does not resolve in the audit"
                  for name in repository_names(parsed["narrowed"][:MAX_UNRESOLVED_NOTES])]
    notes += [f"repository {name} had its artefact-only metadata source given back while the audit resolved, so "
              "a module without metadata may be listed without its dependencies"
              for name in repository_names(parsed["restored"][:MAX_UNRESOLVED_NOTES])]
    for module in parsed["modules"]:
        if not module["parsed"]:
            notes.append(f"{module_label(module['id'])}: did not report its whole dependency graph")
        if module["unfinished"]:
            notes.append(f"{module_label(module['id'])}: kept adding configurations while they were walked; the "
                         "last ones were not walked")
        notes += [f"{module_label(module['id'])}, {safe(configuration, WORD_RE, 'configuration')}: resolved before "
                  "the audit could take back an artefact-only metadata source the build had given back"
                  for configuration in module["early"][:MAX_UNRESOLVED_NOTES]]
        notes += [f"{module_label(module['id'])}, {safe(configuration, WORD_RE, 'configuration')}: its resolution "
                  f"failed ({safe(kind, CLASS_NAME_RE, 'exception')})" for configuration, kind in module["failed"]]
        notes += [f"{module_label(module['id'])}, {safe(configuration, WORD_RE, 'configuration')}: a dependency "
                  f"result of a kind the audit cannot read ({safe(kind, CLASS_NAME_RE, 'class')}) was not walked"
                  for configuration, kind in module["unknown"]]
        if module["others"]:
            notes.append(f"{module_label(module['id'])}: {module['others']} components that are neither a module "
                         "nor a project could not be matched against advisories")
    if parsed["malformed"]:
        notes.append(f"{parsed['malformed']} lines of the init script's output could not be read")
    return notes


def _read_property(text: str, key: str):
    """One value of a Java properties file, its backslash escapes undone (`https\\://` is `https://`)."""
    found = re.search(rf"^[ \t]*{re.escape(key)}[ \t]*[=:][ \t]*(\S+)[ \t]*$", text, re.M)
    return re.sub(r"\\(.)", r"\1", found.group(1)) if found else None


def _plain_relative(path: str) -> bool:
    return bool(path) and not os.path.isabs(path) and all(p not in ("", ".", "..") for p in path.split("/"))


def wrapper_url_hash(url: str) -> str:
    """The directory name the Gradle wrapper gives a distribution URL: the MD5 of the URL without its user
    information, in base 36. MD5 here is Gradle's naming scheme, not a security control."""
    number = int.from_bytes(hashlib.md5(re.sub(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/@]*@", r"\1", url)
                                        .encode("utf-8"), usedforsecurity=False).digest(), "big")
    digits = ""
    while number:
        number, rest = divmod(number, 36)
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"[rest] + digits
    return digits or "0"


def gradle_wrapper_distribution(project_dir: str, repo, environ) -> str | None:
    """The bin/gradle of the distribution the project's wrapper names, when the wrapper has already unpacked
    it into the user's Gradle user home (GRADLE_USER_HOME, else ~/.gradle) and left its completion marker, in
    the directory Gradle names after this distribution URL only: a distribution of the same file name from
    another URL is another distribution. With a distributionSha256Sum, an archive the wrapper left there must
    have that digest; the wrapper deletes it once installed, and checked it before unpacking. A wrapper that
    keeps its distribution anywhere but the Gradle user home gives None: that
    copy would be a program inside the project."""
    data = read_small(os.path.join(project_dir, GRADLE_WRAPPER_PROPERTIES), 65536)
    text = data.decode("utf-8", "replace") if data else ""
    url = _read_property(text, "distributionUrl")
    name = url.rsplit("/", 1)[-1] if url else ""
    bases = [_read_property(text, key) or "GRADLE_USER_HOME" for key in ("distributionBase", "zipStoreBase")]
    paths = [_read_property(text, key) or "wrapper/dists" for key in ("distributionPath", "zipStorePath")]
    if not DIST_ZIP_RE.match(name) or bases != ["GRADLE_USER_HOME"] * 2 or not all(map(_plain_relative, paths)):
        return None
    home = environ.get("GRADLE_USER_HOME") or os.path.join(os.path.expanduser("~"), ".gradle")
    unpacked, zips = (os.path.join(home, *p.split("/"), name[:-len(".zip")]) for p in paths)
    digest = wrapper_url_hash(url)
    if not os.path.isfile(os.path.join(zips, digest, name + ".ok")):
        return None
    # The wrapper checks distributionSha256Sum against the archive it downloaded before it unpacks it, writes the
    # marker once the distribution is unpacked, and then deletes the archive; a later run that finds the marker
    # and the unpacked distribution checks nothing again (Install.createDist in Gradle's wrapper-shared). So the
    # audit trusts a completed installation as far as the wrapper
    # itself does, no further: whoever can write the Gradle user home can change it, as they could change what
    # the wrapper runs. An archive still beside the marker must have the digest the properties give.
    expected = _read_property(text, "distributionSha256Sum")
    archive = os.path.join(zips, digest, name)
    if expected and os.path.lexists(archive) and file_sha256(archive) != expected.lower():
        return None
    pattern = os.path.join(glob.escape(os.path.join(unpacked, digest)), "*", "bin", "gradle")
    for tool in sorted(glob.glob(pattern)):
        if os.path.isfile(tool) and os.access(tool, os.X_OK) and not (repo and inside(tool, repo)):
            return tool
    return None


def find_gradle(project_dir: str, repo, environ) -> tuple:
    """(path, where it came from): the wrapper's distribution when the project has a wrapper, else gradle from
    PATH, never a program that resolves inside the repository. A wrapper whose distribution is not there stops
    the audit rather than falling back to PATH, because another Gradle version may not configure the build."""
    if any(os.path.lexists(os.path.join(project_dir, p)) for p in ("gradlew", GRADLE_WRAPPER_PROPERTIES)):
        distribution = gradle_wrapper_distribution(project_dir, repo, environ)
        if distribution:
            return distribution, "the wrapper's distribution"
        raise NotRun("wrapper not provisioned", f"run `./gradlew --version` in {shown(project_dir)} once with "
                                                "network access, then the audit again")
    found = shutil.which("gradle", path=absolute_path(environ))
    if found and repo and inside(found, repo):
        raise NotRun("build tool missing", f"the gradle on PATH ({shown(found)}) resolves inside the repository and "
                                           "is never run: install Gradle outside it")
    if found:
        return found, "PATH"
    raise NotRun("build tool missing", "install Gradle (/implement-from-spec:setup offers it), then run the audit "
                                       "again")


def gradle_problem(code, text: str, parsed: dict, project: str, log: str, timeout: float, command: str) -> tuple:
    """(category, remedy) of a Gradle run that gave no complete result. A failed build is categorised from
    fixed phrases of Gradle's messages, an incomplete graph from what the init script printed; no line of the
    output is copied (a repository URL in it may carry a credential)."""
    online = f"run `{command} help` in {shown(project)} once with network access, then the audit again"
    if code == "time limit":
        return "time limit", time_limit_remedy(f"the build tool did not finish within {int(timeout)} seconds")
    if code == "output limit":
        return "build tool failed", f"its output passed {mib(MAX_BUILD_OUTPUT_BYTES)}: see {shown(log)}"
    if code != 0:
        if re.search(r"Plugin \[id: '[^']*'[^\]\n]*\] was not found", text):
            return "plugin not in the local repository", online
        if any(phrase in text for phrase in ("No cached version", "available for offline mode", "Could not resolve")):
            return "artifacts not in the local repository", online
        if "Unsupported class file major version" in text:
            return "build tool failed", (f"this Gradle cannot run on the Java it started with: set JAVA_HOME to a "
                                         f"Java it supports (its output is at {shown(log)})")
        if any(phrase in text for phrase in ("Could not compile", "A problem occurred evaluating", "unexpected token",
                                              "Could not find method", "Could not get unknown property")):
            return "invalid project", f"Gradle could not configure the build: fix it (its output is at {shown(log)})"
        return "build tool failed", f"gradle exited {code}: see its output at {shown(log)}"
    if parsed["included"]:
        return "partial coverage", ("the build includes other builds, which are not audited: audit each with "
                                    "`audit --repo <its directory>`")
    unresolved = [m for m in parsed["modules"] if m["unresolved"]]
    if unresolved:
        tasks = [m["id"][len("project "):] for m in unresolved if GRADLE_PATH_RE.match(m["id"][len("project "):])]
        tasks = " ".join((":dependencies" if p == ":" else p + ":dependencies") for p in tasks[:5]) \
            or "<project>:dependencies"
        count = len({(m["id"], requested) for m in unresolved for _configuration, requested in m["unresolved"]})
        why = "an error in the build"
        if parsed["narrowed"]:
            why += (" or a module without metadata in a repository the audit reads without its artefact-only "
                    f"metadata source ({named_list(repository_names(parsed['narrowed']))}), whose dependencies "
                    "no metadata lists: publish it with a POM or Gradle module metadata")
        return "partial coverage", (f"{count} dependencies did not resolve offline: run `{command} {tasks}` in "
                                    f"{shown(project)} once with network access, then the audit again; one that "
                                    f"still does not resolve is {why}")
    failed = sum(len(m["failed"]) for m in parsed["modules"])
    if failed:
        return "partial coverage", f"the resolution of {failed} configurations failed: see {shown(log)}"
    if parsed["restored"]:
        return "partial coverage", (f"the build gives {named_list(repository_names(parsed['restored']))} its "
                                    "artefact-only metadata source back after the audit took it away, so a module without "
                                    "metadata may be listed without its dependencies: stop the build from adding "
                                    "artifact() to metadataSources, then run the audit again")
    early = sum(len(m["early"]) for m in parsed["modules"])
    if early:
        return "partial coverage", (f"{early} configurations were resolved while the build had given a repository "
                                    "its artefact-only metadata source back, before the audit could take it back: "
                                    "stop the build from adding artifact() to metadataSources, then run the audit "
                                    "again")
    unfinished = sum(1 for m in parsed["modules"] if m["unfinished"])
    if unfinished:
        return "partial coverage", (f"{unfinished} projects kept adding configurations while they were walked: see "
                                    f"{shown(log)}")
    unknown = sum(len(m["unknown"]) for m in parsed["modules"])
    if unknown:
        return "partial coverage", (f"{unknown} dependency results of a kind the audit cannot read were not walked: "
                                    f"check those dependencies by hand (the build output at {shown(log)} names their "
                                    "configurations)")
    if parsed["flatdirs"]:
        return "partial coverage", (f"the build declares the flat-directory repository "
                                    f"{named_list(repository_names(parsed['flatdirs']))}, whose artefacts have no "
                                    "metadata to list their dependencies: move them to a repository with POMs or "
                                    "Gradle module metadata, then run the audit again")
    others = sum(m["others"] for m in parsed["modules"])
    if others:
        return "partial coverage", (f"{others} components that are neither a module nor a project cannot be matched "
                                    f"against advisories: check them by hand (the build output at {shown(log)} names "
                                    "them)")
    missing = sum(1 for m in parsed["modules"] if not m["parsed"])
    if missing:
        return "partial coverage", f"{missing} projects of the build reported no dependency graph: see {shown(log)}"
    return "partial coverage", f"the build printed no complete dependency graph: see {shown(log)}"


def gradle_inventory(project_dir: str, repo, timeout: float, environ, label: str, deadline=None,
                     total=None) -> dict:
    """The inventory of a Gradle build, resolved offline through the plugin's init script. The project cache
    directory and the build directories go to a scratch directory that is removed afterwards, so Gradle writes
    nothing in the project; the nonce is new for every run, so no line left from another run is read."""
    tool, source = find_gradle(project_dir, repo, environ)
    timeout = run_limit(timeout, deadline, total, f"Gradle resolved the {label}")
    if not os.path.isfile(GRADLE_INIT_SCRIPT):
        raise NotRun("build tool failed", f"the plugin's {shown(GRADLE_INIT_SCRIPT)} is missing: reinstall the plugin")
    log = build_log(repo, label)
    scratch = tempfile.mkdtemp(prefix="ifs-dependency-audit-gradle-")
    try:
        if repo and inside(scratch, repo):
            raise NotRun("scratch directory refused", "the temporary directory resolves inside the repository: "
                                                      "unset TMPDIR")
        nonce = secrets.token_hex(16)
        argv = [tool, *GRADLE_ARGS, "--project-cache-dir", os.path.join(scratch, "project-cache"),
                "-I", GRADLE_INIT_SCRIPT, f"-D{NONCE_PROPERTY}={nonce}", f"-D{SCRATCH_PROPERTY}={scratch}",
                GRADLE_TASK]
        code, text = run_build_tool(argv, project_dir, timeout, log, tool_environ(environ, repo))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    parsed = parse_gradle_output(text, nonce)
    complete = parsed["complete"] and code == 0
    command = "./gradlew" if source == "the wrapper's distribution" else "gradle"
    return {"modules": [dict(m, tool="Gradle") for m in parsed["modules"] if m["parsed"] or m["nodes"]],
            "complete": complete,
            "notes": gradle_notes(parsed),
            "problem": None if complete else gradle_problem(code, text, parsed, project_dir, log, timeout, command),
            "unparsed": [],  # gradle_notes names them, with what they did report
            "info": {"tool": "Gradle", "path": tool, "source": source, "log": log,
                     "version": safe(parsed["info"]["gradle"], TOOL_VERSION_RE, "version"),
                     "java": safe(parsed["info"]["java"], TOOL_VERSION_RE, "version"),
                     "command": (f"{command} {' '.join(GRADLE_ARGS)} -I {os.path.basename(GRADLE_INIT_SCRIPT)} "
                                 f"{GRADLE_TASK} (project cache and build directories in a scratch directory)")}}


def resolve_tree(snap, ctx: dict, rev, label: str) -> tuple:
    """(inventory, resolution inputs) of one side: the working tree when `rev` is None, else that revision
    written out to a scratch directory that is removed afterwards. NotRun when nothing can be resolved."""
    root, project = ctx["root"], ctx["project"]
    build_files = ("pom.xml", *GRADLE_BUILD_FILES)
    if rev is None:
        names = worktree_files(snap, root, ctx["git"])
        inputs = worktree_inputs(root, names, project)
        project_dir = os.path.join(root, project) if project else root
        present = {name for name in build_files if os.path.isfile(os.path.join(project_dir, name))}
        selection = select_tools(present, ctx.get("build_tool"), shown(project_dir))
        return _resolve_directory(ctx, project_dir, label, selection), inputs
    entries = list_tree(snap, root, rev)
    inputs = revision_inputs(snap, root, entries, project)
    prefix = project + "/" if project else ""
    present = {path[len(prefix):] for mode, _o, _s, path in entries
               if mode in ("100644", "100755", "120000") and path[len(prefix):] in build_files
               and path.startswith(prefix)}
    selection = select_tools(present, ctx.get("build_tool"), f"{safe_path(project or '.')} of {rev[:12]}")
    scratch = tempfile.mkdtemp(prefix="ifs-dependency-audit-")
    try:
        if inside(scratch, root):
            raise NotRun("scratch directory refused",
                         "the temporary directory resolves inside the repository: unset TMPDIR")
        counts = materialise(snap, root, rev, scratch)
        inventory = _resolve_directory(ctx, os.path.join(scratch, project) if project else scratch, label, selection)
        if counts["links_omitted"] or counts["submodules"]:
            inventory["notes"].append(f"{counts['links_omitted']} links and {counts['submodules']} submodules of "
                                      f"{rev[:12]} were not written out")
            inventory["complete"] = False
            inventory["problem"] = inventory["problem"] or (
                "partial coverage", f"{counts['links_omitted']} links that leave {rev[:12]} or cannot be written, and "
                                    f"{counts['submodules']} submodules of it, were not written out, and the build "
                                    "could read them: check the revision out and run `audit --repo` on that "
                                    "working tree")
        return inventory, inputs
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


BUILD_TOOLS = {"maven": "Maven", "gradle": "Gradle"}  # the --build-tool values and the tools they name


def and_list(items: list) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def select_tools(present: set, chosen, where: str) -> tuple:
    """(tools, why): the build tool or tools that resolve a project, from the build files in its directory
    (`present`, their names) or the tool the user named with --build-tool, which then applies alone. A project
    holding a pom.xml and Gradle build files is resolved by both: either could be the build it ships (one being
    migrated to the other, or one left behind), and picking one would leave the other unchecked without a
    word. `where` names the directory for the not-run line."""
    gradle = [name for name in GRADLE_BUILD_FILES if name in present]
    has_pom = "pom.xml" in present
    if chosen:
        if not (has_pom if chosen == "maven" else gradle):
            files = "pom.xml" if chosen == "maven" else "Gradle build"
            raise NotRun("no build file", f"no {files} in {where}, which --build-tool {chosen} names: name the build "
                                          "tool whose build files the project holds")
        return [BUILD_TOOLS[chosen]], f"named with --build-tool {chosen}"
    found = (["pom.xml"] if has_pom else []) + gradle
    if not found:
        raise NotRun("no build file", f"no pom.xml and no Gradle build in {where}: name the directory that holds "
                                      "one with --project-dir")
    tools = (["Maven"] if has_pom else []) + (["Gradle"] if gradle else [])
    both = "; each is resolved, and coverage is complete only when both are" if len(tools) > 1 else ""
    return tools, f"{and_list(found)} found{both}"


def selection_text(tools: list, why: str) -> str:
    """The build tools of a resolution and why: "build tool Maven (pom.xml found)"."""
    return f"build tool{'s' if len(tools) > 1 else ''} {' and '.join(tools)} ({why})"


def _run_tool(tool: str, ctx: dict, project_dir: str, label: str) -> dict:
    """The inventory of one build tool; each of its runs is limited to the smaller of --timeout and what is left
    of the audit's total limit."""
    deadline, total = ctx.get("deadline"), ctx.get("total_timeout")
    if tool == "Maven":
        return maven_inventory(project_dir, ctx["root"], ctx["profiles"], ctx["timeout"], ctx["environ"], label,
                               deadline, total)
    return gradle_inventory(project_dir, ctx["root"], ctx["timeout"], ctx["environ"], label, deadline, total)


def both_tools_remedy(run: dict, tools: list, with_category: bool = False) -> str:
    """The remedy of one of two builds that did not resolve, naming its build and the option that audits the
    other build alone, for a project that keeps the build files of a tool it no longer uses; `with_category`
    for the note of a second such build, whose category the status line does not carry."""
    tool = run["info"]["tool"]
    other = next(t for t in tools if t != tool)
    category = f"{run['problem'][0]}: " if with_category else ""
    return (f"the {tool} build: {category}{run['problem'][1]}; if the project builds with {other} only, "
            f"`--build-tool {other.lower()}` audits that build alone")


def _resolve_directory(ctx: dict, project_dir: str, label: str, selection: tuple) -> dict:
    """The inventory of a project directory, resolved by each selected tool. With one tool, a NotRun stops the
    side. With two, each tool's result is kept: their modules together (each module carries its
    tool), complete only when both are, a tool that could not run counting as an incomplete result, and the
    problem of the first incomplete one, naming its build, as the side's problem."""
    tools, why = selection
    runs = []
    for tool in tools:
        try:
            runs.append(_run_tool(tool, ctx, project_dir, label))
        except NotRun as exc:
            if len(tools) == 1:
                raise
            runs.append({"modules": [], "complete": False, "notes": [], "problem": (exc.category, exc.remedy),
                         "unparsed": [], "info": {"tool": tool, "not_run": exc.category}})
    if ctx["profiles"] and "Maven" not in tools:
        runs[0]["notes"].append("the Maven profiles named (--profile) do not apply to a Gradle build")
    elif ctx["profiles"] and len(tools) > 1:
        runs[0]["notes"].append("the Maven profiles named (--profile) apply to the Maven build only")
    if len(runs) == 1:
        inventory = runs[0]
    else:
        incomplete = [r for r in runs if not r["complete"]]
        first = incomplete[0] if incomplete else None
        inventory = {"modules": [m for r in runs for m in r["modules"]], "complete": not incomplete,
                     "notes": [n for r in runs for n in r["notes"]] +
                              [both_tools_remedy(r, tools, with_category=True) for r in incomplete[1:]],
                     "problem": (first["problem"][0], both_tools_remedy(first, tools)) if first else None,
                     "unparsed": [u for r in runs for u in r["unparsed"]]}
    inventory["tools"] = [r["info"] for r in runs]
    inventory["selection"] = selection_text(tools, why)
    return inventory


# ---------------------------------------------------------------- attribution and classification
INVENTORY = {
    "Maven": ("the dependencies of every module of the build, in every scope, as Maven resolved them for the default "
              "build configuration and, each in a run of its own, the profiles named. Not in it: build plugins, "
              "annotation-processor paths "
              "configured in the compiler plugin, shaded or relocated content."),
    "Gradle": ("every resolvable configuration of every project of the build, annotation-processor paths included, "
               "as Gradle resolved them. Not in it: the buildscript classpath, file dependencies (files and file "
               "trees, which Gradle's resolution result does not hold), shaded or relocated content, included builds. "
               "A module without metadata counts as unresolved, never as a module with no dependencies."),
}


def inventory_line(resolution) -> str:
    """What the inventory is, for the build tool that resolved it; both when both resolved it or the audit
    stopped before one ran."""
    tools = [info["tool"] for info in resolution["tools"]] if resolution else []
    what = INVENTORY[tools[0]] if len(tools) == 1 else \
        f"for Maven, {INVENTORY['Maven']} For Gradle, {INVENTORY['Gradle']}"
    return f"Inventory: {what} {INVENTORY_MEANING}"


def module_label(module_id: str) -> str:
    """A Maven module as its group:artifact, a Gradle project as "project <path>"."""
    if module_id.startswith("project "):
        return gradle_project_label(module_id[len("project "):])
    if module_id == OTHER_COMPONENT:
        return module_id
    return safe_coordinate(module_id)


def path_label(package: str, version) -> str:
    """One element of a dependency path: a coordinate with its version, or a Gradle project (version None)."""
    if version is None:
        return module_label(package)
    return f"{safe_coordinate(package)}:{safe(version, VERSION_RE, 'version')}"


def scope_label(node: dict) -> str:
    """The Maven scope, or the Gradle context followed by the configurations that hold the dependency."""
    text = safe(node["scope"], WORD_RE, "scope")
    configurations = node.get("configurations") or []
    if configurations:
        listed = ", ".join(safe(c, WORD_RE, "configuration") for c in configurations[:3])
        text += f": {listed}" + (f", +{len(configurations) - 3} more" if len(configurations) > 3 else "")
    return text + (", optional" if node["optional"] else "")


def occurrence(module: dict, node: dict, advisories: list, fix, fix_checked: bool = True) -> dict:
    """One report entry, every value passed through its grammar: a report is read by a model, so nothing in it
    is worded by an advisory, a build file or the build tool."""
    worst = min(advisories, key=lambda a: CLASS_ORDER[a["class"]])
    return {"module": module_label(module["id"]), "tool": module.get("tool"),
            "coordinate": safe_coordinate(node["package"]),
            "version": safe(node["version"], VERSION_RE, "version"), "scope": scope_label(node),
            "path": [path_label(package, version) for package, version in node["path"]],
            "advisories": osv.advisory_entries(advisories),
            "class": worst["class"],
            "fix": safe(fix, VERSION_RE, "version") if fix else None, "fix_checked": fix_checked}


def tool_text(info: dict) -> str:
    """One build tool of the resolution line: what ran, where its output went and its command."""
    if info.get("not_run"):
        return f"{info['tool']} not run ({info['not_run']})"
    if info["tool"] == "Maven":
        text = (f"Maven {info['version']} at {info['path']} (from {info['source']}), dependency plugin "
                f"{info['plugin']}, Java {info['java']}")
    else:
        text = f"Gradle {info['version']} at {info['path']} (from {info['source']}), Java {info['java']}"
    return f"{text}; build output: {info['log']}; command: {info['command']}"


def resolution_line(resolution: dict) -> str:
    if not resolution:
        return "Resolution: none (the audit stopped before the build tool ran)"
    tools = "; ".join(tool_text(info) for info in resolution["tools"])
    return (f"Resolution: {resolution['selection']}; {tools}; "
            f"profiles: {', '.join(resolution['profiles']) or 'none'}; "
            f"project: {resolution['project']}; candidate: {resolution['candidate']}; modules "
            f"({len(resolution['modules'])}, coverage {resolution['coverage']}): "
            f"{', '.join(resolution['modules'][:40]) or 'none'}; base: {resolution['base']}")


MAVEN = osv.register(osv.Ecosystem(
    name="Maven", accepts=lambda name: name == "Maven" or name.startswith("Maven:"), export_url=EXPORT_URL,
    minimum=MIN_ADVISORIES, label="OSV Maven export", attribution=ATTRIBUTION, compare=compare_versions,
    occurrence=occurrence, resolution_line=resolution_line, inventory_line=inventory_line,
    refresh_command="refresh",
    refresh_remedy=("run `dependency-audit.py refresh` with network access, or `refresh --from <zip>` with a copy "
                    "of the export")))


# ---------------------------------------------------------------- the audit
def resolve_base(snap, ctx: dict) -> tuple:
    """(base occurrences or None, the base's inputs or None, what the report says about the base). The base is
    always resolved from its own revision: no list of file names covers everything a build reads to choose
    its dependencies (a script it applies, a file a profile's activation tests), so equal inputs prove nothing.
    Its build tools are chosen from its own build files by the rule the candidate's follow, so a build the
    change adds has no base and its occurrences are the change's. Nothing short of a complete base resolution
    moves an occurrence out of unknown."""
    rev = ctx["base"]
    if rev is None:
        return None, None, "none given (every entry is attribution unknown)"
    try:
        inventory, base_inputs = resolve_tree(snap, ctx, rev, "base")
    except NotRun as exc:
        return None, None, f"not resolved from {rev[:12]} ({exc.category}): every entry is attribution unknown"
    if not inventory["complete"]:
        return None, base_inputs, (f"not resolved from {rev[:12]} ({inventory['problem'][0]}): every entry is "
                                   "attribution unknown")
    return (base_occurrences(inventory["modules"]), base_inputs,
            f"resolved from {rev[:12]} with {inventory['selection']}")


# ---------------------------------------------------------------- the PyPI side
# The PyPI inventory (dependency_audit_pypi.py) reads files, never runs a tool: from the working tree through these
# checks, or from a revision through git, the way materialise reads one, but without writing anything out.
PYPI = pypi.PYPI


class WorkTreeFiles:
    """The working tree's files for the PyPI inventory: the paths a candidate holds (worktree_files) and a reader
    that reads nothing else: a path that is not one of them (a git-ignored file, a file inside .git) is refused,
    a link is followed only to another of them, and the file is opened without following a link, at most
    INPUT_LIMIT bytes. The check is made on names, so it cannot stop a process that changes the working tree while
    the audit reads it (the user's own processes, TM-34)."""

    def __init__(self, snap, root: str, git: bool) -> None:
        self.root, self.real_root = root, os.path.realpath(root)
        # git ls-files --cached still names a tracked file the working tree deleted: it is not in the candidate
        self.paths = {p for p in worktree_files(snap, root, git) if os.path.lexists(os.path.join(root, *p.split("/")))}

    def read(self, rel: str) -> tuple:
        if rel not in self.paths or pypi.in_git_dir(rel):
            return None, "is not one of the candidate's files"
        path = os.path.join(self.root, *rel.split("/"))
        if not os.path.lexists(path):
            return None, "is missing"
        try:
            target = os.path.relpath(os.path.realpath(path), self.real_root).replace(os.sep, "/")
        except (OSError, ValueError):  # cannot be resolved, or on another drive: refused, never read
            return None, "is a link that leaves the repository"
        if target == ".." or target.startswith("../") or os.path.isabs(target):
            return None, "is a link that leaves the repository"
        if target not in self.paths or pypi.in_git_dir(target):
            return None, "is a link to a file that is not one of the candidate's files"
        data = read_small(os.path.join(self.real_root, *target.split("/")))
        return (data, None) if data is not None else (None, f"is not a regular file of at most {mib(INPUT_LIMIT)}")

    def close(self) -> None:
        pass


class RevisionFiles:
    """A revision's files for the PyPI inventory, read with git ls-tree and git cat-file (no attribute or filter
    applies): a link is followed inside the revision only, at most MAX_LINK_HOPS links, and a submodule or a
    file over INPUT_LIMIT is not read."""

    def __init__(self, snap, root: str, rev: str) -> None:
        self.snap, self.root = snap, root
        self.entries = {path: (mode, oid, size) for mode, oid, size, path in list_tree(snap, root, rev)}
        self.paths = {p for p, (mode, _o, _s) in self.entries.items() if mode in ("100644", "100755", "120000")}
        self.blobs = None

    def read(self, rel: str) -> tuple:
        for _hop in range(pypi.MAX_LINK_HOPS + 1):
            found = None if pypi.in_git_dir(rel) else self.entries.get(rel)
            if found is None or found[0] not in ("100644", "100755", "120000"):
                return None, "is missing" if found is None else "is not a regular file"
            mode, oid, size = found
            if size > INPUT_LIMIT:
                return None, f"is over {mib(INPUT_LIMIT)}"
            if self.blobs is None:
                self.blobs = BlobReader(self.snap, self.root)
            data = self.blobs.read(oid)
            if mode != "120000":
                return data, None
            pointer = os.fsdecode(data)
            rel = posixpath.normpath(posixpath.join(posixpath.dirname(rel), pointer)) if pointer and \
                not pointer.startswith("/") else ""
            if not rel or rel == ".." or rel.startswith("../"):
                return None, "is a link that leaves the repository"
        return None, "is a chain of links longer than the audit follows"

    def close(self) -> None:
        if self.blobs is not None:
            self.blobs.__exit__(None, None, None)
            self.blobs = None


def pypi_files(snap, ctx: dict, rev):
    return WorkTreeFiles(snap, ctx["root"], ctx["git"]) if rev is None else RevisionFiles(snap, ctx["root"], rev)


def pypi_inputs(files, project: str, budget) -> dict:
    """{path: sha256} of every file of the side that can change the Python inventory (pypi.is_input), a file
    that cannot be read recorded by what it is; each read charged to the side's budget (a file the inventory read
    already is not charged again), so a repository of many such files stops at its limits."""
    found = {}
    for rel in sorted(p for p in files.paths if pypi.is_input(p, project) and not pypi.in_git_dir(p)):
        budget.check_time()
        data, _reason = files.read(rel)
        if data is not None:
            budget.charge(rel, len(data))
        found[rel] = sha256(data) if data is not None else "not a readable regular file"
    return found


def pypi_budget(ctx: dict):
    """A new budget for one pass over a PyPI side, ending at the audit's deadline."""
    return pypi.Budget(deadline=ctx.get("deadline"))


def pypi_tree(snap, ctx: dict, rev, label: str) -> tuple:
    """(inventory, inputs) of the PyPI side of a working tree (rev None) or of a revision."""
    files = pypi_files(snap, ctx, rev)
    try:
        where = shown(ctx["project_shown"]) if rev is None else f"{safe_path(ctx['project'] or '.')} of {rev[:12]}"
        budget = pypi_budget(ctx)
        return pypi.inventory(files, ctx["project"], where, budget), pypi_inputs(files, ctx["project"], budget)
    finally:
        files.close()


def pypi_base(snap, ctx: dict) -> tuple:
    """(base occurrences or None, the base's inputs or None, what the report says about the base) of the PyPI
    side: the base revision's own files read the same way. A base without any Python dependency file has none of
    the candidate's occurrences, which are then the change's; a module the base could not read whole leaves its
    occurrences attribution unknown, and the modules it did read still attribute theirs."""
    rev = ctx["base"]
    if rev is None:
        return None, None, "none given (every entry is attribution unknown)"
    try:
        files = RevisionFiles(snap, ctx["root"], rev)
        budget = pypi_budget(ctx)
        try:
            if not pypi.selected(files, ctx["project"], budget):
                return {}, pypi_inputs(files, ctx["project"], budget), (f"read from {rev[:12]}: no Python lock, pin "
                                                                        "or declaration file there")
            inventory = pypi.inventory(files, ctx["project"], f"{safe_path(ctx['project'] or '.')} of {rev[:12]}",
                                       budget)
            inputs = pypi_inputs(files, ctx["project"], budget)
        finally:
            files.close()
    except NotRun as exc:
        return None, None, f"not read from {rev[:12]} ({exc.category}): every entry is attribution unknown"
    unread = [m for m in inventory["modules"] if not m["complete"]]
    text = f"read from {rev[:12]}" + (f"; {len(unread)} of its modules not read whole, whose entries are attribution "
                                      "unknown" if unread else "")
    return pypi.base_occurrences(inventory["modules"]), inputs, text


# ---------------------------------------------------------------- which ecosystems a project has
ECOSYSTEM_CHOICES = {"maven": "Maven", "pypi": "PyPI"}  # the --ecosystem values


def java_build_files(snap, ctx: dict, rev) -> bool:
    """Whether the project directory holds a Maven or Gradle build file, in the working tree or at `rev`."""
    project = ctx["project"]
    names = ("pom.xml", *GRADLE_BUILD_FILES)
    if rev is None:
        directory = os.path.join(ctx["root"], project) if project else ctx["root"]
        return any(os.path.isfile(os.path.join(directory, name)) for name in names)
    prefix = project + "/" if project else ""
    return any(mode in ("100644", "100755", "120000") and path.startswith(prefix) and path[len(prefix):] in names
               for mode, _o, _s, path in list_tree(snap, ctx["root"], rev))


def select_ecosystems(snap, ctx: dict) -> list:
    """The ecosystems an audit covers, as the files found decide, like the Maven and Gradle choice: Maven for its
    build files, PyPI for Python lock, pin or declaration files (pypi.selected), both when the project holds both,
    since either may be what it ships; --ecosystem names one alone. Python sources with no Python dependency file
    anywhere in the repository (pypi.undeclared) select PyPI too, whose part then passes with nothing to match.
    A project with neither is audited as a Java
    one, whose resolution then says what is missing. --build-tool, which is Maven's, makes it a Java project as
    well, without leaving its Python files unread."""
    chosen = ctx.get("ecosystem")
    if chosen:
        return [MAVEN if chosen == "maven" else PYPI]
    rev = ctx["candidate"]
    try:
        java = ctx.get("build_tool") is not None or java_build_files(snap, ctx, rev)
        files = pypi_files(snap, ctx, rev)
    except NotRun:
        return [MAVEN]  # the revision cannot be read: the audit then says so, as its result
    try:
        budget = pypi_budget(ctx)
        python = bool(pypi.selected(files, ctx["project"], budget) or pypi.undeclared(files, ctx["project"], budget))
    except NotRun:
        python = True  # past the budget or the deadline: the PyPI side runs, and stops with the same reason
    finally:
        files.close()
    if python and java:
        return [MAVEN, PYPI]
    if python:
        return [PYPI]
    ctx["nothing_found"] = True
    return [MAVEN]


# ---------------------------------------------------------------- the audit of each ecosystem, then together
def run_side(snap, ctx: dict, ecosystem, store, side: dict) -> None:
    """One ecosystem's part of an audit, written into `side` as each step finishes, so a NotRun leaves what was
    established: the data, its notes, the inventory and inputs of the candidate, and the base. Maven loads its
    data first, as it always has; PyPI reads its files first, which is cheap and needs no network, so a project
    whose files cannot be read never waits for a download."""
    if ecosystem is MAVEN:
        dataset, meta, notes = store.dataset_for_audit(ctx["cached_only"])
        side.update(data=data_record(meta), notes=notes)
        inventory, inputs = resolve_tree(snap, ctx, ctx["candidate"], "candidate")
        side["inputs"] = inputs
        base, base_inputs, base_text = resolve_base(snap, ctx)
        index = Index(dataset)
    else:
        inventory, inputs = pypi_tree(snap, ctx, ctx["candidate"], "candidate")
        side["inputs"] = inputs
        if any(m["nodes"] for m in inventory["modules"]):
            dataset, meta, notes = store.dataset_for_audit(ctx["cached_only"])
            side.update(data=data_record(meta), notes=notes)
            index = osv.Index(dataset, PYPI)
        else:
            # Nothing to match: no data is needed, so none is downloaded and none can be missing (a Java review
            # of a repository with a helper script must not depend on the PyPI export). A project that declares
            # nothing names the cached PyPI data when there is some, read without a refresh.
            index = osv.Index({"advisories": []}, PYPI)
            if inventory.get("absent"):
                meta = cached_meta(store, ctx["root"])
                if meta:
                    side["data"] = data_record(meta)
        base, base_inputs, base_text = pypi_base(snap, ctx)
        removed = [m for m, found in (base or {}).items() if found]
        if inventory.get("absent") and removed:
            # The change removed every Python dependency file the base had: what the base listed is not the
            # change's, and the removal is in the diff for the reviewer to judge.
            count = sum(len(base[m]) for m in removed)
            base_text += (f"; the base listed {count} dependencies in {len(removed)} modules, and the change "
                          "removed every Python dependency file")
    side.update(inventory=inventory, base=base, base_inputs=base_inputs, base_text=base_text, index=index)


def cached_meta(store, repo):
    """The published metadata of an ecosystem's cache, read as it is (no refresh, no directory created), or None
    when there is none, it cannot be used, or it lies inside the repository under audit. Its directories are
    checked as an audit's own read checks them (private_dir, without creating them): the user's own, writable by
    no one else, no link, so another user cannot plant the Data line."""
    try:
        if inside(store.directory, repo):
            return None
        directories = ([os.path.dirname(store.directory)] if store.ecosystem.cache_subdir else []) + [store.directory]
        for directory in directories:
            if not os.path.lexists(directory):
                return None
            osv.check_owned(directory, directory=True)
        return store.read_meta()
    except (NotRun, OSError):
        return None


def side_resolution(ctx: dict, side: dict) -> dict:
    """The report's resolution record of one ecosystem that ran."""
    inventory = side["inventory"]
    record = {"selection": inventory["selection"]}
    if side["ecosystem"] is MAVEN:
        record.update(profiles=ctx["profiles"],
                      # escaped here, once, so the JSON report carries the values the text report prints
                      tools=[dict(i, path=shown(i["path"]), log=shown(i["log"])) if "path" in i else i
                             for i in inventory["tools"]])
    else:
        record = {"ecosystem": "PyPI", "selection": inventory["selection"], "tools": []}
    modules = inventory["modules"]
    labels = [module_label(m["id"]) for m in modules] if side["ecosystem"] is MAVEN else \
        [safe_path(m["id"]) for m in modules]
    record.update(project=shown(ctx["project_shown"]),
                  candidate=f"revision {ctx['candidate'][:12]}" if ctx["candidate"] else "the working tree",
                  modules=labels, coverage="complete" if inventory["complete"] else "partial", base=side["base_text"])
    return record


def nothing_found(ctx: dict, exc):
    """The not-run of a project holding no build file of any ecosystem, naming both kinds of file."""
    if ctx.get("nothing_found") and exc.category == "no build file" and not ctx.get("build_tool"):
        return NotRun("no build file", f"no pom.xml, no Gradle build and no Python lock, pin or dependency "
                                       f"declaration file in {shown(ctx['project_shown'])}: name the directory that "
                                       "holds one with --project-dir")
    return exc


def run_audit(snap, ctx: dict, store: Store) -> dict:
    """The audit of one candidate, as a result that always renders: a NotRun at any step becomes its status,
    with whatever was established before it. With two ecosystems each runs on its own: one that cannot run
    counts as an incomplete result, the other's findings stay, and the result is complete only when both are.
    `store` is the Maven store; ctx["stores"] holds the others."""
    result = empty_result(ctx.get("snapshot_id"))
    result["accepted_ids"] = sorted(ctx["accept"])
    ecosystems = ctx.get("ecosystems") or [MAVEN]
    if ecosystems != [MAVEN]:
        result["ecosystems"] = [e.name for e in ecosystems]  # for a report that stops before any resolution
    stores = dict(ctx.get("stores") or {}, Maven=store)
    sides = []
    try:
        for ecosystem in ecosystems:
            side = {"ecosystem": ecosystem}
            sides.append(side)
            try:
                run_side(snap, ctx, ecosystem, stores[ecosystem.name], side)
            except NotRun as exc:
                if len(ecosystems) == 1:
                    result["data"] = side.get("data")
                    result["not_evaluated"] += side.get("notes", [])
                    if "inputs" in side:
                        result["inputs"]["candidate"] = {safe_path(p): d for p, d in sorted(side["inputs"].items())}
                    raise nothing_found(ctx, exc)
                side["problem"] = (exc.category, exc.remedy)
        assemble(result, ctx, sides)
    except NotRun as exc:
        result["status"], result["problem"] = "not-run", [exc.category, exc.remedy]
    result["status_line"] = status_line(result)
    return result


def assemble(result: dict, ctx: dict, sides: list) -> None:
    """The result of the sides that ran: their occurrences evaluated together, their notes in order, one data and
    one resolution record each (a list of them when two ecosystems ran), and the problem of the first incomplete
    side, which names its ecosystem when there are two."""
    ran = [side for side in sides if "inventory" in side]
    # A PyPI side that found Python sources and no dependency file, beside another ecosystem, adds only its
    # coverage note: no data, inputs, resolution or counts, so a Java review of a repository with a helper script
    # reads exactly as it did before the PyPI audit existed.
    silent = [s for s in ran if s["inventory"].get("absent")] if len(sides) > 1 else []
    sides = [s for s in sides if s not in silent]
    ran = [s for s in ran if s not in silent]
    two = len(sides) > 1
    candidate_inputs, base_inputs = {}, None
    for side in sides:
        candidate_inputs.update(side.get("inputs") or {})
        if side.get("base_inputs") is not None:
            base_inputs = dict(base_inputs or {}, **side["base_inputs"])
    result["inputs"]["candidate"] = {safe_path(p): digest for p, digest in sorted(candidate_inputs.items())}
    if base_inputs is not None:
        result["inputs"]["base"] = {safe_path(p): digest for p, digest in sorted(base_inputs.items())}
    found = osv.evaluate_sides([(s["index"], s["inventory"]["modules"], s["base"]) for s in ran], ctx["accept"],
                               deadline=ctx.get("deadline"))
    result["blocks"] = found["blocks"]
    result["counts"] = {"dependencies": found["dependencies"],
                        "modules": sum(len(s["inventory"]["modules"]) for s in ran)}
    for side in sides:
        result["not_evaluated"] += side.get("notes", [])
        if "problem" in side:
            result["not_evaluated"].append(f"the {side['ecosystem'].name} dependencies were not audited: "
                                           f"{side['problem'][0]}: {side['problem'][1]}")
            continue
        result["not_evaluated"] += side["inventory"]["notes"]
        result["not_evaluated"] += [f"module {module_label(m)}: no dependency tree was parsed"
                                    for m in side["inventory"].get("unparsed", [])]
    result["not_evaluated"] += [f"accepted id {safe(a, ID_GRAMMAR, 'advisory id')} matches no entry of this audit"
                                for a in found["unused_accepts"]]
    resolutions, data = [], []
    for side in sides:
        name = side["ecosystem"].name
        if "problem" in side:
            resolutions.append({"ecosystem": name, "not_run": list(side["problem"])})
        else:
            record = side_resolution(ctx, side)
            resolutions.append(dict(record, ecosystem=name) if two else record)
        if side.get("data"):
            data.append(dict(side["data"], ecosystem=name) if two else side["data"])
    result["resolution"] = resolutions if two else resolutions[0]
    result["data"] = data if two else (data[0] if data else None)
    incomplete = [s for s in sides if "problem" in s or not s["inventory"]["complete"]]
    result["status"] = gate_status(result["blocks"], not incomplete)
    result["coverage"] = "partial" if incomplete else "complete"
    if not incomplete and silent:
        result["coverage_note"] = f"PyPI: {pypi.ABSENT}"
    elif not incomplete and any(s["inventory"].get("absent") for s in sides):
        result["coverage_note"] = pypi.ABSENT
    if not data and not incomplete:
        result["data_note"] = "not needed (no package to match)"
    if incomplete:
        first = incomplete[0]
        category, remedy = first["problem"] if "problem" in first else first["inventory"]["problem"]
        result["problem"] = [category, f"the {first['ecosystem'].name} dependencies: {remedy}" if two else remedy]


# ---------------------------------------------------------------- the snapshot: attach, then record
def call_snapshot(snap, handler, **fields) -> tuple:
    """(exit code, what it printed or why it stopped) of one review-snapshot.py command, run in process."""
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = handler(argparse.Namespace(**fields))
    except snap.Failure as exc:
        return exc.code, exc.message
    except OSError as exc:
        return EXIT_ERROR, str(exc)
    return code, buffer.getvalue().strip()


def record_gate(snap, directory: str, status: str, command: str, reason=None, name: str = GATE_NAME) -> tuple:
    return call_snapshot(snap, snap.cmd_record_gate, dir=directory, name=name, status=status,
                         command=one_line(command)[:snap.MAX_STATE_TEXT],
                         reason=one_line(reason)[:snap.MAX_REASON] if reason else None)


def next_attempt(directory: str) -> int:
    found = [0]
    for sub, suffix in (("gates", ".txt"), ("input", ".json")):
        with contextlib.suppress(OSError):
            for name in os.listdir(os.path.join(directory, sub)):
                number = name[len(GATE_NAME) + 1:-len(suffix)]
                if name.startswith(GATE_NAME + "-") and name.endswith(suffix) and number.isdigit():
                    found.append(int(number))
    return max(found) + 1


def attach_reports(snap, directory: str, result: dict) -> str | None:
    """Attaches the text and the JSON report of this attempt through review-snapshot.py attach (write-once),
    from a scratch directory outside the repository. None when both are attached, else why not."""
    scratch = tempfile.mkdtemp(prefix="ifs-dependency-audit-report-")
    try:
        for _ in range(3):  # another audit of this snapshot may take the number first
            result["attempt"] = next_attempt(directory)
            text, body = os.path.join(scratch, "report.txt"), os.path.join(scratch, "report.json")
            for path, data in ((text, render_text(result).encode("utf-8")), (body, render_json(result))):
                with open(path, "wb") as fh:
                    fh.write(data)
            code, said = call_snapshot(snap, snap.cmd_attach, dir=directory, source=text,
                                       to=f"gates/{GATE_NAME}-{result['attempt']}.txt")
            if code != EXIT_OK and "already attached" in said:
                continue
            if code == EXIT_OK:
                code, said = call_snapshot(snap, snap.cmd_attach, dir=directory, source=body,
                                           to=f"input/{GATE_NAME}-{result['attempt']}.json")
            return None if code == EXIT_OK else (said or f"review-snapshot.py attach exited {code}")
        return "the attempt number was taken three times"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def exit_code(status: str) -> int:
    return {"pass": EXIT_OK, "fail": EXIT_FAIL}.get(status, EXIT_NOT_RUN)


def audit_command_text(directory: str, result: dict, accept: list) -> str:
    accepted = "".join(f" --accept {a}" for a in sorted(accept))
    return (f"dependency-audit.py audit --snapshot {shown(directory)}{accepted} "
            f"(report gates/{GATE_NAME}-{result['attempt']}.txt)")


def finish_snapshot_audit(snap, directory: str, result: dict, accept: list) -> int:
    """Attaches both reports and only then records the gates: for a pass or a fail first its coverage
    (COVERAGE_GATE: pass when complete, not run with the category and remedy when partial), then the audit's
    own status, so an attempt stopped between the two leaves the audit pending, never a result without its
    coverage. A failed attachment is recorded as not run. Prints the report with the status recorded."""
    problem = attach_reports(snap, directory, result)
    if problem:
        result["status"], result["problem"] = "not-run", ["attachment failed", shown(problem)]
        result["status_line"] = status_line(result)
    command = audit_command_text(directory, result, accept)
    if result["status"] in ("pass", "fail"):
        partial = result.get("coverage") == "partial"
        code, said = record_gate(snap, directory, "not-run" if partial else "pass", command,
                                 "coverage partial: " + ": ".join(result["problem"]) if partial else None,
                                 name=COVERAGE_GATE)
        if code != EXIT_OK:
            print(not_run_line("gate not recorded", shown(said or f"record-gate exited {code}")))
            return EXIT_CHANGED if code == EXIT_CHANGED else EXIT_NOT_RUN
    reason = ": ".join(result["problem"]) if result["status"] == "not-run" else None
    code, said = record_gate(snap, directory, result["status"], command, reason)
    if code != EXIT_OK:
        print(not_run_line("gate not recorded", shown(said or f"record-gate exited {code}")))
        return EXIT_CHANGED if code == EXIT_CHANGED else EXIT_NOT_RUN
    sys.stdout.write(render_text(result))
    print(one_line(said))
    return exit_code(result["status"])


# ---------------------------------------------------------------- commands
def git_root(snap, path: str):
    """The work tree `path` lies in, None when it lies in none."""
    code, out, _err = snap.git_try(path, ["rev-parse", "--show-toplevel"])
    return None if code else os.path.realpath(os.fsdecode(out).rstrip("\n"))


REFUSED = "setting not obeyed"


def setting_stop(setting: Setting):
    """(exit code, line) when the setting keeps a command from running, else None."""
    if setting.state == "off":
        return EXIT_OK, off_line(setting.source)
    if setting.state == "refused":
        return EXIT_NOT_RUN, not_run_line(REFUSED, setting.source)
    return None


def cmd_register(args, snap) -> int:
    directory, manifest = snap.load_manifest(args.snapshot)
    setting = resolve_setting(args.dependency_audit, os.environ, manifest["repo"])
    if setting.state == "off":
        print(off_line(setting.source))
        return EXIT_OK
    command = f"dependency-audit.py audit --snapshot {shown(directory)}"
    refused = setting.state == "refused"
    code, said = record_gate(snap, directory, "not-run", command,
                             f"{REFUSED}: {setting.source}" if refused else PENDING_REASON)
    if code != EXIT_OK:
        print(f"dependency-audit: the gate was not registered: {shown(said)}", file=sys.stderr)
        return code
    print(not_run_line(REFUSED, setting.source) if refused else "Dependency audit: pending")
    return EXIT_OK


def project_context(args, snap, root: str, git: bool) -> dict:
    project = ""
    if args.project_dir:
        joined = args.project_dir if os.path.isabs(args.project_dir) else os.path.join(root, args.project_dir)
        project = os.path.relpath(os.path.normpath(joined), root).replace(os.sep, "/")
        if project == ".":
            project = ""
        elif project.startswith("../") or project == ".." or os.path.islink(os.path.join(root, project)) \
                or not inside(os.path.join(root, project), root):
            raise Stop(EXIT_USAGE, f"--project-dir is not a directory of the repository: {shown(args.project_dir)}")
    for value in args.profile + args.accept:
        if not (PROFILE_RE if value in args.profile else ID_GRAMMAR).match(value):
            raise Stop(EXIT_USAGE, f"not a profile id or an advisory id: {shown(value)}")
    return {"root": root, "git": git, "project": project, "project_shown": project or ".",
            "build_tool": args.build_tool, "ecosystem": args.ecosystem, "total_timeout": args.total_timeout,
            "deadline": time.monotonic() + args.total_timeout,
            "profiles": list(args.profile), "accept": list(args.accept), "timeout": args.timeout,
            "cached_only": args.cached_data, "environ": os.environ, "candidate": None, "base": None}


def cmd_audit(args, snap) -> int:
    if args.snapshot:
        directory, manifest = snap.load_manifest(args.snapshot)
        root, git = manifest["repo"], True
    else:
        path = os.path.realpath(os.path.expanduser(args.repo))
        if not os.path.isdir(path):
            raise Stop(EXIT_USAGE, f"--repo is not a directory: {shown(args.repo)}")
        root = git_root(snap, path)
        git = root is not None
        if git and path != root and not args.project_dir:
            args.project_dir = path  # a project below the work tree's root
        root = root or path
    setting = resolve_setting(args.dependency_audit, os.environ, root)
    stop = setting_stop(setting)
    if stop and (setting.state == "off" or not args.snapshot):
        print(stop[1])
        return stop[0]
    ctx = project_context(args, snap, root, git)
    store = Store(default_cache_dir(), repo=root, deadline=ctx["deadline"])
    ctx["stores"] = {"PyPI": osv.Store(osv.cache_dir(PYPI), PYPI, repo=root, deadline=ctx["deadline"])}
    if not args.snapshot:
        if args.base:
            if not git:
                raise Stop(EXIT_USAGE, "--base needs a git work tree")
            ctx["base"] = snap.resolve_commit(root, args.base, "--base")
        ctx["ecosystems"] = select_ecosystems(snap, ctx)
        result = run_audit(snap, ctx, store)
        sys.stdout.write(render_text(result))
        return exit_code(result["status"])
    changed = snap.verify_manifest(manifest) + [r for _k, r in snap.integrity_problems(directory, manifest)]
    if changed:
        for rel in changed:
            print(f"changed: {shown(rel)}")
        print(f"dependency-audit: snapshot {manifest['id'][:12]} no longer verifies; nothing was recorded. Take a "
              "new snapshot and run the audit on it", file=sys.stderr)
        return EXIT_CHANGED
    ctx.update(snapshot_id=manifest["id"], base=manifest["base"])
    if manifest["mode"] == "range":
        ctx["candidate"] = manifest["source"]["to_commit"]
    # This attempt supersedes any earlier result on the snapshot at once: an attempt that crashes or is killed
    # leaves the gate pending, never an earlier pass standing for a run that did not finish.
    code, said = record_gate(snap, directory, "not-run", f"dependency-audit.py audit --snapshot {shown(directory)}",
                             ATTEMPT_REASON)
    if code != EXIT_OK:
        print(not_run_line("gate not recorded", shown(said or f"record-gate exited {code}")))
        return EXIT_CHANGED if code == EXIT_CHANGED else EXIT_NOT_RUN
    ctx["ecosystems"] = select_ecosystems(snap, ctx) if manifest["mode"] != "diff-file" else [MAVEN]
    uncovered = uncovered_inputs(snap, ctx, manifest)
    if setting.state == "refused":  # recorded, so the review is incomplete and says why
        result = dict(empty_result(manifest["id"]), problem=[REFUSED, setting.source])
        result["status_line"] = status_line(result)
    elif manifest["mode"] == "diff-file":
        result = dict(empty_result(manifest["id"]),
                      problem=["pasted diff", "a pasted diff has no project to resolve: review a working tree or a "
                                              "commit range to audit its dependencies"])
        result["status_line"] = status_line(result)
    elif uncovered:
        result = dict(empty_result(manifest["id"]),
                      problem=["snapshot does not cover the build",
                               f"the snapshot holds the files named with --files only, and the build also reads "
                               f"{named_list([safe_path(p) for p in uncovered])}, which could change without the "
                               "snapshot showing it: take a snapshot of the working tree or of a commit range to "
                               "audit the dependencies"])
        result["status_line"] = status_line(result)
    else:
        result = run_audit(snap, ctx, store)
        if manifest["mode"] == "files":
            files_snapshot_partial(result)
    return finish_snapshot_audit(snap, directory, result, ctx["accept"])


def uncovered_inputs(snap, ctx: dict, manifest: dict) -> list:
    """The resolution inputs of the working tree's project that a --files snapshot does not hold: the snapshot
    verifies its own files only, so an audit result bound to it would stand after one of these changed."""
    if manifest["mode"] != "files":
        return []
    names = worktree_files(snap, ctx["root"], ctx["git"])
    held = set(manifest["source"].get("files") or [])
    inputs = set(worktree_inputs(ctx["root"], names, ctx["project"])) if MAVEN in ctx["ecosystems"] else set()
    if PYPI in ctx["ecosystems"]:
        files = WorkTreeFiles(snap, ctx["root"], ctx["git"])
        try:
            python = bool(pypi.selected(files, ctx["project"], pypi_budget(ctx)))
        except NotRun:
            python = True  # doubt: the files are inputs
        if python:  # a project that declares nothing has no Python input to hold
            inputs |= {p for p in names if pypi.is_input(p, ctx["project"])}
    return sorted(p for p in inputs if p not in held)


def files_snapshot_partial(result: dict) -> None:
    """Makes the result of a --files snapshot partial, as an inventory a build tool reports in part is: what it
    found stays and fails, nothing reads as a pass. The snapshot verifies only the files it holds, and no list of
    file names covers what a build reads: a script it applies, a version catalogue, a convention plugin, or a file
    whose mere existence activates a profile, which may appear after the audit. Holding every file of the working
    tree now does not change that, so no --files snapshot gives a complete result. A result already partial keeps
    the problem its resolution named; one that did not resolve is left as it is."""
    if result["status"] not in ("pass", "fail"):
        return
    if result.get("coverage") != "partial":
        result["problem"] = ["snapshot does not cover the build",
                             "the snapshot holds the files named with --files only, and any other file of the "
                             "working tree, one created later included, can change what the build resolves "
                             "without the snapshot showing it: take a snapshot of the working tree or of a "
                             "commit range to audit the dependencies"]
    result["coverage"] = "partial"
    for record in osv.records(result["resolution"]):
        if "coverage" in record:
            record["coverage"] = "partial"
    result["status"] = gate_status(result["blocks"], False)
    result["status_line"] = status_line(result)


def check_line(index, coordinate: str) -> tuple:
    """(whether it matched, its line) for one GROUP:ARTIFACT:VERSION or pypi:<name>==<version>."""
    if index.ecosystem is PYPI:
        name, version = pypi.parse_pin(coordinate)
        named = {"package": name, "version": version, "scope": "pin", "optional": False, "path": [], "ships": True}
        label = pypi.occurrence
        module = {"id": "check"}
    else:
        group, artifact, version = coordinate.split(":")
        name = f"{group}:{artifact}"
        named = new_node(group, artifact, "jar", "", version, "compile", False, [])
        label = occurrence
        module = {"id": name}
    matched = match_package(index, name, version)
    if not matched["advisories"]:
        return False, f"{coordinate}: no matching advisory in this dataset"
    listed = label(module, named, matched["advisories"], matched["fix"], matched["fix_checked"])
    text = occurrence_line(listed)
    return True, f"{coordinate}: {len(listed['advisories'])} matching " + text[text.index("advisories: "):]


def check_ecosystem(coordinate: str):
    """The ecosystem a check argument names, None when it is neither form."""
    if coordinate.lower().startswith("pypi:") and pypi.parse_pin(coordinate):
        return PYPI
    # anything else keeps the Maven reading 0.3.0 gave it, a group named pypi included (pypi:demo:1.0)
    parts = coordinate.split(":")
    if len(parts) == 3 and NAME_RE.match(parts[0]) and NAME_RE.match(parts[1]) and VERSION_RE.match(parts[2]):
        return MAVEN
    return None


def cmd_check(args, snap) -> int:
    wanted = []
    for coordinate in args.coordinates:
        ecosystem = check_ecosystem(coordinate)
        if ecosystem is None:
            raise Stop(EXIT_USAGE, f"not GROUP:ARTIFACT:VERSION or pypi:<name>==<version>: {shown(coordinate)}")
        wanted.append(ecosystem)
    repo = git_root(snap, os.getcwd())
    stop = setting_stop(resolve_setting(args.dependency_audit, os.environ, repo))
    if stop:
        print(stop[1])
        return stop[0]
    loaded = {}
    for ecosystem in (e for e in (MAVEN, PYPI) if e in wanted):
        store = Store(default_cache_dir(), repo=repo) if ecosystem is MAVEN else \
            osv.Store(osv.cache_dir(PYPI), PYPI, repo=repo)
        try:
            dataset, meta, notes = store.dataset_for_audit(args.cached_data)
        except NotRun as exc:
            print(not_run_line(exc.category, exc.remedy))
            return EXIT_NOT_RUN
        loaded[ecosystem.name] = (osv.Index(dataset, ecosystem), meta, notes)
    lines = [check_line(loaded[e.name][0], c) for e, c in zip(wanted, args.coordinates)]
    hits = sum(1 for hit, _line in lines if hit)
    print(f"Dependency check: {hits} of {len(lines)} coordinates match an advisory (named coordinates only: "
          "transitive dependencies are not seen)")
    for _hit, line in lines:
        print(one_line(line))
    for _index, meta, _notes in loaded.values():
        print(one_line(data_line(data_record(meta))))
    for _index, _meta, notes in loaded.values():
        for note in notes:
            print(one_line(f"Note: {note}"))
    return EXIT_FAIL if hits else EXIT_OK


def cmd_refresh(args, snap) -> int:
    if args.source is not None and not args.source.strip():
        raise Stop(EXIT_USAGE, "--from needs the path of the export's zip or of a directory of its records")
    repo = git_root(snap, os.getcwd())
    store = Store(default_cache_dir(), repo=repo) if args.ecosystem == "maven" else \
        osv.Store(osv.cache_dir(PYPI), PYPI, repo=repo)
    try:
        store.prepare()
        if args.source:
            meta, what = store.import_from(args.source), "imported"
        else:
            meta, what = store.refresh(force=True)
    except NotRun as exc:
        print(not_run_line(exc.category, exc.remedy))
        return EXIT_NOT_RUN
    except RefreshFailed as exc:
        print(not_run_line("advisory data not refreshed", f"{shown(exc.reason)}; the dataset published before, if "
                                                          "any, is unchanged"))
        return EXIT_NOT_RUN
    print(one_line(f"{data_line(data_record(meta))} ({what})"))
    return EXIT_OK


class Parser(argparse.ArgumentParser):
    """argparse with the documented usage exit status, 64."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def build_parser() -> Parser:
    parser = Parser(prog="dependency-audit.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                    description="Audit a Java or Python project's dependencies against the public OSV advisory data.",
                    epilog="Status line" + __doc__.split("Status line", 1)[1])
    sub = parser.add_subparsers(dest="command_name", metavar="{register,audit,check,refresh}", parser_class=Parser)
    sub.required = True
    setting = {"dest": "dependency_audit", "choices": VALUES,
               "help": "the user's explicit setting for this run: off only for a user who has switched the audit "
                       "off, never to skip it for one review (a skipped audit is a check that did not run)"}
    register = sub.add_parser("register", help="record the gate as pending for a snapshot")
    register.add_argument("--snapshot", required=True, metavar="DIR")
    register.add_argument("--dependency-audit", **setting)
    audit = sub.add_parser("audit", help="resolve, match, attribute and report")
    where = audit.add_mutually_exclusive_group(required=True)
    where.add_argument("--snapshot", metavar="DIR", help="the review snapshot: attach the reports, record the gate")
    where.add_argument("--repo", metavar="PATH", help="a project directory: report to standard output")
    audit.add_argument("--base", metavar="REV", help="with --repo: the revision the working tree is compared with")
    audit.add_argument("--accept", action="append", default=[], metavar="ID",
                       help="an advisory id the user accepted in this conversation (repeatable)")
    audit.add_argument("--profile", action="append", default=[], metavar="ID",
                       help="a Maven profile to audit too (repeatable; Gradle has none)")
    audit.add_argument("--timeout", type=int, default=BUILD_TIMEOUT_SECONDS, metavar="SECONDS",
                       help=f"the build tool's time limit (default {BUILD_TIMEOUT_SECONDS})")
    audit.add_argument("--total-timeout", type=int, default=TOTAL_TIMEOUT_SECONDS, metavar="SECONDS",
                       help=f"the time limit of the whole audit, every build-tool run included (default "
                            f"{TOTAL_TIMEOUT_SECONDS})")
    audit.add_argument("--cached-data", action="store_true", help="never contact the server for advisory data")
    audit.add_argument("--project-dir", metavar="PATH", help="the directory holding the build file, when not the root")
    audit.add_argument("--build-tool", choices=tuple(BUILD_TOOLS), metavar="{maven,gradle}",
                       help="the build tool the project uses, which then resolves alone (default: Maven for a "
                            "pom.xml, Gradle for Gradle build files, both when there are both)")
    audit.add_argument("--ecosystem", choices=tuple(ECOSYSTEM_CHOICES), metavar="{maven,pypi}",
                       help="audit this ecosystem alone (default: Maven for Maven or Gradle build files, PyPI for "
                            "Python lock, pin or dependency declaration files, both when there are both)")
    audit.add_argument("--dependency-audit", **setting)
    check = sub.add_parser("check", help="match named coordinates, with no resolution")
    check.add_argument("coordinates", nargs="+", metavar="GROUP:ARTIFACT:VERSION|pypi:NAME==VERSION")
    check.add_argument("--cached-data", action="store_true", help="never contact the server for advisory data")
    check.add_argument("--dependency-audit", **setting)
    refresh = sub.add_parser("refresh", help="download the advisory data, or import a local copy")
    refresh.add_argument("--from", dest="source", metavar="ZIP-OR-DIRECTORY")
    refresh.add_argument("--ecosystem", choices=tuple(ECOSYSTEM_CHOICES), default="maven", metavar="{maven,pypi}",
                         help="the ecosystem whose OSV export is downloaded or imported (default maven)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        snap = load_sibling("review-snapshot.py", "ifs_review_snapshot")
    except (ImportError, OSError, SyntaxError) as exc:
        print(f"dependency-audit: cannot load review-snapshot.py: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.command_name == "audit":
        if args.base and args.snapshot:
            build_parser().error("--base goes with --repo: a snapshot carries its own base")
        if args.timeout < 1 or args.total_timeout < 1:
            build_parser().error("--timeout and --total-timeout must be at least 1 second")
        if args.ecosystem == "pypi" and (args.build_tool or args.profile):
            build_parser().error("--build-tool and --profile apply to the Maven ecosystem, not to --ecosystem pypi")
    handler = {"register": cmd_register, "audit": cmd_audit, "check": cmd_check, "refresh": cmd_refresh}
    try:
        return handler[args.command_name](args, snap)
    except Stop as exc:
        print(f"dependency-audit: {exc.message}", file=sys.stderr)
        return exc.code
    except snap.Failure as exc:
        print(f"dependency-audit: {shown(exc.message)}", file=sys.stderr)
        return exc.code
    except NotRun as exc:
        print(not_run_line(exc.category, exc.remedy))
        return EXIT_NOT_RUN
    except Exception as exc:  # noqa: BLE001 - an internal error never looks like a result: exit 1, nothing recorded
        print(f"dependency-audit: internal error: {type(exc).__name__}: {shown(exc)}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
