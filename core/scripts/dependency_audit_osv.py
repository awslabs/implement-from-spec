# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
dependency_audit_osv.py — the ecosystem-neutral half of core/scripts/dependency-audit.py: the local copy of an
OSV export and its store, the reduction of OSV records to the facts the audit uses, range and version matching
through the ecosystem's own ordering, the review classes, attribution against the base, and the text and JSON
reports.

Owner: the implement-from-spec plugin. Owns no command and no file of its own: dependency-audit.py loads it by
path (python3 -I keeps this directory off sys.path, so a planted module cannot stand in for it) and passes it
an Ecosystem for each OSV ecosystem it audits: Maven in dependency-audit.py itself, PyPI in
dependency_audit_pypi.py. An Ecosystem names its export, its cache directory, its version ordering, how a
package name is keyed, and how its occurrences, resolution and inventory are worded; nothing here knows a build
tool or a lock file format. The contract every report keeps (status lines, blocks, data line, limits) is the one
dependency-audit.py's header states.

It must stay importable by python3 3.9, the plugin's stated minimum: no syntax newer than 3.9 at module level
(annotations are strings under the __future__ import), and no import of tomllib here.

Usage: not run directly; dependency-audit.py loads it with load_sibling("dependency_audit_osv.py", ...).
"""
from __future__ import annotations

import contextlib
import datetime
import email.utils
import functools
import hashlib
import io
import json
import os
import re
import stat
import struct
import tempfile
import time
import unicodedata
import zipfile

try:
    import fcntl
except ImportError:  # pragma: no cover - not POSIX; the plugin runs on macOS and Linux
    fcntl = None  # type: ignore[assignment]

SCHEMA = "ifs-dependency-audit/1"
DATASET_SCHEMA = "ifs-advisory-dataset/1"
CACHE_SCHEMA = "ifs-advisory-cache/1"
GATE_NAME = "dependency-audit"
USER_AGENT = "implement-from-spec-dependency-audit"

# The advisory store's limits (dependency-audit.py's header documents them). The minimum number of advisories
# is the ecosystem's own (Ecosystem.minimum), a constant with no flag and no environment variable behind it.
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 200_000
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
# Events of one range that are read at all: a range with more is opaque. The OSV PyPI export of 2026-11-25 held at
# most 78 in one range; a hostile record of a few MiB could otherwise hold hundreds of thousands, each compared.
MAX_EVENTS = 1000
# The reports' bounds: a finding lists its advisories, and a PyPI inventory of many pins could make a report of
# gigabytes that a review then reads (2,000 pins of one package gave 74 MB). The text report lists at most
# MAX_TEXT_ADVISORIES per entry and MAX_TEXT_OCCURRENCES per block, the JSON report MAX_JSON_ADVISORIES and
# MAX_JSON_OCCURRENCES, each cut said in the report; the counts and the status are always of everything.
MAX_TEXT_ADVISORIES = 10
MAX_TEXT_OCCURRENCES = 500
MAX_JSON_ADVISORIES = 100
MAX_JSON_OCCURRENCES = 5000
MATCH_CHECK_EVERY = 64  # occurrences matched between two checks of the deadline
ENTRY_CHECK_EVERY = 256  # advisory entries of one package scanned between two checks of the deadline
FRESH_SECONDS = 24 * 3600
USABLE_SECONDS = 7 * 24 * 3600
DOWNLOAD_DEADLINE_SECONDS = 120
SOCKET_TIMEOUT_SECONDS = 30
LOCK_WAIT_SECONDS = DOWNLOAD_DEADLINE_SECONDS + 30


class Stop(Exception):
    """A typed stop: exit code and message."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotRun(Exception):
    """The audit could not run: a category and the one action that remedies it."""

    def __init__(self, category: str, remedy: str) -> None:
        super().__init__(f"{category}: {remedy}")
        self.category = category
        self.remedy = remedy


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


MIB = 1024 * 1024


def mib(size: int) -> str:
    """A size for a message, in MiB: at most one decimal from 1 MiB up, six below it."""
    value = size / MIB
    return (f"{value:.1f}" if value >= 1 else f"{value:.6f}").rstrip("0").rstrip(".") + " MiB"


# ---------------------------------------------------------------- what may appear in a report
# A report is read by a model, so nothing reaches it that an advisory, a build file, a lock file or the build
# tool could word freely. A value is printed only when it passes its grammar; one that does not is replaced by a
# digest of itself. Paths, which no grammar can cover, are escaped and capped instead.
UNSAFE_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]")


class _AdvisoryIdGrammar:
    """An advisory id (GHSA-xxxx-xxxx-xxxx, CVE-2024-1234, PYSEC-2021-1): a prefix of a letter and up to 15
    letters or digits, then one to six parts of one to 32 letters or digits, each after a dash. Checked by
    splitting at the dashes rather than with one regex whose quantified group holds a quantifier, so no
    input can make the check backtrack; match() is the regex interface the callers use."""
    PREFIX = re.compile(r"[A-Za-z][A-Za-z0-9]{0,15}")
    PART = re.compile(r"[A-Za-z0-9]{1,32}")

    def match(self, value) -> bool:
        parts = value.split("-") if isinstance(value, str) else []
        return 2 <= len(parts) <= 7 and bool(self.PREFIX.fullmatch(parts[0])) and \
            all(self.PART.fullmatch(part) for part in parts[1:])


ID_GRAMMAR = _AdvisoryIdGrammar()
# The report grammars end in \Z, never $: with .match, "$" also matches before a final newline, so "dev\n" would
# pass as a word and carry a line break into a report.
HEX_RE = re.compile(r"^[0-9a-f]{40,64}\Z")
PLAIN_PATH_RE = re.compile(r"^[A-Za-z0-9_./+@-]{1,240}\Z")
WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")  # a scope, a type, a classifier, a configuration, a group
SEVERITY_WORDS = ("CRITICAL", "HIGH", "MODERATE", "MEDIUM", "LOW")
MAX_SHOWN = 240
MAX_NAMED = 3  # values a not-run line names, before "and N more"


def shown(text) -> str:
    """text for a report line: every UNSAFE_RE character as \\n, \\t, \\xNN or \\uNNNN, a backslash doubled
    first, and capped, so a path cannot start a line of its own or reorder the text."""
    named = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

    def esc(m):
        ch = m.group(0)
        return named.get(ch) or ("\\x%02x" % ord(ch) if ord(ch) < 0x100 else "\\u%04x" % ord(ch))
    out = UNSAFE_RE.sub(esc, str(text).replace("\\", "\\\\"))
    return out if len(out) <= MAX_SHOWN else out[:MAX_SHOWN] + "..."


def withheld(kind: str, value) -> str:
    digest = sha256(str(value).encode("utf-8", "surrogatepass"))[:12]
    return f"({kind} withheld, sha256 {digest})"


def safe(value, pattern, kind: str) -> str:
    """value when it passes its grammar, else a placeholder naming what was withheld and its digest."""
    return value if isinstance(value, str) and pattern.match(value) else withheld(kind, value)


def safe_path(path: str) -> str:
    """A repository-relative path for a report: as it is when plain, else withheld (a directory can be named
    like an instruction)."""
    return path if isinstance(path, str) and PLAIN_PATH_RE.match(path) else withheld("path", path)


def iso_date(seconds) -> str:
    """The UTC date of a timestamp, 'unknown' when there is none."""
    try:
        return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):  # no timestamp, or one no calendar holds
        return "unknown"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\Z")


def safe_date(value) -> str:
    return value if isinstance(value, str) and DATE_RE.match(value) else "unknown"


def named_list(values: list) -> str:
    """Values for a not-run line: the first MAX_NAMED, cut short at MAX_SHOWN characters, then how many more."""
    unique = list(dict.fromkeys(values))
    shown_values: list = []
    for value in unique[:MAX_NAMED]:
        if shown_values and len(", ".join(shown_values + [value])) > MAX_SHOWN:
            break
        shown_values.append(value)
    rest = len(unique) - len(shown_values)
    return ", ".join(shown_values) + (f" and {rest} more" if rest else "")


def time_limit_remedy(what: str) -> str:
    """The remedy of a time limit, naming both limits: a run is cut at the smaller of its own limit and what is
    left of the audit's."""
    return (f"{what}: raise --timeout, the limit of each build-tool run, or --total-timeout, the limit of the whole "
            "audit")


# ---------------------------------------------------------------- paths and their identity
def inside(path: str, root: str) -> bool:
    """Whether path is root or lies below it, for every name of either: on a volume that ignores letter case or
    Unicode normalisation /p/Repo and /p/repo are one directory, which comparing strings would miss. Both are
    resolved first; then each existing component of path, from the deepest up, is compared by identity (lstat's
    st_dev and st_ino, never following a link) with root, or, for a root not created yet, with its deepest
    existing directory, below which the names must match root's in letter case and normalisation folded (fold),
    as they would on a volume that ignores both. So a component that is root under another spelling makes path
    inside, and so does a new file below it. What cannot be read counts as inside, since every caller refuses
    what is inside: an lstat that fails for any reason but a missing name, and a link among the resolved
    components (the path changed after it was resolved)."""
    try:
        real, base = os.path.realpath(path), os.path.realpath(root)
        if real == base or real.startswith(base.rstrip(os.sep) + os.sep):
            return True
        anchor, missing = existing_prefix(base)
        if anchor is None:
            return True
        target = os.lstat(anchor)
        if stat.S_ISLNK(target.st_mode):
            return True
        names = [part for part in real.split(os.sep) if part]
        for depth in range(len(names), -1, -1):
            try:
                st = os.lstat(os.sep + os.sep.join(names[:depth]))
            except (FileNotFoundError, NotADirectoryError):
                continue  # not created yet: a directory above it decides
            if stat.S_ISLNK(st.st_mode):
                return True
            if (st.st_dev, st.st_ino) == (target.st_dev, target.st_ino):
                below = names[depth:depth + len(missing)]
                return len(below) == len(missing) and all(fold(a) == fold(b) for a, b in zip(below, missing))
        return False
    except (OSError, ValueError):
        return True


def existing_prefix(path: str) -> tuple:
    """(the deepest existing directory at or above the absolute path, the names below it), or (None, []) when
    that cannot be read: an lstat that fails for any reason but a missing name."""
    names = [part for part in path.split(os.sep) if part]
    for depth in range(len(names), -1, -1):
        prefix = os.sep + os.sep.join(names[:depth])
        try:
            os.lstat(prefix)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except (OSError, ValueError):
            return None, []
        return prefix, names[depth:]
    return None, []


def fold(name: str) -> str:
    """name as a volume that ignores letter case and Unicode normalisation compares it: the Unicode canonical
    caseless match, "NFD(toCasefold(NFD(X))) = NFD(toCasefold(NFD(Y)))" (The Unicode Standard, section 3.13,
    D145, read 2026-11-24), with format characters (Unicode category Cf) dropped first, since HFS+ skips some of
    them when it compares names."""
    if name.isascii():
        return name.lower()
    visible = "".join(ch for ch in name if unicodedata.category(ch) != "Cf")
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", visible).casefold())


def nfd(name: str) -> str:
    return unicodedata.normalize("NFD", name)


def name_rules(directory: str) -> tuple:
    """(case, normalisation): whether the file system under `directory` takes two names that differ only in
    letter case (only in Unicode normalisation form) for one; True, False, or None when that cannot be
    established. The volume itself is asked: a directory is created there under a name with a letter of each
    kind, looked up under its other spellings and removed again, so the answer holds for an empty directory,
    whatever the operating system."""
    try:
        probe = tempfile.mkdtemp(prefix=".ifs-name-probe-\u00e9-", dir=directory)
    except (OSError, ValueError, UnicodeError):
        return None, None
    try:
        head, name = os.path.split(probe)
        return (one_name(probe, os.path.join(head, name.swapcase())),
                one_name(probe, os.path.join(head, nfd(name))))
    finally:
        with contextlib.suppress(OSError):
            os.rmdir(probe)


def one_name(path: str, other: str):
    """Whether `other` names the directory `path`: True or False, None when that cannot be read. A directory
    has one name only (no hard link reaches one), so the same identity under both shows the volume took the
    two spellings for one."""
    try:
        here = os.lstat(path)
    except (OSError, ValueError):
        return None
    try:
        there = os.lstat(other)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return None
    return (here.st_dev, here.st_ino) == (there.st_dev, there.st_ino)


INPUT_LIMIT = 16 * MIB  # the most of one resolution input (a build file, a lock file) that is read


def read_small(path: str, limit: int = INPUT_LIMIT):
    """The bytes of a regular file, None when it is absent, a link, special or over `limit`: opened without
    following a link or blocking on a special file, and checked on the descriptor that is read."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            return None
        data = fh.read(limit + 1)
    return data if len(data) <= limit else None


def file_sha256(path: str):
    """The sha256 of a regular file of any size, read in pieces; None when it is a link, special or unreadable."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            return None
        digest = hashlib.sha256()
        try:
            for piece in iter(lambda: fh.read(1 << 20), b""):
                digest.update(piece)
        except OSError:
            return None
    return digest.hexdigest()


# ---------------------------------------------------------------- an ecosystem
class Ecosystem:
    """One OSV ecosystem as the audit reads it. Every field is a constant of the ecosystem, set once where it is
    defined (MAVEN in dependency-audit.py, PYPI in dependency_audit_pypi.py):

    name              the OSV ecosystem name, also the key of ECOSYSTEMS and the word reports name it by
    accepts           whether an `affected` entry's package.ecosystem belongs to it ("Maven" and "Maven:<repo>")
    export_url        the one fixed HTTPS URL of its OSV export
    cache_subdir      its directory below the advisory cache, "" for the cache itself (Maven, the first one)
    minimum           the fewest usable advisories a dataset may hold
    label, attribution  the Data line's words for the export and its sources' licences
    compare(a, b)     -1, 0 or 1 in the ecosystem's version ordering, for two versions `parses` accepts
    parses(v)         whether `compare` can place v; a bound it cannot place makes the range opaque
    version_key(v)    the form compared with an advisory's enumerated versions (equal versions, equal keys)
    package_key(n)    the form a package name is indexed by (PyPI names normalised, Maven coordinates as they are)
    forms(v)          the versions an inventory version is matched as (a PyPI local version also as its public one)
    merge_aliases     whether advisories of one occurrence that are aliases of each other are reported as one
    severity_fill     whether a record without a severity word takes one from an aliased GHSA record of the
                      dataset, or else from its CVSS v3 base score (PYSEC records carry no word)
    unsure_version(v) whether every match of the inventory version v is unsure (a PyPI local version)
    occurrence        (module, node, advisories, fix, fix_checked) -> one report entry, every value checked
    resolution_line, inventory_line   (resolution or None) -> the report's Resolution and Inventory lines
    refresh_command   the refresh command a cache remedy names ("refresh --ecosystem pypi")
    refresh_remedy    the remedy of missing or too old advisory data
    separator         what a report line puts between a package and its version (":" by default, "==" for PyPI)
    matcher           a version of `parses`, `compare` and `version_key`, recorded with a dataset it built: a cache
                      built by another one reads as empty, so the next refresh rebuilds it (None: not recorded)
    """

    def __init__(self, **fields) -> None:
        defaults = {"cache_subdir": "", "parses": lambda version: True, "version_key": lambda version: version,
                    "package_key": lambda name: name, "forms": lambda version: (version,), "merge_aliases": False,
                    "severity_fill": False, "unsure_version": lambda version: False,
                    "separator": ":", "matcher": None}
        for key, value in dict(defaults, **fields).items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"Ecosystem({self.name})"


ECOSYSTEMS: dict = {}  # name -> Ecosystem, filled by register()


def register(ecosystem: Ecosystem) -> Ecosystem:
    ECOSYSTEMS[ecosystem.name] = ecosystem
    return ecosystem


# The ecosystem of a record or report entry with no "ecosystem" key: the first one the audit had, whose reports
# are kept byte for byte as they were before a second ecosystem existed.
UNNAMED_ECOSYSTEM = "Maven"


def ecosystem_of(record) -> Ecosystem:
    """The ecosystem a data or resolution record belongs to: its "ecosystem" key, else UNNAMED_ECOSYSTEM."""
    name = record.get("ecosystem", UNNAMED_ECOSYSTEM) if isinstance(record, dict) else UNNAMED_ECOSYSTEM
    return ECOSYSTEMS[name]


# ---------------------------------------------------------------- the advisory dataset and its index
EVENT_KINDS = ("introduced", "fixed", "last_affected", "limit")
# The range type whose versions the ecosystem's ordering compares. A SEMVER range is ordered by SemVer 2.0.0,
# whose rules differ from Maven's and from PEP 440 (build metadata, pre-release identifiers), so it is not
# evaluated: its entry is opaque.
VERSIONED_RANGES = ("ECOSYSTEM",)


class DataError(Exception):
    """The advisory data is not what the export holds: nothing is published from it."""


def normalise_entry(affected, ecosystem: Ecosystem) -> dict | None:
    """One `affected` entry of the ecosystem as the matcher reads it, None for another ecosystem. `opaque` marks
    an entry holding something the matcher does not understand (a range type, an event, a bound the ordering
    cannot place, no version information at all): it can still match by what was understood, and otherwise is
    reported, never dropped."""
    package = affected.get("package") if isinstance(affected, dict) else None
    name_of = package.get("ecosystem") if isinstance(package, dict) else None
    if not isinstance(name_of, str) or not ecosystem.accepts(name_of):
        return None
    name = package.get("name")
    if not isinstance(name, str) or not name:
        raise DataError(f"a {ecosystem.name} entry without a package name")
    opaque = False
    versions = affected.get("versions") or []
    if not isinstance(versions, list) or not all(isinstance(v, str) for v in versions):
        versions, opaque = [], True
    ranges = []
    listed = affected.get("ranges") or []
    if not isinstance(listed, list):
        listed, opaque = [], True
    for rng in listed:
        kind = rng.get("type") if isinstance(rng, dict) else None
        if kind == "GIT":
            continue  # commits, not versions: says nothing the matcher could use or get wrong
        events = rng.get("events") if isinstance(rng, dict) else None
        pairs = []
        if kind in VERSIONED_RANGES and isinstance(events, list) and len(events) <= MAX_EVENTS:
            for event in events:
                if isinstance(event, dict) and len(event) == 1:
                    (key, bound), = event.items()
                    if key in EVENT_KINDS and isinstance(bound, str) and bound and \
                            ((key == "introduced" and bound == "0") or ecosystem.parses(bound)):
                        pairs.append([key, bound])
                        continue
                pairs = None
                break
        if not pairs or not well_formed(pairs, ecosystem):
            opaque = True
            continue
        ranges.append(pairs)
    if not versions and not ranges:
        opaque = True
    return {"package": ecosystem.package_key(name), "versions": [ecosystem.version_key(v) for v in versions],
            "ranges": ranges, "opaque": opaque}


def well_formed(pairs: list, ecosystem: Ecosystem) -> bool:
    """Whether a range's events can be read one way only: at least one introduced, fixed or last_affected but
    not both (OSV schema, ossf.github.io/osv-schema, read 2026-11-24), and no two events of different kinds at
    versions the ordering takes as equal, whose order would then be the record's order and not the versions'."""
    kinds = {key for key, _bound in pairs}
    if "introduced" not in kinds or {"fixed", "last_affected"} <= kinds or len(pairs) > MAX_EVENTS:
        return False
    # Sorted once, events the ordering takes as equal are neighbours, so comparing each with the next finds every
    # such pair in O(n log n) comparisons; comparing every pair was quadratic in a record's events.
    ordered = sorted(pairs, key=functools.cmp_to_key(lambda a, b: _event_order(a, b, ecosystem)))
    return not any(a[0] != b[0] and _event_order(a, b, ecosystem) == 0 for a, b in zip(ordered, ordered[1:]))


def normalise_record(raw, ecosystem: Ecosystem) -> dict | None:
    """One OSV record reduced to the facts the audit uses (no summary, details or references are kept, so no
    advisory text is even stored); None for a withdrawn record or one with no entry of the ecosystem."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
        raise DataError("a record without an id")
    if raw.get("withdrawn"):
        return None
    affected = raw.get("affected") or []
    if not isinstance(affected, list):
        raise DataError(f"record {raw['id'][:40]!r}: affected is not a list")
    entries = [e for e in (normalise_entry(a, ecosystem) for a in affected) if e is not None]
    if not entries:
        return None
    specific = raw.get("database_specific")
    word = specific.get("severity") if isinstance(specific, dict) else None
    word = word.upper() if isinstance(word, str) and word.upper() in SEVERITY_WORDS else ""
    aliases = raw.get("aliases") or []
    aliases = sorted({a for a in aliases if isinstance(a, str)}) if isinstance(aliases, list) else []
    modified = raw.get("modified") if isinstance(raw.get("modified"), str) else ""
    record = {"id": raw["id"], "aliases": aliases, "severity": word, "modified": modified, "affected": entries}
    if ecosystem.severity_fill and not word:
        vector = cvss_vector(raw.get("severity"))
        if vector:
            record["cvss"] = vector
    return record


# ---------------------------------------------------------------- a severity word for a record without one
# CVSS v3.1 base score, as the FIRST specification defines it (https://www.first.org/cvss/v3.1/specification-document,
# read 2026-11-25): section 7.1's equations, Table 16's metric values, Appendix A's Roundup, and section 5's
# qualitative rating scale (Low 0.1-3.9, Medium 4.0-6.9, High 7.0-8.9, Critical 9.0-10.0). A 3.0 vector is
# scored the same way: the base equations are those of 3.1, which changed the rounding only. A CVSS v4 vector
# is not scored, so a record with only that keeps no word.
CVSS_WEIGHTS = {"AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}, "AC": {"L": 0.77, "H": 0.44},
                "PR": {"N": 0.85, "L": 0.62, "H": 0.27}, "UI": {"N": 0.85, "R": 0.62},
                "S": {"U": None, "C": None}, "C": {"H": 0.56, "L": 0.22, "N": 0.0},
                "I": {"H": 0.56, "L": 0.22, "N": 0.0}, "A": {"H": 0.56, "L": 0.22, "N": 0.0}}
CVSS_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
CVSS_OPTIONAL = frozenset(("E", "RL", "RC", "CR", "IR", "AR", "MAV", "MAC", "MPR", "MUI", "MS", "MC", "MI", "MA"))


def cvss_vector(listed):
    """The first CVSS v3 vector of a record's severity list that cvss_base_score can score, else None."""
    for item in listed if isinstance(listed, list) else []:
        score = item.get("score") if isinstance(item, dict) and item.get("type") == "CVSS_V3" else None
        if isinstance(score, str) and len(score) <= 200 and cvss_base_score(score) is not None:
            return score
    return None


def cvss_base_score(vector: str):
    """The CVSS v3 base score of a vector string, None when it is not one: the CVSS:3.0/ or CVSS:3.1/ label,
    then every base metric exactly once with a value of Table 16 ("A vector string must not include the same
    metric more than once"), in any order, and temporal or environmental metrics, which do not change the base
    score, allowed and ignored."""
    if not isinstance(vector, str) or not vector.startswith(("CVSS:3.0/", "CVSS:3.1/")):
        return None
    values: dict = {}
    for part in vector[len("CVSS:3.x/"):].split("/"):
        metric, sep, value = part.partition(":")
        if not sep or metric in values:
            return None
        if metric in CVSS_WEIGHTS:
            if value not in CVSS_WEIGHTS[metric]:
                return None
        elif metric not in CVSS_OPTIONAL:
            return None
        values[metric] = value
    if any(metric not in values for metric in CVSS_WEIGHTS):
        return None
    changed = values["S"] == "C"
    weight = {m: CVSS_WEIGHTS[m][values[m]] for m in ("AV", "AC", "UI", "C", "I", "A")}
    privileges = (CVSS_PR_CHANGED if changed else CVSS_WEIGHTS["PR"])[values["PR"]]
    iss = 1 - (1 - weight["C"]) * (1 - weight["I"]) * (1 - weight["A"])
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    exploitability = 8.22 * weight["AV"] * weight["AC"] * privileges * weight["UI"]
    if impact <= 0:
        return 0.0
    return cvss_roundup(min((1.08 if changed else 1.0) * (impact + exploitability), 10))


def cvss_roundup(value: float) -> float:
    """Appendix A's Roundup, in integer arithmetic: the smallest number with one decimal at or above value."""
    whole = round(value * 100000)
    if whole % 10000 == 0:
        return whole / 100000.0
    return (whole // 10000 + 1) / 10.0


def cvss_word(score: float) -> str:
    """Section 5's rating of a base score, as one of SEVERITY_WORDS; a score of 0.0 ("None") reads as LOW, the
    lowest word a record can have, so it is a Minor and never dropped."""
    return "CRITICAL" if score >= 9.0 else "HIGH" if score >= 7.0 else "MEDIUM" if score >= 4.0 else "LOW"


def fill_severity(advisories: list) -> None:
    """Gives each record without a severity word one: from the GHSA records of the dataset it is an alias of (it
    names one, one names it, or both name one alias), the strongest of their words, else from its CVSS v3 base
    score; `severity_from` says which. A record with neither keeps no word and is classed Major unsure."""
    rank = {word: n for n, word in enumerate(SEVERITY_WORDS)}
    by_name: dict = {}
    for advisory in advisories:
        if advisory["id"].startswith("GHSA-") and advisory["severity"]:
            for name in (advisory["id"], *advisory["aliases"]):
                by_name.setdefault(name, []).append(advisory)
    for advisory in advisories:
        vector = advisory.pop("cvss", None)
        if advisory["severity"]:
            continue
        linked = {id(a): a for name in (advisory["id"], *advisory["aliases"]) for a in by_name.get(name, ())}
        if linked:
            best = min(linked.values(), key=lambda a: (rank[a["severity"]], a["id"]))
            advisory["severity"], advisory["severity_from"] = best["severity"], best["id"]
        elif vector:
            score = cvss_base_score(vector)
            advisory["severity"], advisory["severity_from"] = cvss_word(score), f"CVSS {vector[5:8]} {score:.1f}"


def build_dataset(records, ecosystem: Ecosystem, minimum=None) -> dict:
    """The dataset of an iterable of parsed OSV records; DataError when it holds fewer than `minimum` (the
    ecosystem's own by default) usable advisories, or two different records under one id (which one is current
    cannot be told, and keeping either could drop an affected range or a withdrawal); a record repeated byte for
    byte is read once. `minimum` is an argument for the unit tests only: no command passes one. A dataset of an
    ecosystem other than Maven names it, so the store refuses one published under the other's directory; a Maven
    dataset keeps the form it had before a second ecosystem existed, so its digest does not change."""
    minimum = ecosystem.minimum if minimum is None else minimum
    advisories, withdrawn, seen = [], 0, {}
    for raw in records:
        record = normalise_record(raw, ecosystem)
        digest = sha256(json.dumps(raw, sort_keys=True, ensure_ascii=True).encode("ascii"))
        if raw["id"] in seen:
            if seen[raw["id"]] != digest:
                raise DataError(f"two different records with the id {shown(raw['id'][:40])}")
            continue
        seen[raw["id"]] = digest
        if raw.get("withdrawn"):
            withdrawn += 1
        if record is not None:
            advisories.append(record)
    if len(advisories) < minimum:
        raise DataError(f"{len(advisories)} usable advisories, fewer than the minimum of {minimum}")
    advisories.sort(key=lambda r: r["id"])
    if ecosystem.severity_fill:
        fill_severity(advisories)
    dataset = {"schema": DATASET_SCHEMA, "advisories": advisories, "withdrawn": withdrawn}
    if ecosystem.name != UNNAMED_ECOSYSTEM:
        dataset["ecosystem"] = ecosystem.name
    return dataset


def dataset_bytes(dataset: dict) -> bytes:
    """Canonical, so one export gives one digest on every machine."""
    return json.dumps(dataset, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def newest_modified(dataset: dict) -> str:
    return max((r["modified"] for r in dataset["advisories"]), default="")


class Index:
    """The dataset by package key: every affected entry kept apart, with the advisory it belongs to."""

    def __init__(self, dataset: dict, ecosystem: Ecosystem) -> None:
        self.ecosystem = ecosystem
        self.count = len(dataset["advisories"])
        self.by_package: dict = {}
        for advisory in dataset["advisories"]:
            for entry in advisory["affected"]:
                self.by_package.setdefault(entry["package"], []).append((advisory, entry))

    def entries(self, package: str) -> list:
        return self.by_package.get(self.ecosystem.package_key(package), [])


# ---------------------------------------------------------------- matching and the reported fix
def _event_order(a: list, b: list, ecosystem: Ecosystem) -> int:
    # "0" is OSV's word for "from the first version", whatever the ecosystem's ordering makes of it.
    if (a[0] == "introduced" and a[1] == "0") != (b[0] == "introduced" and b[1] == "0"):
        return -1 if a[1] == "0" and a[0] == "introduced" else 1
    return ecosystem.compare(a[1], b[1])


def range_state(events: list, version: str, ecosystem: Ecosystem) -> tuple:
    """(affected, fix): whether `version` lies inside the range, and the fixed event that closes the interval
    it lies in. limit is an exclusive upper bound like fixed, but names no fix."""
    affected, fix = False, None
    order_of = functools.cmp_to_key(lambda a, b: _event_order(a, b, ecosystem))
    for kind, bound in sorted(events, key=order_of):
        order = 1 if (kind == "introduced" and bound == "0") else ecosystem.compare(version, bound)
        if kind == "introduced":
            if order >= 0:
                affected, fix = True, None
        elif kind == "last_affected":
            if order > 0:
                affected = False
        elif order >= 0:
            affected = False
        elif affected and fix is None and kind == "fixed":
            fix = bound
    return affected, fix


def match_entry(entry: dict, version: str, ecosystem: Ecosystem) -> tuple:
    """(basis, fix) of `version` against one affected entry: basis is 'range', 'enumerated version', 'both',
    'not evaluable' (nothing understood matched, and the entry holds something that was not understood, or the
    version is one the ordering cannot place while the entry has ranges) or None; fix is the highest fixed event
    closing a matching range. Each of the version's forms (ecosystem.forms) is matched, and a match by any of
    them counts."""
    listed = in_range = False
    fix = None
    placeable = True
    for form in ecosystem.forms(version):
        listed = listed or ecosystem.version_key(form) in entry["versions"]
        if not ecosystem.parses(form):
            placeable = False
            continue
        for events in entry["ranges"]:
            hit, bound = range_state(events, form, ecosystem)
            if hit:
                in_range = True
                if bound is not None and (fix is None or ecosystem.compare(bound, fix) > 0):
                    fix = bound
    if listed or in_range:
        return ("both" if listed and in_range else "range" if in_range else "enumerated version"), fix
    if entry["opaque"] or (not placeable and entry["ranges"]):
        return "not evaluable", None
    return None, None


def reported_fix(entries: list, version: str, start, ecosystem: Ecosystem, deadline=None) -> tuple:
    """(fix, checked) to report for a package: `start` (the highest fixed event of the ranges that matched)
    matched again against every entry for the package, moving up to a later fixed event while it is still
    affected. fix is None when the data names no version that is unaffected; checked is False when an entry
    for the package could not be evaluated at the fix, which then is the advisories' word only."""
    compare = ecosystem.compare
    later = [] if not ecosystem.parses(version) else \
        sorted({bound for _adv, entry in entries for events in entry["ranges"] for kind, bound in events
                if kind == "fixed" and compare(bound, version) > 0}, key=functools.cmp_to_key(compare))
    candidate = start
    for _ in range(len(later) + 1):
        check_deadline(deadline)
        if candidate is None:
            return None, True
        hits = []
        for count, (_adv, entry) in enumerate(entries):
            if count % ENTRY_CHECK_EVERY == 0 and count:
                check_deadline(deadline)
            hits.append(match_entry(entry, candidate, ecosystem))
        opaque = any(basis == "not evaluable" for basis, _fix in hits)
        hits = [(basis, fix) for basis, fix in hits if basis not in (None, "not evaluable")]
        if not hits:
            return candidate, not opaque
        closing = [fix for _basis, fix in hits if fix is not None]
        above = [v for v in later if compare(v, candidate) > 0]
        candidate = max(closing, key=functools.cmp_to_key(compare)) if closing else \
            above[0] if above else None
    return None, True


def review_class(advisory: dict, basis: str) -> tuple:
    """(class, unsure) of one match: the GitHub severity word decides; a malicious-package record is a
    Blocker; an unknown word, and an entry that could not be evaluated, are Major and unsure, so doubt never
    lowers a class."""
    if basis == "not evaluable":
        return "Major", True
    if advisory["id"].startswith("MAL-"):
        return "Blocker", False
    word = advisory["severity"]
    if word in ("CRITICAL", "HIGH"):
        return "Blocker", False
    if word in ("MODERATE", "MEDIUM"):
        return "Major", False
    if word == "LOW":
        return "Minor", False
    return "Major", True


CLASS_ORDER = {"Blocker": 0, "Major": 1, "Minor": 2}


def advisory_entries(advisories: list) -> list:
    """The advisories of one report entry, each id and alias passed through the id grammar, at most three
    aliases shown."""
    entries = []
    for a in advisories:
        entry = {"id": safe(a["id"], ID_GRAMMAR, "advisory id"),
                 "aliases": [alias for alias in a["aliases"] if ID_GRAMMAR.match(alias)][:3],
                 "severity": a["severity"], "class": a["class"], "unsure": a["unsure"], "basis": a["basis"]}
        if a.get("severity_from"):  # only a record whose word was taken or scored (severity_fill) has one
            entry["severity_from"] = safe(a["severity_from"], SEVERITY_FROM, "severity source")
        entries.append(entry)
    return entries


class _SeverityFrom:
    """What a taken or scored severity word came from: an advisory id, or "CVSS 3.1 7.5"."""
    SCORE = re.compile(r"CVSS 3\.[01] (10|[0-9])\.[0-9]")

    def match(self, value) -> bool:
        return isinstance(value, str) and (ID_GRAMMAR.match(value) or bool(self.SCORE.fullmatch(value)))


SEVERITY_FROM = _SeverityFrom()


def merge_aliases(found: list) -> list:
    """The matches of one occurrence with every set of advisories that are aliases of each other reported as one.
    OSV calls two records aliases when "they affect any given software component the same way" (OSV schema,
    aliases, read 2026-11-25), and the PyPI export carries most vulnerabilities twice, as a PYSEC record with no
    severity word and as the GHSA record of the same vulnerability with one, so reported apart each would be a
    Major unsure that the other's word contradicts. Records are linked when one names the other in its aliases or
    both name one alias. The set takes its class from its members whose class is sure (the strongest of them),
    and is unsure only when none is; a malicious-package record is a Blocker in any set. The shown id is the
    member that decided the class, the others become its first aliases, and an accepted id or alias of any
    member accepts the set. A word the record carries, or one taken from an aliased GHSA record, outranks one
    scored from a CVSS vector (source_rank); within one rank the strongest class decides."""
    parent = list(range(len(found)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner: dict = {}
    for i, advisory in enumerate(found):
        for name in (advisory["id"], *advisory["aliases"]):
            j = owner.setdefault(name, i)
            if root(j) != root(i):
                parent[root(i)] = root(j)
    groups: dict = {}
    for i, advisory in enumerate(found):
        groups.setdefault(root(i), []).append(advisory)
    merged = []
    for members in groups.values():
        if len(members) == 1:
            merged.append(members[0])
            continue
        sure = [m for m in members if not m["unsure"]]
        best = min((source_rank(m) for m in sure), default=None)
        pool = [m for m in sure if source_rank(m) == best] or members
        lead = min(pool, key=lambda m: (CLASS_ORDER[m["class"]], m["id"]))
        bases = {m["basis"] for m in members if m["basis"] != "not evaluable"}
        basis = "both" if "both" in bases or len(bases) > 1 else (bases.pop() if bases else "not evaluable")
        others = sorted(m["id"] for m in members if m is not lead)
        names = sorted({a for m in members for a in m["aliases"]} - {lead["id"], *others})
        merged.append(dict(lead, aliases=others + names, basis=basis, unsure=not sure))
    return merged


def source_rank(match: dict) -> int:
    """Which class of an alias set decides: a record's own severity word (a GHSA record's), then one taken from
    an aliased GHSA record, then one scored from a CVSS vector, then a malicious-package record's Blocker."""
    origin = match.get("severity_from") or ""
    if match["id"].startswith("MAL-"):
        return 0
    return 2 if origin.startswith("CVSS ") else 1 if origin else 0


def check_deadline(deadline) -> None:
    """NotRun (time limit) once `deadline` (time.monotonic()) has passed; None means no limit."""
    if deadline is not None and time.monotonic() > deadline:
        raise NotRun("time limit", time_limit_remedy("the audit reached its total limit while it matched the "
                                                     "dependencies against the advisory data"))


def match_package(index: Index, package: str, version: str, deadline=None) -> dict:
    """Every advisory matching `package` at `version`, one per advisory id (its strongest basis), aliases of
    each other merged where the ecosystem asks for it, and the fix to report for the package. `deadline` is
    checked while the fix is sought, whose steps a dataset of chained ranges can make many."""
    ecosystem = index.ecosystem
    entries = index.entries(package)
    found: dict = {}
    start = None
    for count, (advisory, entry) in enumerate(entries):
        if count % ENTRY_CHECK_EVERY == 0:  # a hostile dataset can give one package many entries of many ranges
            check_deadline(deadline)
        basis, fix = match_entry(entry, version, ecosystem)
        if basis is None:
            continue
        if fix is not None and (start is None or ecosystem.compare(fix, start) > 0):
            start = fix
        known = found.get(advisory["id"])
        if known is None or known["basis"] == "not evaluable":
            cls, unsure = review_class(advisory, basis)
            found[advisory["id"]] = {"id": advisory["id"], "aliases": advisory["aliases"],
                                     "severity": advisory["severity"] or "UNKNOWN", "class": cls,
                                     "unsure": unsure, "basis": basis}
            if advisory.get("severity_from"):
                found[advisory["id"]]["severity_from"] = advisory["severity_from"]
        elif basis != "not evaluable" and known["basis"] != basis:
            known["basis"] = "both"
    listed = list(found.values())
    if ecosystem.merge_aliases:
        listed = merge_aliases(listed)
    if listed and ecosystem.unsure_version(version):
        listed = [dict(a, unsure=True) for a in listed]
    advisories = sorted(listed, key=lambda a: (CLASS_ORDER[a["class"]], a["id"]))
    fix, checked = reported_fix(entries, version, start, ecosystem, deadline) if advisories else (None, True)
    return {"advisories": advisories, "fix": fix, "fix_checked": checked}


# ---------------------------------------------------------------- the advisory store
class FetchError(Exception):
    """The download did not give a usable answer."""


class RefreshFailed(Exception):
    """A refresh or import that published nothing; the dataset published before it is untouched."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def state_home() -> str:
    """The plugin's state directory, located from HOME alone: CLAUDE_PLUGIN_DATA and XDG_STATE_HOME are two
    more variables a repository's settings could point at a directory it controls."""
    return os.path.join(os.path.expanduser("~"), ".local", "state", "implement-from-spec")


def default_cache_dir() -> str:
    return os.path.join(state_home(), "advisories")


def cache_dir(ecosystem: Ecosystem) -> str:
    """The ecosystem's advisory cache: the cache itself for Maven, a directory below it for another, so the gate's
    protection of the cache covers every ecosystem's data."""
    base = default_cache_dir()
    return os.path.join(base, ecosystem.cache_subdir) if ecosystem.cache_subdir else base


def then_run(what: str) -> str:
    """The command a state-entry remedy ends with: refresh for the advisory cache, the audit otherwise."""
    return "run refresh" if what == "advisory cache" else "run the audit again"


def check_owned(path: str, directory: bool, what: str = "advisory cache") -> None:
    """A state entry (the advisory cache, the build output directory) must be the user's own, writable by no
    one else, never a link, and a file has one name only: anyone else who could write it could plant advisory
    data or read the build output, and a second name is a way in that this path's checks do not see."""
    check_stat(os.lstat(path), path, directory, what)


def check_stat(st, path: str, directory: bool, what: str) -> None:
    then = then_run(what)
    kind_ok = stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)
    if not kind_ok:
        kind = "directory" if directory else "regular file"
        raise NotRun(f"{what} refused", f"{shown(path)} is a link or not a {kind}: remove it and {then}")
    if st.st_uid != os.geteuid():
        raise NotRun(f"{what} refused", f"{shown(path)} belongs to another user: remove it and {then}")
    if st.st_mode & 0o022:
        raise NotRun(f"{what} refused", f"{shown(path)} can be written by other users: run `chmod go-w "
                                        f"{shown(path)}`, then {then}")
    if not directory and st.st_nlink != 1:
        raise NotRun(f"{what} refused", f"{shown(path)} has another name (a hard link): remove it and {then}")


def read_private(path: str, what: str = "advisory cache", limit: int = MAX_TOTAL_BYTES) -> bytes:
    """The bytes of a state file, checked on the descriptor that is read, so the file checked is the file
    read: opened without following a link or blocking on a special file."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as fh:
        check_stat(os.fstat(fh.fileno()), path, False, what)
        return fh.read(limit)


def private_dir(path: str, repo, what: str) -> str:
    """`path` as a directory of the user's own, created 0700; refused when it resolves inside the repository
    under audit, where the change itself could have written it."""
    if repo and inside(path, repo):
        raise NotRun(f"{what} refused", f"{shown(path)} resolves inside the repository under audit: run the audit "
                                        "with HOME set to your own home directory")
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise NotRun(f"{what} refused", f"{shown(path)} cannot be created ({exc.strerror}): create it as a "
                                        f"directory of your own, then {then_run(what)}")
    check_owned(path, directory=True, what=what)
    return path


def write_private(path: str, data: bytes) -> None:
    """Atomically, 0600, never through a link."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def no_redirect_opener():
    """A urllib opener that follows no redirect: the export is read from the one fixed URL or not at all."""
    import urllib.request  # here, not at the top: register and a fresh cache never need the network modules

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            raise FetchError(f"the server answered with a redirect ({code}), which is never followed")

    return urllib.request.build_opener(NoRedirect)


def read_limited(stream, limit: int, deadline: float, clock=time.monotonic) -> bytes:
    """Everything `stream` holds, refused past `limit` bytes or `deadline` seconds."""
    started, chunks, size = clock(), [], 0
    while True:
        if clock() - started > deadline:
            raise FetchError(f"no complete answer within {int(deadline)} seconds")
        chunk = stream.read(1 << 16)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > limit:
            raise FetchError(f"the download is larger than {mib(limit)}")
        chunks.append(chunk)


def http_fetch(url: str, headers: dict, limit: int = MAX_DOWNLOAD_BYTES,
               deadline: float = DOWNLOAD_DEADLINE_SECONDS) -> tuple:
    """(status, body, {"last-modified", "etag"}) of one HTTPS GET: no redirect followed, at most `limit` bytes
    within `deadline` seconds, certificates verified by Python's default context (TM-29). 304 is an answer."""
    if not url.startswith("https://"):
        raise FetchError("refusing a download that is not https")
    import urllib.error
    import urllib.request
    request = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": USER_AGENT}))
    try:
        # https-only is enforced above (the scheme check B310 asks for).
        timeout = min(SOCKET_TIMEOUT_SECONDS, deadline)  # a peer trickling bytes is held to the deadline too
        with no_redirect_opener().open(request, timeout=timeout) as resp:  # nosec B310
            body = read_limited(resp, limit, deadline)
            return resp.status, body, {"last-modified": resp.headers.get("Last-Modified"),
                                       "etag": resp.headers.get("ETag")}
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, b"", {}
        raise FetchError(f"HTTP {exc.code}")
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 - URLError, a timeout, TLS, a cut connection: all one outcome
        raise FetchError(type(exc).__name__)  # the kind is enough; the text is not printed


def parse_record(data: bytes):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise DataError("a record that is not JSON")


class Limits:
    """How much of an archive or a directory is read before it is refused."""

    def __init__(self, entries: int = MAX_ENTRIES, entry_bytes: int = MAX_ENTRY_BYTES,
                 total_bytes: int = MAX_TOTAL_BYTES) -> None:
        self.entries, self.entry_bytes, self.total_bytes = entries, entry_bytes, total_bytes
        self.seen = self.total = 0

    def charge(self, size: int) -> None:
        self.seen += 1
        self.total += size
        if self.seen > self.entries:
            raise DataError(f"more than {self.entries} entries")
        if size > self.entry_bytes:
            raise DataError(f"an entry larger than {mib(self.entry_bytes)}")
        if self.total > self.total_bytes:
            raise DataError(f"more than {mib(self.total_bytes)} in all")


# zipfile builds an entry for every central-directory record before the first member is read, so the record
# count and the directory's size are checked from the end-of-central-directory record first (APPNOTE.TXT 4.3.16,
# and 4.3.14/4.3.15 for zip64): at most limits.entries members and CENTRAL_BYTES_PER_ENTRY bytes per allowed member
# (the OSV PyPI export of 2026-11-25 used 66 per member), so a crafted directory cannot cost more memory than
# that many entries. The member count is checked again on the list zipfile built, since a directory can declare
# fewer records than it holds.
END_RECORD, ZIP64_LOCATOR, ZIP64_END_RECORD = b"PK\x05\x06", b"PK\x06\x07", b"PK\x06\x06"
CENTRAL_BYTES_PER_ENTRY = 128


def central_directory(fh) -> tuple:
    """(member count, central directory bytes) the archive's end records declare; (None, None) when there is no
    end record, which zipfile then refuses itself."""
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    start = max(0, size - 22 - 0xFFFF)  # the record is 22 bytes, then a comment of at most 65,535
    fh.seek(start)
    tail = fh.read()
    at = tail.rfind(END_RECORD)
    if at < 0 or len(tail) - at < 22:
        return None, None
    count, directory = struct.unpack("<HL", tail[at + 10:at + 16])
    if count != 0xFFFF and directory != 0xFFFFFFFF:
        return count, directory
    fh.seek(max(0, start + at - 20))
    locator = fh.read(20)
    if len(locator) < 20 or locator[:4] != ZIP64_LOCATOR:
        return count, directory  # saturated without a zip64 record: the saturated values are checked
    fh.seek(struct.unpack("<Q", locator[8:16])[0])
    record = fh.read(56)
    if len(record) < 56 or record[:4] != ZIP64_END_RECORD:
        return None, None
    return struct.unpack("<QQ", record[32:48])


def read_archive(source, limits: Limits):
    """The parsed records of the export zip (bytes, or a path), read in memory: nothing is extracted to disk,
    and the limits apply to what is actually read, whatever sizes the archive declares: every member counts
    against limits.entries, a JSON record or not."""
    try:
        with contextlib.ExitStack() as stack:
            fh = io.BytesIO(source) if isinstance(source, bytes) else stack.enter_context(open(source, "rb"))
            count, directory = central_directory(fh)
            if count is not None and count > limits.entries:
                raise DataError(f"more than {limits.entries} entries")
            if count is not None and directory > limits.entries * CENTRAL_BYTES_PER_ENTRY:
                raise DataError(f"a central directory larger than {limits.entries} entries take")
            fh.seek(0)
            archive = stack.enter_context(zipfile.ZipFile(fh))
            if len(archive.infolist()) > limits.entries:
                raise DataError(f"more than {limits.entries} entries")
            for info in archive.infolist():
                if info.is_dir() or not info.filename.endswith(".json"):
                    continue
                with archive.open(info) as member:
                    data = member.read(limits.entry_bytes + 1)
                limits.charge(len(data))
                yield parse_record(data)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError, RuntimeError, NotImplementedError) as exc:
        raise DataError(f"not a readable zip archive ({type(exc).__name__})")
    except Exception as exc:  # noqa: BLE001 - zlib.error and the like: a corrupt member
        if isinstance(exc, DataError):
            raise
        raise DataError(f"a corrupt archive ({type(exc).__name__})")


def read_directory(path: str, limits: Limits):
    """The parsed records of an unpacked export: every *.json under `path`, links never followed. A directory
    that cannot be listed, a linked directory and a record that is not a regular file stop the import: a
    traversal that skipped part of the export would publish less than it holds."""
    def refuse(exc):
        raise DataError(f"a directory that cannot be read ({exc.strerror})")

    for current, dirs, files in os.walk(path, followlinks=False, onerror=refuse):
        dirs.sort()
        if any(os.path.islink(os.path.join(current, d)) for d in dirs):
            raise DataError("a linked directory in the export, which is not followed")
        for name in sorted(files):
            if not name.endswith(".json"):
                continue
            try:
                fd = os.open(os.path.join(current, name),
                             os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "rb") as fh:
                    if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                        raise DataError("a record that is not a regular file")
                    data = fh.read(limits.entry_bytes + 1)
            except OSError as exc:
                raise DataError(f"a record that cannot be read ({exc.strerror})")
            limits.charge(len(data))
            yield parse_record(data)


class Store:
    """The advisory cache of one ecosystem: one published dataset (datasets/<sha256>.json) named by current.json,
    which holds its digest, its count and three dates kept apart: when the server last changed the export
    (published), when the plugin last checked with the server (checked) and when the dataset was validated. The
    clock, the network and the minimum are arguments so the tests need no environment knob."""

    def __init__(self, directory: str, ecosystem: Ecosystem, repo=None, fetch=None, now=time.time,
                 minimum=None, limits=Limits, deadline=None) -> None:
        # fetch is looked up when the store is made, not when this module is, so a test that patches http_fetch
        # patches what the store calls
        self.directory, self.ecosystem, self.repo, self.now = directory, ecosystem, repo, now
        self.fetch = http_fetch if fetch is None else fetch
        self.minimum = ecosystem.minimum if minimum is None else minimum
        self.limits = limits
        self.deadline = deadline  # time.monotonic() by which an audit must end, None for refresh and check

    def seconds_left(self, most: float) -> float:
        return most if self.deadline is None else min(most, self.deadline - time.monotonic())

    # -- files
    def prepare(self) -> None:
        if self.ecosystem.cache_subdir:  # makedirs gives only the last directory its mode: the cache first
            private_dir(os.path.dirname(self.directory), self.repo, "advisory cache")
        private_dir(self.directory, self.repo, "advisory cache")
        private_dir(os.path.join(self.directory, "datasets"), self.repo, "advisory cache")

    def _dataset_path(self, digest: str) -> str:
        return os.path.join(self.directory, "datasets", digest + ".json")

    def read_meta(self):
        """current.json when it names a dataset, else None (nothing published, or a record nobody can use:
        the next refresh replaces it)."""
        path = os.path.join(self.directory, "current.json")
        if not os.path.lexists(path):
            return None
        if os.path.islink(path):
            check_owned(path, directory=False)  # refused by name
        try:
            meta = json.loads(read_private(path, limit=1024 * 1024).decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        ok = (isinstance(meta, dict) and meta.get("schema") == CACHE_SCHEMA
              and isinstance(meta.get("sha256"), str) and HEX_RE.match(meta["sha256"])
              and isinstance(meta.get("advisories"), int) and isinstance(meta.get("checked"), (int, float))
              and isinstance(meta.get("validated"), (int, float)) and meta.get("source") in ("download", "import")
              and isinstance(meta.get("published"), str) and isinstance(meta.get("origin"), str)
              and isinstance(meta.get("withdrawn", 0), int)
              and meta.get("ecosystem", UNNAMED_ECOSYSTEM) == self.ecosystem.name
              and meta.get("matcher") == self.ecosystem.matcher)  # a dataset another matcher keyed: rebuilt
        return meta if ok else None

    def load(self, meta: dict) -> dict:
        """The published dataset, its digest checked again: a file edited or swapped since it was validated is
        refused, and so is one below the minimum or of another ecosystem."""
        path = self._dataset_path(meta["sha256"])
        if os.path.islink(path):
            check_owned(path, directory=False)  # refused by name
        try:
            data = read_private(path)
        except OSError:
            raise NotRun("advisory data missing", f"the published dataset is gone: {self.refresh_word()}")
        if sha256(data) != meta["sha256"]:
            raise NotRun("advisory data digest mismatch", "the dataset changed after it was validated: "
                                                          f"{self.refresh_word()}")
        try:
            dataset = json.loads(data.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            dataset = None
        if not isinstance(dataset, dict) or dataset.get("schema") != DATASET_SCHEMA \
                or not isinstance(dataset.get("advisories"), list) \
                or dataset.get("ecosystem", UNNAMED_ECOSYSTEM) != self.ecosystem.name:
            raise NotRun("advisory data unreadable", self.refresh_word())
        if len(dataset["advisories"]) < self.minimum or len(dataset["advisories"]) != meta["advisories"]:
            raise NotRun("advisory data too small", f"{len(dataset['advisories'])} advisories, fewer than the "
                                                    f"minimum of {self.minimum} or than the cache records: "
                                                    f"{self.refresh_word()}")
        return dataset

    def refresh_word(self) -> str:
        """The command a remedy names: plain refresh for Maven, as it always was."""
        return f"run {self.ecosystem.refresh_command}" if self.ecosystem.cache_subdir else "run refresh"

    def _publish(self, dataset: dict, source: str, origin: str, published: str, extra: dict) -> dict:
        data = dataset_bytes(dataset)
        digest = sha256(data)
        now = self.now()
        meta = dict(extra, schema=CACHE_SCHEMA, sha256=digest, advisories=len(dataset["advisories"]),
                    withdrawn=dataset["withdrawn"], source=source, origin=origin, published=published,
                    newest_record=newest_modified(dataset), checked=now, validated=now)
        if self.ecosystem.name != UNNAMED_ECOSYSTEM:
            meta["ecosystem"] = self.ecosystem.name
        if self.ecosystem.matcher is not None:
            meta["matcher"] = self.ecosystem.matcher
        previous = self.read_meta()
        write_private(self._dataset_path(digest), data)
        self._write_meta(meta)
        # The previous generation is kept: an audit reads current.json and then its dataset without the lock,
        # and may have read the metadata this publication just replaced.
        keep = {digest + ".json"} | ({previous["sha256"] + ".json"} if previous else set())
        for name in os.listdir(os.path.join(self.directory, "datasets")):
            if name not in keep:
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(self.directory, "datasets", name))
        return meta

    def _write_meta(self, meta: dict) -> None:
        write_private(os.path.join(self.directory, "current.json"),
                      (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    @contextlib.contextmanager
    def lock(self):
        """Refresh and import hold it, so two at once publish one after the other, never interleaved."""
        path = os.path.join(self.directory, ".lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                     0o600)
        try:
            check_stat(os.fstat(fd), path, False, "advisory cache")
            limit = time.monotonic() + LOCK_WAIT_SECONDS
            total = self.deadline is not None and self.deadline < limit
            limit = min(limit, self.deadline) if self.deadline is not None else limit
            while fcntl:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() > limit:
                        if total:
                            raise NotRun("time limit", time_limit_remedy("the audit reached its total limit while "
                                                                         "another refresh held the advisory cache"))
                        raise NotRun("advisory cache busy", "another refresh holds its lock: run the command again")
                    time.sleep(0.1)
            yield
        finally:
            os.close(fd)

    # -- refresh and import
    def refresh(self, force: bool = False) -> tuple:
        """(metadata, what happened): 'fresh' (checked within 24 hours, or by another refresh while this one
        waited for the lock), 'not modified' (a 304: only the check date moves) or 'downloaded'. RefreshFailed
        leaves the published dataset as it was."""
        before = self.read_meta()
        with self.lock():
            meta = self.read_meta()
            if meta and (meta != before or (not force and 0 <= self.now() - meta["checked"] < FRESH_SECONDS)):
                return meta, "fresh"
            headers = {}
            if meta and meta["source"] == "download":
                for header, key in (("If-Modified-Since", "last_modified"), ("If-None-Match", "etag")):
                    value = meta.get(key)
                    if isinstance(value, str) and re.match(r"^[\x20-\x7e]{1,200}$", value):
                        headers[header] = value
            try:
                left = self.seconds_left(DOWNLOAD_DEADLINE_SECONDS)
                if left < 1:
                    raise FetchError("the audit reached its total time limit before the download")
                status, body, got = self.fetch(self.ecosystem.export_url, headers, deadline=left)
                if status == 304 and meta:
                    meta = dict(meta, checked=self.now())
                    self._write_meta(meta)
                    return meta, "not modified"
                if status != 200:
                    raise FetchError(f"HTTP {status}")
                dataset = build_dataset(read_archive(body, self.limits()), self.ecosystem, self.minimum)
            except (FetchError, DataError) as exc:
                raise RefreshFailed(str(exc))
            try:
                published = iso_date(email.utils.mktime_tz(email.utils.parsedate_tz(got.get("last-modified") or "")))
            except (TypeError, ValueError, OverflowError):
                published = "unknown"
            if published == "unknown":  # no usable Last-Modified header: the newest record dates the export
                published = newest_modified(dataset)[:10]
            extra = {"last_modified": got.get("last-modified"), "etag": got.get("etag"), "archive_sha256": sha256(body)}
            return self._publish(dataset, "download", self.ecosystem.export_url, published, extra), "downloaded"

    def import_from(self, path: str) -> dict:
        """Publishes a local copy of the export (the zip, or a directory of its records), held to the same
        limits and the same minimum as a download. Its publication date is its newest record's."""
        path = os.path.abspath(os.path.expanduser(path))
        with self.lock():
            try:
                reader = read_directory if os.path.isdir(path) else read_archive
                records = reader(path, self.limits())
                dataset = build_dataset(records, self.ecosystem, self.minimum)
            except DataError as exc:
                raise RefreshFailed(str(exc))
            return self._publish(dataset, "import", path, newest_modified(dataset)[:10], {})

    def dataset_for_audit(self, cached_only: bool = False) -> tuple:
        """(dataset, metadata, notes) for an audit, or NotRun: fresh data as it is; otherwise a refresh; when
        that fails, data checked within 7 days, with a note; older than that, or none, and no audit."""
        self.prepare()
        meta = self.read_meta()
        notes = []
        age = self.now() - meta["checked"] if meta else None
        if meta is None or not 0 <= age < FRESH_SECONDS:
            reason = "--cached-data"
            if not cached_only:
                try:
                    meta, _what = self.refresh()
                    return self.load(meta), meta, notes
                except RefreshFailed as exc:
                    reason = f"the refresh failed: {exc.reason}"
            command = self.ecosystem.refresh_remedy
            if meta is None:
                raise NotRun("no advisory data", f"{reason}; {command}")
            if not 0 <= age < USABLE_SECONDS:
                raise NotRun("advisory data too old", f"last checked {iso_date(meta['checked'])}, more than 7 days "
                                                      f"ago ({reason}); {command}")
            notes.append(f"advisory data not checked with the server ({reason}); using data last checked "
                         f"{iso_date(meta['checked'])}, published {safe_date(meta['published'])}")
        return self.load(meta), meta, notes


def data_record(meta: dict) -> dict:
    """What the reports say about the dataset, every value a date, a count, a digest or an escaped path; an
    ecosystem other than Maven is named, a Maven record keeps the keys it always had."""
    record = {"source": "download" if meta["source"] == "download" else "import", "origin": shown(meta["origin"]),
              "published": safe_date(meta["published"]), "checked": iso_date(meta["checked"]),
              "validated": iso_date(meta["validated"]), "advisories": int(meta["advisories"]),
              "sha256": meta["sha256"] if HEX_RE.match(str(meta["sha256"])) else "unknown"}
    if meta.get("ecosystem", UNNAMED_ECOSYSTEM) != UNNAMED_ECOSYSTEM and meta.get("ecosystem") in ECOSYSTEMS:
        record["ecosystem"] = meta["ecosystem"]
    return record


def data_line(data: dict) -> str:
    ecosystem = ecosystem_of(data)
    return (f"Data: {ecosystem.label}, {data['source']} ({data['origin']}); published {data['published']}; "
            f"last checked {data['checked']}; validated {data['validated']}; {data['advisories']} advisories; "
            f"dataset sha256 {data['sha256'][:16]}; {ecosystem.attribution}")


# ---------------------------------------------------------------- attribution and classification
BLOCKS = (("introduced", "Introduced by this change"), ("unknown", "Attribution unknown"),
          ("accepted", "Accepted by the user"), ("pre_existing", "Pre-existing"))
INVENTORY_MEANING = ("An entry means a version matching an advisory is in the inventory, not that the vulnerable code "
                     "is called; with no entry, the result is no matching advisory in this dataset.")


def base_occurrences(modules: list, version_key=None) -> dict:
    """{module: {(package, version): whether any occurrence ships}} of a resolved base. `version_key` is the
    ecosystem's (Ecosystem.version_key), so a version spelled another way in the base ("5.3" and "5.3.0" in PyPI)
    is still the same version; attribution() looks it up by the same key."""
    found: dict = {}
    for module in modules:
        seen = found.setdefault(module["id"], {})
        for node in module["nodes"]:
            key = (node["package"], version_key(node["version"]) if version_key else node["version"])
            seen[key] = seen.get(key, False) or node["ships"]
    return found


def attribution(module: dict, node: dict, base, version_key=None) -> str:
    """Whose an occurrence is, so that old vulnerabilities in untouched dependencies never block a change that
    neither added nor newly shipped them. `base` is None when no base was resolved: the occurrence is then
    unknown and counts as the change's. Against a resolved base it is the change's when the base lacks that
    module, coordinate and version, or had it only where it does not ship while the candidate ships it; an
    occurrence whose scope narrowed is not new. A base maps a module to None when that module's base inventory
    was not read whole (a PyPI lock or pin file the base could not read), and its occurrences are then unknown."""
    if base is None:
        return "unknown"
    known = base.get(module["id"], {})
    if known is None:
        return "unknown"
    was = known.get((node["package"], version_key(node["version"]) if version_key else node["version"]))
    if was is None or (node["ships"] and not was):
        return "introduced"
    return "pre_existing"


def evaluate(index: Index, modules: list, base, accept: list) -> dict:
    """The four blocks of a report from an inventory: every occurrence matching an advisory goes to exactly
    one of introduced, unknown and pre_existing with the advisories the user has not accepted, and to accepted
    with those the user has. `accept` holds advisory ids or aliases; one that occurs nowhere is returned."""
    return evaluate_sides([(index, modules, base)], accept)


def evaluate_sides(sides: list, accept: list, deadline=None) -> dict:
    """evaluate over the inventories of one or more ecosystems, each (index, modules, base) matched against its
    own index and worded by its own ecosystem, into one set of blocks: an id accepted in one ecosystem is used.
    `deadline` (time.monotonic()) is checked every MATCH_CHECK_EVERY occurrences: a PyPI inventory of many pins
    costs seconds to match, and the audit must end within its total limit (NotRun, time limit)."""
    wanted = {a.lower() for a in accept}
    matched_count = 0
    used: set = set()
    blocks: dict = {key: [] for key, _title in BLOCKS}
    dependencies = set()
    for index, modules, base in sides:
        occurrence = index.ecosystem.occurrence
        for module in modules:
            for node in module["nodes"]:
                if matched_count % MATCH_CHECK_EVERY == 0:  # the first occurrence included
                    check_deadline(deadline)
                matched_count += 1
                dependencies.add((index.ecosystem.name, module["id"], node["package"], node["version"]))
                matched = match_package(index, node["package"], node["version"], deadline)
                if not matched["advisories"]:
                    continue
                taken, left = [], []
                for advisory in matched["advisories"]:
                    names = {advisory["id"].lower(), *(alias.lower() for alias in advisory["aliases"])} & wanted
                    used |= names
                    (taken if names else left).append(advisory)
                if taken:
                    blocks["accepted"].append(occurrence(module, node, taken, matched["fix"], matched["fix_checked"]))
                if left:
                    blocks[attribution(module, node, base, index.ecosystem.version_key)].append(
                        occurrence(module, node, left, matched["fix"], matched["fix_checked"]))
    for entries in blocks.values():
        entries.sort(key=lambda e: (CLASS_ORDER[e["class"]], e["module"], e["coordinate"], e["version"]))
    return {"blocks": blocks, "dependencies": len(dependencies),
            "unused_accepts": sorted(a for a in accept if a.lower() not in used)}


def gate_status(blocks: dict, complete: bool) -> str:
    """fail when an occurrence that is the change's, or whose attribution is unknown, is a Blocker or a Major
    the user has not accepted, so the state cannot read clean while an introduced vulnerability is open;
    otherwise pass only with complete coverage: a partial result keeps what it found and is otherwise not run,
    so it never reads as clean."""
    if any(e["class"] in ("Blocker", "Major") for key in ("introduced", "unknown") for e in blocks[key]):
        return "fail"
    return "pass" if complete else "not-run"


# ---------------------------------------------------------------- rendering
def one_line(text: str) -> str:
    """The last guard of every status and report line: no control or bidirectional character survives."""
    return UNSAFE_RE.sub(lambda m: "\\u%04x" % ord(m.group(0)), text)


def not_run_line(category: str, remedy: str) -> str:
    return one_line(f"Dependency audit: not run ({category}: {remedy})")


def off_line(source: str) -> str:
    return one_line(f"Dependency audit: off (configuration: {shown(source)})")


def records(value) -> list:
    """A result's data or resolution as a list: one record for one ecosystem, a list of them for two."""
    return value if isinstance(value, list) else [value] if value else []


def published_text(data) -> str:
    """The publication date of the advisory data, one per ecosystem with its name when two were used."""
    listed = records(data)
    if not listed:
        return "none (no package to match)"
    if len(listed) == 1:
        return listed[0]["published"]
    return ", ".join(f"{d['published']} ({ecosystem_of(d).name})" for d in listed)


def status_line(result: dict) -> str:
    if result["status"] == "not-run":
        return not_run_line(*result["problem"])
    counts, blocks = result["counts"], result["blocks"]
    coverage = "coverage complete" if result.get("coverage") != "partial" else \
        f"coverage partial ({': '.join(result['problem'])})"
    if result.get("coverage") != "partial" and result.get("coverage_note"):
        coverage += f" ({result['coverage_note']})"  # a complete inventory that is empty by declaration
    by_class = {name: sum(1 for e in blocks["introduced"] if e["class"] == name) for name in CLASS_ORDER}
    return one_line(
        f"Dependency audit: {result['status']} (introduced: {by_class['Blocker']} Blocker, {by_class['Major']} Major, "
        f"{by_class['Minor']} Minor; attribution unknown: {len(blocks['unknown'])}; "
        f"accepted: {len(blocks['accepted'])}; "
        f"pre-existing: {len(blocks['pre_existing'])}; {counts['dependencies']} dependencies in {counts['modules']} "
        f"modules; {data_field(result)}; {coverage})")


def data_field(result: dict) -> str:
    """The status line's advisory-data field: the publication date(s), or, for a result that had no package to
    match and loaded no data, that none was needed."""
    if not records(result.get("data")) and result.get("data_note"):
        return f"advisory data {result['data_note']}"
    return f"advisory data published {published_text(result['data'])}"


def occurrence_line(entry: dict, labelled: bool = False) -> str:
    """One report line; `labelled` names the build tool after the module, for a result two tools resolved. At
    most MAX_TEXT_ADVISORIES advisories are listed, the most severe first (match_package orders them), then how
    many more the JSON report holds."""
    listed = entry["advisories"][:MAX_TEXT_ADVISORIES]
    advisories = ", ".join(
        f"{a['id']}{' (' + ', '.join(a['aliases']) + ')' if a['aliases'] else ''} {a['severity']}"
        f"{' (from ' + a['severity_from'] + ')' if a.get('severity_from') else ''} {a['class']}"
        f"{' unsure' if a['unsure'] else ''} [{a['basis']}]" for a in listed)
    more = len(entry["advisories"]) - len(listed) + entry.get("advisories_not_listed", 0)
    if more > 0:
        advisories += f", and {more} more advisories (the JSON report lists up to {MAX_JSON_ADVISORIES})"
    fix = f"fix reported: {entry['fix']}" if entry["fix"] else "no fixed version in the advisory data"
    if entry["fix"] and not entry.get("fix_checked", True):
        fix += " (not checked against every advisory: one could not be evaluated)"
    tool = f" ({entry['tool']})" if labelled and entry.get("tool") else ""
    separator = ecosystem_of(entry).separator
    return (f"- module {entry['module']}{tool}; {entry['coordinate']}{separator}{entry['version']} ({entry['scope']}); "
            f"path: {' > '.join(entry['path'])}; advisories: {advisories}; {fix}")


def render_text(result: dict) -> str:
    """The text report: the status line, then for each ecosystem audited its Data line, then for each its
    Resolution and Inventory lines, then the five blocks."""
    lines = [result["status_line"]]
    data = records(result.get("data"))
    lines += [data_line(d) for d in data] or \
        [f"Data: none {'needed (no package to match)' if result.get('data_note') else 'loaded'}"]
    resolutions = records(result.get("resolution"))
    if resolutions:
        for resolution in resolutions:
            ecosystem = ecosystem_of(resolution)
            shown_record = None if resolution.get("not_run") else resolution  # an ecosystem that could not run
            lines += [ecosystem.resolution_line(shown_record), ecosystem.inventory_line(shown_record)]
    else:
        names = result.get("ecosystems") or [UNNAMED_ECOSYSTEM]
        for name in names:
            lines.append(ECOSYSTEMS[name].resolution_line(None))
        for name in names:
            lines.append(ECOSYSTEMS[name].inventory_line(None))
    labelled = any(len(r.get("tools") or []) > 1 for r in resolutions)
    for key, title in BLOCKS:
        entries = result["blocks"][key]
        shown_entries = [occurrence_line(e, labelled) for e in entries[:MAX_TEXT_OCCURRENCES]]
        if len(entries) > MAX_TEXT_OCCURRENCES:  # a bound on the report a model reads, said where it applies
            shown_entries.append(f"- {len(entries) - MAX_TEXT_OCCURRENCES} more entries, not listed here: the JSON "
                                 f"report lists up to {MAX_JSON_OCCURRENCES}")
        lines += ["", f"{title} ({len(entries)}):", *(shown_entries or ["- none"])]
    notes = result["not_evaluated"]
    lines += ["", f"Could not be evaluated ({len(notes)}):", *([f"- {n}" for n in notes] or ["- none"])]
    if result.get("attempt"):
        lines += ["", f"Report: attempt {result['attempt']} on snapshot {result['snapshot'][:12]}, "
                      f"gates/{GATE_NAME}-{result['attempt']}.txt and input/{GATE_NAME}-{result['attempt']}.json"]
    return "\n".join(one_line(line) for line in lines) + "\n"


def render_json(result: dict) -> bytes:
    """The JSON report. A block holds at most MAX_JSON_OCCURRENCES entries and an entry at most MAX_JSON_ADVISORIES
    advisories; past either, the count left out is recorded ("not_listed", "advisories_not_listed"), so the
    report's size is bounded and says where it was cut. No Java report reaches either bound."""
    keep = ("schema", "snapshot", "attempt", "status", "status_line", "problem", "coverage", "counts", "data",
            "resolution", "inputs", "blocks", "not_evaluated", "accepted_ids")
    body = {k: result.get(k) for k in keep}
    blocks = body.get("blocks") or {}
    if any(len(v) > MAX_JSON_OCCURRENCES or any(len(e["advisories"]) > MAX_JSON_ADVISORIES for e in v)
           for v in blocks.values()):
        body["blocks"] = {key: [capped_entry(e) for e in entries[:MAX_JSON_OCCURRENCES]]
                          for key, entries in blocks.items()}
        body["not_listed"] = {key: max(0, len(entries) - MAX_JSON_OCCURRENCES) for key, entries in blocks.items()}
    return (json.dumps(body, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def capped_entry(entry: dict) -> dict:
    if len(entry["advisories"]) <= MAX_JSON_ADVISORIES:
        return entry
    return dict(entry, advisories=entry["advisories"][:MAX_JSON_ADVISORIES],
                advisories_not_listed=len(entry["advisories"]) - MAX_JSON_ADVISORIES)


def empty_result(snapshot_id) -> dict:
    return {"schema": SCHEMA, "snapshot": snapshot_id, "attempt": None, "status": "not-run", "problem": None,
            "counts": {"dependencies": 0, "modules": 0}, "data": None, "resolution": None,
            "inputs": {"candidate": {}, "base": None}, "blocks": {key: [] for key, _t in BLOCKS},
            "not_evaluated": [], "accepted_ids": []}
