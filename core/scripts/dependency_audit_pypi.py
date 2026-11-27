# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
dependency_audit_pypi.py — the PyPI half of core/scripts/dependency-audit.py: PEP 440 version parsing and
ordering, PEP 503 name normalisation, the inventory of a Python project read from its lock and pin files, and
the PYPI ecosystem the shared matcher (dependency_audit_osv.py) is given.

Owner: the implement-from-spec plugin. Owns no command: dependency-audit.py loads it by path and injects the
shared module as `osv` before this code runs, so both use one instance of it.

The inventory is read, never resolved: no installer, resolver or build backend runs, and nothing from the
project is imported or executed, since building a source distribution runs the repository's code and the
repository under review is untrusted. It comes from these files, in every directory of the project directory
outside SOURCE_EXCLUDED, each one module of the report:
    uv.lock, poetry.lock, pdm.lock, Pipfile.lock, pylock.toml and pylock.<name>.toml (PEP 751), and the
    requirements files (requirements*.txt, *-requirements.txt, *_requirements.txt and requirements/*.txt, and
    every file they name with -r or -c that is one of the candidate's files) whose requirements are pinned with
    == (or ===), hashes optional; one package at one version is one entry of its module.
Python sources (.py files outside SOURCE_EXCLUDED) with no lock, pin or declaration file anywhere in the repository
are an empty, complete inventory (undeclared(), absent_inventory()): nothing third-party is declared.
A declaration (pyproject.toml's [project], Poetry, PDM, uv or [dependency-groups] tables, setup.cfg's
install_requires, a setup.py, a Pipfile) is covered by the lock and pin files of its directory or of the nearest
directory above it that holds any (a workspace locks its members at its root). Uncovered, the result is partial
(no lock file); covered, a declared dependency those files do not list makes it partial too (lock file out of
date): a main dependency always (one with an environment marker only against a lock file), a group's or an
extra's only against a lock file, which locks every group, since a requirements file may be compiled from the
main set alone. Every requirement that is not pinned to one version (a range, a VCS, a URL, a local path, an
editable install) and every lock entry from a VCS, a URL or a local path is partial as well: none of them names
a version the advisory data can place. A requirement is covered by an unconditional == pin of a constraint file
of the same install, as pip installs it; a file two installs reach is judged in each.
An environment marker is never evaluated, so a package locked for one platform or one Python counts for every
one: a marker narrows where a package installs, not whether the project ships it.

Every file is hostile input: read through the caller's source (a working tree's candidate files or a revision's
tree), never a file outside it (an ignored file, anything inside .git), at most osv.INPUT_LIMIT bytes each; one
side's pass reads at most MAX_FILES distinct files and MAX_TOTAL_BYTES in all, keeps at most MAX_SIDE_PACKAGES
packages and stops at the audit's deadline (Budget), the files read to choose the ecosystems and the input
digests counted with the inventory's; a path that leaves the repository, through `..` or a link, is never read;
no value read reaches a shell (there is none) or a report without passing its grammar; where a package came from
is a fixed phrase (source_phrase), never the file's text.
TOML needs tomllib, Python 3.11 or later: on an older interpreter a side that holds a TOML lock file, a Pipfile
or a declaring pyproject.toml is not run, while requirements files, Pipfile.lock and setup.cfg are read; a
pyproject.toml is judged there by its table headers alone (headers_declare), so tool settings select nothing,
and this module still imports there (no newer syntax, tomllib imported where it is used).

Usage: not run directly; dependency-audit.py loads it with load_sibling(..., inject={"osv": <shared module>}).
"""
from __future__ import annotations

import collections
import configparser
import functools
import json
import posixpath
import re
import sys
import time

osv = globals().get("osv")  # injected by dependency-audit.py's load_sibling before this code runs
if osv is None:
    raise ImportError("dependency_audit_pypi.py is loaded by dependency-audit.py, which supplies its shared module")

MIN_ADVISORIES = 10000
# The OSV PyPI export (https://google.github.io/osv.dev/data/, read 2026-11-25: "A zip containing all
# vulnerabilities for each ecosystem is available at gs://osv-vulnerabilities/<ECOSYSTEM>/all.zip"), served over
# HTTPS at the bucket's public host. On 2026-11-25 it held 27,082 records, 26,440 of them usable PyPI advisories
# (12,095 malicious-package records among them); MIN_ADVISORIES stays below the 14,345 records that are not
# malicious-package ones, so the export without those still passes, and far above any test or cut file.
EXPORT_URL = "https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip"
# The export's sources and their licences, as the OSV data page lists them for PyPI (read 2026-11-25).
ATTRIBUTION = ("OSV, PyPI Advisory Database and GitHub Advisory Database, CC-BY 4.0; OpenSSF Malicious Packages, "
               "Apache 2.0")
MIN_PYTHON = (3, 11)  # tomllib
MATCHER = "pep440/2"  # the version of the PEP 440 reading below, recorded with each PyPI dataset (Ecosystem.matcher)
RUNNING = tuple(sys.version_info[:3])  # this interpreter's version, which interpreter_problem() compares

MAX_FILES = 200  # lock, pin and declaration files read for one side, -r and -c includes counted
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_INCLUDE_DEPTH = 16
MAX_PACKAGES = 100_000  # entries of one file
MAX_SIDE_PACKAGES = 100_000  # packages and requirements kept for one side: each costs memory, a few bytes of input do
MAX_NOTES = 20
MAX_LINK_HOPS = 8
MAX_VERSION = 128  # characters of a version string that is parsed at all
MAX_NAME = 200

LOCK_FILES = ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock")
DECLARATION_FILES = ("pyproject.toml", "setup.cfg", "setup.py", "Pipfile")
FORMATS = {"uv.lock": "uv", "poetry.lock": "Poetry", "pdm.lock": "PDM", "Pipfile.lock": "Pipenv"}
LOCK_COMMANDS = "uv lock, poetry lock, pdm lock, pipenv lock, or pip-compile with every requirement pinned"


# ---------------------------------------------------------------- PEP 440 versions
# The version scheme of https://packaging.python.org/en/latest/specifications/version-specifiers/ (read
# 2026-11-25): "[N!]N(.N)*[{a|b|rc}N][.postN][.devN]" with an optional "+<local version label>", and its
# normalisation rules: case-insensitive, integers by int(), "-", "_" or "." (or nothing) as separators, alpha,
# beta, c, pre and preview for a, b, rc, rc and rc, rev and r for post, an implicit 0 for an omitted number,
# "1.0-1" as 1.0.post1, a leading "v" ignored, surrounding whitespace dropped. Read by a scanner that moves
# forward only: no regex, so no input can make the parse backtrack, and a version over MAX_VERSION characters is
# not parsed at all.
PRE_WORDS = (("preview", "rc"), ("alpha", "a"), ("beta", "b"), ("pre", "rc"), ("rc", "rc"), ("a", "a"),
             ("b", "b"), ("c", "rc"))
POST_WORDS = ("post", "rev", "r")
PRE_RANK = {"a": 0, "b": 1, "rc": 2}
VERSION_SEPARATORS = "-_."
ALNUM = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
DIGITS = frozenset("0123456789")


class Version:
    """A parsed PEP 440 version: its parts, its canonical text and its sort key."""

    __slots__ = ("epoch", "release", "pre", "post", "dev", "local", "key", "text", "public")

    def __init__(self, epoch, release, pre, post, dev, local) -> None:
        # "All integers are interpreted via the int() built in and normalize to the string form of the output",
        # local segments included: 1.0+01 is 1.0+1, in its key and in its text
        if local is not None:
            local = tuple(str(int(part)) if part.isdigit() else part for part in local)
        self.epoch, self.release, self.pre, self.post, self.dev, self.local = epoch, release, pre, post, dev, local
        trimmed = list(release)
        while len(trimmed) > 1 and trimmed[-1] == 0:
            trimmed.pop()
        # The ordering of the specification's "Summary of permitted suffixes and relative ordering": a
        # developmental release of a release sorts before its pre-releases, a release without a suffix after
        # them, a post-release after that; release segments compare padded with zeros; a local label sorts after
        # its public version, segment by segment, "the numeric section always compares as greater than the
        # lexicographic segment", and more segments with an equal start sort after fewer.
        if pre is None and post is None and dev is not None:
            pre_key = (0,)
        elif pre is None:
            pre_key = (2,)
        else:
            pre_key = (1, PRE_RANK[pre[0]], pre[1])
        post_key = (0,) if post is None else (1, post)
        dev_key = (1,) if dev is None else (0, dev)
        local_key = (0,) if local is None else \
            (1, tuple((1, int(part)) if part.isdigit() else (0, part) for part in local))
        self.key = (epoch, tuple(trimmed), pre_key, post_key, dev_key, local_key)
        public = (f"{epoch}!" if epoch else "") + ".".join(str(n) for n in release)
        if pre is not None:
            public += f"{pre[0]}{pre[1]}"
        if post is not None:
            public += f".post{post}"
        if dev is not None:
            public += f".dev{dev}"
        self.public = public
        self.text = public + ("+" + ".".join(local) if local is not None else "")


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text, self.at = text, 0

    def peek(self, n: int = 1) -> str:
        return self.text[self.at:self.at + n]

    def done(self) -> bool:
        return self.at >= len(self.text)

    def digits(self):
        start = self.at
        while self.at < len(self.text) and self.text[self.at] in DIGITS:
            self.at += 1
        return int(self.text[start:self.at]) if self.at > start else None

    def word(self, words):
        """The first of `words` the text continues with, consumed; None when none."""
        for word in words:
            if self.text.startswith(word, self.at):
                self.at += len(word)
                return word
        return None


def _number_after(scan: _Scanner) -> int:
    """The number after a pre, post or dev word: an optional separator, then digits; 0 when there are none. The
    separator is taken whether or not digits follow, as the specification's pattern allows ("1.0a..dev1",
    "1b--1"): every part after it has a separator of its own that may be left out, so taking it never refuses a
    version the pattern accepts."""
    if scan.peek() and scan.peek() in VERSION_SEPARATORS:
        scan.at += 1  # the specification's [-_.]? after the word, taken even when no number follows
    value = scan.digits()
    return 0 if value is None else value


def _optional_word(scan: _Scanner, words):
    """A pre, post or dev word with the separator allowed before it: (word, number) consumed, or None."""
    at = scan.at
    if scan.peek() and scan.peek() in VERSION_SEPARATORS:
        scan.at += 1
    found = scan.word(words)
    if found is None:
        scan.at = at
        return None
    return found, _number_after(scan)


def parse_version(text) -> Version | None:
    """The PEP 440 version `text` denotes, None when it is not one (or is longer than MAX_VERSION)."""
    if not isinstance(text, str) or len(text) > MAX_VERSION:
        return None
    return _parse_version(text)


# The matcher compares the same few versions many times (each bound of a range against each version, each event
# against the others when a range is checked), so a parse is kept; a Version is never changed after it is made.
@functools.lru_cache(maxsize=65536)
def _parse_version(text: str) -> Version | None:
    text = text.strip().lower()
    if not text or not text.isascii():
        return None
    scan = _Scanner(text[1:] if text[0] == "v" else text)
    first = scan.digits()
    if first is None:
        return None
    epoch = 0
    if scan.peek() == "!":
        scan.at += 1
        epoch, first = first, scan.digits()
        if first is None:
            return None
    release = [first]
    while scan.peek() == "." and scan.peek(2)[1:] in DIGITS and scan.peek(2)[1:]:
        scan.at += 1
        release.append(scan.digits())
    pre = None
    found = _optional_word(scan, [word for word, _norm in PRE_WORDS])
    if found:
        pre = (dict(PRE_WORDS)[found[0]], found[1])
    post = None
    if scan.peek() == "-" and scan.peek(2)[1:] in DIGITS and scan.peek(2)[1:]:
        scan.at += 1
        post = scan.digits()  # the implicit post-release "1.0-1"
    else:
        found = _optional_word(scan, POST_WORDS)
        if found:
            post = found[1]
    dev = None
    found = _optional_word(scan, ("dev",))
    if found:
        dev = found[1]
    local = None
    if scan.peek() == "+":
        scan.at += 1
        local, part = [], ""
        while not scan.done():
            ch = scan.peek()
            scan.at += 1
            if ch in ALNUM:
                part += ch
            elif ch in VERSION_SEPARATORS and part:
                local.append(part)
                part = ""
            else:
                return None
        if not part:
            return None
        local.append(part)
    if not scan.done():
        return None
    return Version(epoch, tuple(release), pre, post, dev, tuple(local) if local is not None else None)


def compare(a: str, b: str) -> int:
    """-1, 0 or 1, as PEP 440 orders a against b; ValueError for a string that is not a version (the matcher
    calls it only with versions `parses` accepted)."""
    left, right = parse_version(a), parse_version(b)
    if left is None or right is None:
        raise ValueError("not a PEP 440 version")
    return (left.key > right.key) - (left.key < right.key)


def parses(text) -> bool:
    return parse_version(text) is not None


def version_key(text: str) -> str:
    """The form compared with an advisory's enumerated versions: the canonical text with trailing zero release
    segments dropped, so equal versions ("1.0" and "1.0.0") give one key; a string that is not a version stays
    as it is, which no key of a version can equal."""
    version = parse_version(text)
    if version is None:
        return text
    trimmed = list(version.release)
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed.pop()
    return Version(version.epoch, tuple(trimmed), version.pre, version.post, version.dev, version.local).text


def forms(text: str) -> tuple:
    """The versions an inventory version is matched as: itself, and for a local version ("1.0+ubuntu1") its
    public version as well. PEP 440 orders 1.0+ubuntu1 after 1.0, so a range that ends with last_affected 1.0
    would leave a local rebuild of 1.0 out; matched as both, the rebuild counts as what it was built from."""
    version = parse_version(text)
    if version is None or version.local is None:
        return (text,)
    return (text, version.public)


# ---------------------------------------------------------------- names
NAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
NAME_ENDS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
_RUNS = re.compile(r"[-_.]+")


def valid_name(name) -> bool:
    """The specification's valid project name, "^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])\\Z" without case
    (https://packaging.python.org/en/latest/specifications/name-normalization/, read 2026-11-25), checked
    character by character, at most MAX_NAME characters."""
    return isinstance(name, str) and 0 < len(name) <= MAX_NAME and name[0] in NAME_ENDS and \
        name[-1] in NAME_ENDS and all(ch in NAME_CHARS for ch in name)


def normalise_name(name: str) -> str:
    """PEP 503's normalised name, as the specification writes it: re.sub(r"[-_.]+", "-", name).lower(). The OSV
    PyPI ecosystem's names are normalised the same way (OSV schema, ecosystems, read 2026-11-25)."""
    return _RUNS.sub("-", name).lower()


class _Grammar:
    """A report grammar with the regex interface osv.safe uses, checked by a function."""

    def __init__(self, check) -> None:
        self.check = check

    def match(self, value) -> bool:
        return isinstance(value, str) and self.check(value)


NAME_GRAMMAR = _Grammar(lambda v: valid_name(v) and normalise_name(v) == v)
VERSION_GRAMMAR = _Grammar(lambda v: 0 < len(v) <= 64 and v[0].isalnum() and v.isascii()
                           and all(ch.isalnum() or ch in "._-+!" for ch in v))


# ---------------------------------------------------------------- the ecosystem
def occurrence(module: dict, node: dict, advisories: list, fix, fix_checked: bool = True) -> dict:
    """One report entry, every value passed through its grammar: a report is read by a model, so nothing in it
    is worded by an advisory or a lock file."""
    worst = min(advisories, key=lambda a: osv.CLASS_ORDER[a["class"]])
    name = osv.safe(node["package"], NAME_GRAMMAR, "package")
    version = osv.safe(node["version"], VERSION_GRAMMAR, "version")
    return {"module": osv.safe_path(module["id"]), "tool": None, "ecosystem": "PyPI", "coordinate": f"pypi:{name}",
            "version": version, "scope": scope_label(node), "path": [osv.safe_path(module["id"]), f"{name}=={version}"],
            "advisories": osv.advisory_entries(advisories), "class": worst["class"],
            "fix": osv.safe(fix, VERSION_GRAMMAR, "version") if fix else None, "fix_checked": fix_checked}


def scope_label(node: dict) -> str:
    """lock, pin or constraint, then the groups or sections that list the package when the file names them."""
    text = node["scope"]
    groups = node.get("configurations") or []
    if groups:
        listed = ", ".join(osv.safe(g, osv.WORD_RE, "group") for g in groups[:3])
        text += f": {listed}" + (f", +{len(groups) - 3} more" if len(groups) > 3 else "")
    return text


INVENTORY_TEXT = ("every package version the lock files (uv.lock, poetry.lock, pdm.lock, pylock.toml, Pipfile.lock) "
                  "and the pinned requirements files of every directory of the project list, in every group and extra and whatever environment marker "
                  "it carries (a marker is not evaluated, so a package locked for one platform counts everywhere), "
                  "read as data: no installer, resolver or build backend ran. Not in it: the project's own packages "
                  "(its workspace members), what a package from a VCS, a URL or a local path holds (each is listed "
                  "under Could not be evaluated), vendored or copied code.")


def inventory_line(resolution) -> str:
    return f"Inventory: for PyPI, {INVENTORY_TEXT} {osv.INVENTORY_MEANING}"


def resolution_line(resolution) -> str:
    if not resolution:
        return "Resolution: PyPI: none (the audit stopped before the PyPI result was complete)"
    return (f"Resolution: PyPI: {resolution['selection']}; project: {resolution['project']}; candidate: "
            f"{resolution['candidate']}; modules ({len(resolution['modules'])}, coverage {resolution['coverage']}): "
            f"{', '.join(resolution['modules'][:40]) or 'none'}; base: {resolution['base']}")


PYPI = osv.register(osv.Ecosystem(
    name="PyPI", accepts=lambda name: name == "PyPI", export_url=EXPORT_URL, cache_subdir="pypi",
    minimum=MIN_ADVISORIES, label="OSV PyPI export", attribution=ATTRIBUTION, compare=compare, parses=parses,
    version_key=version_key, package_key=lambda name: normalise_name(name) if isinstance(name, str) else name,
    forms=forms, merge_aliases=True, severity_fill=True, occurrence=occurrence, separator="==",
    # MATCHER names this module's parses, compare and version_key: change it with any of them, so a cache keyed by
    # the old ones is rebuilt by the next refresh instead of being matched by the new ones
    matcher=MATCHER,
    unsure_version=lambda text: getattr(parse_version(text), "local", None) is not None,
    resolution_line=resolution_line,
    inventory_line=inventory_line, refresh_command="refresh --ecosystem pypi",
    refresh_remedy=("run `dependency-audit.py refresh --ecosystem pypi` with network access, or `refresh --ecosystem "
                    "pypi --from <zip>` with a copy of the OSV PyPI export")))


def interpreter_problem():
    """(category, remedy) when this interpreter cannot read TOML, else None."""
    if RUNNING >= MIN_PYTHON:
        return None
    here = ".".join(str(n) for n in RUNNING)
    return ("interpreter", f"the Python dependency audit needs python3 3.11 or later, which reads TOML lock files "
                           f"(tomllib), and this is python3 {here}: run the audit with python3.11 or later")


# ---------------------------------------------------------------- the plan-time form
def parse_pin(text: str):
    """(name, version) of a check argument pypi:<name>==<version>, None when it is not one."""
    if not isinstance(text, str) or not text.lower().startswith("pypi:"):
        return None
    name, sep, version = text[5:].partition("==")
    if not sep or version.startswith("=") or not valid_name(name) or parse_version(version) is None:
        return None
    return normalise_name(name), version


# ---------------------------------------------------------------- the files of a project
def is_pylock(name: str) -> bool:
    """A PEP 751 lock file name: "pylock.toml or match the regular expression r"^pylock\\.([^.]+\\.)?toml$""
    (https://packaging.python.org/en/latest/specifications/pylock-toml/, read 2026-11-25)."""
    if name == "pylock.toml":
        return True
    middle = name[len("pylock."):-len(".toml")] if name.startswith("pylock.") and name.endswith(".toml") else ""
    return bool(middle) and "." not in middle


def is_requirements(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".txt") and (lower.startswith("requirements") or lower.endswith("-requirements.txt")
                                       or lower.endswith("_requirements.txt"))


# Directories whose files are not the project's own: a virtual environment, an installed or vendored package tree,
# a build output, a cache. They are skipped both when sources are counted and when dependency files are looked
# for, so neither a vendored package's setup.py nor a virtual environment's scripts decide anything.
SOURCE_EXCLUDED = frozenset((".git", ".venv", "venv", ".tox", ".nox", "node_modules", "site-packages",
                             "__pycache__", "__pypackages__", "build", "dist", "target", ".gradle", ".mypy_cache",
                             ".pytest_cache", ".eggs"))


def excluded(rel: str) -> bool:
    return any(part in SOURCE_EXCLUDED or part.endswith(".egg-info") for part in rel.split("/")[:-1])


def in_git_dir(rel: str) -> bool:
    """Whether a repository-relative path names something inside a .git directory, which is never read: it holds
    the repository's configuration (remote URLs with credentials among it), not the project's files."""
    return ".git" in rel.split("/")


def kind_of(rel: str, project: str) -> str | None:
    """What a repository-relative file is to the project in `project`: "lock", "requirements", "declaration" or
    None (also for a file outside the project directory or in an excluded directory). Every directory of the
    project counts, not only its top: a repository holds a Lambda function's requirements.txt or a service's own
    pyproject.toml beside the main project, and each is installed somewhere."""
    prefix = project + "/" if project else ""
    if not rel.startswith(prefix) or excluded(rel) or in_git_dir(rel):
        return None
    parts = rel[len(prefix):].split("/")
    name = parts[-1]
    if name in LOCK_FILES or is_pylock(name):
        return "lock"
    if name in DECLARATION_FILES:
        return "declaration"
    if is_requirements(name) or (len(parts) > 1 and parts[-2] == "requirements" and name.lower().endswith(".txt")):
        return "requirements"
    return None


def group_of(rel: str) -> str:
    """The directory a lock, pin or declaration file belongs to: its own, or for a file of a requirements/
    directory the directory holding that one, as for requirements/*.txt beside a pyproject.toml."""
    directory = posixpath.dirname(rel)
    return posixpath.dirname(directory) if posixpath.basename(directory) == "requirements" else directory


def is_input(rel: str, project: str = "") -> bool:
    """Whether a repository-relative path can change the Python inventory, so that a --files snapshot must hold
    it and the JSON report records its digest: lock, pin and declaration files wherever they are, and every
    constraints*.txt (a -c target). A file a requirements file names under another name is read all the same,
    but is not known here without reading the requirements file."""
    name = rel.split("/")[-1]
    lower = name.lower()
    return name in LOCK_FILES or name in DECLARATION_FILES or is_pylock(name) or is_requirements(name) or \
        (lower.startswith("constraints") and lower.endswith(".txt")) or "/requirements/" in "/" + rel


def present(paths, project: str) -> list:
    """The Python lock, pin and declaration files of the project directory, in any of its directories, sorted."""
    return sorted(p for p in paths if kind_of(p, project))


def python_sources(paths, project: str) -> list:
    """The .py files of the project directory, the excluded directories left out."""
    prefix = project + "/" if project else ""
    return sorted(p for p in paths if p.endswith(".py") and p.startswith(prefix) and not excluded(p))


# A declaration file decides only once read: a pyproject.toml or setup.cfg may configure tools alone.
READ_TO_DECIDE = ("pyproject.toml", "setup.cfg")


def undeclared(source, project: str, budget=None) -> int:
    """The number of Python source files of a project that has no Python lock, pin or dependency declaration file
    anywhere in the repository (the excluded directories left out), 0 when it has one or has no source. Such a
    project declares no third-party dependency, which is normal for a standard-library-only script or a Lambda
    function using the runtime's packages: its inventory is empty and complete, never not run. An import of a
    package nothing declares is the security reviewer's to find, not this inventory's. A pyproject.toml or
    setup.cfg that configures tools only declares nothing; one that cannot be read counts as declaring. Every
    file read is charged to `budget` (a new one when None), and files that need no reading are looked at first."""
    budget = Budget() if budget is None else budget
    inputs = sorted(rel for rel in source.paths if not excluded(rel) and not in_git_dir(rel) and is_input(rel))
    if any(rel.split("/")[-1] not in READ_TO_DECIDE for rel in inputs):
        return 0
    if any(declares(source, rel, budget) for rel in inputs):
        return 0
    return len(python_sources(source.paths, project))


def declares(source, rel: str, budget) -> bool:
    """Whether a pyproject.toml or setup.cfg declares dependencies; True when it cannot be read or parsed (doubt
    runs the audit). Without tomllib (python3 older than 3.11) a pyproject.toml's table headers decide
    (headers_declare), so a file of tool settings alone is not a declaration there either, and a Java project with
    one audits as it did before the PyPI audit existed."""
    budget.check_time()
    data, _reason = source.read(rel)
    if data is None:
        return True
    budget.charge(rel, len(data))
    text = data.decode("utf-8", "replace")
    if rel.split("/")[-1] == "setup.cfg":
        return setup_cfg_declared(text).count != 0
    if interpreter_problem() is not None:
        return headers_declare(text)
    doc = load_toml(text)
    if doc is None:
        return True
    found = pyproject_declared(doc)
    # a dynamic field's files are read only later (declarations()): naming any is declaring, so a project whose
    # dependencies are all in such a file is audited, never taken for one that declares nothing
    return found.count != 0 or bool(found.files)


DECLARING_TABLES = ("project", "dependency-groups", "tool.poetry", "tool.pdm")
DECLARING_UV_KEYS = ("dev-dependencies", "sources")
DECLARING_INLINE = ("tool", "tool.uv")  # an inline table there can hold a declaring table


def headers_declare(text: str) -> bool:
    """Whether a pyproject.toml read line by line, without a TOML parser, can declare dependencies: a [project],
    [dependency-groups], [tool.poetry...] or [tool.pdm...] table (or a dotted key naming one), an inline table at
    `tool` or `tool.uv`, or in a [tool.uv...] table a dev-dependencies or sources key. Doubt counts as declaring: a
    header-shaped line in a multi-line string is read as a header, and a quoted table name or key, a line too long
    to judge and a file of more than MAX_LINES lines declare."""
    lines = text.split("\n")
    if len(lines) > MAX_LINES:
        return True
    table = ""
    for raw in lines:
        line = raw.strip()
        if len(line) > 4096:
            return True
        if line.startswith("["):
            name = line.strip("[]").split("]")[0].strip()
            if '"' in name or "'" in name:
                return True
            table = ".".join(part.strip() for part in name.split("."))
            if table in DECLARING_TABLES or any(table.startswith(t + ".") for t in DECLARING_TABLES):
                return True
            if table == "tool.uv.sources" or table.startswith("tool.uv.sources."):
                return True
            continue
        key, _eq, value = line.partition("=") if "=" in line else ("", "", "")
        key = key.strip()
        if not key or line.startswith("#"):
            continue
        if '"' in key or "'" in key:
            return True
        dotted = ".".join(part.strip() for part in key.split("."))
        full = f"{table}.{dotted}" if table else dotted
        if any(full == t or full.startswith(t + ".") for t in DECLARING_TABLES):
            return True
        if full in DECLARING_INLINE and value.strip().startswith("{"):
            return True
        if (table == "tool.uv" and dotted.split(".")[0] in DECLARING_UV_KEYS) or \
                any(full.startswith(f"tool.uv.{k}") for k in DECLARING_UV_KEYS):
            return True
    return False


ABSENT = "no third-party Python dependency declared"


def absent_inventory(sources: int) -> dict:
    """The inventory of a project undeclared() found: no module, complete, and the selection naming the absence."""
    return {"modules": [], "complete": True, "notes": [], "problem": None, "unparsed": [], "tools": [],
            "absent": True, "selection": f"no Python lock, pin or dependency declaration file in the repository and "
                                         f"{sources} Python source files: {ABSENT}"}


def selected(source, project: str, budget=None) -> list:
    """The files that make the project's dependencies Python ones to audit, as the build files found make a
    project a Maven or a Gradle one: any lock or requirements file, a setup.py or Pipfile, and a pyproject.toml or
    setup.cfg that declares dependencies, in any directory of the project. One that configures tools only (a Java
    repository's formatter settings) selects nothing; one this interpreter cannot read (no tomllib) or that cannot
    be parsed selects, so doubt runs the audit rather than skipping it."""
    budget = Budget() if budget is None else budget
    found = present(source.paths, project)
    return [rel for rel in found if rel.split("/")[-1] not in READ_TO_DECIDE or declares(source, rel, budget)]


# ---------------------------------------------------------------- reading what a file holds
class Problems:
    """What keeps an inventory from being complete: the first problem names the category and remedy of the
    status line, every one adds a note under Could not be evaluated (at most MAX_NOTES, then a count)."""

    def __init__(self) -> None:
        self.first = None
        self.notes: list = []
        self.dropped = 0

    def add(self, category: str, remedy: str, note: str) -> None:
        if self.first is None:
            self.first = (category, remedy)
        if len(self.notes) < MAX_NOTES:
            self.notes.append(note)
        else:
            self.dropped += 1

    def rendered(self) -> list:
        return self.notes + ([f"{self.dropped} more Python dependencies or files that could not be evaluated"]
                             if self.dropped else [])


class Budget:
    """What one pass over a side may read: MAX_FILES distinct files and MAX_TOTAL_BYTES in all, MAX_SIDE_PACKAGES
    packages and requirements in all, and the audit's deadline. Every read of the PyPI side is charged here, the
    files that decide the selection (undeclared, selected) and the input digests as well as the inventory's: a
    file read again (selection, then inventory, then its digest) is charged once, so the limits count files, not
    reads. Past a file or byte limit the side is not run; past the package limit the inventory stops adding
    packages and is partial; past the deadline the side is not run, checked before each file so the audit ends
    within one file's reading of --total-timeout."""

    def __init__(self, deadline=None) -> None:
        self.files = self.bytes = 0
        self.charged: set = set()
        self.packages = 0
        self.deadline = deadline  # time.monotonic() by which the audit must end, None for no limit

    def charge(self, rel: str, size: int) -> None:
        if rel in self.charged:
            return
        self.charged.add(rel)
        self.files += 1
        self.bytes += size
        if self.files > MAX_FILES or self.bytes > MAX_TOTAL_BYTES:
            raise osv.NotRun("too many Python dependency files",
                             f"more than {MAX_FILES} lock, pin and declaration files or {osv.mib(MAX_TOTAL_BYTES)} "
                             f"in all, at {osv.safe_path(rel)}: audit a smaller project directory with --project-dir")

    def check_time(self) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise osv.NotRun("time limit", osv.time_limit_remedy("the audit reached its total limit while it read "
                                                                 "the Python dependency files"))

    def take_package(self) -> bool:
        """Whether one more package or requirement may be kept; False once MAX_SIDE_PACKAGES are."""
        if self.packages >= MAX_SIDE_PACKAGES:
            return False
        self.packages += 1
        return True


def read_text(source, rel: str, budget: Budget, problems: Problems, what: str):
    """The text of a project file, None (with a problem) when it cannot be read or is not UTF-8."""
    budget.check_time()
    data, reason = source.read(rel)
    if data is None:
        problems.add("file not read", f"{osv.safe_path(rel)} {reason}: replace it with a regular file inside the "
                                      "repository, then run the audit again",
                     f"{osv.safe_path(rel)}: {what} not read ({reason})")
        return None
    budget.charge(rel, len(data))
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        problems.add("file not read", f"{osv.safe_path(rel)} is not UTF-8: save it as UTF-8, then run the audit "
                                      "again", f"{osv.safe_path(rel)}: {what} not read (not UTF-8)")
        return None


def load_toml(text: str):
    """The TOML document, or None when it is not one. tomllib's own message is not kept: a value from the file
    could be in it."""
    import tomllib  # Python 3.11 and later; interpreter_problem() is checked before any file is read
    try:
        return tomllib.loads(text)
    except (tomllib.TOMLDecodeError, RecursionError, ValueError):
        return None


def table(value) -> dict:
    return value if isinstance(value, dict) else {}


def listing(value) -> list:
    return value if isinstance(value, list) else []


NOT_TABLES = "its package list is not an array of tables"


def package_tables(doc: dict, key: str):
    """The array of tables a lock file lists its packages in, [] when it has none, None when `key` holds anything
    else: a package list of the wrong type is not read as an empty one, which would read clean."""
    value = doc.get(key)
    if value is None:
        return []
    return value if isinstance(value, list) and all(isinstance(item, dict) for item in value) else None


def major(value) -> str:
    return str(value).split(".")[0] if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


# ---------------------------------------------------------------- lock files
# What a report says about where a package came from is one of these fixed phrases, never a value of the file: a
# lock file can hold any string where a source kind belongs, and a report is read by a model.
UNRECOGNISED_SOURCE = "from an unrecognised source kind"
SOURCE_WORDS = {"git": "from git", "hg": "from hg", "svn": "from svn", "bzr": "from bzr", "url": "from a URL",
                "file": "from a file", "path": "from a path", "directory": "from a directory",
                "editable": "an editable install", "virtual": "a virtual project", "vcs": "from a VCS",
                "archive": "from an archive"}


def source_phrase(kind) -> str:
    """The fixed phrase of a source kind, UNRECOGNISED_SOURCE for anything else."""
    return SOURCE_WORDS.get(kind, UNRECOGNISED_SOURCE) if isinstance(kind, str) else UNRECOGNISED_SOURCE


class Entry:
    """One package a lock or pin file lists: a version to match, or why there is none (`unevaluable`)."""

    __slots__ = ("name", "version", "groups", "unevaluable")

    def __init__(self, name, version=None, groups=(), unevaluable=None) -> None:
        self.name, self.version, self.groups, self.unevaluable = name, version, list(groups), unevaluable


def own_packages(doc: dict) -> set:
    """The normalised names uv.lock lists as the project's own: its workspace members ([manifest] members), and
    with no manifest the one package whose source is the lock file's own directory."""
    members = listing(table(doc.get("manifest")).get("members"))
    names = {normalise_name(m) for m in members if valid_name(m)}
    if not names:
        for package in listing(doc.get("package")):
            source = table(table(package).get("source"))
            if source.get("editable") == "." or source.get("virtual") == ".":
                name = table(package).get("name")
                if valid_name(name):
                    names.add(normalise_name(name))
    return names


def uv_entries(doc: dict):
    """uv.lock: [[package]] with name, version and source; a package from a registry is matched, the project's
    own members are left out, and one from git, a URL, a path or a directory, or any other local project, cannot
    be evaluated. uv documents the format as "specific to uv" (docs.astral.sh/uv/concepts/projects/layout/, read
    2026-11-25); the fields read here are those of its version 1."""
    if doc.get("version") != 1:
        return None, "its version is not 1, the uv.lock version this audit reads"
    packages = package_tables(doc, "package")
    if packages is None:
        return None, NOT_TABLES
    own = own_packages(doc)
    entries = []
    for package in packages:
        name, version, source = package.get("name"), package.get("version"), table(package.get("source"))
        if not valid_name(name):
            entries.append(Entry(name, unevaluable="a package without a valid name"))
            continue
        local = [key for key in ("editable", "virtual") if key in source]
        if local and normalise_name(name) in own:
            continue
        kinds = [key for key in ("git", "url", "path", "directory", "editable", "virtual") if key in source]
        if kinds or "registry" not in source:
            entries.append(Entry(name, unevaluable=source_phrase(kinds[0]) if kinds else UNRECOGNISED_SOURCE))
        elif not isinstance(version, str):
            entries.append(Entry(name, unevaluable="no version"))
        else:
            entries.append(Entry(name, version))
    return entries, None


def poetry_entries(doc: dict):
    """poetry.lock: [[package]] with name, version, groups and an optional [package.source] whose type is git,
    directory, file or url for a package from outside an index (Poetry's own lock fixtures and its locker, read
    2026-11-25), legacy for a package from another index, which is matched by name like one from PyPI. Any other
    type is an unrecognised source kind, and its text is never shown."""
    if major(table(doc.get("metadata")).get("lock-version")) not in ("1", "2"):
        return None, "its lock-version is not 1.x or 2.x, the Poetry lock versions this audit reads"
    packages = package_tables(doc, "package")
    if packages is None:
        return None, NOT_TABLES
    entries = []
    for package in packages:
        name, version = package.get("name"), package.get("version")
        groups = [g for g in listing(package.get("groups")) if isinstance(g, str)]
        kind = table(package.get("source")).get("type")
        if not valid_name(name):
            entries.append(Entry(name, unevaluable="a package without a valid name"))
        elif kind not in (None, "legacy"):
            known = kind in POETRY_SOURCES
            entries.append(Entry(name, groups=groups,
                                 unevaluable=source_phrase(kind) if known else UNRECOGNISED_SOURCE))
        elif not isinstance(version, str):
            entries.append(Entry(name, groups=groups, unevaluable="no version"))
        else:
            entries.append(Entry(name, version, groups))
    return entries, None


POETRY_SOURCES = ("git", "directory", "file", "url")
PDM_LOCAL_KEYS = ("git", "hg", "svn", "bzr", "path", "url", "editable")


def pdm_entries(doc: dict):
    """pdm.lock: [[package]] with name, version and groups; a key of a VCS (git, hg, svn, bzr), path, url or
    editable marks a package from outside an index (pdm's src/pdm/models/requirements.py, read 2026-11-25)."""
    if major(table(doc.get("metadata")).get("lock_version")) != "4":
        return None, "its lock_version is not 4.x, the PDM lock version this audit reads"
    packages = package_tables(doc, "package")
    if packages is None:
        return None, NOT_TABLES
    entries = []
    for package in packages:
        name, version = package.get("name"), package.get("version")
        groups = [g for g in listing(package.get("groups")) if isinstance(g, str)]
        local = [key for key in PDM_LOCAL_KEYS if key in package]
        if not valid_name(name):
            entries.append(Entry(name, unevaluable="a package without a valid name"))
        elif local:
            entries.append(Entry(name, groups=groups, unevaluable=source_phrase(local[0])))
        elif not isinstance(version, str):
            entries.append(Entry(name, groups=groups, unevaluable="no version"))
        else:
            entries.append(Entry(name, version, groups))
    return entries, None


def pylock_entries(doc: dict):
    """pylock.toml (PEP 751): lock-version "1.0" ("If a tool doesn't support a major version, it MUST raise an
    error"), [[packages]] with name and version; [packages.vcs], [packages.directory] and [packages.archive] are
    the sources outside an index, and "The version MUST NOT be included when it cannot be guaranteed to be
    consistent with the code used" (the specification, read 2026-11-25)."""
    if major(doc.get("lock-version")) != "1":
        return None, "its lock-version is not 1.x, the pylock.toml version this audit reads"
    packages = package_tables(doc, "packages")
    if packages is None:
        return None, NOT_TABLES
    entries = []
    for package in packages:
        name, version = package.get("name"), package.get("version")
        local = [key for key in ("vcs", "directory", "archive") if key in package]
        if not valid_name(name):
            entries.append(Entry(name, unevaluable="a package without a valid name"))
        elif local:
            entries.append(Entry(name, unevaluable=source_phrase(local[0])))
        elif not isinstance(version, str):
            entries.append(Entry(name, unevaluable="no version"))
        else:
            entries.append(Entry(name, version))
    return entries, None


PIPENV_LOCAL_KEYS = ("git", "hg", "svn", "bzr", "path", "file", "editable")


def pipfile_entries(doc):
    """Pipfile.lock: JSON, _meta.pipfile-spec 6, then one section per package category ("default" for
    [packages], "develop" for [dev-packages], and any custom category) mapping each package to its "version"
    ("==<version>"); a VCS, path, file or editable key marks one from outside an index (the pipenv
    documentation, "Pipfile & Pipfile.lock", read 2026-11-25)."""
    meta = table(table(doc).get("_meta"))
    if meta.get("pipfile-spec") != 6:
        return None, "its pipfile-spec is not 6, the Pipfile.lock version this audit reads"
    entries = []
    for section in sorted(k for k in table(doc) if k != "_meta"):
        packages = doc[section]
        if not isinstance(packages, dict):
            return None, f"its {osv.safe(section, osv.WORD_RE, 'section')} section is not a table of packages"
        for name, spec in packages.items():
            spec = table(spec)
            pinned = spec.get("version")
            local = [key for key in PIPENV_LOCAL_KEYS if key in spec]
            if not valid_name(name):
                entries.append(Entry(name, unevaluable="a package without a valid name"))
            elif local:
                entries.append(Entry(name, groups=[section], unevaluable=source_phrase(local[0])))
            elif not (isinstance(pinned, str) and pinned.startswith("==") and not pinned.startswith("===")):
                entries.append(Entry(name, groups=[section], unevaluable="not pinned with =="))
            else:
                entries.append(Entry(name, pinned[2:].strip(), [section]))
    return entries, None


def lock_entries(name: str, text: str):
    """(entries or None, why not, the parsed document): the packages of a lock file by its format."""
    if name == "Pipfile.lock":
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            return None, "it is not valid JSON", None
        return (*pipfile_entries(doc), doc)
    doc = load_toml(text)
    if doc is None:
        return None, "it is not valid TOML", None
    reader = {"uv.lock": uv_entries, "poetry.lock": poetry_entries, "pdm.lock": pdm_entries}.get(name, pylock_entries)
    return (*reader(doc), doc)


# ---------------------------------------------------------------- requirements files
# The format of https://pip.pypa.io/en/stable/reference/requirements-file-format/ (pip 26.3, read 2026-11-25): a
# line ending in an unescaped backslash continues on the next; "A line that begins with # is treated as a comment
# and ignored. Whitespace followed by a # causes the # and the remainder of the line to be treated as a comment";
# options on their own lines (-r and -c name further files, relative to the file that names them, as pip reads
# them); --hash and --config-settings after a requirement; ${NAME} is an environment variable pip expands.
# Every word of an option line is read, as pip's option parser reads them all: the global options below are
# ignored with their values, and of the include options pip follows the first -r, else the first -c
# (pip/_internal/req/req_file.py, _parse_and_recurse, pip 26.1.1); an editable install on the line is a
# requirement and includes nothing. A word that is none of these makes the file not read whole. GLOBAL_OPTIONS maps
# each option to whether it takes a value (pip's cmdoptions).
GLOBAL_OPTIONS = {"-i": True, "--index-url": True, "--pypi-url": True, "--extra-index-url": True, "--no-index": False,
                  "-f": True, "--find-links": True, "--no-binary": True, "--only-binary": True,
                  "--prefer-binary": False, "--require-hashes": False, "--no-require-hashes": False, "--pre": False,
                  "--all-releases": True, "--only-final": True, "--trusted-host": True, "--use-feature": True}
INCLUDE_OPTIONS = {"-r": "requirement", "--requirement": "requirement", "-c": "constraint",
                   "--constraint": "constraint"}
EDITABLE_OPTIONS = ("-e", "--editable")
SHORT_WITH_VALUE = ("-i", "-f", "-r", "-c", "-e")  # "-rfile" is "-r file", as optparse reads a short option
OPERATORS = ("===", "==", "!=", "<=", ">=", "~=", "<", ">")
MAX_LINES = 100_000
CHECK_EVERY = 4096  # entries between two checks of the deadline
# What a constraint file may hold without changing where a package comes from: a range or a bare name narrows what
# installs, and pip refuses an editable constraint. Anything else there is reported (CONSTRAINT_WHY).
CONSTRAINT_SILENT = ("not pinned to a version", "a version range", "an editable install (-e), which names no version")
CONSTRAINT_WHY = {"a URL, a VCS or a local path": "a constraint to a URL, a VCS or a local path"}


def logical_lines(text: str) -> list:
    """(line number, text) of each logical line: continuations joined, comments stripped, blank lines left out.
    The pieces of a continued line are collected and joined once, so a file of continuations reads in linear
    time."""
    out, pieces, start, lead = [], [], 0, None
    for number, raw in enumerate(text.split("\n")[:MAX_LINES], 1):
        line = raw.rstrip("\r")
        if not pieces:
            start = number
        # pip's rule: a line ending in a backslash continues, unless it is a comment line; `lead` is the first
        # character the joined line has so far that is not whitespace
        first = lead if lead is not None else (line.lstrip()[:1] or None)
        if line.endswith("\\") and first != "#":
            pieces.append(line[:-1])
            lead = first if lead is not None else (line[:-1].lstrip()[:1] or None)
            continue
        pieces.append(line)
        line, pieces, lead = "".join(pieces), [], None
        cut = next((i for i, ch in enumerate(line) if ch == "#" and (i == 0 or line[i - 1].isspace())), None)
        line = (line if cut is None else line[:cut]).strip()
        if line:
            out.append((start, line))
    pending = "".join(pieces).strip()
    if pending:
        out.append((start, pending))
    return out


def coding_other_than_utf8(text: str) -> bool:
    """Whether a PEP 263 coding comment in the first two lines names an encoding other than UTF-8."""
    for line in text.split("\n", 2)[:2]:
        stripped = line.strip()
        at = stripped.find("coding")
        if stripped.startswith("#") and at >= 0 and stripped[at + 6:at + 7] in (":", "="):
            name = stripped[at + 7:].strip().split()[0] if stripped[at + 7:].strip() else ""
            return name.lower().replace("_", "-") not in ("utf-8", "utf8")
    return False


# The options pip reads after a requirement on its line (SUPPORTED_OPTIONS_REQ in pip/_internal/req/req_file.py,
# pip 26.1.1: --hash and --config-settings, whose short form is -C), each with a value; pip refuses any other.
REQUIREMENT_OPTIONS = ("--hash", "--config-settings", "-C")


def requirement_options_read(tail: str) -> bool:
    """Whether every word after a requirement (what split_requirement cut off) is one of REQUIREMENT_OPTIONS with
    its value: "--hash=v", "--hash v", "-Cv" or "-C v"."""
    words, at = tail.split(), 0
    while at < len(words):
        word = words[at]
        if word.startswith("--") and "=" in word:
            option, step = word.partition("=")[0], 1
        elif word.startswith("-C") and len(word) > 2:
            option, step = "-C", 1
        else:
            option, step = word, 2
        if option not in REQUIREMENT_OPTIONS or at + step > len(words):
            return False
        at += step
    return True


def split_requirement(line: str) -> str:
    """The requirement of a line, without the per-requirement options that follow it (" --hash=...")."""
    at = 0
    while True:
        at = line.find(" -", at)
        if at < 0:
            return line
        if at + 2 < len(line) and (line[at + 2].isalpha() or line[at + 2] == "-"):
            return line[:at].rstrip()
        at += 2


def parse_requirement(text: str) -> tuple:
    """(name or None, version or None, why it cannot be evaluated or None) of one requirement specifier
    (https://packaging.python.org/en/latest/specifications/dependency-specifiers/, read 2026-11-25:
    "name_req = name wsp* extras? wsp* versionspec? wsp* quoted_marker?"). Pinned means one clause, == with a
    version and no wildcard, or === ; the marker after ";" is not evaluated."""
    if "${" in text:
        return None, None, "names an environment variable, which is not expanded here"
    spec, _sep, _marker = text.partition(";")
    at = 0
    while at < len(spec) and spec[at] in NAME_CHARS:
        at += 1
    name, rest = spec[:at], spec[at:].strip()
    if not valid_name(name) or rest[:1] in ("+", ":", "/", "\\"):
        if "://" in text or text.startswith((".", "/", "~")) or rest[:1] in ("+", ":", "/", "\\"):
            return None, None, "a URL, a VCS or a local path"
        return None, None, "not a requirement this audit can read"
    if rest.startswith("["):
        close = rest.find("]")
        if close < 0:
            return name, None, "not a requirement this audit can read"
        extras = [e.strip() for e in rest[1:close].split(",") if e.strip()]
        if not all(valid_name(e) for e in extras):
            return name, None, "not a requirement this audit can read"
        rest = rest[close + 1:].strip()
    if rest.startswith("@"):
        return name, None, "a URL, a VCS or a local path"
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1].strip()
    if not rest:
        return name, None, "not pinned to a version"
    clauses = [c.strip() for c in rest.split(",")]
    if len(clauses) != 1:
        return name, None, "a version range"
    clause = clauses[0]
    operator = next((op for op in OPERATORS if clause.startswith(op)), None)
    version = clause[len(operator):].strip() if operator else ""
    if operator == "===":
        return (name, version, None) if parse_version(version) else \
            (name, None, "pinned with === to a version PEP 440 cannot order")
    if operator != "==" or "*" in version:
        return name, None, "a version range"
    if parse_version(version) is None:
        return name, None, "pinned to a version PEP 440 cannot parse"
    return name, version, None


def option_arity(option: str):
    """Whether an option of a requirements file takes a value, None for one this audit does not read."""
    if option in INCLUDE_OPTIONS or option in EDITABLE_OPTIONS:
        return True
    return GLOBAL_OPTIONS.get(option)


def read_option_line(words: list) -> tuple:
    """(editable, requirement targets, constraint targets, every word read) of an option line, each option with
    its value: "--opt=value", "-rvalue", or the next word."""
    editable, requirements, constraints, understood = False, [], [], True
    at = 0
    while at < len(words):
        word = words[at]
        if word.startswith("--") and "=" in word:
            option, _eq, value = word.partition("=")
            takes, step = option_arity(option), 1
            if takes is False:
                understood = False  # a flag given a value: pip refuses it
        elif len(word) > 2 and word[:2] in SHORT_WITH_VALUE and not word.startswith("--"):
            option, value, takes, step = word[:2], word[2:], True, 1
        else:
            option, takes = word, option_arity(word)
            value = words[at + 1] if takes and at + 1 < len(words) else None
            step = 2 if takes and value is not None else 1
        at += step
        if takes is None:
            understood = False  # an option this audit does not read, or a word no option takes
        elif option in EDITABLE_OPTIONS:
            editable = True
        elif option in INCLUDE_OPTIONS:
            (requirements if INCLUDE_OPTIONS[option] == "requirement" else constraints).append(value)
    return editable, requirements, constraints, understood


def resolve_include(including: str, target: str):
    """The repository-relative path a -r or -c names, relative to the file that names it as pip reads it; None
    for a URL or a path that leaves the repository."""
    if "://" in target or target.startswith("~"):
        return None
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(including), target)) if not \
        target.startswith("/") else None
    if joined is None or joined == ".." or joined.startswith("../") or joined.startswith("/"):
        return None
    return joined


# ---------------------------------------------------------------- the inventory of one side
def new_module(rel: str, scope: str) -> dict:
    return {"id": rel, "nodes": [], "parsed": True, "complete": True, "scope": scope}


def too_many_packages(module: dict, problems: Problems) -> None:
    rel = osv.safe_path(module["id"])
    module["complete"] = False
    problems.add("lock file too large", f"the lock and pin files list more than {MAX_SIDE_PACKAGES} packages in all, "
                                        f"at {rel}: audit a smaller project directory with --project-dir",
                 f"module {rel}: more than {MAX_SIDE_PACKAGES} packages in all, the rest not read")


def add_entries(module: dict, entries: list, problems: Problems, scope: str, budget: Budget,
                charge: bool = True) -> None:
    """The entries of one file as nodes of its module; one that cannot be evaluated is a problem and leaves the
    module incomplete. One package at one version is one node however often the file lists it (a requirements
    file naming it twice, a lock file with a marker fork of one version), its groups merged, so it is reported
    and counted once. Each node is charged to the side's budget (unless `charge` is False: a requirements file's
    lines were charged as they were read): past MAX_SIDE_PACKAGES the rest is not kept."""
    rel = osv.safe_path(module["id"])
    nodes: dict = {}
    groups: dict = {}  # node key -> its groups, sorted once at the end: merging sorted lists per entry was quadratic
    for count, entry in enumerate(entries[:MAX_PACKAGES]):
        if count % CHECK_EVERY == 0:
            budget.check_time()
        version = entry.version
        why = entry.unevaluable
        if why is None and parse_version(version) is None:
            why = "a version PEP 440 cannot parse"
        if why is not None:
            module["complete"] = False
            label = osv.safe(normalise_name(entry.name), NAME_GRAMMAR, "package") if valid_name(entry.name) else \
                osv.withheld("package", entry.name)
            problems.add("packages not evaluated", f"{label} in {rel} cannot be checked against the advisory data "
                                                   f"({why}): pin it to a released version from an index, or review it "
                                                   "yourself; the result stays partial while it is there",
                         f"module {rel}: {label} ({why})")
            continue
        key = (normalise_name(entry.name), version_key(version.strip()))
        node = nodes.get(key)
        if node is None:
            if charge and not budget.take_package():
                too_many_packages(module, problems)
                break
            node = nodes[key] = {"package": key[0], "version": version.strip(), "scope": scope, "optional": False,
                                 "path": [], "ships": True}
            module["nodes"].append(node)
        if entry.groups:
            groups.setdefault(key, set()).update(entry.groups)
    for key, names in groups.items():
        nodes[key]["configurations"] = sorted(names)
    if len(entries) > MAX_PACKAGES:
        module["complete"] = False
        problems.add("lock file too large", f"{rel} lists more than {MAX_PACKAGES} packages: audit a smaller project",
                     f"module {rel}: more than {MAX_PACKAGES} packages, the rest not read")


class RequirementsFile:
    """What one requirements file holds, read once whichever installs reach it: its module, the requirements that
    are not pinned, the names it pins with == and no marker (which, in a constraint file, cover an unpinned
    requirement of the same install), every name it lists, and the files it includes."""

    __slots__ = ("module", "entries", "unpinned", "pins", "names", "edges", "targets")

    def __init__(self, module: dict) -> None:
        self.module, self.entries, self.unpinned, self.pins, self.names, self.edges = module, [], [], set(), set(), []
        self.targets: set = set()  # (kind, target) of the edges, so a file named on many lines is one edge


class RequirementsReader:
    """The requirements files of one side, each parsed once, and each root file's install walked through them:
    the files it installs (reached by -r from the root or from a file it installs) and the files that constrain
    it (reached by -c), as pip reads them. An unpinned requirement is a problem once when some install reaches its
    file and no constraint file of that install pins it; a file any root installs is a pin module, one only
    constraints reach is a constraint module."""

    def __init__(self, source, budget: Budget, problems: Problems) -> None:
        self.source, self.budget, self.problems = source, budget, problems
        self.files: dict = {}  # path -> RequirementsFile, None for a file that was not read
        self.modules: dict = {}  # path -> module
        self.installs: dict = {}  # root path -> the paths it installs
        self.installed: set = set()  # paths some root installs
        self.reported: set = set()  # (path, line) of the problems already added

    def read_root(self, rel: str) -> None:
        """One requirements file the project holds and every file it names; then the requirements of that install
        that are not pinned and that no constraint of the same install pins are problems."""
        installs, constraints = set(), set()
        queue, seen = collections.deque([(rel, "pin", 0)]), {(rel, "pin")}
        while queue:  # breadth first, so a file is reached first by its shortest chain of includes
            path, scope, depth = queue.popleft()
            self.budget.check_time()  # a file parsed already costs no read, but its walk still costs time
            (installs if scope == "pin" else constraints).add(path)
            info = self._file(path)
            if info is None:
                continue
            for kind, target, number in info.edges:
                state = (target, "constraint" if kind == "constraint" else "pin")
                if state in seen:
                    continue  # marked when queued, so a state is queued once however many lines name it
                if depth + 1 > MAX_INCLUDE_DEPTH:
                    self._include_problem(path, number, kind, "nests deeper than the audit follows")
                    continue
                seen.add(state)
                queue.append((*state, depth + 1))
        self.installs[rel] = installs
        self.installed |= installs
        constrained = set().union(*(self.files[p].pins for p in constraints if self.files.get(p)))
        installed_names = set().union(*(self.files[p].names for p in installs if self.files.get(p)))
        for path in sorted(constraints - installs):
            info = self.files.get(path)
            for number, name, why in info.unpinned if info else ():
                # pip keeps a constraint to a URL, a VCS or a path, and the resolver then takes the package from
                # there: what installs is not the index release the advisory data describes. A range or a bare name
                # only narrows what installs, and pip refuses an editable constraint.
                if why in CONSTRAINT_SILENT or (name is not None and normalise_name(name) not in installed_names):
                    continue
                self._constraint_problem(path, number, name, why)
        for path in sorted(installs):
            info = self.files.get(path)
            for number, name, why in info.unpinned if info else ():
                if name is not None and why in ("not pinned to a version", "a version range") and \
                        normalise_name(name) in constrained:
                    continue  # this install's constraint pins it
                self._unpinned_problem(path, number, name, why)

    def root_names(self, rel: str) -> set:
        """The normalised names the files a root installs list."""
        return set().union(*(self.files[p].names for p in self.installs.get(rel, ()) if self.files.get(p)))

    def finish(self) -> None:
        """Every file's nodes, once each install is known: a file some root installs is a pin module, a file only
        constraints reach a constraint module (a constraint installs nothing, but its pins are still matched)."""
        for path, info in self.files.items():
            scope = "pin" if path in self.installed else "constraint"
            self.modules[path]["scope"] = scope
            if info is not None:
                add_entries(info.module, info.entries, self.problems, scope, self.budget, charge=False)
                info.entries = []

    def _include_problem(self, path: str, number: int, kind: str, why: str) -> None:
        if (path, number) in self.reported:
            return
        self.reported.add((path, number))
        shown_rel = osv.safe_path(path)
        self.modules[path]["complete"] = False
        self.problems.add("include not followed", f"the {kind} file on line {number} of {shown_rel} {why}: name a "
                                                  "file inside the repository, then run the audit again",
                          f"module {shown_rel}: line {number}: the {kind} file is not read ({why})")

    def _constraint_problem(self, path: str, number: int, name, why: str) -> None:
        if (path, number) in self.reported:
            return
        self.reported.add((path, number))
        rel = osv.safe_path(path)
        phrase = CONSTRAINT_WHY.get(why, "a constraint this audit cannot read")
        label = osv.safe(normalise_name(name), NAME_GRAMMAR, "package") if name and valid_name(name) else \
            f"line {number}"
        self.modules[path]["complete"] = False
        self.problems.add("packages not evaluated", f"{label} in {rel} cannot be checked against the advisory data "
                                                    f"({phrase}): pin it to a released version from an index, or "
                                                    "review it yourself; the result stays partial while it is there",
                          f"module {rel}: line {number}: {label} ({phrase})")

    def _unpinned_problem(self, path: str, number: int, name, why: str) -> None:
        if (path, number) in self.reported:
            return
        self.reported.add((path, number))
        rel = osv.safe_path(path)
        if name and valid_name(name):
            label = osv.safe(normalise_name(name), NAME_GRAMMAR, "package")
            subject, note = f"{label} in {rel}", f"{label} ({why})"
        else:
            subject, note = f"line {number} of {rel}", why
        self.modules[path]["complete"] = False
        self.problems.add("requirements not pinned",
                          f"{subject} is {why}: pin every requirement with == (pip-compile writes such a file) or "
                          "commit a lock file, then run the audit again", f"module {rel}: line {number}: {note}")

    def _file(self, rel: str):
        """The parsed file, read the first time any install reaches it; None when it could not be read."""
        if rel in self.files:
            return self.files[rel]
        module = self.modules[rel] = new_module(rel, "pin")
        self.files[rel] = None
        text = read_text(self.source, rel, self.budget, self.problems, "requirements file")
        if text is None:
            module["complete"] = module["parsed"] = False
            return None
        if coding_other_than_utf8(text):
            module["complete"] = module["parsed"] = False
            self.problems.add("file not read", f"{osv.safe_path(rel)} names an encoding other than UTF-8: save it "
                                               "as UTF-8, then run the audit again",
                              f"{osv.safe_path(rel)}: requirements file not read (not UTF-8)")
            return None
        info = self.files[rel] = RequirementsFile(module)
        if text.count("\n") >= MAX_LINES:
            module["complete"] = False
            self.problems.add("requirements file too large", f"{osv.safe_path(rel)} has more than {MAX_LINES} lines: "
                                                             "split it, then run the audit again",
                              f"module {osv.safe_path(rel)}: more than {MAX_LINES} lines, the rest not read")
        for number, line in logical_lines(text):
            if line.startswith("-"):
                self._option(rel, info, number, line)
                continue
            if not self.budget.take_package():
                too_many_packages(module, self.problems)
                break
            requirement = split_requirement(line)
            if not requirement_options_read(line[len(requirement):]):
                self._not_read(info.module, rel, number)  # pip refuses the file for an option it does not know
            name, version, why = parse_requirement(requirement)
            if name is not None and valid_name(name):
                info.names.add(normalise_name(name))
            if why is None:
                info.entries.append(Entry(name, version))
                if not requirement.partition(";")[2].strip():
                    info.pins.add(normalise_name(name))  # a pin with a marker constrains only where it applies
            else:
                info.unpinned.append((number, name, why))
        return info

    def _option(self, rel: str, info: RequirementsFile, number: int, line: str) -> None:
        editable, requirements, constraints, understood = read_option_line(line.split())
        if not understood:
            self._not_read(info.module, rel, number)
        if editable:  # pip installs it, from a path or a VCS, whatever constraint names it; it includes nothing
            info.unpinned.append((number, None, "an editable install (-e), which names no version"))
            return
        if not requirements and not constraints:
            return
        kind = "requirement" if requirements else "constraint"
        value = (requirements or constraints)[0]  # pip follows the first -r, else the first -c
        target = resolve_include(rel, value) if value else None
        if target is None:
            self._include_problem(rel, number, kind, "names a URL, a path outside the repository or nothing")
        elif in_git_dir(target) or target not in self.source.paths:
            # only a file of the candidate is read: an ignored .env or a .git file holds no requirement, and its
            # lines would reach the report
            self._include_problem(rel, number, kind, "names a file that is not one of the candidate's files")
        elif (kind, target) not in info.targets:  # a file named twice is one edge, kept at its first line
            if not self.budget.take_package():
                too_many_packages(info.module, self.problems)
                return
            info.targets.add((kind, target))
            info.edges.append((kind, target, number))

    def _not_read(self, module: dict, rel: str, number: int) -> None:
        shown_rel = osv.safe_path(rel)
        module["complete"] = False
        self.problems.add("requirements not read",
                          f"line {number} of {shown_rel} holds an option this audit does not read: remove it or "
                          "commit a lock file, then run the audit again",
                          f"module {shown_rel}: line {number}: an option not read")


class Declared:
    """What one declaration file says the project depends on: count (None when it cannot be known: a setup.py, a
    dynamic list, a file that is not read or a field of the wrong type), the main dependencies by normalised name
    with whether an environment marker narrows each, the other groups' and extras' names, and the project's own
    name."""

    __slots__ = ("rel", "count", "main", "others", "title", "why", "files")

    def __init__(self, rel: str = "", count=None, main=None, others=None, title=None, why=None) -> None:
        self.rel, self.count, self.main, self.others, self.title = rel, count, main or {}, others or set(), title
        self.why = why  # when count is None: why, a fixed phrase (UNREAD_WHY), never the file's text
        self.files: list = []  # (whether main, path relative to the declaration) of setuptools' dynamic files

    def add(self, text: str, main: bool) -> None:
        """One dependency specifier, counted, its name kept as main or other. Once the declaration is unknown
        (why set) it stays unknown: a later readable file never makes a count of it again."""
        if self.why is None:
            self.count = (self.count or 0) + 1
        name, marker = specifier_name(text)
        if name and main:
            self.main[name] = self.main.get(name, True) and marker
        elif name:
            self.others.add(name)


# Why a declaration's dependencies are not known; each is a remedy's words, never a value of the file.
UNREAD_WHY = ("it is not valid TOML", "it is not valid Python", "setup.py builds them in code",
              "a dynamic field this audit does not read", "a field of an unexpected type",
              "setup.cfg names them with file: or attr:", "it is not a valid setup.cfg", "a file it names is not read",
              "the file could not be read")


def specifier_name(text):
    """(normalised name or None, whether a marker follows) of a dependency specifier: its name is the run of name
    characters it starts with ("name_req = name wsp* extras? ..." of the dependency specifiers specification)."""
    spec = text.strip()
    at = 0
    while at < len(spec) and spec[at] in NAME_CHARS:
        at += 1
    return (normalise_name(spec[:at]) if valid_name(spec[:at]) else None), ";" in spec


class _Shape:
    """Reads parts of a parsed file by the type its format gives them, remembering any part of another type, so
    a declaration that is not understood is unknown rather than empty."""

    def __init__(self) -> None:
        self.wrong = False

    def table(self, value) -> dict:
        if value is None or isinstance(value, dict):
            return value or {}
        self.wrong = True
        return {}

    def strings(self, value, allowed=()) -> list:
        """The strings of an array; an item of a type in `allowed` (a dependency group's include-group table) is
        skipped, any other makes the shape wrong."""
        if value is None:
            return []
        if not isinstance(value, list):
            self.wrong = True
            return []
        if not all(isinstance(item, (str, *allowed)) for item in value):
            self.wrong = True
        return [item for item in value if isinstance(item, str)]


def pyproject_declared(doc: dict) -> Declared:
    """What a parsed pyproject.toml declares: the [project] dependencies and optional-dependencies (PEP 621),
    [dependency-groups] (PEP 735), Poetry's dependencies, dev-dependencies and groups (python left out), PDM's
    and uv's dev-dependencies. The main dependencies are [project] dependencies and Poetry's; everything else is a
    group or an extra."""
    shape = _Shape()
    project, tool = shape.table(doc.get("project")), shape.table(doc.get("tool"))
    main, others, count = {}, set(), 0

    def add(specifiers, into_main):
        nonlocal count
        for text in specifiers:
            count += 1
            name, marker = specifier_name(text)
            if name and into_main:
                main[name] = main.get(name, True) and marker
            elif name:
                others.add(name)
    dynamic = shape.strings(project.get("dynamic"))
    add(shape.strings(project.get("dependencies")), True)
    for extra in shape.table(project.get("optional-dependencies")).values():
        add(shape.strings(extra), False)
    for group in shape.table(doc.get("dependency-groups")).values():
        add(shape.strings(group, allowed=(dict,)), False)  # {include-group = "..."} names a group, not a package
    poetry = shape.table(tool.get("poetry"))
    for name, value in shape.table(poetry.get("dependencies")).items():
        if name != "python":
            count += 1
            if valid_name(name):
                # a list of constraints, or a table with markers, a platform or a Python range, applies somewhere
                marker = isinstance(value, list) or (isinstance(value, dict) and
                                                     any(k in value for k in ("markers", "platform", "python")))
                key = normalise_name(name)
                main[key] = main.get(key, True) and marker
    poetry_groups = [shape.table(poetry.get("dev-dependencies"))]
    poetry_groups += [shape.table(shape.table(g).get("dependencies")) for g in shape.table(poetry.get("group")).values()]
    for group in poetry_groups:
        count += len(group)
        others.update(normalise_name(n) for n in group if valid_name(n))
    for group in shape.table(shape.table(tool.get("pdm")).get("dev-dependencies")).values():
        add(shape.strings(group), False)
    add(shape.strings(shape.table(tool.get("uv")).get("dev-dependencies")), False)
    title = project.get("name") if valid_name(project.get("name")) else \
        poetry.get("name") if valid_name(poetry.get("name")) else None
    found = Declared(count=count, main=main, others=others, title=normalise_name(title) if title else None)
    # setuptools reads a dynamic field from its [tool.setuptools.dynamic] table; a list of files is read here as
    # requirement lines (https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html, read 2026-11-25:
    # "dependencies = {file = ["requirements.in"]}"), anything else there (an attr, another backend) is unknown
    setuptools_dynamic = shape.table(shape.table(tool.get("setuptools")).get("dynamic"))
    if "dependencies" in dynamic:
        files = dynamic_files(setuptools_dynamic.get("dependencies"))
        found.files += [(True, path) for path in files or ()]
        found.why = found.why or (None if files is not None else "a dynamic field this audit does not read")
    if "optional-dependencies" in dynamic:
        extras = setuptools_dynamic.get("optional-dependencies")
        for spec in (extras.values() if isinstance(extras, dict) else [None]):
            files = dynamic_files(spec)
            found.files += [(False, path) for path in files or ()]
            found.why = found.why or (None if files is not None else "a dynamic field this audit does not read")
    if shape.wrong:
        found.why = "a field of an unexpected type"
    if found.why:
        found.count = None
    return found


def dynamic_files(spec):
    """The file list of a setuptools dynamic field ({file = "a.txt"} or {file = ["a.txt", ...]}), None for any other
    form."""
    files = spec.get("file") if isinstance(spec, dict) and set(spec) == {"file"} else None
    files = [files] if isinstance(files, str) else files
    return files if isinstance(files, list) and files and all(isinstance(f, str) and f for f in files) else None


SETUP_CALLS = ("setup", "setuptools.setup")


def setup_py_declared(text: str) -> Declared:
    """What a setup.py declares, read with ast and never run: install_requires (the main dependencies) and
    extras_require of its one setup() call, when each is a literal (a list or tuple of strings; for extras a dict
    of them). Anything else that may declare dependencies (no setup() call or more than one, **kwargs, a value
    built in code) is unknown."""
    import ast  # only a setup.py needs it
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return Declared(why="it is not valid Python")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _call_name(node.func) in SETUP_CALLS]
    if len(calls) != 1 or any(keyword.arg is None for keyword in calls[0].keywords) or \
            not _setuptools_setup(tree, calls[0]):
        return Declared(why="setup.py builds them in code")
    found = Declared(count=0)
    for keyword in calls[0].keywords:
        if keyword.arg not in ("install_requires", "extras_require"):
            continue
        try:
            value = ast.literal_eval(keyword.value)
        except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError):
            return Declared(why="setup.py builds them in code")
        groups = [value] if keyword.arg == "install_requires" else \
            list(value.values()) if isinstance(value, dict) else None
        if groups is None or not all(isinstance(g, (list, tuple)) and all(isinstance(t, str) for t in g)
                                     for g in groups):
            return Declared(why="setup.py builds them in code")
        for group in groups:
            for item in group:
                found.add(item, keyword.arg == "install_requires")
    return found


SETUP_MODULES = ("setuptools", "distutils.core")


# What makes a setup.py's setup() call unreadable as a literal whatever its bindings look like: a star import, a match
# statement (a capture binds a name), a store to any attribute or subscript named setup, and the ways code reaches
# names or modules dynamically. Python has more binding forms than a reader can list, so the rest is a residual
# (TM-82): a setup.py written to evade this reader is the author's own build code, the security reviewer's
# PY-DEP-08.
DYNAMIC_NAMES = frozenset(("globals", "vars", "locals", "exec", "eval", "compile", "setattr", "__import__",
                           "importlib"))


def _evasive(tree) -> bool:
    import ast
    match = getattr(ast, "Match", ())  # Python 3.10 and later
    for node in ast.walk(tree):
        if (match and isinstance(node, match)) or \
                (isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)):
            return True
        if isinstance(node, ast.Attribute) and node.attr == "setup" and not isinstance(node.ctx, ast.Load):
            return True
        if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Load):
            if isinstance(node.slice, ast.Constant) and node.slice.value == "setup":
                return True
        if isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr == "modules" and isinstance(node.value, ast.Name) and \
                node.value.id == "sys":
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)) and \
                any(alias.name.split(".")[0] == "importlib" for alias in node.names) or \
                (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "importlib"):
            return True
    return False


def _setup_import(node) -> bool:
    """`from setuptools import setup` (or distutils.core), absolute, not renamed."""
    import ast
    return isinstance(node, ast.ImportFrom) and node.module in SETUP_MODULES and node.level == 0 and \
        len(node.names) >= 1 and any(a.name == "setup" and a.asname in (None, "setup") for a in node.names)


def _setup_fallback(node) -> list:
    """The imports of a module-level `try: from setuptools import setup` / `except ImportError: from
    distutils.core import setup` (each branch that one import alone), [] for anything else."""
    import ast
    if not isinstance(node, ast.Try) or node.orelse or node.finalbody or not node.handlers:
        return []
    branches = [node.body] + [h.body for h in node.handlers]
    errors = all(isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError") and not h.name
                 for h in node.handlers)
    if not errors or not all(len(b) == 1 and _setup_import(b[0]) for b in branches):
        return []
    return [b[0] for b in branches]


def _setuptools_setup(tree, call) -> bool:
    """Whether the one setup() call surely calls setuptools' (or distutils') own setup, so its keywords are all it
    declares. `setup(...)`: the name bound only by one module-level `from setuptools import setup` (or
    distutils.core), or by the two imports of a module-level try/except ImportError fallback between them, and used
    only as that call. `setuptools.setup(...)`: `setuptools` bound only by one module-level `import setuptools`,
    every other use of it reading another attribute (`setuptools.find_packages()`), and nothing stored on it. A
    name rebound, wrapped (functools.partial(setup, install_requires=...)), passed on or imported again may carry
    dependencies the call does not show, and so does anything _evasive finds."""
    import ast
    if _evasive(tree):
        return False
    name = _call_name(call.func)
    bound = "setup" if name == "setup" else "setuptools"
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    bindings, uses = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == bound:
            (uses if isinstance(node.ctx, ast.Load) else bindings).append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == bound:
            bindings.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bindings += [node for alias in node.names if (alias.asname or alias.name.split(".")[0]) == bound]
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and bound in node.names:
            bindings.append(node)
        elif isinstance(node, ast.arg) and node.arg == bound:
            bindings.append(node)
        elif isinstance(node, ast.ExceptHandler) and node.name == bound:
            bindings.append(node)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == bound and \
                not isinstance(node.ctx, ast.Load):
            return False  # something stored on setuptools
    if name == "setup":
        fallback = [found for node in tree.body for found in _setup_fallback(node)]
        allowed = fallback if fallback else [n for n in tree.body if _setup_import(n)]
        return bool(allowed) and len(allowed) <= 2 and sorted(map(id, bindings)) == sorted(map(id, allowed)) and \
            uses == [call.func]
    if len(bindings) != 1 or bindings[0] not in tree.body or not isinstance(bindings[0], ast.Import) or \
            not any(a.name == "setuptools" and a.asname is None for a in bindings[0].names):
        return False
    # every use of setuptools but the call's reads another attribute of it, so setup is reached only there
    return all(use is call.func.value or (isinstance(parents.get(use), ast.Attribute) and
                                          parents[use].attr != "setup") for use in uses)


def _call_name(func) -> str:
    import ast
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return ""


PIPFILE_OTHER_TABLES = ("source", "requires", "scripts", "pipenv")  # Pipfile tables that list no package
MARKER_KEYS = ("markers", "sys_platform", "platform_machine", "platform_system", "os_name", "python_version",
               "python_full_version", "platform_python_implementation", "implementation_name")


def pipfile_declared(doc: dict) -> Declared:
    """What a Pipfile declares: [packages] (the main dependencies), [dev-packages] and every custom category, which
    is any other table ("You can define custom package categories beyond the standard packages and dev-packages",
    https://pipenv.pypa.io/en/latest/pipfile.html, read 2026-11-25), so a table this audit does not know is a
    category too."""
    main, others, count = {}, set(), 0
    for section, packages in doc.items():
        if section in PIPFILE_OTHER_TABLES or not isinstance(packages, dict):
            continue
        for name, spec in packages.items():
            count += 1
            if not valid_name(name):
                continue
            key = normalise_name(name)
            if section == "packages":
                marker = isinstance(spec, dict) and any(k in spec for k in MARKER_KEYS)
                main[key] = main.get(key, True) and marker
            else:
                others.add(key)
    return Declared(count=count, main=main, others=others)


def setup_cfg_declared(text: str) -> Declared:
    """What a setup.cfg declares: [options] install_requires (the main dependencies) and [options.extras_require].
    A file it names ("file:") or one that cannot be parsed declares an unknown number."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(text)
    except (configparser.Error, ValueError):
        return Declared(why="it is not a valid setup.cfg")
    main, others, count = {}, set(), 0
    requires = parser.get("options", "install_requires", fallback="")
    extras = parser["options.extras_require"] if parser.has_section("options.extras_require") else {}
    for value, into in [(requires, main)] + [(extras[key], others) for key in extras]:
        for line in (part.strip() for part in value.split("\n")):
            if not line:
                continue
            if line.startswith(("file:", "attr:")):
                return Declared(why="setup.cfg names them with file: or attr:")
            count += 1
            name, marker = specifier_name(line)
            if name and into is main:
                main[name] = main.get(name, True) and marker
            elif name:
                others.add(name)
    title = parser.get("metadata", "name", fallback=None)
    return Declared(count=count, main=main, others=others,
                    title=normalise_name(title) if valid_name(title) else None)


def declarations(source, rel: str, budget: Budget, problems: Problems) -> Declared:
    """What one declaration file (pyproject.toml, setup.cfg, Pipfile, setup.py) says the project depends on. A
    setup.py is never run: its literal lists are read with ast. A TOML file that does not parse is a problem of
    its own (declarations not read), whatever covers it; a file that cannot be read declares an unknown number,
    and so does a declaration this audit cannot read (Declared.why)."""
    name = rel.split("/")[-1]
    text = read_text(source, rel, budget, problems, "declaration file")
    if text is None:
        found = Declared(why="the file could not be read")
    elif name == "setup.py":
        found = setup_py_declared(text)
    elif name == "setup.cfg":
        found = setup_cfg_declared(text)
    else:
        doc = load_toml(text)
        if doc is None:
            shown_rel = osv.safe_path(rel)
            problems.add("declarations not read", f"{shown_rel} cannot be read as a declaration file (it is not "
                                                  "valid TOML): fix it, then run the audit again",
                         f"{shown_rel}: declaration file not read (it is not valid TOML)")
            found = Declared(why="it is not valid TOML")
        else:
            found = pipfile_declared(doc) if name == "Pipfile" else pyproject_declared(doc)
    found.rel = rel
    for main, path in found.files:
        dynamic_requirements(source, rel, path, main, found, budget, problems)
    return found


def dynamic_requirements(source, rel: str, path: str, main: bool, found: Declared, budget: Budget,
                         problems: Problems) -> None:
    """The requirement lines of a file a setuptools dynamic field names, relative to the pyproject.toml, read as
    the declaration's dependencies: only one of the side's own files, never an option line (setuptools reads none);
    otherwise the declaration is unknown."""
    target = resolve_include(rel, path)
    if target is None or in_git_dir(target) or target not in source.paths:
        found.count, found.why = None, "a file it names is not read"
        return
    text = read_text(source, target, budget, problems, "declaration file")
    if text is None or text.count("\n") >= MAX_LINES:  # never cut silently: the lines past the limit could declare
        found.count, found.why = None, "a file it names is not read"
        return
    for _number, line in logical_lines(text):
        if line.startswith("-"):
            found.count, found.why = None, "a file it names is not read"
            return
        found.add(line, main)


# Lock files that hold every group and extra the project declares (each tool locks them all by default); a
# requirements file may be compiled from the main dependencies only, so groups and extras are compared with these
# alone. Pipfile.lock holds every Pipfile category.
FULL_LOCKS = ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile.lock")
TOML_FILES = ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile", "pyproject.toml")


def needs_toml(rel: str) -> bool:
    name = rel.split("/")[-1]
    return name in TOML_FILES or is_pylock(name)


def ancestors(directory: str, project: str):
    """directory, then each directory above it, up to the project directory."""
    while True:
        yield directory
        if directory == project or not directory:
            return
        directory = posixpath.dirname(directory)


def shown_names(names: list) -> str:
    listed = ", ".join(osv.safe(n, NAME_GRAMMAR, "package") for n in names[:3])
    return listed + (f", and {len(names) - 3} more" if len(names) > 3 else "")


def inventory(source, project: str, project_shown: str, budget: Budget | None = None) -> dict:
    """The PyPI inventory of one side (a working tree or a revision, through `source`), in the shape the Java
    resolution gives: modules (one per lock or pin file, each with its nodes and whether it was read whole),
    complete, notes, problem, and the selection text. NotRun when there is nothing Python to read, when a TOML
    file must be read and the interpreter has no tomllib, or past the budget's file limits or deadline.

    Each declaration file is covered by the lock and pin files of its own directory, or else of the nearest
    directory above it (up to the project directory) that holds any, as a uv or Poetry workspace locks its members
    at its root. Covered, its dependencies must be listed there: every main dependency in any of those files, one
    an environment marker narrows included (the remedy then names per-platform pin files), a group's or an extra's
    where a lock file that locks every group is among them."""
    budget = Budget() if budget is None else budget
    files = present(source.paths, project)
    sources = undeclared(source, project, budget)
    if sources:
        return absent_inventory(sources)
    problem = interpreter_problem()
    if problem:  # requirements files, Pipfile.lock (JSON) and setup.cfg need no TOML parser
        files = [rel for rel in files if rel.split("/")[-1] != "pyproject.toml" or declares(source, rel, budget)]
        if any(needs_toml(rel) for rel in files):
            raise osv.NotRun(*problem)
    if not files:
        raise osv.NotRun("no Python dependency file", f"no Python lock, pin or dependency declaration file in "
                                                      f"{project_shown}: name the directory that holds one with "
                                                      "--project-dir")
    problems = Problems()
    modules, lock_names, declared, roots = [], {}, [], {}
    reader = RequirementsReader(source, budget, problems)
    for rel in files:
        kind = kind_of(rel, project)
        name = rel.split("/")[-1]
        if kind == "declaration":
            declared.append(declarations(source, rel, budget, problems))
            continue
        roots.setdefault(group_of(rel), []).append(rel)
        if kind == "requirements":
            reader.read_root(rel)
            continue
        module = new_module(rel, "lock")
        modules.append(module)
        text = read_text(source, rel, budget, problems, "lock file")
        if text is None:
            module["complete"] = module["parsed"] = False
            continue
        entries, why, doc = lock_entries(name, text)
        if entries is None:
            module["complete"] = module["parsed"] = False
            fmt = FORMATS.get(name, "pylock.toml")
            problems.add("lock file not read", f"{osv.safe_path(rel)} cannot be read as a {fmt} lock file ({why}): "
                                               f"regenerate it with the tool that wrote it, then run the audit "
                                               "again", f"module {osv.safe_path(rel)}: not read ({why})")
            continue
        if name == "uv.lock":
            module["uv_own"] = own_packages(doc)
        lock_names[rel] = {normalise_name(e.name) for e in entries if valid_name(e.name)} | module.get("uv_own", set())
        add_entries(module, entries, problems, "lock", budget)
        doc = entries = None  # a lock file's parsed form can be large: dropped before the next is read
    reader.finish()
    modules += [reader.modules[p] for p in sorted(reader.modules)]
    by_id = {m["id"]: m for m in modules}
    uv_owned = {}  # uv.lock path -> its workspace members and own project
    for module in modules:
        uv_own = module.pop("uv_own", None)
        if uv_own is None:
            continue
        uv_owned[module["id"]] = uv_own
        titles = {d.title for d in declared if d.title and group_of(d.rel) == group_of(module["id"])}
        if titles and not uv_own & titles:
            module["complete"] = False
            problems.add("lock file of another project",
                         f"{osv.safe_path(module['id'])} does not hold the project its pyproject.toml names: run "
                         "`uv lock` in the project directory, then run the audit again",
                         f"module {osv.safe_path(module['id'])}: not the lock file of this project")
    uncovered, empty, unread = [], {}, []
    for found in declared:
        if found.count == 0:
            continue
        cover = next((roots[d] for d in ancestors(group_of(found.rel), project) if d in roots), None)
        if cover is None:
            uncovered.append(found.rel)
            continue
        covering = [by_id[r] for r in cover if r not in reader.installs] + \
            [reader.modules[p] for r in cover for p in sorted(reader.installs.get(r, ()))]
        if not any(m["nodes"] for m in covering) and all(m["complete"] for m in covering):
            empty.setdefault(tuple(cover), []).append(found.rel)
            continue
        full = any(r.split("/")[-1] in FULL_LOCKS or is_pylock(r.split("/")[-1]) for r in cover)
        listed = set().union(*(lock_names.get(r, set()) for r in cover), *(reader.root_names(r) for r in cover))
        if found.count is None or found.why is not None:
            # what it declares is not wholly known: a lock tool resolved the declaration itself, so a lock file that
            # locks every group covers the rest, but the names that are known are still compared below; a
            # requirements file was written by hand or from another input
            if not full:
                if found.why not in ("it is not valid TOML", "the file could not be read"):  # those are reported
                    unread.append((found, cover))
                continue
        # the project's own name, and its workspace's, are not dependencies to lock: only the project of the
        # declaration's own directory and the members of the lock file that covers it
        own = {d.title for d in declared if d.title and group_of(d.rel) == group_of(found.rel)}
        own |= set().union(*(uv_owned.get(r, set()) for r in cover))
        missing = sorted((set(found.main) | (found.others if full else set())) - listed - own)
        if missing:
            for r in cover:
                by_id[r]["complete"] = False
            files_shown = osv.named_list([osv.safe_path(r) for r in cover])
            decl = osv.safe_path(found.rel)
            # a main dependency an environment marker narrows is compared too, so a pin file compiled for one
            # platform reads partial for another's dependencies: the remedy says how to cover every platform
            platforms = "" if full or not any(found.main.get(n) for n in missing) else \
                "; a dependency an environment marker narrows needs one pin file per platform or a lock file that " \
                "records every platform"
            problems.add("lock file out of date",
                         f"{decl} declares {len(missing)} {'dependency' if len(missing) == 1 else 'dependencies'} "
                         f"that {files_shown} {'does' if len(cover) == 1 else 'do'} not list: regenerate the lock or "
                         f"pin file ({LOCK_COMMANDS}){platforms}, then run the audit again",
                         f"{decl}: {len(missing)} declared dependencies not in {files_shown}: {shown_names(missing)}")
    for found, cover in unread:
        for r in cover:
            by_id[r]["complete"] = False
        decl = osv.safe_path(found.rel)
        problems.add("declarations not read",
                     f"{decl} declares dependencies this audit cannot read ({found.why}): declare them as literal "
                     f"lists in pyproject.toml or setup.cfg, or commit a lock file ({LOCK_COMMANDS}), then run the "
                     "audit again", f"{decl}: dependencies not read ({found.why}), so not compared with "
                                    f"{osv.named_list([osv.safe_path(r) for r in cover])}")
    if uncovered:
        problems.add("no lock file", f"{osv.named_list([osv.safe_path(p) for p in uncovered])} "
                                     f"{'declares' if len(uncovered) == 1 else 'declare'} dependencies and no lock "
                                     f"or pin file covers them: commit a lock file ({LOCK_COMMANDS}), then run the "
                                     "audit again", f"{osv.named_list([osv.safe_path(p) for p in uncovered])}: "
                                                    "dependencies declared, no lock or pin file")
    for declaring in empty.values():
        problems.add("lock file empty", f"the lock and pin files list no package while "
                                        f"{osv.named_list([osv.safe_path(p) for p in declaring])} "
                                        "declare dependencies: regenerate the lock file, then run the audit again",
                     "the lock and pin files list no package, and dependencies are declared")
    listed_files = [rel for rel in files if kind_of(rel, project) != "declaration"]
    found_files = osv.named_list([osv.safe_path(p) for p in files])
    selection = (f"lock and pin files {osv.named_list([osv.safe_path(p) for p in listed_files])} read as data "
                 f"(no tool runs)" if listed_files else f"{found_files} found, no lock or pin file")
    return {"modules": modules, "complete": problems.first is None, "notes": problems.rendered(),
            "problem": problems.first, "unparsed": [], "tools": [], "selection": selection}


def base_occurrences(modules: list) -> dict:
    """osv.base_occurrences of a base, with each module that was not read whole mapped to None: its candidate
    occurrences are then attribution unknown, and the modules read whole still attribute theirs."""
    found = osv.base_occurrences([m for m in modules if m["complete"]], version_key=version_key)
    found.update({m["id"]: None for m in modules if not m["complete"]})
    return found
