#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
spec-layout.py — finds a project's specification, checks its format and the history of its items, binds a
specification draft to its plan, and renders the traceability report.

Owns one thing: deciding, without judgement, which specification a repository keeps, whether a
specification (or a draft of one under `ai-planning/<slug>.spec/`) keeps the established format and never
loses or silently rewords an item, whether the draft written into the project is the draft the user
approved, and which tests and code cite each item. It is the specification half of the analysis gate of
the implementing-*-from-spec skills and of the spec-handling skill (the contract, section 13);
spec-trace.py is the plan half. It changes nothing: every command prints, and the skill writes what
`traceability` prints with a tool call the approval gate judges. Whether an item says what the code really
does remains the skill's and the user's judgement.

Recognised layouts, in the order they are preferred when a repository holds several:
  named         the Markdown files given with --spec (each must exist): a specification kept somewhere else,
                which the user confirmed is the project's specification; the standard documents beside each
                file belong to it, as in the flat layout
  combined      specification/SPECIFICATION.md carrying the line
                `Format: implement-from-spec specification format 1`, item files under
                specification/functional/ (SPEC-Fnnn) and specification/non-functional/ (SPEC-NFnnn), and
                the documents ARCHITECTURE.md, DEPLOYMENT.md, FEATURE-LIST.md, TEST-CASES.md,
                TRACEABILITY.md and open-questions.md beside the index. The layout the spec-handling skill
                creates
  kit           specification/SPECIFICATION.md without the Format line, with functional/ or non-functional/
  unstructured  a specification/ directory of Markdown files that is neither of the above
  structured    docs/specifications/*.md with one heading per SPEC-<SVC>-n item
  flat          docs/SPECIFICATION.md holding every item, the documents beside it in docs/
  none          no specification found
When more than one recognised place holds specification files (specification/, docs/specifications/,
docs/SPECIFICATION.md), whether or not they define items, the repository is ambiguous: detect says so, and
check fails `layout-ambiguous` unless --spec, or a `Specification root:` line in the plan's Specification
changes naming the place in backticks, says which one is the specification.

An item is defined in an item file by a heading of level 2 to 5 that carries its ID (the first ID of the
heading), or by a paragraph or a top-level list item that starts at the margin with the ID and a title in
bold (`**SPEC-F003 Open.** ...`); an indented or nested line is never a definition. Its text runs to the
next definition or heading. An item is struck when `~~` precedes its ID on the defining line. Fenced code
(CommonMark fences: a closing fence uses the opening character and is at least as long) and HTML comments
are never read.
An item file that cannot be read, is binary or is over 2 MB stops the run (exit 2), so no command
answers from part of a specification.

`detect` prints the layout, its files, every item with its file and line, the next free ID of each family
(SPEC-F, SPEC-NF, SPEC-<SVC>-), the standard documents the layout lacks, the other layouts found, and the
candidates: Markdown or text files outside the recognised places (and outside build, vendor and planning
directories) whose name says specification or requirements, or that define items. A candidate may be the
project's specification kept somewhere else; the skill asks before it derives a new one. Only a Markdown
candidate can be named with --spec; the others are reported as not checkable.

`digest <draft-dir>` prints `Draft digest: sha256 <hex>`, the line the plan's `## Specification changes`
carries, computed by core/gate/draft_digest.py, which the approval gate uses too: the sha256 of the sorted
lines `<path relative to the draft, POSIX>\t<sha256 of the file>\n` of every file in the draft, from one
traversal through descriptors anchored at the draft (no-follow, non-blocking opens checked with fstat), read
streamed; --json lists the files of that same traversal. A symlink or anything other than a regular file or a directory, a name with a control, separator
or bidi character (which would make two drafts give the same lines), a directory or file that cannot be
read, and a file swapped during the read stop it (exit 2); `check` stops on the same names and unreadable
directories.

`survey --repo <repo>` prints the repository files a baseline may read: what git lists (as for
`traceability`) minus the files the external review never sends (its sensitive-file rule, `SENSITIVE_RE`
in spec-external-review.py: keys, credentials, state, real tfvars), lock files, build output and caches
(its `EXCLUDE_RE`), the planning and vendor directories, and binary files. The withheld files are named,
with the reason, so the skill can say what it did not read.

`check` (FAIL unless noted). With --draft (the plan's draft, `ai-planning/<slug>.spec/` beside
`<slug>.plan`) the checked tree is the work tree's specification with the draft's files laid over it (a
draft file replaces the project file of the same repository-relative path) and the plan's deleted paths
removed; the earlier state is the work tree, except for the paths the change writes: a drafted file the
work tree already holds byte for byte and a deleted path already gone are taken from the base commit, and,
once any of those is in place, so are the files a task of the plan owns outside the draft (the traceability
report and the living documents the last wave writes). A check re-run after a full or partial apply, or
after the sync, therefore still sees the change, and an uncommitted edit elsewhere is still the work tree's.
`id-dropped` is judged over the earlier state and the base commit's items in the drafted and deleted paths.
Without --draft the checked tree is the work tree and the
earlier state is the base commit. The base commit is --base, else the commit the plan's ledger
(`<slug>.ledger.md`) names under `## Baseline`, else HEAD; a repository with no commit yet has an empty
earlier state.
  - `no-specification`: nothing to check; `draft-path`: a draft file that is not a specification path;
    `draft-symlink`: a symlink or a special file in the draft; `draft-sensitive`: a draft file, anywhere in
    the draft, that the external review's sensitive-file rule names (SENSITIVE_RE: keys, credentials, .env
    files, state, real tfvars), which the apply step would copy into the repository; `draft-binary`: a draft
    file that is binary or over 2 MB, so it cannot be scanned for credentials, and that the plan's
    Specification changes do not name in backticks
  - `layout-ambiguous`: see above
  - `id-duplicate`: an ID defined twice; `id-dropped`: an ID defined before and no longer defined (IDs are
    never removed or renumbered: strike the item through)
  - `source-missing`: a path an item's `*Source:*` field names neither exists in the repository nor is
    created by a task of the plan (patterns skipped; outside the combined layout, only for items that are
    new or changed)
  - `stub-wording` (drafts): TODO, FIXME, TBD, ??? or "not implemented" on a line the draft adds to its
    file (lines of the earlier state are not judged), which the code check would fail
  - `secret`: a draft file (any text file of it, Markdown or not), or (without --draft) a specification
    file the change added or changed, holds
    text the external review's secret patterns match (spec-external-review.py `SECRET_PATTERNS`: access
    keys, private keys, tokens, password assignments); the kind is named, never the value. A file the change
    did not touch is a WARN
  - `draft-traceability`: the draft holds a TRACEABILITY.md, which is written only by the last wave, from
    `traceability`, once the code exists. In draft mode a missing TRACEABILITY.md is therefore no
    `document-missing`, and the report is not compared
  - combined layout only: `document-missing` (a standard document absent or empty); `index-unlisted` (an
    item the index does not name) and `index-unknown` (an ID the index names that no item file defines);
    `misplaced` (SPEC-Fnnn outside functional/, SPEC-NFnnn outside non-functional/); `statement` (no MUST
    or SHOULD) and `acceptance` (no `Acceptance:`) on every item that is not struck
  - `new-layout`: no specification before, and the checked tree is not the combined layout
  - other layouts: `acceptance` and `misplaced` are WARN, and only for items that are new or changed
  - `traceability-stale` (without --draft): a TRACEABILITY.md that carries the generated mark and differs
    (line endings apart) from what `traceability` prints now. A TRACEABILITY.md without the mark is the
    project's own report: never checked, never failed (WARN `traceability-project`).
    A symlink anywhere in the specification places stops the run (exit 2), the report's path included
  - with --plan (FAIL with exit 2 when the file does not exist): the item delta (new, changed, struck)
    must equal the records of the plan's `## Specification changes` section,
    `- <ID> — new|changed|struck — <file> — <reason>`: `change-unlisted` (a delta the plan does not
    record), `change-unbacked` (a record with no such delta), `record-duplicate` (two records of one ID),
    `record-file` (the record names no file, or not the file that holds the item). `- baseline — <n> items ...` records the
    items of a first specification that have no line of their own: `baseline-existing` (a specification
    existed before), `baseline-count` (n differs), `baseline-unsourced` (such an item names no existing
    `Source:` path). `- deleted — <path> — <reason>` removes a specification file (a move into another
    layout): `deletion-path` (not a specification path), `deletion-unowned` (no task owns it as
    `(deleted)`), `deletion-not-applied` (without --draft: the file still exists). "none" records nothing
  - with --plan, a plan without `## Specification changes` was drafted before specification handling: WARN
    `plan-section`, and each item the change adds, changes or strikes is a WARN `change-legacy`, for the user
    to confirm as the 0.2.0 contract's section 10 required; with a draft (or a digest line) it is a FAIL
    `plan-section`. Plans with the section keep the two-way rule above
  - with --plan and a draft: the section carries exactly one `Draft digest: sha256 <hex>` line
    (`draft-digest-missing`, `draft-digest-duplicate`, `draft-digest-malformed`; a `Draft digest:` label
    anywhere else in the plan, with or without the section, fails `draft-digest-misplaced`; fenced code and
    HTML comments are neither a section nor a line, by draft_digest.py's one parse) equal to the draft's
    digest (`draft-digest-mismatch`). Without --draft, the digest is compared again and every file of the
    plan's draft must be in the repository byte for byte (`draft-not-applied`): a drafted file is frozen at
    approval, and the last wave never edits one; `draft-missing` when the plan records a digest and the
    draft has gone
  - with --plan: `traceability-unowned` when the layout is combined or keeps a generated TRACEABILITY.md
    and no task owns `<root>/TRACEABILITY.md` (the last-wave specification task)
  - WARN `baseline`: outside a git work tree the delta, `id-dropped` and the applied-file comparison were
    not checked

`traceability` prints TRACEABILITY.md for the checked tree (with --plan, the layout its `Specification
root:` line picks, as check does): per item, the test files and the code files
that cite its ID exactly (SPEC-F001 is not cited by SPEC-F0010), with the number of citing lines. Tests
are the files spec-trace.py treats as tests, plus *.tftest.hcl and *_tests.yaml; Markdown, plans, lock
files, build output and caches (spec-external-review.py EXCLUDE_RE: package-lock.json and .terraform.lock.hcl
among them), the files the sensitive-file rule names, the specification itself and ai-planning/ are not
searched, binary files are skipped, and a file that cannot be read stops the run (exit 2). Files are read
whole, with no size cap. They are listed from git (tracked, and
untracked files the repository's own .gitignore files do not exclude; the user's global excludes do not
apply), so the same tree gives the same report. It prints nothing unless the run is clean: on a FAIL the
findings go to stderr and stdout stays empty, so a redirect into a temporary file followed by a move on
exit 0 never leaves a truncated report; and when the report's place (`<root>/TRACEABILITY.md`) or a parent
of it in the repository is a symlink, it exits 2, so a move cannot land elsewhere. When the report's place
holds the project's own report (a non-empty file without the generated mark), it exits 2 and prints nothing:
the plugin never replaces that report, and the work-tree file is the one judged, with --draft too.

Usage:
    python3 -I <plugin-root>/core/scripts/spec-layout.py detect --repo <repo> [--json]
    python3 -I <plugin-root>/core/scripts/spec-layout.py digest <repo>/ai-planning/queue.spec
    python3 -I <plugin-root>/core/scripts/spec-layout.py survey --repo <repo>
    python3 -I <plugin-root>/core/scripts/spec-layout.py check --repo <repo> --draft <repo>/ai-planning/queue.spec \\
        --plan <repo>/ai-planning/queue.plan
    python3 -I <plugin-root>/core/scripts/spec-layout.py check --repo <repo> --plan <repo>/ai-planning/queue.plan --base <commit>
    python3 -I <plugin-root>/core/scripts/spec-layout.py traceability --repo <repo> [--plan <plan>] [--draft <dir>]
    python3 -I <plugin-root>/core/scripts/spec-layout.py detect --repo <repo> --spec docs/requirements.md

Exit codes: 0 no FAIL (WARN lines may print); 1 at least one FAIL; 2 usage, a file, the draft or the
repository could not be read, an unexpected error, or (`traceability`) there is no specification to
report on or the report's place holds the project's own report. `<mode> --help` lists that mode's options.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SPEC_DIR = "specification"
STRUCTURED_DIR = "docs/specifications"
FLAT_DIR = "docs"
INDEX = "SPECIFICATION.md"
FLAT_FILE = FLAT_DIR + "/" + INDEX
# The documents the combined layout keeps beside its index (the spec-handling skill's templates).
DOCUMENTS = ("ARCHITECTURE.md", "DEPLOYMENT.md", "FEATURE-LIST.md", "TEST-CASES.md", "TRACEABILITY.md",
             "open-questions.md")
TRACEABILITY = "TRACEABILITY.md"
FORMAT_RE = re.compile(r"^[ \t]*Format:[ \t]*implement-from-spec specification format (\d+)\b", re.M)
GENERATED_MARK = "Generated by the implement-from-spec plugin"
# The wording spec-trace.py's code check fails in a file a task owns (its STUB_RE), plus the plan
# placeholders: caught in the draft, before approval, where fixing it costs no amendment.
STUB_WORDING_RE = re.compile(r"\bTODO\b|\bFIXME\b|\bTBD\b|\?\?\?|not implemented", re.I)
KEYWORD_RE = re.compile(r"\bMUST\b|\bSHOULD\b")
ACCEPTANCE_RE = re.compile(r"\bAcceptance\b\**\s*:", re.I)
# The evidence field as the format writes it: `*Source:*` (or bold, as a structured item's field line).
# Plain "source:" in an item's prose (an event field, a data source) is not the field.
SOURCE_RE = re.compile(r"\*{1,2}Source:\*{1,2}")
FIELD_MARK_RE = re.compile(r"\*[A-Z][A-Za-z -]*:\*|^\s*[-*]\s+\*\*[A-Z][A-Za-z -]*:\*\*", re.M)
PATTERN_CHARS_RE = re.compile(r"[<>*{}\[\]?]")
EXTRA_TEST_SUFFIXES = (".tftest.hcl", "_tests.yaml", "_tests.yml")
NOT_SEARCHED_SUFFIXES = (".md", ".plan", ".lock")
# CommonMark: an opening fence is indented at most three spaces; a backtick fence's info string holds no
# backtick; the closing fence uses the same character, is at least as long and is followed only by spaces.
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
# Candidates for a specification kept outside the recognised places (detect).
CANDIDATE_SUFFIXES = (".md", ".markdown", ".txt", ".rst", ".adoc")
CANDIDATE_NAME_RE = re.compile(r"^(?:specs?|specifications?|requirements?|reqs|prd|srs)$|requirement|specification",
                               re.I)
SKIP_DIRS = frozenset({".git", ".claude", "ai-planning", "node_modules", "vendor", "third_party", "build", "dist",
                       "target", "out", ".venv", "venv", "env", ".tox", "cdk.out", ".terraform", "__pycache__",
                       ".aws-sam", "site-packages", ".gradle", ".idea"})
# The plan line that names which recognised place is the specification when a repository holds several.
ROOT_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+)?[*_`]*Specification root[*_`]*\s*:[*_`]*\s*`([^`]+)`", re.I)
ROOTS = {"specification/": "specification", "specification": "specification",
         "docs/specifications/": "docs/specifications", "docs/specifications": "docs/specifications",
         "docs/SPECIFICATION.md": "docs/SPECIFICATION.md"}
RECORD_RE = re.compile(r"^\s*[-*]\s+(\S+)\s+(?:—|–|-|:)\s+(new|changed|struck)\b", re.I)
BASELINE_RE = re.compile(r"^\s*[-*]\s+[`*]*baseline[`*]*\s+(?:—|–|-|:)\s+(\d+)\s+items?\b", re.I)
DELETED_RE = re.compile(r"^\s*[-*]\s+[`*]*deleted[`*]*\s+(?:—|–|-|:)\s+`([^`]+)`", re.I)
# Characters a repository-derived name must never carry into the report or the terminal: C0 and C1
# controls, DEL, the line and paragraph separators and the bidi controls (as review-prepare.py UNSAFE_RE).
UNSAFE_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c\ud800-\udfff]")


def load_trace():
    """spec-trace.py, the sibling that owns the item-ID and test-file rules, loaded by its path (works
    under python3 -I, which keeps the script's directory off sys.path)."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "spec-trace.py")
    spec = importlib.util.spec_from_file_location("ifs_spec_trace", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # No __pycache__ in the plugin's directory: an installed plugin is read-only content.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


TRACE = load_trace()
MAX_READ = TRACE.MAX_READ


def load_draft_digest():
    """core/gate/draft_digest.py, the one definition of a draft's digest and of the plan's `Draft digest:` line,
    which the approval gate uses too; loaded by its path, as spec-trace.py is."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "gate", "draft_digest.py")
    spec = importlib.util.spec_from_file_location("ifs_draft_digest", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


try:
    DIGEST = load_draft_digest()
    DIGEST_ERROR = None
except (OSError, ImportError) as _exc:  # a plugin without its gate module: every command stops (exit 2), never guesses
    DIGEST, DIGEST_ERROR = None, f"{type(_exc).__name__}: {_exc}"
_REVIEW: dict = {}


def review_rules():
    """spec-external-review.py, loaded by its path on first use, for the plugin's one definition of the
    sensitive-file rule (SENSITIVE_RE), the excluded files (EXCLUDE_RE) and the secret patterns
    (secret_kind): the baseline survey and the secret check reuse them instead of keeping a second list."""
    if "module" not in _REVIEW:
        path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "spec-external-review.py")
        spec = importlib.util.spec_from_file_location("ifs_spec_external_review", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = previous
        _REVIEW["module"] = module
    return _REVIEW["module"]


def safe(text: str) -> str:
    """Text with the backslash and every control, separator and bidi character escaped: applied to every line
    printed for a person, so a repository-derived name can neither forge a line nor fake an escape."""
    return UNSAFE_RE.sub(lambda m: "\\u%04x" % ord(m.group(0)), text.replace("\\", "\\\\"))


def code_span(text: str) -> str:
    """Markdown code for a repository-derived path: escaped, and fenced with more backticks than it holds."""
    text = safe(text)
    run = max((len(r) for r in re.findall(r"`+", text)), default=0)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return "`" * (run + 1) + pad + text + pad + "`" * (run + 1)


class Unreadable(Exception):
    """A file, a directory or a git object the run needs could not be read (exit 2)."""


def emit(text: str, stream=None) -> None:
    """Write text as UTF-8 whatever the locale (python3 -I ignores PYTHONIOENCODING, and the report holds
    non-ASCII characters)."""
    target = stream or sys.stdout
    target.flush()
    target.buffer.write(text.encode("utf-8"))
    target.buffer.flush()


def run_git(repo: str, *args: str, stdin: bytes = None):
    """(return code, stdout bytes) of one git command run in REPO without a shell; (None, b'') when git
    cannot start."""
    try:
        proc = subprocess.run(["git", *args], cwd=repo, input=stdin, capture_output=True, check=False)
    except OSError:
        return None, b""
    return proc.returncode, proc.stdout


def read_bytes(path: str):
    """The file's bytes, or None when it is unreadable or over MAX_READ bytes."""
    try:
        if os.path.getsize(path) > MAX_READ:
            return None
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def decode(data):
    """Text from bytes, or None for binary content."""
    if data is None or b"\0" in data:
        return None
    return data.decode("utf-8", errors="replace")


def read_text(path: str):
    """The file's text, or None when it is unreadable, over MAX_READ bytes or binary."""
    return decode(read_bytes(path))


def inside(path: str, root: str) -> bool:
    real, real_root = os.path.realpath(path), os.path.realpath(root)
    return real == real_root or real.startswith(real_root + os.sep)


def posix(rel: str) -> str:
    return rel.replace(os.sep, "/")


def named_documents(named) -> list:
    """The standard documents beside each --spec file, as the flat layout keeps them beside its file."""
    return sorted({posix(os.path.join(os.path.dirname(n), d)) for n in named for d in DOCUMENTS})


def is_spec_path(rel: str, named=()) -> bool:
    """A repository-relative path where a recognised layout keeps specification files."""
    return (rel in named or rel.startswith(SPEC_DIR + "/") or rel.startswith(STRUCTURED_DIR + "/")
            or rel == FLAT_FILE or (os.path.dirname(rel) == FLAT_DIR and os.path.basename(rel) in DOCUMENTS)
            or (bool(named) and rel in named_documents(named)))


def is_item_path(rel: str, named=()) -> bool:
    """A path whose items count, whatever the layout: an item file rather than an index or a document."""
    base = os.path.basename(rel)
    if rel in named or rel == FLAT_FILE:
        return True
    if rel.startswith((SPEC_DIR + "/functional/", SPEC_DIR + "/non-functional/")):
        return True
    if rel.startswith(SPEC_DIR + "/"):
        return base not in DOCUMENTS and base != INDEX and "/test-cases/" not in rel
    if rel.startswith(STRUCTURED_DIR + "/"):
        return base not in DOCUMENTS and base != "README.md"
    return False


def symlink_on_path(repo: str, rel: str):
    """The first component of REPO/REL that is a symlink, as a repository-relative path, or None."""
    parts = rel.split("/")
    for i in range(1, len(parts) + 1):
        sub = "/".join(parts[:i])
        if os.path.islink(os.path.join(repo, sub)):
            return sub
    return None


def worktree_view(repo: str, named=()) -> dict:
    """{repository-relative path: text} of the Markdown files in the places a specification lives. A symlink
    there (a file, a directory or a parent, whether it resolves inside the repository or not), a file that
    cannot be read, is binary or is over the size cap stops the run."""
    view: dict = {}

    def add(rel: str) -> None:
        full = os.path.join(repo, rel)
        link = symlink_on_path(repo, rel)
        if link:
            raise Unreadable(f"{link} is a symlink; a specification file is a regular file of the project")
        if not inside(full, repo):
            raise Unreadable(f"{rel} resolves outside the repository; a specification file is the project's own")
        text = read_text(full)
        if text is None:
            raise Unreadable(f"{rel} is unreadable, binary or over {MAX_READ} bytes")
        view[rel] = text

    for top in (SPEC_DIR, STRUCTURED_DIR):
        base = os.path.join(repo, top)
        link = symlink_on_path(repo, top)
        if link:
            raise Unreadable(f"{link} is a symlink; a specification directory is the project's own")
        if not os.path.isdir(base):
            continue
        def unreadable(exc: OSError) -> None:
            raise Unreadable(f"a specification directory cannot be read ({exc.strerror or exc.__class__.__name__}: "
                             f"{posix(os.path.relpath(exc.filename or base, repo))})")

        for dirpath, dirnames, filenames in os.walk(base, onerror=unreadable):
            for name in dirnames + filenames:
                if os.path.islink(os.path.join(dirpath, name)):
                    raise Unreadable(f"{posix(os.path.relpath(os.path.join(dirpath, name), repo))} is a symlink; a "
                                     "specification holds regular files and directories only")
            dirnames.sort()
            for name in sorted(filenames):
                if name.endswith(".md"):
                    add(posix(os.path.relpath(os.path.join(dirpath, name), repo)))
    for rel in [FLAT_FILE] + [FLAT_DIR + "/" + d for d in DOCUMENTS] + sorted(named) + named_documents(named):
        if rel not in view and (os.path.isfile(os.path.join(repo, rel)) or os.path.islink(os.path.join(repo, rel))):
            add(rel)
    return view


def commit_view(repo: str, commit: str, named=()) -> dict:
    """The same view read from a commit: one `git ls-tree` and one `git cat-file --batch`, with the size cap
    of the work-tree reader. Raises Unreadable when git fails or a file is over the cap or binary."""
    paths = [SPEC_DIR, STRUCTURED_DIR, FLAT_FILE] + [FLAT_DIR + "/" + d for d in DOCUMENTS] + sorted(named) + \
        named_documents(named)
    code, out = run_git(repo, "ls-tree", "-r", "-z", "-l", commit, "--", *paths)
    if code != 0:
        raise Unreadable(f"git ls-tree {commit} failed in {repo}")
    wanted = []
    for entry in out.split(b"\0"):
        if not entry:
            continue
        meta, _tab, raw = entry.partition(b"\t")
        fields = meta.split()
        rel = os.fsdecode(raw)
        if len(fields) != 4 or fields[1] != b"blob" or not rel.endswith(".md") or not is_spec_path(rel, named):
            continue
        if fields[3].isdigit() and int(fields[3]) > MAX_READ:
            raise Unreadable(f"{rel} at {commit} is over {MAX_READ} bytes")
        wanted.append((rel, fields[2]))
    view: dict = {}
    if not wanted:
        return view
    code, out = run_git(repo, "cat-file", "--batch", stdin=b"".join(oid + b"\n" for _rel, oid in wanted))
    if code != 0:
        raise Unreadable(f"git cat-file --batch failed in {repo}")
    pos = 0
    for rel, oid in wanted:
        end = out.find(b"\n", pos)
        header = out[pos:end].split() if end >= 0 else []
        if len(header) != 3 or header[0] != oid or not header[2].isdigit():
            raise Unreadable(f"git cat-file gave no blob for {rel} at {commit}")
        size = int(header[2])
        text = decode(out[end + 1:end + 1 + size])
        if text is None:
            raise Unreadable(f"{rel} at {commit} is binary")
        view[rel] = text
        pos = end + 1 + size + 1
    return view


def walk_draft(draft: str):
    """([(path relative to the draft, absolute path)] sorted, [problems]): every regular file of the
    draft. A symlink, file or directory, or a special file is a problem and is not listed. A name that
    draft_digest.py refuses (a control, separator or bidi character) and a directory that cannot be read stop
    the run (Unreadable, exit 2), as `digest` does."""
    files, problems = [], []

    def failed(exc: OSError) -> None:
        raise Unreadable(f"a directory of the draft cannot be read ({exc.strerror or exc.__class__.__name__})")

    for dirpath, dirnames, filenames in os.walk(draft, onerror=failed):
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            rel = posix(os.path.relpath(full, draft))
            if DIGEST.UNSAFE_RE.search(rel):
                raise Unreadable(f"the draft holds the name {rel}, which carries a control, separator or bidi character")
            if os.path.islink(full):
                problems.append(rel)
                dirnames.remove(name)
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = posix(os.path.relpath(full, draft))
            if DIGEST.UNSAFE_RE.search(rel):
                raise Unreadable(f"the draft holds the name {rel}, which carries a control, separator or bidi character")
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                problems.append(rel)
                continue
            files.append((rel, full))
    return sorted(files), sorted(problems)


def file_sha256(path: str) -> str:
    """The sha256 of a file, read streamed (no size cap). OSError propagates."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def draft_digest(draft: str):
    """(digest hex, [(path, file sha256)]) of a draft directory, the digest from core/gate/draft_digest.py;
    raises Unreadable for everything it refuses (a symlink or special file, an unsafe name, a directory or
    file that cannot be read, a file swapped during the read)."""
    try:
        return DIGEST.manifest(draft)  # one traversal: the digest and the files it covers
    except DIGEST.DraftError as exc:
        raise Unreadable(str(exc))


def sensitive_in_draft(files, rep) -> set:
    """The draft's files that the external review's sensitive-file rule names (a key, a credentials file, an
    .env file, state, real tfvars), each a FAIL `draft-sensitive`: the apply step would copy it into the
    repository."""
    rule = review_rules().SENSITIVE_RE
    found = set()
    for rel, _full in files:
        if rule.search(rel):
            found.add(rel)
            rep.add("FAIL", "draft-sensitive", f"the draft holds {rel}, a file the sensitive-file rule names; "
                                               "a specification draft never carries keys, credentials or state")
    return found


def draft_view(draft: str, rep, named=(), listed=frozenset()) -> dict:
    """{path relative to the draft directory: text} of the draft's Markdown files; a file that is not a
    specification path FAILs `draft-path`, a symlink or a special file `draft-symlink`, a file the
    sensitive-file rule names `draft-sensitive`."""
    files, problems = walk_draft(draft)
    for rel in problems:
        rep.add("FAIL", "draft-symlink", f"the draft holds {rel}, a symlink or a special file; a draft holds "
                                         "regular files only")
    sensitive = sensitive_in_draft(files, rep)
    view: dict = {}
    for rel, full in files:
        if rel in sensitive:
            continue
        if not is_spec_path(rel, named):
            rep.add("FAIL", "draft-path", f"the draft holds {rel}, which is not a specification path "
                                          f"({SPEC_DIR}/, {STRUCTURED_DIR}/, {FLAT_FILE}, a document beside it "
                                          "or a file named with --spec)")
            continue
        if os.path.basename(rel) == TRACEABILITY:
            rep.add("FAIL", "draft-traceability", f"the draft holds {rel}: the traceability report is never drafted; "
                                                  "the last wave writes it from `spec-layout.py traceability`")
            continue
        if not rel.endswith(".md"):
            # A diagram or another asset: carried by the draft and its digest, and scanned like the rest.
            data = read_bytes(full)
            text = decode(data)
            if text is None:
                if rel not in listed:
                    rep.add("FAIL", "draft-binary", f"the draft holds {rel}, which is binary or over {MAX_READ} bytes "
                                                    "and so cannot be scanned for credentials; name it in the plan's "
                                                    "Specification changes to carry it anyway")
                continue
            kind = review_rules().secret_kind(text)
            if kind:
                rep.add("FAIL", "secret", f"{rel} holds what looks like {kind}; a specification states requirements, "
                                          "never credential values")
            continue
        text = read_text(full)
        if text is None:
            raise Unreadable(f"the draft's {rel} is unreadable, binary or over {MAX_READ} bytes")
        view[rel] = text
    return view


def mask_fences(text: str) -> str:
    """Fenced code and HTML comments blanked, offsets and newlines kept (draft_digest.mask_fences, the one
    rule the approval gate uses too), so neither an example inside a fence nor text inside a comment reads as a
    definition or a plan line."""
    return DIGEST.mask_fences(text)


def parse_items(rel: str, text: str, id_pattern: str) -> list:
    """The items one file defines, in file order: id, title, file, line, struck, text (whitespace
    normalised, the comparison form), body (as written, for reporting and history comparison) and
    semantic (body with fenced code and HTML comments blanked, the form every format and content check
    reads, so a requirement, an Acceptance: or a Source: that is not actually readable in the rendered
    specification can never satisfy a check)."""
    masked = mask_fences(text)
    id_re = re.compile(id_pattern)
    # At the margin only: a nested or indented list line ("  - **SPEC-F002** must run first") is a
    # reference inside an item, not a definition. The group names are unlikely to clash with --id-regex.
    bold_re = re.compile(r"^(?:[-*+][ \t]+)?(?P<ifs_s1>~~)?\*\*(?P<ifs_s2>~~)?[ \t]*(?P<ifs_id>%s)"
                         r"(?P<ifs_title>[^*\n]{0,300}?)\*\*" % id_pattern, re.M)
    marks = []  # (position, heading level or 0 for a bold definition, id or None, struck, title)
    for m in re.finditer(r"^ {0,3}(#{1,6})[ \t]+(.*)$", masked, re.M):
        level, rest = len(m.group(1)), m.group(2)
        found = id_re.search(rest) if 2 <= level <= 5 else None
        if found:
            marks.append((m.start(), level, found.group(0), "~~" in rest[:found.start()], rest[found.end():]))
        else:
            marks.append((m.start(), level, None, False, ""))
    for m in bold_re.finditer(masked):
        if not re.search(r"\w", m.group("ifs_title").replace("~~", "")):
            continue  # "**SPEC-F002**" with no title is a reference, not a definition
        marks.append((m.start(), 0, m.group("ifs_id"), bool(m.group("ifs_s1") or m.group("ifs_s2")),
                      m.group("ifs_title")))
    marks.sort(key=lambda mark: mark[0])
    items = []
    for i, (pos, level, item_id, struck, title) in enumerate(marks):
        if item_id is None:
            continue
        end = len(text)
        for later_pos, later_level, later_id, _struck, _title in marks[i + 1:]:
            if later_id is not None or later_level and (level == 0 or later_level <= level):
                end = later_pos
                break
        body = text[pos:end].rstrip()
        semantic = masked[pos:end].rstrip()
        items.append({"id": item_id, "title": " ".join(title.replace("~~", "").strip(" \t\n—–-:.").split()),
                      "file": rel, "line": text.count("\n", 0, pos) + 1, "struck": struck,
                      "text": " ".join(body.split()), "body": body, "semantic": semantic})
    return items


def source_paths(body: str) -> list:
    """The backticked paths an item's `Source:` names (from the marker to the next field marker)."""
    m = SOURCE_RE.search(body)
    if not m:
        return []
    rest = body[m.end():]
    nxt = FIELD_MARK_RE.search(rest)
    return re.findall(r"`([^`\n]+)`", rest[:nxt.start()] if nxt else rest)


def family_of(item_id: str):
    m = re.match(r"^(.*?)(\d+)$", item_id)
    return (m.group(1), int(m.group(2)), len(m.group(2))) if m else (item_id, 0, 0)


def id_key(item_id: str):
    family, number, _width = family_of(item_id)
    return (family, number)


def document_map(view: dict, layout: str, roots=()) -> dict:
    """{document name: its path or None} for the directories the layout keeps its documents in."""
    if layout == "flat":
        places = {name: [FLAT_DIR + "/" + name] for name in DOCUMENTS}
    elif layout == "structured":
        places = {name: [STRUCTURED_DIR + "/" + name, FLAT_DIR + "/" + name] for name in DOCUMENTS}
    elif layout == "named":
        places = {name: [(r + "/" if r else "") + name for r in roots] for name in DOCUMENTS}
    else:
        places = {name: [SPEC_DIR + "/" + name] for name in DOCUMENTS}
        # The kit layout keeps its test cases one directory down, under another spelling.
        places["TEST-CASES.md"].append(SPEC_DIR + "/test-cases/TEST_CASES.md")
    return {name: next((p for p in paths if p in view), None) for name, paths in places.items()}


def places(view: dict, named=()) -> list:
    """The recognised places that hold specification files (named files apart)."""
    out = []
    if any(p.startswith(SPEC_DIR + "/") and p not in named for p in view):
        out.append(SPEC_DIR)
    if any(p.startswith(STRUCTURED_DIR + "/") and p not in named for p in view):
        out.append(STRUCTURED_DIR)
    if FLAT_FILE in view and FLAT_FILE not in named:
        out.append(FLAT_FILE)
    return out


def classify(view: dict, id_pattern: str, named=(), root=None) -> dict:
    """What specification the view holds: the preferred layout with its files, items, families and
    missing documents, and the other layouts found. `root` (a plan's `Specification root:`) picks one of
    several recognised places; with --spec files the layout is `named`."""
    found = []
    if named:
        files = [p for p in sorted(named) if p in view]
        roots = sorted({os.path.dirname(p) for p in named})
        found.append({"layout": "named", "format": None, "root": os.path.commonpath(roots) if roots else "",
                      "roots": roots, "index": None, "item_files": files})
    spec = sorted(p for p in view if p.startswith(SPEC_DIR + "/") and p not in named)
    if spec:
        index = SPEC_DIR + "/" + INDEX if SPEC_DIR + "/" + INDEX in view else None
        fmt = FORMAT_RE.search(mask_fences(view[index])) if index else None
        dims = [p for p in spec if p.startswith((SPEC_DIR + "/functional/", SPEC_DIR + "/non-functional/"))]
        if fmt:
            name, item_files = "combined", dims
        elif index and dims:
            name, item_files = "kit", dims
        else:
            name = "unstructured"
            item_files = [p for p in spec if os.path.basename(p) not in DOCUMENTS and "/test-cases/" not in p]
        found.append({"layout": name, "format": int(fmt.group(1)) if fmt else None, "root": SPEC_DIR,
                      "index": index, "item_files": item_files})
    structured = sorted(p for p in view if p.startswith(STRUCTURED_DIR + "/") and p not in named)
    if structured:
        index = STRUCTURED_DIR + "/README.md" if STRUCTURED_DIR + "/README.md" in view else None
        item_files = [p for p in structured if p != index and os.path.basename(p) not in DOCUMENTS]
        found.append({"layout": "structured", "format": None, "root": STRUCTURED_DIR, "index": index,
                      "item_files": item_files})
    if FLAT_FILE in view and FLAT_FILE not in named:
        found.append({"layout": "flat", "format": None, "root": FLAT_DIR, "index": FLAT_FILE,
                      "item_files": [FLAT_FILE]})
    for entry in found:
        entry["place"] = FLAT_FILE if entry["layout"] == "flat" else entry["root"]
    if root and not named:
        found.sort(key=lambda entry: entry["place"] != root)
    for entry in found:
        entry["items"] = [item for rel in entry["item_files"] for item in parse_items(rel, view[rel], id_pattern)]
        entry["documents"] = document_map(view, entry["layout"], entry.get("roots", ()))
        entry["missing_documents"] = [name for name in DOCUMENTS if not entry["documents"][name]]
    if not found:
        primary = {"layout": "none", "format": None, "root": None, "index": None, "item_files": [], "items": [],
                   "documents": {name: None for name in DOCUMENTS}, "missing_documents": list(DOCUMENTS)}
        others = []
    else:
        primary, others = found[0], found[1:]
    families: dict = {}
    for item in primary["items"]:
        family, number, width = family_of(item["id"])
        slot = families.setdefault(family, {"count": 0, "highest": 0, "width": 0})
        slot["count"] += 1
        slot["highest"] = max(slot["highest"], number)
        slot["width"] = max(slot["width"], width)
    if primary["layout"] in ("none", "combined"):
        for family in ("SPEC-F", "SPEC-NF"):
            families.setdefault(family, {"count": 0, "highest": 0, "width": 3})
    for family, slot in families.items():
        slot["next"] = "%s%0*d" % (family, slot["width"], slot["highest"] + 1)
    primary = dict(primary, families={f: {"count": s["count"], "next": s["next"]} for f, s in sorted(families.items())})
    primary["other_layouts"] = [{"layout": o["layout"], "root": o["root"], "items": len(o["items"])} for o in others]
    # Several recognised places, whether or not they define items yet: which one is the specification is the
    # user's answer (--spec, or the plan's `Specification root:` line), never this script's preference.
    primary["places"] = places(view, named)
    primary["ambiguous"] = not named and not (root and root in primary["places"]) and len(primary["places"]) > 1
    return primary


def item_index(layout: dict, rep) -> dict:
    """{id: item}; a second definition of an ID FAILs `id-duplicate` and the first one is kept."""
    out: dict = {}
    for item in layout["items"]:
        if item["id"] in out:
            first = out[item["id"]]
            rep.add("FAIL", "id-duplicate", f"{item['id']} is defined twice: {first['file']}:{first['line']} and "
                                            f"{item['file']}:{item['line']}")
            continue
        out[item["id"]] = item
    return out


def delta_of(before: dict, after: dict) -> dict:
    """The item delta: new, changed and struck IDs, and the IDs that are no longer defined."""
    new = sorted((i for i in after if i not in before), key=id_key)
    dropped = sorted((i for i in before if i not in after), key=id_key)
    struck = sorted((i for i in after if after[i]["struck"] and (i not in before or not before[i]["struck"])),
                    key=id_key)
    changed = sorted((i for i in after if i in before and i not in struck and after[i]["text"] != before[i]["text"]),
                     key=id_key)
    return {"new": [i for i in new if i not in struck], "changed": changed, "struck": struck, "dropped": dropped}


def load_plan(plan_path: str, id_pattern: str) -> dict:
    """What check reads from a plan: its Specification changes section (records, the baseline count, the
    deleted paths and the digest lines) and the paths its tasks own."""
    text = read_text(plan_path)
    if text is None:
        raise Unreadable(f"cannot read {plan_path}")
    body = DIGEST.specification_changes(text)  # fences and comments blanked: the parse the digest line comes from
    plan = {"path": plan_path, "section": body is not None, "records": {}, "duplicates": [], "baseline": None,
            "deleted": [], "digest": None, "digest_error": None, "root": None, "listed": set(), "owned": set(),
            "owned_deleted": set()}
    try:
        plan["digest"] = DIGEST.plan_digest(text)
    except DIGEST.DraftError as exc:
        kind = "duplicate" if "more than one" in str(exc) else "misplaced" if "is outside" in str(exc) else "malformed"
        plan["digest_error"] = (kind, str(exc))
    id_re = re.compile(id_pattern)
    for line in (body or "").splitlines():
        plan["listed"].update(os.path.normpath(p).replace(os.sep, "/") for p in re.findall(r"`([^`\n]+)`", line))
        if DIGEST.LABEL_RE.match(line):
            continue  # draft_digest.py reads it
        chosen = ROOT_LINE_RE.match(line)
        if chosen:
            plan["root"] = ROOTS.get(chosen.group(1).strip(), chosen.group(1).strip())
            continue
        deleted = DELETED_RE.match(line)
        if deleted:
            plan["deleted"].append(os.path.normpath(deleted.group(1).strip()).replace(os.sep, "/"))
            continue
        m = RECORD_RE.match(line)
        token = m.group(1).strip("*`") if m else ""  # the ID may be bold or in backticks
        if m and id_re.fullmatch(token):
            named_file = re.search(r"`([^`\n]+)`", line[m.end():]) or \
                re.match(r"\s+(?:—|–|-|:)\s+([^\s`]+\.md)(?=\s|$)", line[m.end():])
            record = {"kind": m.group(2).lower(),
                      "file": os.path.normpath(named_file.group(1)).replace(os.sep, "/") if named_file else None}
            if token in plan["records"]:
                plan["duplicates"].append(token)
            else:
                plan["records"][token] = record
            continue
        b = BASELINE_RE.match(line)
        if b:
            plan["baseline"] = int(b.group(1))
    # The tasks' Owns, read with spec-trace's own parser; its findings are spec-trace's to report.
    for task in TRACE.parse_tasks(text, id_re, TRACE.Report()).values():
        for owned in task["owns"]:
            (plan["owned_deleted"] if owned["deleted"] else plan["owned"]).add(owned["path"])
    return plan


def owned_by(path: str, owned) -> bool:
    return any(path == o or path.startswith(o.rstrip("/") + "/") for o in owned)


def is_test(rel: str) -> bool:
    return TRACE.is_test(rel) or rel.endswith(EXTRA_TEST_SUFFIXES)


def list_files(repo: str) -> list:
    """Repository-relative paths of the files the report searches: tracked files and untracked files that
    the repository's own .gitignore files do not exclude. The user's global excludes file and
    .git/info/exclude are not used, so the same tree gives the same list on every machine."""
    code, out = run_git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-per-directory=.gitignore")
    if code == 0:
        return sorted({os.fsdecode(p) for p in out.split(b"\0") if p})
    return sorted(posix(os.path.relpath(str(p), repo)) for p in Path(repo).rglob("*")
                  if p.is_file() and ".git" not in p.parts)


def text_lines(path: str, rel: str):
    """The lines of a text file, read streamed; None for a binary file (a NUL in its first 8 KiB). A file that
    cannot be read stops the run, so a report is never printed from part of the repository."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8192)
            if b"\0" in head:
                return None
            data = head + fh.read()
    except OSError as exc:
        raise Unreadable(f"{rel} cannot be read ({exc.strerror or exc.__class__.__name__}); the report would be partial")
    return data.decode("utf-8", errors="replace").splitlines()


def citations(repo: str, ids: list, named=()) -> dict:
    """{id: {"tests": {path: citing lines}, "code": {path: citing lines}}} over the repository's files.
    Markdown, plans, lock files, build output and caches (spec-external-review.py EXCLUDE_RE), the files the
    sensitive-file rule names (SENSITIVE_RE), the specification itself and ai-planning/ are not searched; a
    file that resolves outside the repository is not read, a binary file is skipped, and a file that cannot
    be read stops the run."""
    found = {item_id: {"tests": {}, "code": {}} for item_id in ids}
    if not ids:
        return found
    exact = {item_id: re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(item_id)) for item_id in ids}
    any_id = re.compile("|".join(re.escape(item_id) for item_id in sorted(ids, key=len, reverse=True)))
    rules = review_rules()
    for rel in list_files(repo):
        if rel.startswith("ai-planning/") or rel.endswith(NOT_SEARCHED_SUFFIXES) or is_spec_path(rel, named) \
                or rules.EXCLUDE_RE.search(rel) or rules.SENSITIVE_RE.search(rel):
            continue
        full = os.path.join(repo, rel)
        try:
            mode = os.lstat(full).st_mode
        except FileNotFoundError:
            continue  # listed by git but deleted in the work tree
        except OSError as exc:  # an unreadable directory on the way: the report would be partial
            raise Unreadable(f"{rel} cannot be examined ({exc.strerror or exc.__class__.__name__}); the report "
                             "would be partial")
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or not inside(full, repo):
            continue
        lines = text_lines(full, rel)
        if lines is None:
            continue
        kind = "tests" if is_test(rel) else "code"
        for line in lines:
            if not any_id.search(line):
                continue
            for item_id, rx in exact.items():
                if rx.search(line):
                    found[item_id][kind][rel] = found[item_id][kind].get(rel, 0) + 1
    return found


def render_traceability(layout: dict, items: dict, cited: dict) -> str:
    """TRACEABILITY.md for the items. No heading carries an ID, so the report never defines an item when
    it is passed to spec-trace.py with the specification files."""
    live = [i for i in sorted(items, key=id_key) if not items[i]["struck"]]
    struck = [i for i in sorted(items, key=id_key) if items[i]["struck"]]
    untested = [i for i in live if not cited[i]["tests"]]
    groups: dict = {}
    for item_id in live:
        family = family_of(item_id)[0]
        title = {"SPEC-F": "Functional items", "SPEC-NF": "Non-functional items"}.get(family, f"Items {family}n")
        groups.setdefault(title, []).append(item_id)
    lines = ["# Traceability report", "",
             f"{GENERATED_MARK} (`spec-layout.py traceability`) from the specification items under",
             f"{code_span((layout['root'] or '.') + '/')} and the item IDs cited in the repository's tests and code. Do not edit by hand;",
             "regenerate it after the tests or the items change.", "",
             "## Summary", "",
             f"- Items: {len(live)}" + (f", and {len(struck)} struck" if struck else ""),
             f"- Items cited by at least one test: {len(live) - len(untested)} of {len(live)}",
             "- Items cited by no test: " + (", ".join(untested) if untested else "none")]
    order = [t for t in ("Functional items", "Non-functional items") if t in groups]
    order += sorted(t for t in groups if t not in order)
    for title in order:
        lines += ["", f"## {title}"]
        for item_id in groups[title]:
            tests, code = cited[item_id]["tests"], cited[item_id]["code"]
            name = safe(f"{item_id} {items[item_id]['title']}".strip()).replace("*", "\\*")
            lines += ["", f"**{name}** — {len(tests)} test file{'s' if len(tests) != 1 else ''}, "
                          f"{len(code)} code file{'s' if len(code) != 1 else ''}"]
            for label, hits in (("Test", tests), ("Code", code)):
                lines += [f"- {label}: {code_span(p)} ({n})" for p, n in sorted(hits.items())]
    if struck:
        lines += ["", "## Struck items", "", "- " + ", ".join(struck)]
    return "\n".join(lines) + "\n"


def check_format(layout: dict, items: dict, view: dict, delta: dict, repo: str, draft_files: dict,
                 before_view: dict, owned, id_pattern: str, drafting: bool, rep) -> None:
    combined = layout["layout"] == "combined"
    touched = set(delta["new"]) | set(delta["changed"])
    for item_id, item in sorted(items.items(), key=lambda kv: id_key(kv[0])):
        where = f"{item_id} ({item['file']}:{item['line']})"
        if not combined and item_id not in touched:
            continue  # an existing layout is extended in its own format: only what this change writes is judged
        for path in source_paths(item["semantic"]):
            if PATTERN_CHARS_RE.search(path):
                continue  # a pattern, not a path
            normal = os.path.normpath(path).replace(os.sep, "/")
            if os.path.isabs(path) or normal == ".." or normal.startswith("../"):
                rep.add("FAIL", "source-missing", f"{where}: its Source names `{path}`, which leaves the repository")
            elif not os.path.lexists(os.path.join(repo, normal)) and not owned_by(normal, owned):
                rep.add("FAIL", "source-missing", f"{where}: its Source names `{path}`, which neither exists nor "
                                                  "is created by a task of the plan")
        if item["struck"]:
            continue
        level = "FAIL" if combined else "WARN"
        family = family_of(item_id)[0]
        wanted = {"SPEC-F": "/functional/", "SPEC-NF": "/non-functional/"}.get(family)
        if wanted and layout["layout"] in ("combined", "kit") and wanted not in "/" + item["file"]:
            rep.add(level, "misplaced", f"{where}: {family}nnn items live under {SPEC_DIR}{wanted}")
        if combined and not KEYWORD_RE.search(item["semantic"]):
            rep.add("FAIL", "statement", f"{where}: the item states no requirement (MUST or SHOULD)")
        if not ACCEPTANCE_RE.search(item["semantic"]):
            rep.add(level, "acceptance", f"{where}: the item has no Acceptance: check")
    for rel, text in sorted(draft_files.items()):
        for number, line in TRACE.added_lines(text, before_view.get(rel, "")):
            if STUB_WORDING_RE.search(line):
                rep.add("FAIL", "stub-wording", f"{rel}:{number}: {line.strip()[:100]} (an unknown goes to the "
                                                "open questions; this wording fails the code check)")
                break
    if not combined:
        return
    # A combined layout is recognised by its index's format line, so the index always exists here.
    index_text = mask_fences(view[layout["index"]])
    for item_id in sorted(items, key=id_key):
        if not TRACE.id_cited(item_id, index_text):
            rep.add("FAIL", "index-unlisted", f"{item_id} ({items[item_id]['file']}) is not named in {layout['index']}")
    for item_id in sorted({m.group(0) for m in re.finditer(id_pattern, index_text)}, key=id_key):
        if item_id not in items:
            rep.add("FAIL", "index-unknown", f"{layout['index']} names {item_id}, which no item file defines")
    for name in DOCUMENTS:
        path = layout["documents"][name]
        if drafting and name == TRACEABILITY and not path:
            continue  # never drafted: the last wave writes it once the code exists
        if not path or not view[path].strip():
            rep.add("FAIL", "document-missing", f"{SPEC_DIR}/{name} is missing or empty")


def check_secrets(view: dict, before_view, draft_files: dict, rep) -> None:
    """No specification text that looks like a credential: the draft's files and the files the change
    added or changed FAIL, an untouched file is a WARN. The kind is named, never the value."""
    secret_kind = review_rules().secret_kind
    for rel, text in sorted(view.items()):
        kind = secret_kind(text)
        if not kind:
            continue
        touched = rel in draft_files or before_view is None or before_view.get(rel) != text
        rep.add("FAIL" if touched else "WARN", "secret",
                f"{rel} holds what looks like {kind}; a specification states requirements, never credential "
                "values" + ("" if touched else " (the change does not touch this file)"))


def check_plan_records(plan: dict, delta: dict, before_layout: dict, items: dict, repo: str, has_draft: bool,
                       rep) -> None:
    records = {i: r["kind"] for i, r in plan["records"].items()}
    baseline = plan["baseline"]
    for item_id in sorted(set(plan["duplicates"]), key=id_key):
        rep.add("FAIL", "record-duplicate", f"the plan records {item_id} more than once; one record per item")
    for item_id, record in sorted(plan["records"].items(), key=lambda kv: id_key(kv[0])):
        if item_id not in items:
            continue  # change-unbacked, below
        if not record["file"]:
            rep.add("FAIL", "record-file", f"the plan's record of {item_id} names no specification file")
        elif record["file"] != items[item_id]["file"]:
            rep.add("FAIL", "record-file", f"the plan records {item_id} in {record['file']}, but "
                                           f"{items[item_id]['file']} holds it")
    if not plan["section"]:
        if has_draft:
            rep.add("FAIL", "plan-section", "the plan has a specification draft but no '## Specification changes' "
                                            "section (one record per new, changed or struck item, and the draft digest)")
        else:
            rep.add("WARN", "plan-section", "the plan has no '## Specification changes' section, so it was drafted "
                                            "before specification handling")
    kinds = {i: kind for kind in ("new", "changed", "struck") for i in delta[kind]}
    if not plan["section"] and not has_draft:
        # A plan drafted before specification handling could change an item with the user's agreement (0.2.0,
        # contract section 10): reported for the user to confirm, not failed.
        for item_id, kind in sorted(kinds.items(), key=lambda kv: id_key(kv[0])):
            rep.add("WARN", "change-legacy", f"{item_id} is {kind} in the specification under a plan drafted before "
                                             "specification handling: confirm with the user that the change was agreed, "
                                             "as the 0.2.0 contract's section 10 required")
        return
    covered = []
    for item_id, kind in sorted(kinds.items(), key=lambda kv: id_key(kv[0])):
        if records.get(item_id) == kind:
            continue
        if item_id in records:
            rep.add("FAIL", "change-unlisted", f"{item_id} is {kind} in the specification, but the plan records it "
                                               f"as {records[item_id]}")
        elif kind == "new" and baseline is not None:
            covered.append(item_id)
        else:
            rep.add("FAIL", "change-unlisted", f"{item_id} is {kind} in the specification, but the plan's "
                                               "Specification changes do not record it")
    for item_id, kind in sorted(records.items(), key=lambda kv: id_key(kv[0])):
        if item_id not in kinds:
            rep.add("FAIL", "change-unbacked", f"the plan records {item_id} as {kind}, but the specification "
                                               "shows no such change")
    if baseline is None:
        return
    if before_layout["layout"] != "none":
        rep.add("FAIL", "baseline-existing", f"the plan records a baseline, but the project already keeps a "
                                             f"specification ({before_layout['layout']}, {before_layout['root']}/)")
    if baseline != len(covered):
        rep.add("FAIL", "baseline-count", f"the plan's baseline record says {baseline} items; {len(covered)} new "
                                          "items have no record of their own")
    for item_id in covered:
        paths = [p for p in source_paths(items[item_id]["semantic"]) if not PATTERN_CHARS_RE.search(p)]
        if not any(os.path.lexists(os.path.join(repo, os.path.normpath(p))) for p in paths):
            rep.add("FAIL", "baseline-unsourced", f"{item_id} is a baseline item but names no existing Source: path "
                                                  "(a baseline item says which files evidence it)")


def check_deletions(plan: dict, repo: str, named, live: bool, rep) -> None:
    for path in plan["deleted"]:
        if not is_spec_path(path, named) or path.startswith("../") or os.path.isabs(path):
            rep.add("FAIL", "deletion-path", f"the plan deletes `{path}`, which is not a specification path")
            continue
        if path not in plan["owned_deleted"]:
            rep.add("FAIL", "deletion-unowned", f"the plan deletes `{path}`, but no task owns it as "
                                                f"`{path}` (deleted)")
        if live and os.path.lexists(os.path.join(repo, path)):
            rep.add("FAIL", "deletion-not-applied", f"the plan deletes `{path}`, which still exists")


def check_digest(plan: dict, draft: str, rep) -> None:
    """The plan's one `Draft digest:` line (draft_digest.plan_digest) against the draft as it is now
    (draft_digest.digest)."""
    if plan["digest_error"]:
        kind, reason = plan["digest_error"]
        rep.add("FAIL", "draft-digest-" + kind, reason)
        return
    if not plan["digest"]:
        rep.add("FAIL", "draft-digest-missing", "the plan's Specification changes carry no 'Draft digest: sha256 "
                                                "<hex>' line; run `spec-layout.py digest` on the draft")
        return
    try:
        current = DIGEST.digest(draft)
    except DIGEST.DraftError as exc:
        rep.add("FAIL", "draft-digest-mismatch", str(exc))
        return
    if current != plan["digest"]:
        rep.add("FAIL", "draft-digest-mismatch", f"the draft's digest is sha256 {current}, the plan records "
                                                 f"{plan['digest']}: the draft changed after the plan was written, so it "
                                                 "is not the draft the approval covers")


def check_applied(draft: str, repo: str, rep) -> None:
    """Every file of the approved draft is in the repository byte for byte."""
    files, problems = walk_draft(draft)
    for rel in problems:
        rep.add("FAIL", "draft-symlink", f"the draft holds {rel}, a symlink or a special file")
    sensitive_in_draft(files, rep)
    for rel, full in files:
        target = os.path.join(repo, rel)
        try:
            regular = stat.S_ISREG(os.lstat(target).st_mode) and inside(target, repo)
            same = regular and file_sha256(target) == file_sha256(full)
            why = "changed after the copy: a drafted file is frozen at approval, and a change to it is an amendment" \
                if regular else "not a regular file of the repository"
        except OSError as exc:
            same, why = False, f"cannot be read or is missing ({exc.strerror or exc.__class__.__name__})"
        if not same:
            rep.add("FAIL", "draft-not-applied", f"{rel} is not its approved draft byte for byte ({why})")


def resolve_commit(repo: str, args, plan, rep):
    """('commit', sha), ('empty', None) for a git work tree with no commit yet, or ('none', None) outside git.
    The commit is --base, else the plan ledger's ## Baseline commit, else HEAD."""
    code, out = run_git(repo, "rev-parse", "--is-inside-work-tree")
    if code != 0 or out.strip() != b"true":
        return "none", None

    def commit(ref: str):
        code, out = run_git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        sha = out.strip().decode("ascii", errors="replace")
        return sha if code == 0 and sha else None

    if args.base:
        sha = commit(args.base)
        if not sha:
            rep.add("FAIL", "baseline", f"--base {args.base} is not a commit of {repo}; nothing was compared with it")
            return "none", None
        return "commit", sha
    if plan:
        for token in re.findall(r"\b[0-9a-f]{7,40}\b", TRACE.ledger_sections(plan["path"])["baseline"]):
            sha = commit(token)
            if sha:
                return "commit", sha
    sha = commit("HEAD")
    return ("commit", sha) if sha else ("empty", None)


def build(args, rep, plan, need_before: bool):
    """(checked view, its layout, before view or None, before layout or None, the draft's files)."""
    repo, named = args.repo, args.spec
    work = worktree_view(repo, named)
    deleted = set(plan["deleted"]) if plan else set()
    base_cache: dict = {}

    def base_view():
        if "view" not in base_cache:
            kind, sha = resolve_commit(repo, args, plan, rep)
            base_cache["view"] = commit_view(repo, sha, named) if kind == "commit" else {} if kind == "empty" else None
        return base_cache["view"]

    draft_files: dict = {}
    extra_before = set()  # IDs the base commit defines in the drafted and deleted paths (id-dropped is judged over both)
    if args.draft:
        draft_files = draft_view(args.draft, rep, named, plan["listed"] if plan else frozenset())
        after_view = {p: t for p, t in work.items() if p not in deleted}
        after_view.update(draft_files)
        before_view = dict(work)
        if need_before:
            # The earlier state is the work tree, except for the paths this change writes: a drafted file the
            # work tree already holds byte for byte and a deleted path already gone (a resumed run), and, once
            # any of that is in place, the files a task of the plan owns outside the draft (the traceability
            # report and the living documents the last wave writes). Those come from the base commit.
            applied = [p for p, t in draft_files.items() if work.get(p) == t]
            gone = [p for p in deleted if p not in work]
            base = base_view() if (draft_files or deleted) else None
            if base is None and (applied or gone):
                rep.add("WARN", "baseline", "not a git work tree: drafted files already in place were compared "
                                            "with themselves")
            if base is not None:
                synced = [p for p in work if p not in draft_files and plan and owned_by(p, plan["owned"])] \
                    if (applied or gone) else []
                for p in applied + gone + synced:
                    if p in base:
                        before_view[p] = base[p]
                    else:
                        before_view.pop(p, None)
                for p in set(draft_files) | deleted:
                    if p in base and is_item_path(p, named):
                        extra_before.update(item["id"] for item in parse_items(p, base[p], args.id_regex))
    else:
        after_view, before_view = work, None
        if need_before:
            before_view = base_view()
            if before_view is None and not rep.failed:
                rep.add("WARN", "baseline", "not a git work tree: dropped IDs and the item delta were not checked")
    root = plan["root"] if plan else None
    after = classify(after_view, args.id_regex, named, root)
    before = classify(before_view, args.id_regex, named, root) if before_view is not None else None
    if before is not None:
        before["extra_ids"] = extra_before
    return after_view, after, before_view, before, draft_files


def candidates(repo: str, named, id_pattern: str) -> list:
    """Files outside the recognised places that may hold the project's specification."""
    found = []
    for rel in list_files(repo):
        parts = rel.split("/")
        if not rel.lower().endswith(CANDIDATE_SUFFIXES) or any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        if is_spec_path(rel, named):
            continue
        stem = os.path.splitext(parts[-1])[0]
        reasons = []
        if CANDIDATE_NAME_RE.search(stem):
            reasons.append("its name")
        full = os.path.join(repo, rel)
        text = read_text(full) if os.path.isfile(full) and inside(full, repo) else None
        count = len(parse_items(rel, text, id_pattern)) if text else 0
        if count:
            reasons.append(f"defines {count} item{'s' if count != 1 else ''}")
        if reasons:
            checkable = rel.endswith(".md")
            reason = " and ".join(reasons) + ("" if checkable else "; not checkable: convert it to Markdown or name "
                                                                   "a Markdown file with --spec")
            found.append({"path": rel, "items": count, "reason": reason, "checkable": checkable})
    return found


def cmd_detect(args, rep) -> int:
    layout = classify(worktree_view(args.repo, args.spec), args.id_regex, args.spec)
    items = [{k: item[k] for k in ("id", "title", "file", "line", "struck")} for item in layout["items"]]
    cands = candidates(args.repo, args.spec, args.id_regex)
    result = {"repo": args.repo, "layout": layout["layout"], "format": layout["format"], "root": layout["root"],
              "index": layout["index"], "item_files": layout["item_files"], "documents": layout["documents"],
              "missing_documents": layout["missing_documents"], "families": layout["families"], "items": items,
              "other_layouts": layout["other_layouts"], "ambiguous": layout["ambiguous"], "candidates": cands,
              "findings": rep.lines}
    if args.json:
        emit(json.dumps(result, indent=1) + "\n")
        return 0
    lines = [f"{line['level']} {line['check']}: {line['detail']}" for line in rep.lines]
    if layout["layout"] == "none":
        lines.append("layout: none (no specification found; next IDs SPEC-F001 and SPEC-NF001)")
    else:
        fmt = f", format {layout['format']}" if layout["format"] else ""
        lines.append(f"layout: {layout['layout']}{fmt} ({layout['root'] or '.'}/)")
        lines.append(f"index: {layout['index'] or 'none'}")
        lines.append(f"item files: {', '.join(layout['item_files']) or 'none'}")
        struck = sum(1 for item in items if item["struck"])
        lines.append(f"items: {len(items)}" + (f" ({struck} struck)" if struck else ""))
        for item in items:
            lines.append(f"item: {item['id']} {item['title']} ({item['file']}:{item['line']})"
                         + (" (struck)" if item["struck"] else ""))
        for family, slot in layout["families"].items():
            lines.append(f"family {family}: {slot['count']} items, next free {slot['next']}")
    lines.append("missing documents: " + (", ".join(layout["missing_documents"]) or "none"))
    for other in layout["other_layouts"]:
        lines.append(f"also found: {other['layout']} ({other['root']}/, {other['items']} items)")
    if layout["ambiguous"]:
        lines.append(f"ambiguous: specification files in {', '.join(layout['places'])}; ask which one is the "
                     "specification (--spec, or the plan's 'Specification root:' line)")
    for cand in cands:
        lines.append(f"candidate: {cand['path']} ({cand['reason']}; not a recognised layout)")
    if layout["layout"] == "none" and cands:
        lines.append("candidates found: ask whether one of them is the project's specification before deriving one")
    emit("\n".join(safe(line) for line in lines) + "\n")
    return 0


def cmd_survey(args, rep) -> int:
    """The files a baseline may read, and the ones it may not, with the reason."""
    rules = review_rules()
    readable, withheld = [], []
    for rel in list_files(args.repo):
        full = os.path.join(args.repo, rel)
        parts = rel.split("/")
        if rules.SENSITIVE_RE.search(rel):
            reason = "sensitive file (the external review's rule): never read"
        elif rules.EXCLUDE_RE.search(rel) or any(p in SKIP_DIRS for p in parts[:-1]):
            reason = "lock file, build output, cache, vendored or planning file"
        elif not os.path.isfile(full) or os.path.islink(full) or not inside(full, args.repo):
            reason = "not a regular file of the repository"
        elif read_text(full) is None:
            reason = f"binary, unreadable or over {MAX_READ} bytes"
        else:
            readable.append(rel)
            continue
        withheld.append({"path": rel, "reason": reason})
    if args.json:
        emit(json.dumps({"repo": args.repo, "read": readable, "withheld": withheld}, indent=1) + "\n")
        return 0
    lines = [f"read: {safe(p)}" for p in readable] + [f"withheld: {safe(w['path'])} ({w['reason']})" for w in withheld]
    lines.append(f"survey: {len(readable)} files to read, {len(withheld)} withheld")
    emit("\n".join(lines) + "\n")
    return 0


def cmd_digest(args, rep) -> int:
    digest, files = draft_digest(args.target)  # draft_digest.py's digest; its refusals exit 2
    if args.json:
        emit(json.dumps({"draft": args.target, "digest": digest,
                         "files": [{"path": p, "sha256": s} for p, s in files]}, indent=1) + "\n")
    else:
        emit(f"Draft digest: sha256 {digest}\n")
    return 0


def cmd_check(args, rep) -> int:
    plan = load_plan(args.plan, args.id_regex) if args.plan else None
    view, layout, before_view, before, draft_files = build(args, rep, plan, need_before=True)
    sibling = os.path.splitext(args.plan)[0] + ".spec" if plan else None
    live_draft = sibling if plan and not args.draft and os.path.isdir(sibling) else None
    delta = {"new": [], "changed": [], "struck": [], "dropped": []}
    if layout["layout"] == "none":
        rep.add("FAIL", "no-specification", f"{args.repo} holds no specification"
                + (" and the draft adds none" if args.draft else "") + "; nothing was checked")
    else:
        items = item_index(layout, rep)
        if layout["ambiguous"]:
            rep.add("FAIL", "layout-ambiguous", f"specification files in {', '.join(layout['places'])}: name the "
                                                "specification with --spec or the plan's 'Specification root: `<place>`' line")
        if before is not None:
            delta = delta_of({i["id"]: i for i in before["items"]}, items)
            delta["dropped"] = sorted(set(delta["dropped"]) | (before.get("extra_ids", set()) - set(items)), key=id_key)
            for item_id in delta["dropped"]:
                rep.add("FAIL", "id-dropped", f"{item_id} was defined before and is no longer defined; IDs are "
                                              "never removed or renumbered (strike the item through instead)")
            if before["layout"] == "none" and layout["layout"] != "combined":
                rep.add("FAIL", "new-layout", f"a new specification uses the combined layout: {SPEC_DIR}/{INDEX} "
                                              "with the line 'Format: implement-from-spec specification format 1'")
        owned = plan["owned"] if plan else set()
        check_format(layout, items, view, delta, args.repo, draft_files, before_view or {}, owned, args.id_regex,
                     bool(args.draft), rep)
        check_secrets(view, before_view, draft_files, rep)
        trace_path = layout["documents"][TRACEABILITY]
        trace_target = trace_path or ((layout["root"] + "/" if layout["root"] else "") + TRACEABILITY)
        generated = bool(trace_path) and GENERATED_MARK in view[trace_path]
        if trace_path and not generated and view[trace_path].strip():
            rep.add("WARN", "traceability-project", f"{trace_path} has no generated mark: the project's own report, "
                                                    "which spec-layout neither checks nor regenerates")
        if generated and not args.draft:
            current = render_traceability(layout, items, citations(args.repo, sorted(items, key=id_key), args.spec))
            if current != view[trace_path].replace("\r\n", "\n"):
                rep.add("FAIL", "traceability-stale", f"{trace_path} differs from what `spec-layout.py traceability` "
                                                      "prints now; regenerate it")
        if plan:
            if before is not None:
                check_plan_records(plan, delta, before, items, args.repo, bool(args.draft or live_draft
                                                                               or plan["digest"]), rep)
            else:
                rep.add("WARN", "baseline", "the plan's Specification changes were not compared: no earlier state")
            if plan["section"] and (generated or layout["layout"] == "combined") \
                    and not owned_by(trace_target, plan["owned"]):
                rep.add("FAIL", "traceability-unowned", f"{trace_target} is generated, and the code and tests of the "
                                                        "change move its citations, but no task owns it (the last-wave "
                                                        "specification task)")
            check_deletions(plan, args.repo, args.spec, not args.draft, rep)
    if plan and not plan["section"] and plan["digest_error"]:
        kind, reason = plan["digest_error"]
        rep.add("FAIL", "draft-digest-" + kind, reason)
    if plan and plan["section"]:
        if args.draft:
            check_digest(plan, args.draft, rep)
        elif live_draft:
            check_digest(plan, live_draft, rep)
            check_applied(live_draft, args.repo, rep)
        elif plan["digest"] or plan["digest_error"]:
            rep.add("FAIL", "draft-missing", f"the plan records a draft digest, but {sibling} does not exist")
    fails = sum(1 for line in rep.lines if line["level"] == "FAIL")
    if args.json:
        emit(json.dumps({"mode": "check", "repo": args.repo, "layout": layout["layout"], "failed": rep.failed,
                         "delta": delta, "findings": rep.lines}, indent=1) + "\n")
    else:
        lines = [f"{line['level']} {line['check']}: {line['detail']}" for line in rep.lines]
        lines.append("delta: " + "; ".join(f"{len(delta[k])} {k}" + (f" ({', '.join(delta[k])})" if delta[k] else "")
                                           for k in ("new", "changed", "struck")))
        lines.append(f"spec-layout check: {fails} FAIL, {len(rep.lines) - fails} WARN")
        emit("\n".join(safe(line) for line in lines) + "\n")
    return 1 if rep.failed else 0


def project_report(repo: str, target: str) -> bool:
    """True when the work-tree file at TARGET (repository-relative) is the project's own report: it exists, is
    not empty and carries no GENERATED_MARK. A missing or empty file, or one with the mark, is the plugin's to
    (re)generate. Raises Unreadable when the file is there but cannot be judged (not a regular file, unreadable
    or over MAX_READ bytes): an unjudged file is never treated as replaceable."""
    path = os.path.join(repo, target)
    if not os.path.lexists(path):
        return False
    if not os.path.isfile(path):
        raise Unreadable(f"{target} is not a regular file; the report's place must be a file or nothing")
    data = read_bytes(path)
    if data is None:
        raise Unreadable(f"{target} is unreadable or over {MAX_READ} bytes, so whether it is the project's own "
                         "report cannot be told; nothing was printed")
    return bool(data) and GENERATED_MARK.encode("utf-8") not in data


def cmd_traceability(args, rep) -> int:
    plan = load_plan(args.plan, args.id_regex) if args.plan else None  # its `Specification root:` line only
    _view, layout, _bv, _before, _draft = build(args, rep, plan, need_before=False)
    if layout["layout"] == "none":
        raise Unreadable(f"{args.repo} holds no specification to report on")
    target = layout["documents"][TRACEABILITY] or ((layout["root"] + "/" if layout["root"] else "") + TRACEABILITY)
    link = symlink_on_path(args.repo, target)
    if link:
        raise Unreadable(f"{link} is a symlink: the report's place, {target}, must be a regular path of the project, "
                         "or a move into it would land elsewhere")
    # The redirect-and-move recipe replaces the work-tree file, so it is the one judged, with --draft too: a
    # report without the mark is the project's own (contract, section 13) and nothing is printed to replace it.
    if project_report(args.repo, target):
        raise Unreadable(f"{target} has no generated mark (\"{GENERATED_MARK}\"): it is the project's own report, "
                         "which spec-layout.py never regenerates; nothing was printed")
    items = item_index(layout, rep)
    report = render_traceability(layout, items, citations(args.repo, sorted(items, key=id_key), args.spec))
    if rep.lines:
        emit("".join(safe(f"{line['level']} {line['check']}: {line['detail']}") + "\n" for line in rep.lines), sys.stderr)
    if rep.failed:
        return 1  # nothing on stdout: a redirect never receives part of a report
    emit(report)
    return 0


def repo_relative(parser, repo: str, raw: str, what: str) -> str:
    normal = os.path.normpath(raw).replace(os.sep, "/")
    if os.path.isabs(raw) or normal == ".." or normal.startswith("../") or not normal.endswith(".md"):
        parser.error(f"{what} {raw}: a repository-relative Markdown path")
    if not inside(os.path.join(repo, normal), repo):
        parser.error(f"{what} {raw} resolves outside the repository")
    return normal


# Each mode's options; build_parser() gives every mode its own subparser, so `<mode> --help` lists only these
# and an option another mode owns is a usage error (exit 2) rather than silently ignored.
MODE_OPTIONS = {
    "detect": ("repo", "spec", "id-regex", "json"),
    "check": ("repo", "draft", "plan", "base", "spec", "id-regex", "json"),
    "traceability": ("repo", "plan", "draft", "spec", "id-regex"),
    "digest": ("target", "json"),
    "survey": ("repo", "json"),
}
MODE_HELP = {
    "detect": "report which specification the repository keeps, and candidates kept elsewhere",
    "check": "check the specification's format and item history, and bind a draft to its plan",
    "traceability": "print TRACEABILITY.md for the checked tree (nothing when the report is the project's own)",
    "digest": "print the plan's 'Draft digest:' line for a specification draft",
    "survey": "list the files a baseline specification may read, and the ones withheld",
}
# The attributes the cmd_* functions read, for the options a mode does not take.
DEFAULTS = {"target": None, "repo": None, "draft": None, "plan": None, "base": None, "spec": [],
            "id_regex": TRACE.DEFAULT_ID_RE, "json": False}


def add_option(sub, name: str) -> None:
    if name == "target":
        sub.add_argument("target", help="the draft directory, <repo>/ai-planning/<slug>.spec")
    elif name == "repo":
        sub.add_argument("--repo", required=True, help="the project repository root")
    elif name == "draft":
        sub.add_argument("--draft", help="the specification draft under <repo>/ai-planning/ (with --plan, the plan's "
                                         "own <slug>.spec/), laid over the specification")
    elif name == "plan":
        sub.add_argument("--plan", help="check: the plan whose '## Specification changes' must equal the item delta; "
                                        "traceability: the plan whose 'Specification root:' line picks the layout")
    elif name == "base":
        sub.add_argument("--base", help="the commit the work started from (default: the plan ledger's Baseline "
                                        "commit, else HEAD)")
    elif name == "spec":
        sub.add_argument("--spec", action="append", default=[],
                         help="a Markdown file, repository-relative, that is the project's specification kept "
                              "outside the recognised places (repeatable): the layout 'named'")
    elif name == "id-regex":
        sub.add_argument("--id-regex", default=TRACE.DEFAULT_ID_RE, help="regex for specification item IDs")
    elif name == "json":
        sub.add_argument("--json", action="store_true", help="print the result as JSON")


def build_parser():
    """(the top-level parser, {mode: its subparser})."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("Usage:", 1)[1])
    modes = parser.add_subparsers(dest="mode", metavar="mode", required=True)
    subs = {}
    for mode, options in MODE_OPTIONS.items():
        subs[mode] = modes.add_parser(mode, help=MODE_HELP[mode], description=MODE_HELP[mode])
        for name in options:
            add_option(subs[mode], name)
    return parser, subs


def main() -> int:
    parser, subs = build_parser()
    # parse_known_args, not parse_args: argparse reports leftover arguments through the top-level parser, and an
    # option another mode owns should print the usage of the mode that was asked for.
    args, extra = parser.parse_known_args()
    sub = subs[args.mode]  # validation errors print this mode's usage
    if extra:
        sub.error("unrecognized arguments: " + " ".join(safe(a) for a in extra))
    for name, value in DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, list(value) if isinstance(value, list) else value)
    if DIGEST is None:
        emit(f"spec-layout: core/gate/draft_digest.py, the draft digest the approval gate shares, cannot be loaded "
             f"({safe(DIGEST_ERROR)}); the plugin is incomplete, so nothing was checked\n", sys.stderr)
        return 2
    if args.mode == "digest":
        # Normalised before anything is examined: "alias.spec/" or "alias.spec/." would reach through a symlink
        # that "alias.spec" names; draft_digest.py examines the entry itself and refuses it.
        args.target = os.path.normpath(os.path.abspath(os.path.expanduser(args.target)))
        if os.path.islink(args.target) or not os.path.isdir(args.target):
            sub.error(f"digest: {safe(args.target)} is not a directory (a symlink is refused)")
    else:
        given_repo = os.path.abspath(os.path.expanduser(args.repo))
        args.repo = os.path.realpath(given_repo)
        if not os.path.isdir(args.repo):
            sub.error(f"--repo {safe(args.repo)} is not a directory")
        args.spec = frozenset(repo_relative(sub, args.repo, s, "--spec") for s in args.spec)
        for named in sorted(args.spec):
            if not os.path.isfile(os.path.join(args.repo, named)):
                sub.error(f"--spec {safe(named)} does not exist; --spec names the project's existing specification")
        if args.plan:
            if not os.path.isfile(args.plan):
                sub.error(f"--plan {safe(args.plan)} does not exist")
            args.plan = os.path.realpath(args.plan)
        if args.draft:
            planning = os.path.join(args.repo, "ai-planning")
            if os.path.islink(planning) or not inside(planning, args.repo):
                sub.error(f"{safe(planning)} is a symlink or resolves outside the repository; a draft lives in "
                             "the project's own ai-planning/")
            # The draft's place is checked as given, before anything is resolved: under <repo>/ai-planning/ (the
            # repository as given or as resolved), and with no symlink anywhere from ai-planning/ down.
            given = os.path.abspath(os.path.expanduser(args.draft))
            prefixes = {os.path.join(root, "ai-planning") + os.sep for root in (args.repo, given_repo)}
            under = next((p for p in prefixes if given.startswith(p)), None)
            rel_draft = posix(os.path.join("ai-planning", given[len(under):])) if under else None
            if not rel_draft or os.path.normpath(rel_draft).startswith("..") or \
                    os.path.normpath(rel_draft) in ("ai-planning", "."):
                sub.error(f"--draft must be a directory under {safe(planning)}")
            link = symlink_on_path(args.repo, os.path.normpath(rel_draft).replace(os.sep, "/"))
            if link:
                sub.error(f"--draft: {safe(link)} is a symlink; a draft is a directory of the project's own "
                             "ai-planning/")
            args.draft = os.path.join(args.repo, os.path.normpath(rel_draft))
            if not os.path.isdir(args.draft):
                sub.error(f"--draft must be a directory under {safe(planning)}")
            if args.plan and os.path.realpath(args.draft) != os.path.realpath(os.path.splitext(args.plan)[0] + ".spec"):
                sub.error("--draft must be the plan's own draft, <slug>.spec/ beside <slug>.plan")
    try:
        if re.compile(args.id_regex).groupindex.keys() & {"ifs_id", "ifs_s1", "ifs_s2", "ifs_title"}:
            sub.error("--id-regex may not use the group names ifs_id, ifs_s1, ifs_s2 or ifs_title")
    except re.error as exc:
        sub.error(f"--id-regex is not a regular expression: {exc}")
    rep = TRACE.Report()
    try:
        return {"detect": cmd_detect, "check": cmd_check, "traceability": cmd_traceability,
                "digest": cmd_digest, "survey": cmd_survey}[args.mode](args, rep)
    except Unreadable as exc:
        emit(f"spec-layout: {safe(str(exc))}\n", sys.stderr)
        return 2
    except Exception as exc:  # an unexpected failure is never reported as a FAIL (exit 1) or a clean run
        emit(f"spec-layout: internal error: {type(exc).__name__}: {safe(str(exc))}\n", sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
