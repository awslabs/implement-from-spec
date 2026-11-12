#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
review-snapshot.py — one immutable description of what a review reviewed: the changed files of a project
repository with their content digests, the review policy at a fixed revision, and the plan and context
files, so that findings, gate results, fix rounds and the review state can be bound to it.

Owns one thing: creating, verifying and comparing review snapshots, and binding to one what the review
records about it: quality-gate results, the findings file and the review state block (docs/design-notes.md,
"Review model", sections 1, 5 and 6). It never changes the project: git runs read-only (no index refresh,
no fsmonitor, no textconv or external diff), a --diff-file is applied to a throwaway index and object
directory outside the repository, and the snapshot is written outside it.

Subcommands:
    create --repo R --base REV [--range A..B | --files P... | --diff-file F] [--plan P] [--context P...]
           [--policy-rev REV] [--out DIR]
        Writes DIR/manifest.json (schema ifs-review-snapshot/1) and prints
        "Review snapshot: <id12> (<n> files, policy at <rev12>)" and "Snapshot directory: <DIR>".
    verify DIR
        Recomputes the candidate: exit 0 unchanged, exit 3 changed with one "changed: <path>" line each.
    delta OLD NEW [--json]
        Paths added, removed or changed between two snapshots of the same repository and base.
    record-gate DIR --name NAME --status pass|fail|not-run --command CMD [--reason TEXT]
        Appends a gate result to DIR/gates.json with the snapshot id; refused (exit 3) unless verify passes
        and the gate records are intact. pass and fail are results of a check that ran; not-run is a check
        that could not run (a missing binary, a sandbox that blocks it), and needs --reason, which pass and
        fail refuse. A not-run gate makes verification incomplete, never Blocked by itself.
    gates DIR [--json]
        Prints the recorded gate results; exit 3 when gates.json changed outside record-gate.
    state DIR --recommendation REC --verification VER --approval APP --rollback TEXT --open-blocker N
          --open-major N [--fix-round K --previous OLD]
        Verifies the snapshot and prints the review state block and its JSON line (below), the only form the
        review report carries; exit 3, with the block saying invalidated, when the candidate changed.
    save-findings DIR
        Writes standard input, byte for byte, to DIR/findings.md (atomically, 0600): the orchestrator passes
        every finding in a quoted heredoc, so no file is written outside the project with an editor tool.
    attach DIR --to synth/<name>.out|gates/<name>.txt|input/<name> --from PATH|-
        Copies an output the reviewers read into the snapshot, write-once: a synthesised cloud assembly (a
        directory: regular files and directories only, symlinks, special files and CDK's asset.<sha256>
        staging skipped and counted), a gate command's output or an input from outside the repository (a file, or
        standard input with `--from -`). The command that produces it writes to a scratch directory, because
        in a gated session the approval gate denies every tool-call write under the snapshot roots (the
        snapshot is written only by the plugin's scripts, which the gate does not see). Refused: a DIR that is
        not a snapshot directly under one of the default snapshot roots (the only ones reviewers may read),
        exit 64; a snapshot that no longer verifies, exit 3; a name already attached (never replaced),
        input/change.diff (the preparation's), a symlink on either side, a source that is or holds a
        credential path (checked on every entry of a directory), more than 256 MiB
        or 20,000 files, exit 1 or 64. Nothing else in DIR can be written through it: manifest.json, policy/,
        briefs/ and the records stay the other writers' alone.
The main conversation runs state, save-findings and attach; the review-isolation hook allows a reviewer only
verify, delta and gates.

Record integrity. The records of a snapshot are written only by the plugin's scripts, and an edit by any
other means is detectable. gates.json is a hash chain: each entry carries `prev`, the `hash` of the entry
before it (for the first, the sha256 of the snapshot id), and `hash`, the sha256 of its own canonical JSON
without `hash`; record-gate only appends. gates.json, findings.md (save-findings) and risk.json
(review-prepare.py) each have a sidecar <name>.sha256 (schema ifs-review-record/1: file, snapshot, sha256 of
the file's bytes), so a truncated or deleted file is caught too. verify, gates, record-gate and state check
them: a broken chain, a sidecar that does not match, and a record whose sidecar is missing are "<file> changed
outside <writer>", exit 3, and state renders the snapshot invalidated, verification incomplete and human
approval required with that reason. verify and state check the policy copies the same way (policy_problems,
PR 1 code review, item 8): every policy file the manifest records with a digest must be in DIR/policy/ as a
regular file with that sha256, and nothing else may be there; an edited, added, deleted or symlinked copy is
"policy/<path> does not match the manifest", and create refuses to reuse a directory whose copies do not match
(exit 1), since the Claude-stage reviewers read the policy there only. A missing sidecar fails closed
(2026-11-12): deleting risk.json.sha256 and
editing risk.json used to leave the record "unverifiable", and state then rendered the edited classification
with exit 0, so `approval_required` could be emptied. This detects edits made with other tools; it is not a
defence against someone who recomputes the hashes, or who deletes a record together with its sidecar (an absent
gates.json or findings.md reads as none recorded; a missing risk.json stops state).

Candidate, by mode (the paths are repository-relative; planning artefacts, ai-planning/*.plan,
*.ledger.md, *.approved.md and *.changeset-*.json, are never part of it: --plan records the plan):
    (default)     the working tree against --base: tracked changes, staged or not (`git diff`), plus
                  untracked files git does not ignore (.gitignore and the other standard excludes apply)
    --range A..B  committed changes only: the paths `git diff A B` names, with their bytes at B. --base may
                  be omitted (it is A) and, when given, must be the same commit as A. verify resolves B again,
                  so a new commit on a branch named as B shows as a change
    --files P...  exactly these paths, compared with --base (a path that exists at neither is refused)
    --diff-file F a unified diff (a pasted one): applied to --base in a temporary index; the candidate is the
                  post-image. A diff that does not apply to --base is an error, never a partial snapshot
Each candidate entry is {path, status, mode, sha256}: status added | modified | deleted against the base;
mode the git file mode (100644, 100755, 120000 symlink, 160000 directory: a submodule or nested repository);
sha256 of the candidate bytes, null when deleted. A symlink is recorded by the digest of its target text and
never followed; a directory entry is not descended into (sha256 of the commit git records for it in tree
modes, of the empty string in the working tree). Renames are a deletion plus an addition.

Policy: CLAUDE.md, AGENTS.md and REVIEW.md at the root and in every parent directory of a changed path, read
at --policy-rev (default --base; in --range mode A) with `git cat-file blob` (byte-exact: no textconv or
filters) and copied byte for byte to DIR/policy/<path>. A file absent at that revision (or a symlink there)
is recorded with sha256 null and not copied; it never falls back to the candidate. policy_changed lists the
policy files whose candidate bytes (the candidate entry, else the base's) differ from the policy revision.
--plan and --context are repository-relative, may not go through a symlink, and are hashed from the candidate
(in --range and --diff-file mode from B or the post-image when the path is there, else the working tree).

The id is the sha256 of the canonical JSON (sorted keys, no whitespace, ASCII) of the manifest without its
`id` and `created_at` fields, so the same inputs give the same id. Default DIR: <state>/review-snapshots/
<id12>, where <state> is $CLAUDE_PLUGIN_DATA when set, else $XDG_STATE_HOME/implement-from-spec, else
~/.local/state/implement-from-spec. --out must lie outside the repository (a snapshot inside it would be
part of its own candidate). Creating a snapshot whose directory already holds the same id reuses it, gate
results included, after checking its policy copies (a mismatch is refused, exit 1).

The review state (state) is printed exactly as design section 6 defines it, six lines, a blank line and
the JSON line, with the full 12-character id:
    Snapshot: <id12> (valid | invalidated: <paths>)
    Recommendation: <No blocking findings | Changes requested | Blocked>
    Verification: <complete | incomplete (<reasons>)>
    Approval required: <none | human (<reasons>)>
    Risk: <standard | high> (<reasons> | none)
    Rollback: <not applicable | supported (<evidence>) | unsafe (<finding>) | unknown (<what settles it>)>

    <!-- ifs-review-state: {"snapshot":"<id12>","recommendation":"...","verification":"complete|incomplete",
    "approval_required":true|false,"open":{"blocker":N,"major":N},"risk":"standard|high"} -->
(the JSON is one line). In a fix round (--fix-round 1|2 --previous <the reviewed snapshot's DIR>, a
snapshot of the same repository and base) the first line is
    Snapshot: <id12> (valid; fix round <K> of 2, previous <old id12>)
Every argument takes only the forms above (--verification complete or "incomplete (<reasons>)", --approval
none or "human (<reasons>)", --rollback one of the four, counts as non-negative integers); anything else is
a usage error, and so is a recommendation the rules contradict: a red gate (the latest result of a gate
name recorded on this snapshot is fail) is Blocked; an open Blocker is Blocked (never Changes requested);
Changes requested needs an open Major; No blocking findings needs no open Blocker or Major (until the PR 1
code review it was accepted with either, exit 0, and the implementing skills read such a block as complete);
Blocked needs an open Blocker, an open Major or a red gate. A gate whose latest result is not-run adds
"<name> not run:
<reason>" to the Verification reasons (incomplete, merged with the given ones); it never makes the
recommendation Blocked. Risk is the classification review-prepare.py recorded in
DIR/risk.json (schema ifs-review-risk/1, this snapshot's id), never an argument; its approval_required
reasons are always under Approval required, the given ones added after them. When the candidate no longer
verifies, or cannot be recomputed, the block says invalidated, verification becomes incomplete with
"snapshot invalidated" among its reasons, and the exit status is 3: a stale snapshot never renders as
valid. Control characters in a text or a path are printed escaped, so every line stays one line.

Usage:
    python3 -I <plugin-root>/core/scripts/review-snapshot.py create --repo ~/src/app --base main \\
        --plan ai-planning/queue.plan --context docs/specifications/queue.md
    python3 -I <plugin-root>/core/scripts/review-snapshot.py verify <DIR>
    python3 -I <plugin-root>/core/scripts/review-snapshot.py delta <OLD DIR> <NEW DIR> --json
    python3 -I <plugin-root>/core/scripts/review-snapshot.py record-gate <DIR> --name pytest --status pass \\
        --command "uv run pytest -q"
    python3 -I <plugin-root>/core/scripts/review-snapshot.py record-gate <DIR> --name "terraform validate" \\
        --status not-run --command "terraform validate" --reason "the sandbox blocks the provider plugin socket"
    python3 -I <plugin-root>/core/scripts/review-snapshot.py save-findings <DIR> <<'IFS_FINDINGS'
    F1 [Major] src/app.py:12 - failure handling - ... Fix: ... (confirmed)
    IFS_FINDINGS
    cdk synth --quiet --lookups=false --output <work>/change.out > <work>/cdk-synth.txt 2>&1
    python3 -I <plugin-root>/core/scripts/review-snapshot.py attach <DIR> --to synth/change.out \\
        --from <work>/change.out
    python3 -I <plugin-root>/core/scripts/review-snapshot.py attach <DIR> --to gates/cdk-synth.txt \\
        --from <work>/cdk-synth.txt
    python3 -I <plugin-root>/core/scripts/review-snapshot.py state <DIR> --recommendation "Changes requested" \\
        --verification complete --approval none --rollback "not applicable" --open-blocker 0 --open-major 1
    python3 -I <plugin-root>/core/scripts/review-snapshot.py state <NEW DIR> --fix-round 1 --previous <DIR> \\
        --recommendation "No blocking findings" --verification complete --approval none \\
        --rollback "not applicable" --open-blocker 0 --open-major 0

Exit status: 0 done, 1 error (state: no recorded risk classification), 3 snapshot changed or a record
changed outside its writer (verify, gates, a refused record-gate or attach, or state printing an invalidated block),
64 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

try:
    import fcntl
except ImportError:  # pragma: no cover - not POSIX; the plugin runs on macOS and Linux
    fcntl = None  # type: ignore[assignment]

SCHEMA = "ifs-review-snapshot/1"
GATES_SCHEMA = "ifs-review-gates/1"
DELTA_SCHEMA = "ifs-review-snapshot-delta/1"
POLICY_NAMES = ("CLAUDE.md", "AGENTS.md", "REVIEW.md")
# The plugin's own planning artefacts change during a review (ledger entries, approved copies, change sets)
# and are not part of the change; --plan records the plan itself.
PLANNING_RE = re.compile(r"^ai-planning/[^/]*(\.plan|\.ledger\.md|\.approved\.md|\.changeset-[^/]*\.json)$")
RANGE_RE = re.compile(r"^([^\s.][^\s]*?)\.\.([^\s.][^\s]*)$")
FILE_MODES = ("100644", "100755")
EXIT_OK, EXIT_ERROR, EXIT_CHANGED, EXIT_USAGE = 0, 1, 3, 64

# The review state block (design notes, "Review model", section 6).
RISK_FILE = "risk.json"  # written by review-prepare.py: the classification of this snapshot
RISK_SCHEMA = "ifs-review-risk/1"
FINDINGS_FILE = "findings.md"
RECOMMENDATIONS = ("No blocking findings", "Changes requested", "Blocked")
FIX_ROUND_CAP = 2
MAX_FINDINGS_BYTES = 8 * 1024 * 1024
MAX_STATE_TEXT = 4000
COUNT_RE = re.compile(r"^(0|[1-9][0-9]{0,5})$")
ROLLBACK_RE = re.compile(r"^(?:not applicable|(?:supported|unsafe|unknown) \((.+)\))$")
# C0 and C1 controls, line and paragraph separators, bidirectional overrides: never inside a state line.
STATE_CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]")
INVALIDATED_REASON = "snapshot invalidated"
GATE_STATUSES = ("pass", "fail", "not-run")
GATES_FILE = "gates.json"
RECORD_SCHEMA = "ifs-review-record/1"  # the sidecar <name>.sha256 of a record file
SIDECAR_SUFFIX = ".sha256"
MAX_REASON = 1000
# The record files with a sidecar hash, and the only writer of each.
RECORD_WRITERS = {GATES_FILE: "record-gate", FINDINGS_FILE: "save-findings", RISK_FILE: "review-prepare"}

# Read-only, deterministic git: no fsmonitor hook, no relative or quoted path output, no replace objects,
# no optional index writes, literal pathspecs; variables that would point git at another repository,
# index or object store are dropped (a throwaway index is set explicitly for --diff-file).
GIT_OPTS = ("-c", "core.fsmonitor=false", "-c", "core.quotepath=false", "-c", "diff.relative=false",
            "-c", "diff.external=", "-c", "core.untrackedCache=false")
DROP_GIT_ENV = re.compile(
    r"^GIT_(DIR|WORK_TREE|INDEX_FILE|OBJECT_DIRECTORY|ALTERNATE_OBJECT_DIRECTORIES|NAMESPACE|COMMON_DIR|"
    r"PREFIX|EXTERNAL_DIFF|DIFF_OPTS|PAGER|CEILING_DIRECTORIES|DISCOVERY_ACROSS_FILESYSTEM|"
    r"(LITERAL|GLOB|NOGLOB|ICASE)_PATHSPECS|CONFIG_PARAMETERS|CONFIG_COUNT|CONFIG_KEY_\d+|CONFIG_VALUE_\d+|"
    r"REPLACE_REF_BASE|SHALLOW_FILE|GRAFT_FILE|QUARANTINE_PATH)$")


class Failure(Exception):
    """A typed stop: exit code and message."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- helpers
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def snapshot_id(manifest: dict) -> str:
    """sha256 of the canonical manifest without `id` and `created_at`."""
    return sha256(canonical({k: v for k, v in manifest.items() if k not in ("id", "created_at")}))


def state_dir() -> str:
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if data:
        return os.path.expanduser(data)
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        return os.path.join(os.path.expanduser(xdg), "implement-from-spec")
    return os.path.expanduser(os.path.join("~", ".local", "state", "implement-from-spec"))


def git_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not DROP_GIT_ENV.match(k)}
    env.update(GIT_LITERAL_PATHSPECS="1", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_NO_REPLACE_OBJECTS="1", LC_ALL="C")
    env.update(extra or {})
    return env


def git_try(root: str, args: list, env_extra: dict | None = None, data: bytes | None = None):
    proc = subprocess.run(["git", *GIT_OPTS, "-C", root, *args], input=data, capture_output=True,
                          env=git_env(env_extra), check=False)
    return proc.returncode, proc.stdout, proc.stderr


def git(root: str, args: list, env_extra: dict | None = None, data: bytes | None = None) -> bytes:
    code, out, err = git_try(root, args, env_extra, data)
    if code:
        detail = os.fsdecode(err).strip().splitlines()
        raise Failure(EXIT_ERROR, f"git {args[0]} failed (exit {code}): {detail[-1] if detail else 'no output'}")
    return out


def split_z(out: bytes) -> list:
    return [os.fsdecode(p) for p in out.split(b"\0") if p]


def chunks(items: list, size: int = 400):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def is_planning(rel: str) -> bool:
    return PLANNING_RE.match(rel) is not None


def repo_root(given: str) -> str:
    path = os.path.realpath(os.path.expanduser(given))
    if not os.path.isdir(path):
        raise Failure(EXIT_USAGE, f"repository not found: {given}")
    code, out, _err = git_try(path, ["rev-parse", "--show-toplevel"])
    if code:
        raise Failure(EXIT_USAGE, f"not a git work tree: {given}")
    return os.path.realpath(os.fsdecode(out).rstrip("\n"))


def resolve_commit(root: str, ref: str, label: str) -> str:
    if not ref or ref.startswith("-") or any(c.isspace() for c in ref):
        raise Failure(EXIT_USAGE, f"{label} is not a revision: {ref!r}")
    code, out, _err = git_try(root, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"])
    if code:
        raise Failure(EXIT_USAGE, f"{label}: no commit '{ref}' (a repository with no commits has no baseline)")
    return os.fsdecode(out).strip()


def ls_tree(root: str, rev: str, paths, env_extra: dict | None = None) -> dict:
    """{path: (mode, oid)} for the blob, symlink and gitlink entries of `paths` at `rev`."""
    found: dict = {}
    for part in chunks(sorted(set(paths))):
        out = git(root, ["ls-tree", "-z", "--full-tree", rev, "--", *part], env_extra)
        for rec in split_z(out):
            meta, _tab, path = rec.partition("\t")
            mode, kind, oid = meta.split(" ")
            if kind in ("blob", "commit"):
                found[path] = (mode, oid)
    return found


def object_bytes(root: str, mode: str, oid: str, env_extra: dict | None = None) -> bytes:
    if mode == "160000":
        return oid.encode("ascii")  # a gitlink has no blob: its commit id stands for it
    return git(root, ["cat-file", "blob", oid], env_extra)


def check_components(root: str, rel: str, allow_leaf_link: bool) -> None:
    """Refuse a path with '..', an absolute form, or a symlink in a directory component (or the leaf)."""
    parts = rel.split("/")
    if os.path.isabs(rel) or any(p in ("", ".", "..") for p in parts):
        raise Failure(EXIT_USAGE, f"not a normalised repository-relative path: {rel}")
    probe = root
    for i, part in enumerate(parts):
        probe = os.path.join(probe, part)
        last = i == len(parts) - 1
        if os.path.islink(probe) and not (last and allow_leaf_link):
            raise Failure(EXIT_USAGE, f"path goes through a symlink, which is never followed: {rel}")


def confine(root: str, given: str, label: str, allow_leaf_link: bool = False) -> str:
    """The repository-relative form of a user-supplied path, refusing escapes and symlinks."""
    joined = given if os.path.isabs(given) else os.path.join(root, given)
    rel = os.path.relpath(os.path.normpath(joined), root)
    if rel == "." or rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
        raise Failure(EXIT_USAGE, f"{label} path is outside the repository: {given}")
    rel = rel.replace(os.sep, "/")
    check_components(root, rel, allow_leaf_link)
    return rel


def disk_entry(root: str, rel: str):
    """(mode, bytes) of a working-tree path, None when it does not exist. Symlinks are read, never followed."""
    check_components(root, rel, allow_leaf_link=True)
    path = os.path.join(root, rel)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(st.st_mode):
        return "120000", os.readlink(os.fsencode(path))
    if stat.S_ISDIR(st.st_mode):
        return "160000", b""
    if not stat.S_ISREG(st.st_mode):
        raise Failure(EXIT_ERROR, f"{rel} is neither a file, a symlink nor a directory")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        data = fh.read()
    return ("100755" if st.st_mode & stat.S_IXUSR else "100644"), data


def trackable(root: str, rel: str) -> bool:
    """Whether git could add this untracked path: a regular file, a symlink or a directory."""
    try:
        st = os.lstat(os.path.join(root, rel))
    except OSError:
        return True  # vanished or unreadable: disk_entry decides
    return stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or stat.S_ISDIR(st.st_mode)


def status_of(in_base: bool, present: bool) -> str:
    return "added" if not in_base else "deleted" if not present else "modified"


# ---------------------------------------------------------------- the candidate
class Candidate:
    """The changed paths of one mode with their candidate bytes. Use as a context manager (diff-file mode
    keeps a temporary index until closed)."""

    def __init__(self, root: str, base: str, mode: str, source: dict) -> None:
        self.root, self.base, self.mode, self.source = root, base, mode, source
        self.entries: dict = {}
        self._tmp = None
        self._env: dict | None = None
        self._tree: dict = {}  # path: (mode, oid) where bytes come from git objects
        self.to_commit = None
        try:
            getattr(self, "_collect_" + mode.replace("-", "_"))()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    # -- per mode
    def _from_disk(self, paths) -> None:
        base_tree = ls_tree(self.root, self.base, paths)
        for rel in sorted(set(paths)):
            disk = disk_entry(self.root, rel)
            if self.mode == "files" and disk is not None and disk[0] == "160000" and rel not in base_tree:
                raise Failure(EXIT_USAGE, f"--files takes files, not directories: {rel}")
            if disk is None and rel not in base_tree:
                if self.mode == "files":
                    raise Failure(EXIT_USAGE, f"--files: {rel} exists neither in the working tree nor at the base")
                continue  # vanished between git's listing and the read
            self._add(rel, rel in base_tree, disk)

    def _add(self, rel: str, in_base: bool, found) -> None:
        mode, data = found if found is not None else (None, None)
        self.entries[rel] = {"path": rel, "status": status_of(in_base, found is not None), "mode": mode,
                             "sha256": sha256(data) if data is not None else None}

    def _collect_worktree(self) -> None:
        tracked = git(self.root, ["diff", "--name-only", "-z", "--no-renames", "--no-ext-diff", "--no-textconv",
                                  self.base, "--"])
        untracked = git(self.root, ["ls-files", "-z", "--others", "--exclude-standard"])
        # git lists an untracked character device or FIFO but can never add one; Claude Code's Linux sandbox
        # masks dotfiles in the working directory (.bashrc, .bash_profile ...) with /dev/null binds, so such
        # entries are not part of any change and are left out rather than failing the snapshot.
        untracked_paths = [p for p in split_z(untracked) if trackable(self.root, p.rstrip("/"))]
        paths = {p.rstrip("/") for p in split_z(tracked) + untracked_paths}
        self._from_disk([p for p in paths if p and not is_planning(p)])

    def _collect_files(self) -> None:
        self._from_disk(self.source["files"])

    def _collect_range(self) -> None:
        self.to_commit = resolve_commit(self.root, self.source["to"], "--range")
        names = git(self.root, ["diff", "--name-only", "-z", "--no-renames", "--no-ext-diff", "--no-textconv",
                                self.base, self.to_commit, "--"])
        paths = [p for p in split_z(names) if not is_planning(p)]
        self._from_tree(paths, ls_tree(self.root, self.to_commit, paths))

    def _from_tree(self, paths, tree: dict) -> None:
        self._tree = tree
        base_tree = ls_tree(self.root, self.base, paths)
        for rel in sorted(set(paths)):
            if rel not in tree and rel not in base_tree:
                continue  # a path that is a directory on both sides
            found = None
            if rel in tree:
                mode, oid = tree[rel]
                found = (mode, object_bytes(self.root, mode, oid, self._env))
            self._add(rel, rel in base_tree, found)

    def _collect_diff_file(self) -> None:
        path = self.source["path"]
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                raise Failure(EXIT_USAGE, f"--diff-file is not a regular file: {path}")
            with open(path, "rb") as fh:
                diff = fh.read()
        except OSError as exc:
            raise Failure(EXIT_USAGE, f"--diff-file cannot be read: {path} ({exc.strerror})")
        if self.source.get("sha256") and sha256(diff) != self.source["sha256"]:
            raise Failure(EXIT_CHANGED, "the diff file changed")
        self.source = dict(self.source, sha256=sha256(diff))
        code, out, _ = git_try(self.root, ["rev-parse", "--git-path", "objects"])
        objects = os.fsdecode(out).strip()
        if code or not objects:
            raise Failure(EXIT_ERROR, "cannot find the repository's object directory")
        objects = objects if os.path.isabs(objects) else os.path.join(self.root, objects)
        # A throwaway index and object directory: the repository's own objects are read through
        # alternates, the blobs the diff creates are written to the temporary directory, never the repository.
        self._tmp = tempfile.mkdtemp(prefix="review-snapshot-")
        os.mkdir(os.path.join(self._tmp, "objects"))
        self._env = {"GIT_INDEX_FILE": os.path.join(self._tmp, "index"),
                     "GIT_OBJECT_DIRECTORY": os.path.join(self._tmp, "objects"),
                     "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.path.realpath(objects)}
        git(self.root, ["read-tree", self.base], self._env)
        code, _out, err = git_try(self.root, ["apply", "--cached", "--whitespace=nowarn", "-"], self._env, diff)
        if code:
            detail = os.fsdecode(err).strip().splitlines()
            raise Failure(EXIT_ERROR, f"the diff does not apply to the base {self.base[:12]}"
                                      f"{': ' + detail[0] if detail else ''}")
        names = git(self.root, ["diff", "--cached", "--name-only", "-z", "--no-renames", "--no-ext-diff",
                                "--no-textconv", self.base, "--"], self._env)
        paths = [p for p in split_z(names) if not is_planning(p)]
        index: dict = {}
        for part in chunks(paths):
            for rec in split_z(git(self.root, ["ls-files", "-s", "-z", "--", *part], self._env)):
                meta, _tab, rel = rec.partition("\t")
                mode, oid, _stage = meta.split(" ")
                index[rel] = (mode, oid)
        self._from_tree(paths, index)

    # -- reads
    def read(self, rel: str):
        """The candidate bytes of `rel` (a changed path or any other), None when absent in the candidate."""
        if self.mode in ("worktree", "files"):
            found = disk_entry(self.root, rel)
            return found[1] if found else None
        if rel in self._tree:
            mode, oid = self._tree[rel]
            return object_bytes(self.root, mode, oid, self._env)
        if rel in self.entries:
            return None
        if self.mode == "range":
            tree = ls_tree(self.root, self.to_commit, [rel])
            return object_bytes(self.root, *tree[rel]) if rel in tree else None
        tree = ls_tree(self.root, self.base, [rel])  # diff-file: untouched paths are the base's
        return object_bytes(self.root, *tree[rel]) if rel in tree else None

    def read_file(self, rel: str):
        """The candidate bytes of `rel` when it is a regular file there, else None."""
        if self.mode in ("worktree", "files"):
            found = disk_entry(self.root, rel)
        elif rel in self._tree:
            mode, oid = self._tree[rel]
            found = (mode, object_bytes(self.root, mode, oid, self._env))
        elif rel in self.entries:
            found = None
        else:
            tree = ls_tree(self.root, self.to_commit if self.mode == "range" else self.base, [rel])
            found = (tree[rel][0], object_bytes(self.root, *tree[rel])) if rel in tree else None
        return found[1] if found and found[0] in FILE_MODES else None

    def policy_digest(self, rel: str):
        """What a policy path is in the candidate, for the comparison with the policy revision: the sha256 of
        a regular file, None when absent, and '<mode>:<sha256>' for a symlink or directory (never equal to a
        file's digest, so a policy file replaced by a symlink counts as changed)."""
        if rel in self.entries:
            entry = self.entries[rel]
            if entry["mode"] in FILE_MODES or entry["sha256"] is None:
                return entry["sha256"]
            return f"{entry['mode']}:{entry['sha256']}"
        tree = ls_tree(self.root, self.base, [rel])
        if rel not in tree:
            return None
        digest = sha256(object_bytes(self.root, *tree[rel]))
        return digest if tree[rel][0] in FILE_MODES else f"{tree[rel][0]}:{digest}"

    def digests(self) -> dict:
        return {p: (e["status"], e["mode"], e["sha256"]) for p, e in self.entries.items()}


def open_candidate(manifest: dict) -> Candidate:
    """The candidate a manifest describes, recomputed from the repository now."""
    return Candidate(manifest["repo"], manifest["base"], manifest["mode"], dict(manifest["source"]))


def policy_paths(paths) -> list:
    dirs = {""}
    for rel in paths:
        parts = rel.split("/")[:-1]
        for i in range(len(parts)):
            dirs.add("/".join(parts[:i + 1]))
    return sorted((d + "/" + n) if d else n for d in dirs for n in POLICY_NAMES)


def plan_entry(cand: Candidate, root: str, given: str, label: str) -> dict:
    rel = confine(root, given, label)
    data = cand.read_file(rel)
    if data is None and cand.mode in ("range", "diff-file") and rel not in cand.entries:
        found = disk_entry(root, rel)  # a plan or specification that is not committed: the working tree's
        data = found[1] if found and found[0] in FILE_MODES else None
    if data is None:
        raise Failure(EXIT_USAGE, f"{label}: {rel} is not a file in the candidate")
    return {"path": rel, "sha256": sha256(data)}


# ---------------------------------------------------------------- manifest IO
def load_manifest(target: str) -> tuple:
    """(directory, manifest) from a snapshot directory or its manifest.json; the id must match."""
    target = os.path.abspath(os.path.expanduser(target))
    directory = os.path.dirname(target) if os.path.basename(target) == "manifest.json" else target
    path = os.path.join(directory, "manifest.json")
    if os.path.islink(path) or not os.path.isfile(path):
        raise Failure(EXIT_USAGE, f"not a review snapshot (no manifest.json): {target}")
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Failure(EXIT_ERROR, f"cannot read {path}: {exc}")
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise Failure(EXIT_ERROR, f"{path} is not a {SCHEMA} manifest")
    if manifest.get("id") != snapshot_id(manifest):
        raise Failure(EXIT_ERROR, f"{path} does not match its id: the manifest was edited")
    return directory, manifest


def write_new(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def inside(path: str, root: str) -> bool:
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


# ---------------------------------------------------------------- subcommands
def cmd_create(args) -> int:
    root = repo_root(args.repo)
    mode = "range" if args.range else "files" if args.files else "diff-file" if args.diff_file else "worktree"
    source: dict = {}
    if args.range:
        m = RANGE_RE.match(args.range)
        if not m or "..." in args.range:
            raise Failure(EXIT_USAGE, f"--range takes exactly two refs as A..B: {args.range}")
        base = resolve_commit(root, m.group(1), "--range")
        if args.base and resolve_commit(root, args.base, "--base") != base:
            raise Failure(EXIT_USAGE, "--base and the first ref of --range are different commits")
        source = {"from": m.group(1), "to": m.group(2)}
    else:
        if not args.base:
            raise Failure(EXIT_USAGE, "--base is required (unless --range gives it)")
        base = resolve_commit(root, args.base, "--base")
        if args.files:
            source = {"files": sorted({confine(root, f, "--files", allow_leaf_link=True) for f in args.files})}
        elif args.diff_file:
            source = {"path": os.path.realpath(os.path.expanduser(args.diff_file))}
    policy_rev = resolve_commit(root, args.policy_rev, "--policy-rev") if args.policy_rev else base

    out = None
    if args.out:
        out = os.path.abspath(os.path.expanduser(args.out))
        if inside(out, root) or inside(os.path.dirname(out), root):
            raise Failure(EXIT_USAGE, "--out must lie outside the repository (a snapshot inside it would be "
                                      "part of its own candidate)")

    with Candidate(root, base, mode, source) as cand:
        if mode == "range":
            cand.source["to_commit"] = cand.to_commit
        changed = sorted(cand.entries)
        ppaths = policy_paths(changed)
        at_rev = ls_tree(root, policy_rev, ppaths)
        policy_files, copies, policy_changed = [], {}, []
        for rel in ppaths:
            digest = None
            if rel in at_rev and at_rev[rel][0] in FILE_MODES:
                data = object_bytes(root, *at_rev[rel])
                digest = sha256(data)
                copies[rel] = data
            policy_files.append({"path": rel, "sha256": digest})
            if cand.policy_digest(rel) != digest:
                policy_changed.append(rel)
        manifest = {
            "schema": SCHEMA,
            "repo": root,
            "base": base,
            "mode": mode,
            "source": cand.source,
            "candidate": [cand.entries[p] for p in changed],
            "policy": {"revision": policy_rev, "files": policy_files},
            "policy_changed": policy_changed,
            "plan": plan_entry(cand, root, args.plan, "--plan") if args.plan else None,
            "context": [plan_entry(cand, root, c, "--context") for c in (args.context or [])],
        }
    manifest["id"] = snapshot_id(manifest)
    manifest["created_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sid = manifest["id"]
    out = out or os.path.join(state_dir(), "review-snapshots", sid[:12])
    if inside(out, root) or inside(os.path.dirname(out), root):
        raise Failure(EXIT_USAGE, f"the snapshot directory must lie outside the repository: {out}")
    summary = f"Review snapshot: {sid[:12]} ({len(changed)} files, policy at {policy_rev[:12]})"

    if os.path.lexists(out):
        if os.path.islink(out) or not os.path.isdir(out):
            raise Failure(EXIT_ERROR, f"{out} exists and is not a snapshot directory")
        if os.listdir(out):
            try:
                _d, existing = load_manifest(out)
            except Failure:
                existing = None
            if not existing or existing["id"] != sid:
                raise Failure(EXIT_ERROR, f"{out} exists and holds something other than snapshot {sid[:12]}")
            changed_policy = policy_problems(out, existing)
            if changed_policy:
                raise Failure(EXIT_ERROR, f"{out} holds snapshot {sid[:12]}, but "
                                          f"{'; '.join(r for _k, r in changed_policy)}: it is not reused. Never "
                                          "repair it by hand: report it and take the snapshot into a new --out "
                                          "directory (or remove that directory first)")
            print(summary)
            print(f"Snapshot directory: {out} (unchanged, reused)")
            return EXIT_OK
        os.rmdir(out)
    parent = os.path.dirname(out)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".snapshot-", dir=parent)
    try:
        for rel, data in copies.items():
            target = os.path.join(tmp, "policy", *rel.split("/"))
            os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
            write_new(target, data)
        write_new(os.path.join(tmp, "manifest.json"),
                  (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii"))
        os.chmod(tmp, 0o700)
        os.rename(tmp, out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(summary)
    print(f"Snapshot directory: {out}")
    return EXIT_OK


def differences(old: dict, new: dict) -> list:
    return sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))


def verify_manifest(manifest: dict) -> list:
    """The changed paths of a snapshot now; [] when it still verifies. A diff file that is gone, changed or
    no longer applies is reported as a change of the diff file."""
    recorded = {e["path"]: (e["status"], e["mode"], e["sha256"]) for e in manifest["candidate"]}
    try:
        with open_candidate(manifest) as cand:
            return differences(recorded, cand.digests())
    except Failure as exc:
        if manifest["mode"] == "diff-file":  # the diff file is the candidate's only input
            return [f"{manifest['source']['path']} ({exc.message})"]
        raise Failure(EXIT_ERROR, f"the candidate cannot be recomputed: {exc.message}")


def cmd_verify(args) -> int:
    directory, manifest = load_manifest(args.dir)
    changed = verify_manifest(manifest)
    problems = integrity_problems(directory, manifest)
    changed += [reason for kind, reason in problems if kind == "tampered"]
    for rel in changed:
        print(f"changed: {rel}")
    if changed:
        print(f"Snapshot {manifest['id'][:12]}: changed ({len(changed)} paths)", file=sys.stderr)
        return EXIT_CHANGED
    print(f"Snapshot {manifest['id'][:12]}: unchanged ({len(manifest['candidate'])} files)")
    return EXIT_OK


def cmd_delta(args) -> int:
    _d, old = load_manifest(args.old)
    _d, new = load_manifest(args.new)
    if old["repo"] != new["repo"] or old["base"] != new["base"]:
        raise Failure(EXIT_ERROR, "the snapshots are not of the same repository and base")
    a = {e["path"]: (e["status"], e["mode"], e["sha256"]) for e in old["candidate"]}
    b = {e["path"]: (e["status"], e["mode"], e["sha256"]) for e in new["candidate"]}
    result = {"schema": DELTA_SCHEMA, "old": old["id"][:12], "new": new["id"][:12],
              "added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
              "changed": sorted(p for p in set(a) & set(b) if a[p] != b[p])}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return EXIT_OK
    total = len(result["added"]) + len(result["removed"]) + len(result["changed"])
    print(f"Delta {result['old']} to {result['new']}: {total} paths")
    for key in ("added", "changed", "removed"):
        for rel in result[key]:
            print(f"{key}: {rel}")
    return EXIT_OK


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tampered_reason(name: str) -> str:
    return f"{name} changed outside {RECORD_WRITERS[name]}"


def entry_hash(entry: dict) -> str:
    """sha256 of a gate entry's canonical JSON without its own `hash`."""
    return sha256(canonical({k: v for k, v in entry.items() if k != "hash"}))


def chain_start(sid: str) -> str:
    """The `prev` of the first gate entry: the sha256 of the snapshot id."""
    return sha256(sid.encode("ascii"))


def read_regular(path: str):
    """The bytes of a regular file, None when absent; a symlink or another kind of file raises ValueError."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"{path} is not a regular file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        return fh.read()


def sidecar_record(name: str, sid: str, data: bytes) -> bytes:
    return (json.dumps({"schema": RECORD_SCHEMA, "file": name, "snapshot": sid, "sha256": sha256(data)},
                       indent=2, sort_keys=True) + "\n").encode("ascii")


def write_atomic(directory: str, name: str, data: bytes) -> None:
    """DIR/name replaced atomically, 0600, never through a symlink."""
    if os.path.islink(directory):
        raise Failure(EXIT_ERROR, f"{directory} is a symlink")
    target = os.path.join(directory, name)
    if os.path.islink(target) or (os.path.lexists(target) and not os.path.isfile(target)):
        raise Failure(EXIT_ERROR, f"{target} is a symlink or not a regular file")
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{name}-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_record(directory: str, name: str, data: bytes, sid: str) -> None:
    """A record file and its sidecar hash, both atomically: the only way gates.json, findings.md and risk.json
    are written (review-prepare.py calls this for risk.json)."""
    write_atomic(directory, name, data)
    write_atomic(directory, name + SIDECAR_SUFFIX, sidecar_record(name, sid, data))


def check_record(directory: str, name: str, sid: str):
    """(data, problem) of a record file with a sidecar: problem is None when it matches, ("tampered", reason)
    when the file or its sidecar was changed, added or removed by other means, a file whose sidecar is missing
    included (fail closed: the writers always write both). data is the file's bytes, None when absent or
    unreadable."""
    path = os.path.join(directory, name)
    try:
        data = read_regular(path)
        side = read_regular(path + SIDECAR_SUFFIX)
    except (OSError, ValueError):
        return None, ("tampered", tampered_reason(name))
    if data is None and side is None:
        return None, None
    if side is None:
        return data, ("tampered", tampered_reason(name))
    try:
        record = json.loads(side.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        record = None
    expected = {"schema": RECORD_SCHEMA, "file": name, "snapshot": sid,
                "sha256": sha256(data) if data is not None else None}
    if data is None or record != expected:
        return data, ("tampered", tampered_reason(name))
    return data, None


class GateRecords:
    """The gate entries of a snapshot and the state of their chain: problem is None (intact or no gates) or
    ("tampered", reason). entries holds what parses, for display only when a problem is set."""

    def __init__(self, sid: str, entries: list, problem) -> None:
        self.sid, self.entries, self.problem = sid, entries, problem

    @property
    def tampered(self) -> bool:
        return bool(self.problem) and self.problem[0] == "tampered"

    def latest(self) -> dict:
        found: dict = {}
        for gate in self.entries:
            if isinstance(gate, dict) and isinstance(gate.get("name"), str):
                found[gate["name"]] = gate
        return found


def valid_entry_fields(gate) -> bool:
    if not isinstance(gate, dict):
        return False
    if not all(isinstance(gate.get(k), str) for k in ("name", "status", "command", "snapshot", "recorded_at")):
        return False
    if gate["status"] not in GATE_STATUSES:
        return False
    return (gate["status"] == "not-run") == isinstance(gate.get("reason"), str)


@contextlib.contextmanager
def gates_lock(directory: str, exclusive: bool):
    """record-gate holds it exclusively while it writes gates.json and its sidecar; readers take it shared
    (when it exists: a read-only reader never creates it) so they never see one without the other."""
    path = os.path.join(directory, ".gates.lock")
    fd = None
    try:
        if exclusive:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        else:
            with contextlib.suppress(OSError):
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        if fd is not None and fcntl:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        if fd is not None:
            os.close(fd)


def load_gates(directory: str, sid: str) -> GateRecords:
    """The gate records of a snapshot with their chain and sidecar checked (the caller holds gates_lock)."""
    data, problem = check_record(directory, GATES_FILE, sid)
    tampered = ("tampered", tampered_reason(GATES_FILE))
    if data is None:
        return GateRecords(sid, [], problem)
    try:
        body = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return GateRecords(sid, [], tampered)
    if not isinstance(body, dict) or body.get("schema") != GATES_SCHEMA or body.get("snapshot") != sid \
            or not isinstance(body.get("gates"), list):
        return GateRecords(sid, [], tampered)
    entries = [g for g in body["gates"] if isinstance(g, dict)]
    if problem:
        return GateRecords(sid, entries, problem)
    prev = chain_start(sid)
    for gate in body["gates"]:
        if not valid_entry_fields(gate) or gate.get("prev") != prev or gate.get("snapshot") != sid \
                or gate.get("hash") != entry_hash(gate):
            return GateRecords(sid, entries, tampered)
        prev = gate["hash"]
    return GateRecords(sid, entries, None)


def check_gates(directory: str, sid: str) -> GateRecords:
    with gates_lock(directory, exclusive=False):
        return load_gates(directory, sid)


POLICY_TAMPERED = "policy/{} does not match the manifest"


def policy_problems(directory: str, manifest: dict) -> list:
    """Every ("tampered", reason) of DIR/policy/ against the manifest (PR 1 code review, item 8): each policy file
    the manifest records with a digest must be a regular file with that sha256, and nothing else may be there (a
    file recorded with sha256 null, an added file, a symlink or another kind of entry anywhere under policy/). The
    Claude-stage reviewers read the policy there only, so a copy edited, added or deleted after create would
    otherwise steer them while verify and state still said valid. An unreadable policy/ counts as changed."""
    expected = {}
    for entry in manifest["policy"]["files"]:
        if entry.get("sha256"):
            expected[entry["path"]] = entry["sha256"]
    root = os.path.join(directory, "policy")
    found, odd, unreadable = set(), set(), []
    try:
        st = os.lstat(root)
    except FileNotFoundError:
        st = None
    except OSError:
        return [("tampered", POLICY_TAMPERED.format("") + " (it cannot be read)")]
    if st is not None and not stat.S_ISDIR(st.st_mode):
        return [("tampered", "policy/ is not a directory: it does not match the manifest")]
    if st is not None:
        for current, dirs, files in os.walk(root, onerror=unreadable.append):
            rel_dir = os.path.relpath(current, root)
            for name in list(dirs):
                if os.path.islink(os.path.join(current, name)):
                    dirs.remove(name)
                    odd.add(name if rel_dir == "." else f"{rel_dir}/{name}")
            for name in files:
                found.add(name if rel_dir == "." else f"{rel_dir}/{name}")
    bad = set(odd) | (found - set(expected))
    for rel, digest in expected.items():
        try:
            data = read_regular(os.path.join(root, *rel.split("/"))) if rel in found else None
        except (OSError, ValueError):
            data = None
        if data is None or sha256(data) != digest:
            bad.add(rel)
    problems = [("tampered", POLICY_TAMPERED.format(rel)) for rel in sorted(bad)]
    if unreadable:
        problems.append(("tampered", POLICY_TAMPERED.format("") + " (part of it cannot be read)"))
    return problems


def integrity_problems(directory: str, manifest: dict, gates: GateRecords | None = None) -> list:
    """Every ("tampered", reason) of the snapshot's records (gates.json, findings.md and risk.json) and of its
    policy copies (policy_problems)."""
    sid = manifest["id"]
    gates = gates or check_gates(directory, sid)
    problems = [gates.problem] if gates.problem else []
    for name in (FINDINGS_FILE, RISK_FILE):
        _data, problem = check_record(directory, name, sid)
        if problem:
            problems.append(problem)
    return problems + policy_problems(directory, manifest)


def one_line_arg(value: str, label: str, limit: int) -> str:
    if not value.strip() or len(value) > limit or STATE_CONTROL_RE.search(value):
        raise Failure(EXIT_USAGE, f"{label} must be one non-empty line of at most {limit} characters with no "
                                  "control characters")
    return value


def cmd_record_gate(args) -> int:
    directory, manifest = load_manifest(args.dir)
    sid = manifest["id"]
    one_line_arg(args.name, "--name", MAX_STATE_TEXT)
    one_line_arg(args.command, "--command", MAX_STATE_TEXT)
    if args.status == "not-run":
        if args.reason is None:
            raise Failure(EXIT_USAGE, "--status not-run needs --reason: why the check could not run")
        reason = one_line_arg(args.reason, "--reason", MAX_REASON).strip()
    elif args.reason is not None:
        raise Failure(EXIT_USAGE, f"--reason goes only with --status not-run; a {args.status} result is the "
                                  "check's own outcome")
    try:
        changed = verify_manifest(manifest)
    except Failure as exc:
        changed = [f"(the snapshot cannot be recomputed: {exc.message})"]
    if changed:
        for rel in changed:
            print(f"changed: {rel}")
        print(f"Refused: snapshot {sid[:12]} no longer verifies, so a gate result cannot be bound to it; "
              "take a new snapshot and run the gate again", file=sys.stderr)
        return EXIT_CHANGED
    with gates_lock(directory, exclusive=True):
        records = load_gates(directory, sid)
        if records.problem:
            print(f"changed: {records.problem[1]}")
            print(f"Refused: {records.problem[1]}, so its results cannot be extended; nothing was recorded. "
                  "Never repair it by hand: report it, take a new snapshot (a new --out directory) and run the "
                  "gates again", file=sys.stderr)
            return EXIT_CHANGED
        entries = list(records.entries)
        entry = {"name": args.name, "status": args.status, "command": args.command, "snapshot": sid,
                 "recorded_at": now_utc(), "prev": entries[-1]["hash"] if entries else chain_start(sid)}
        if args.status == "not-run":
            entry["reason"] = reason
        entry["hash"] = entry_hash(entry)
        entries.append(entry)
        body = {"schema": GATES_SCHEMA, "snapshot": sid, "gates": entries}
        write_record(directory, GATES_FILE,
                     (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8"), sid)
    suffix = f": {entry['reason']}" if args.status == "not-run" else ""
    print(f"Gate recorded: {args.name} {args.status}{suffix} (snapshot {sid[:12]})")
    return EXIT_OK


def cmd_gates(args) -> int:
    directory, manifest = load_manifest(args.dir)
    sid = manifest["id"]
    records = check_gates(directory, sid)
    if records.tampered:
        print(f"review-snapshot: {records.problem[1]}: its results are not evidence for snapshot {sid[:12]}",
              file=sys.stderr)
        return EXIT_CHANGED
    if records.problem:
        print(f"review-snapshot: {records.problem[1]}", file=sys.stderr)
    if args.json:
        print(json.dumps({"schema": GATES_SCHEMA, "snapshot": sid, "gates": records.entries}, indent=2,
                         sort_keys=True))
        return EXIT_OK
    if not records.entries:
        print(f"No gate results for snapshot {sid[:12]}")
    for gate in records.entries:
        reason = f"  (not run: {gate.get('reason')})" if gate.get("status") == "not-run" else ""
        print(one_line(f"{gate.get('status')}  {gate.get('name')}  snapshot {str(gate.get('snapshot'))[:12]}  "
                       f"{gate.get('recorded_at')}  {gate.get('command')}{reason}"))
    return EXIT_OK


# ---------------------------------------------------------------- the review state block
def one_line(text: str) -> str:
    """Text for a state line: control, separator and bidirectional characters escaped, never interpreted."""
    return STATE_CONTROL_RE.sub(lambda m: "\\u%04x" % ord(m.group(0)), text)


def state_text(value: str, label: str) -> str:
    if not value.strip() or len(value) > MAX_STATE_TEXT or STATE_CONTROL_RE.search(value):
        raise Failure(EXIT_USAGE, f"{label} must be one non-empty line of at most {MAX_STATE_TEXT} characters "
                                  "with no control characters")
    if value != value.strip():
        raise Failure(EXIT_USAGE, f"{label} has leading or trailing white space: {value!r}")
    return value


def word_or_reasons(value: str, label: str, plain: str, word: str):
    """None for the plain form (`complete`, `none`), else the reasons of `<word> (<reasons>)`, a list."""
    value = state_text(value, label)
    if value == plain:
        return None
    m = re.match(rf"^{word} \((.+)\)$", value)
    reasons = [r for r in (part.strip() for part in m.group(1).split(";")) if r] if m else []
    if not reasons or m.group(1) != m.group(1).strip():
        raise Failure(EXIT_USAGE, f"{label} is {plain!r} or '{word} (<reasons>)', not {value!r}")
    return reasons


def count_arg(value: str, label: str) -> int:
    if not COUNT_RE.match(value):
        raise Failure(EXIT_USAGE, f"{label} is a non-negative whole number, not {value!r}")
    return int(value)


def read_risk(directory: str, manifest: dict) -> dict:
    """The classification review-prepare.py recorded for this snapshot (DIR/risk.json), checked."""
    path = os.path.join(directory, RISK_FILE)
    sid12 = manifest["id"][:12]
    if os.path.islink(path) or not os.path.isfile(path):
        raise Failure(EXIT_ERROR, f"no risk classification is recorded for snapshot {sid12} ({path} is "
                                  "missing): review-prepare.py writes it; prepare the review again")
    try:
        with open(path, encoding="utf-8") as fh:
            risk = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Failure(EXIT_ERROR, f"cannot read {path}: {exc}")

    def strings(items) -> bool:
        return isinstance(items, list) and all(isinstance(i, str) for i in items)

    ok = (isinstance(risk, dict) and risk.get("schema") == RISK_SCHEMA and risk.get("snapshot") == sid12
          and risk.get("tier") in ("standard", "high") and strings(risk.get("approval_required"))
          and isinstance(risk.get("reasons"), list)
          and all(isinstance(r, dict) and all(isinstance(r.get(k), str) for k in ("rule", "path", "detail"))
                  for r in risk["reasons"]))
    if not ok:
        raise Failure(EXIT_ERROR, f"{path} is not a {RISK_SCHEMA} classification of snapshot {sid12}")
    return risk


def risk_reasons(risk: dict) -> str:
    """The reasons as review-prepare.py prints them on its Risk: line."""
    return "; ".join(f"{r['rule']}: {r['path']} ({r['detail']})" for r in risk["reasons"]) or "none"


def red_gates(records: GateRecords) -> list:
    """Gate names whose latest result recorded on this snapshot is fail."""
    return sorted(name for name, gate in records.latest().items() if gate.get("status") == "fail")


def not_run_reasons(records: GateRecords) -> list:
    """'<name> not run: <reason>' for each gate whose latest result is not-run."""
    return [f"{name} not run: {gate.get('reason')}" for name, gate in sorted(records.latest().items())
            if gate.get("status") == "not-run"]


def check_recommendation(rec: str, blockers: int, majors: int, red: list) -> None:
    """The rules of design section 6 that the arguments alone decide; a contradiction is a usage error."""
    if red and rec != "Blocked":
        raise Failure(EXIT_USAGE, f"a red gate makes the recommendation Blocked ({', '.join(red)} failed on "
                                  f"this snapshot), not {rec!r}")
    if rec == "No blocking findings" and (blockers or majors):
        raise Failure(EXIT_USAGE, f"No blocking findings needs no open Blocker or Major (--open-blocker is {blockers}, "
                                  f"--open-major {majors}): an open Blocker is Blocked, an open Major Changes "
                                  "requested or Blocked")
    if rec == "Changes requested" and blockers:
        raise Failure(EXIT_USAGE, f"a confirmed open Blocker makes the recommendation Blocked (--open-blocker is "
                                  f"{blockers}), not 'Changes requested'")
    if rec == "Changes requested" and majors == 0:
        raise Failure(EXIT_USAGE, "Changes requested needs a confirmed open Major (--open-major is 0)")
    if rec == "Blocked" and not (blockers or majors or red):
        raise Failure(EXIT_USAGE, "Blocked needs a confirmed open Blocker, an open security Major or a red gate; "
                                  "--open-blocker and --open-major are 0 and no gate failed")


def cmd_state(args) -> int:
    directory, manifest = load_manifest(args.dir)
    sid12 = manifest["id"][:12]
    verification = word_or_reasons(args.verification, "--verification", "complete", "incomplete")
    approval = word_or_reasons(args.approval, "--approval", "none", "human")
    rollback = state_text(args.rollback, "--rollback")
    m = ROLLBACK_RE.match(rollback)
    if not m or (m.group(1) is not None and m.group(1) != m.group(1).strip()):
        raise Failure(EXIT_USAGE, "--rollback is 'not applicable', 'supported (<evidence>)', 'unsafe (<finding>)' "
                                  f"or 'unknown (<what settles it>)', not {rollback!r}")
    blockers = count_arg(args.open_blocker, "--open-blocker")
    majors = count_arg(args.open_major, "--open-major")
    round_text = ""
    if (args.fix_round is None) != (args.previous is None):
        raise Failure(EXIT_USAGE, "--fix-round and --previous go together: the round number and the directory "
                                  "of the snapshot the round follows")
    if args.fix_round is not None:
        if args.fix_round not in [str(k) for k in range(1, FIX_ROUND_CAP + 1)]:
            raise Failure(EXIT_USAGE, f"--fix-round is 1 or 2 (two fix rounds after the first review at most), "
                                      f"not {args.fix_round!r}")
        _pd, previous = load_manifest(args.previous)
        if previous["repo"] != manifest["repo"] or previous["base"] != manifest["base"]:
            raise Failure(EXIT_USAGE, "--previous is not a snapshot of the same repository and base")
        if previous["id"] == manifest["id"]:
            raise Failure(EXIT_USAGE, "--previous is this snapshot: a fix round is reviewed on the new snapshot, "
                                      "--previous names the one reviewed before the fixes")
        round_text = f"; fix round {args.fix_round} of {FIX_ROUND_CAP}, previous {previous['id'][:12]}"
    risk = read_risk(directory, manifest)
    gates = check_gates(directory, manifest["id"])
    check_recommendation(args.recommendation, blockers, majors, red_gates(gates))

    try:
        changed = verify_manifest(manifest)
    except Failure as exc:
        changed = [f"(the candidate cannot be recomputed: {exc.message})"]
    problems = integrity_problems(directory, manifest, gates)
    tampered = [reason for kind, reason in problems if kind == "tampered"]
    added = not_run_reasons(gates) + [reason for _kind, reason in problems]
    if changed and not any(r.startswith(INVALIDATED_REASON) for r in verification or []):
        added.append(INVALIDATED_REASON)
    for reason in added:
        if reason not in (verification or []):
            verification = (verification or []) + [reason]
    changed = changed + tampered
    reasons = list(risk["approval_required"]) + [r for r in (approval or []) if r not in risk["approval_required"]]
    # A record changed outside its writer (risk.json included) is never evidence that no approval is needed.
    reasons += [r for r in tampered if r not in reasons]
    if approval is None and reasons:
        print("review-snapshot: the risk classification requires human approval; Approval required carries its "
              "reasons", file=sys.stderr)
    status = f"invalidated: {', '.join(changed)}" if changed else "valid"
    lines = [
        f"Snapshot: {sid12} ({status}{round_text})",
        f"Recommendation: {args.recommendation}",
        "Verification: " + (f"incomplete ({'; '.join(verification)})" if verification is not None else "complete"),
        "Approval required: " + (f"human ({'; '.join(reasons)})" if reasons else "none"),
        f"Risk: {risk['tier']} ({risk_reasons(risk)})",
        f"Rollback: {rollback}",
    ]
    state = {"snapshot": sid12, "recommendation": args.recommendation,
             "verification": "incomplete" if verification is not None else "complete",
             "approval_required": bool(reasons), "open": {"blocker": blockers, "major": majors},
             "risk": risk["tier"]}
    print("\n".join(one_line(line) for line in lines))
    print()
    print("<!-- ifs-review-state: " + json.dumps(state, separators=(",", ":")) + " -->")
    for reason in tampered:
        print(f"review-snapshot: {reason}: the block says invalidated and verification incomplete; never "
              "repair a record by hand, report it and take a new snapshot", file=sys.stderr)
    if len(changed) > len(tampered):
        print(f"review-snapshot: snapshot {sid12} no longer verifies ({len(changed) - len(tampered)} paths): the "
              "block says invalidated and verification incomplete; review the change since as a fix round",
              file=sys.stderr)
    return EXIT_CHANGED if changed else EXIT_OK


def cmd_save_findings(args) -> int:
    directory, manifest = load_manifest(args.dir)
    stream = getattr(sys.stdin, "buffer", None)
    data = stream.read(MAX_FINDINGS_BYTES + 1) if stream is not None else b""
    if len(data) > MAX_FINDINGS_BYTES:
        raise Failure(EXIT_USAGE, f"the findings are larger than {MAX_FINDINGS_BYTES} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Failure(EXIT_USAGE, "the findings on standard input are not UTF-8 text")
    if "\0" in text:
        raise Failure(EXIT_USAGE, "the findings on standard input contain a NUL character")
    if not text.strip():
        raise Failure(EXIT_USAGE, "no findings text on standard input: pass every finding in a quoted heredoc, "
                                  "save-findings <DIR> <<'IFS_FINDINGS' ... IFS_FINDINGS")
    target = os.path.join(directory, FINDINGS_FILE)
    write_record(directory, FINDINGS_FILE, data, manifest["id"])
    print(f"Findings saved: {target} ({len(text.splitlines())} lines, {len(data)} bytes, sha256 "
          f"{sha256(data)[:12]}) for snapshot {manifest['id'][:12]}")
    return EXIT_OK


# ---------------------------------------------------------------- outputs the reviewers read (attach)
# The orchestrator's tool outputs that reviewers read: a synthesised cloud assembly (synth/<name>.out), a gate
# command's output (gates/<name>.txt) and an input from outside the repository (input/<name>: a supplied
# change-set JSON, a pasted plan output). In a gated session the approval gate denies every tool-call write under
# the snapshot roots, so the producing command writes to a scratch directory and attach copies the result in
# (PR 1 code review, blocker 2). Write-once: an attached output is never replaced.
ATTACH_RE = re.compile(r"^(synth|gates|input)/([A-Za-z0-9][A-Za-z0-9._:+-]{0,127})$")
ATTACH_SUFFIX = {"synth": ".out", "gates": ".txt"}
ATTACH_RESERVED = {"input/change.diff"}  # review-prepare.py's copy of a pasted diff
MAX_ATTACH_BYTES = 256 * 1024 * 1024
MAX_ATTACH_FILES = 20000
MAX_ATTACH_DEPTH = 32
CREDENTIAL_PATHS = ("~/.aws", "~/.ssh", "~/.config/gcloud", "~/.azure", "~/.docker/config.json", "~/.netrc")
# CDK's asset staging in a cloud assembly: asset.<sha256 of the source>, a directory or a file with an extension
# (asset.<hash>.zip). Only that exact form is skipped; a template or manifest whose name merely starts with
# "asset." (a stack artifact may be named so; the manifest's templateFile names it) is copied.
ASSET_STAGING_RE = re.compile(r"^asset\.[0-9a-f]{64}(?:\.[A-Za-z0-9]+)?$")


def snapshot_roots() -> set:
    """The directories review snapshots are created in by default (create without --out), as the isolation hook
    and the gate compute them (core/gate/ifs_paths.py snapshot_roots and state_write_roots)."""
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    roots = {os.path.join(state_dir(), "review-snapshots"),
             os.path.expanduser(os.path.join("~", ".local", "state", "implement-from-spec", "review-snapshots"))}
    if xdg:
        roots.add(os.path.join(os.path.expanduser(xdg), "implement-from-spec", "review-snapshots"))
    return {os.path.realpath(r) for r in roots}


def credential_roots() -> list:
    return [os.path.realpath(os.path.expanduser(cred)) for cred in CREDENTIAL_PATHS]


def holds_credentials(path: str) -> bool:
    """Whether a source directory is an ancestor of a credential path (~/.config holds ~/.config/gcloud)."""
    real = os.path.realpath(path)
    return any(root.startswith(real.rstrip(os.sep) + os.sep) for root in credential_roots())


def credential_source(path: str) -> bool:
    for given in (os.path.abspath(path), os.path.realpath(path)):
        if any(part == ".env" or part.startswith(".env.") for part in given.split(os.sep)):
            return True
        for root in credential_roots():
            if given == root or given.startswith(root + os.sep):
                return True
    return False


def read_source_file(path: str, budget: list) -> bytes:
    """A regular file's bytes, opened without following a symlink and without blocking on a FIFO; budget is
    [bytes left] and is charged."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            raise Failure(EXIT_ERROR, f"{path} is not a regular file")
        data = fh.read(budget[0] + 1)
    if len(data) > budget[0]:
        raise Failure(EXIT_ERROR, f"the output is larger than {MAX_ATTACH_BYTES} bytes: {path}")
    budget[0] -= len(data)
    return data


def copy_assembly(src: str, dst: str, counts: dict, budget: list, depth: int = 0) -> None:
    """Copies a cloud assembly directory: regular files and directories only, never through a symlink (symlinks
    and special files are skipped and counted), without CDK's asset staging (ASSET_STAGING_RE: the reviewers
    read that code in the repository), every file written new (O_EXCL, 0600). Every entry is checked as a
    credential path before it is read or entered, so an ancestor of one (~/.config) copies nothing."""
    if depth > MAX_ATTACH_DEPTH:
        raise Failure(EXIT_ERROR, f"{src} is nested more than {MAX_ATTACH_DEPTH} levels deep")
    with os.scandir(src) as entries:
        listed = sorted(entries, key=lambda e: e.name)
    for entry in listed:
        source, target = os.path.join(src, entry.name), os.path.join(dst, entry.name)
        if entry.is_symlink():  # never followed, so never read: skipped before the credential check
            counts["symlinks"] += 1
            continue
        if credential_source(source) or holds_credentials(source):
            raise Failure(EXIT_ERROR, f"{source} is or holds a credential path; nothing was attached")
        if ASSET_STAGING_RE.match(entry.name):
            counts["assets"] += 1
        elif entry.is_dir(follow_symlinks=False):
            os.mkdir(target, 0o700)
            copy_assembly(source, target, counts, budget, depth + 1)
        elif entry.is_file(follow_symlinks=False):
            counts["files"] += 1
            if counts["files"] > MAX_ATTACH_FILES:
                raise Failure(EXIT_ERROR, f"the output holds more than {MAX_ATTACH_FILES} files")
            write_new(target, read_source_file(source, budget))
        else:
            counts["special"] += 1


def cmd_attach(args) -> int:
    """Copies one output the reviewers read into DIR/synth/, DIR/gates/ or DIR/input/, write-once."""
    m = ATTACH_RE.match(args.to)
    if not m or args.to in ATTACH_RESERVED or not m.group(2).endswith(ATTACH_SUFFIX.get(m.group(1), "")):
        raise Failure(EXIT_USAGE, "--to takes synth/<name>.out, gates/<name>.txt or input/<name> (letters, digits, "
                                  "`.`, `_`, `:`, `+` and `-`; input/change.diff is the preparation's)")
    kind, name = m.group(1), m.group(2)
    if args.source == "-" and kind == "synth":
        raise Failure(EXIT_USAGE, "a synthesised assembly is a directory: --from <its directory>, not -")
    directory, manifest = load_manifest(args.dir)
    sid = manifest["id"]
    real = os.path.realpath(directory)
    if os.path.dirname(real) not in snapshot_roots():
        raise Failure(EXIT_USAGE, f"{directory} is not a review snapshot in the default snapshot directory "
                                  f"({', '.join(sorted(snapshot_roots()))}), the only one reviewers may read")
    try:
        changed = verify_manifest(manifest)
    except Failure as exc:
        changed = [f"(the snapshot cannot be recomputed: {exc.message})"]
    if changed:
        for rel in changed:
            print(f"changed: {rel}")
        print(f"Refused: snapshot {sid[:12]} no longer verifies, so an output cannot be attached to it; take a new "
              "snapshot and run the command again", file=sys.stderr)
        return EXIT_CHANGED
    budget = [MAX_ATTACH_BYTES]
    data = None
    if args.source == "-":
        stream = getattr(sys.stdin, "buffer", None)
        data = stream.read(MAX_ATTACH_BYTES + 1) if stream is not None else b""
        if len(data) > MAX_ATTACH_BYTES:
            raise Failure(EXIT_USAGE, f"standard input is larger than {MAX_ATTACH_BYTES} bytes")
        if not data.strip():
            raise Failure(EXIT_USAGE, "nothing on standard input")
    else:
        source = os.path.abspath(os.path.expanduser(args.source))
        if credential_source(source) or holds_credentials(source):
            raise Failure(EXIT_USAGE, f"{args.source} is or holds a credential path; nothing was attached")
        try:
            st = os.lstat(source)
        except OSError as exc:
            raise Failure(EXIT_USAGE, f"cannot read {args.source}: {exc.strerror}")
        wanted_dir = kind == "synth"
        if stat.S_ISLNK(st.st_mode) or (stat.S_ISDIR(st.st_mode) != wanted_dir) or \
                not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
            raise Failure(EXIT_USAGE, f"{args.source} must be {'a directory' if wanted_dir else 'a regular file'}, "
                                      "not a symlink")
        if not wanted_dir:
            data = read_source_file(source, budget)
    kind_dir = os.path.join(real, kind)
    target = os.path.join(kind_dir, name)
    counts = {"files": 0, "symlinks": 0, "assets": 0, "special": 0}
    lock_fd = os.open(os.path.join(real, ".attach.lock"), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                      0o600)
    try:
        if fcntl:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if os.path.lexists(kind_dir):
            if os.path.islink(kind_dir) or not os.path.isdir(kind_dir):
                raise Failure(EXIT_ERROR, f"{kind_dir} is a symlink or not a directory; nothing was attached")
        else:
            os.mkdir(kind_dir, 0o700)
        if os.path.lexists(target):
            raise Failure(EXIT_ERROR, f"{args.to} is already attached to snapshot {sid[:12]} and is never replaced: "
                                      "attach the new output under another name and say so in the report")
        if data is not None:
            fd, tmp = tempfile.mkstemp(dir=kind_dir, prefix=".attach-")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                os.chmod(tmp, 0o600)
                os.link(tmp, target)  # fails if the name exists: write-once even against a racing writer
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
            counts["files"], size = 1, len(data)
        else:
            tmp = tempfile.mkdtemp(dir=kind_dir, prefix=".attach-")
            try:
                copy_assembly(source, tmp, counts, budget)
                if os.path.lexists(target):
                    raise Failure(EXIT_ERROR, f"{args.to} appeared while it was copied; nothing was attached")
                os.rename(tmp, target)
            except BaseException:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            size = MAX_ATTACH_BYTES - budget[0]
    finally:
        os.close(lock_fd)
    skipped = [f"{n} {what} not copied" for what, n in (("asset staging entries", counts["assets"]),
                                                        ("symlinks", counts["symlinks"]),
                                                        ("special files", counts["special"])) if n]
    print(one_line(f"Attached: {target} ({counts['files']} files, {size} bytes"
                   f"{'; ' + ', '.join(skipped) if skipped else ''}) for snapshot {sid[:12]}"))
    return EXIT_OK


class Parser(argparse.ArgumentParser):
    """argparse with the documented usage exit status, 64."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE)


def build_parser() -> Parser:
    parser = Parser(prog="review-snapshot.py",
                    description="Create, verify and compare review snapshots, and bind gate results, the "
                                "findings file and the review state block to them.",
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                    epilog="Candidate, by mode (" + __doc__.split("Candidate, by mode (", 1)[1])
    sub = parser.add_subparsers(dest="command_name",
                                metavar="{create,verify,delta,record-gate,gates,state,save-findings,attach}")
    sub.required = True
    create = sub.add_parser("create", help="write a new snapshot")
    create.add_argument("--repo", required=True, help="the project repository (any directory in its work tree)")
    create.add_argument("--base", help="the revision the change is reviewed against (required unless --range)")
    mode = create.add_mutually_exclusive_group()
    mode.add_argument("--range", help="committed changes only, exactly A..B")
    mode.add_argument("--files", nargs="+", help="exactly these repository-relative paths")
    mode.add_argument("--diff-file", help="a unified diff to apply to --base (a pasted one)")
    create.add_argument("--plan", help="the approved plan, repository-relative")
    create.add_argument("--context", nargs="+", default=[], help="reference files (specifications), repository-relative")
    create.add_argument("--policy-rev", help="where policy files are read (default --base; --range: A)")
    create.add_argument("--out", help="the snapshot directory, outside the repository "
                                      "(default <state>/review-snapshots/<id12>)")
    verify = sub.add_parser("verify", help="recompute the candidate; exit 3 when it changed")
    verify.add_argument("dir")
    delta = sub.add_parser("delta", help="paths added, removed or changed between two snapshots")
    delta.add_argument("old")
    delta.add_argument("new")
    delta.add_argument("--json", action="store_true")
    gate = sub.add_parser("record-gate", help="bind a gate result to a snapshot that still verifies")
    gate.add_argument("dir")
    gate.add_argument("--name", required=True)
    gate.add_argument("--status", required=True, choices=GATE_STATUSES,
                      help="pass or fail: the result of a check that ran; not-run: it could not run (--reason)")
    gate.add_argument("--command", required=True, help="the command, run or that could not run")
    gate.add_argument("--reason", help="with --status not-run only: why the check could not run, one line")
    gates = sub.add_parser("gates", help="print the recorded gate results")
    gates.add_argument("dir")
    gates.add_argument("--json", action="store_true")
    state = sub.add_parser("state", help="verify the snapshot and print the review state block",
                           formatter_class=argparse.RawDescriptionHelpFormatter,
                           epilog="The review state (state)" + __doc__.split("The review state (state)", 1)[1]
                           .split("Usage:", 1)[0].rstrip())
    state.add_argument("dir", help="the snapshot directory of the review")
    state.add_argument("--recommendation", required=True, choices=RECOMMENDATIONS)
    state.add_argument("--verification", required=True, help="complete, or \"incomplete (<reasons>)\"")
    state.add_argument("--approval", required=True, help="none, or \"human (<reasons>)\"; the risk "
                                                         "classification's reasons are always added")
    state.add_argument("--rollback", required=True, help="\"not applicable\", \"supported (<evidence>)\", "
                                                         "\"unsafe (<finding>)\" or \"unknown (<what settles it>)\"")
    state.add_argument("--open-blocker", required=True, metavar="N", help="confirmed open Blockers of this change")
    state.add_argument("--open-major", required=True, metavar="N", help="confirmed open Majors of this change")
    state.add_argument("--fix-round", metavar="K", help="1 or 2, with --previous: the fix round this review is")
    state.add_argument("--previous", metavar="OLD", help="with --fix-round: the snapshot reviewed before the fixes")
    findings = sub.add_parser("save-findings", help="write standard input to DIR/findings.md")
    findings.add_argument("dir", help="the snapshot directory of the review")
    attach = sub.add_parser("attach", help="copy an output the reviewers read into DIR/synth/, gates/ or input/")
    attach.add_argument("dir", help="the snapshot directory of the review (in the default snapshot directory)")
    attach.add_argument("--to", required=True, metavar="WHERE",
                        help="synth/<name>.out (a directory), gates/<name>.txt or input/<name> (a file)")
    attach.add_argument("--from", required=True, dest="source", metavar="PATH",
                        help="the file or directory the command wrote outside the snapshot; - for standard input "
                             "(gates/ and input/ only)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handler = {"create": cmd_create, "verify": cmd_verify, "delta": cmd_delta, "record-gate": cmd_record_gate,
               "gates": cmd_gates, "state": cmd_state, "save-findings": cmd_save_findings,
               "attach": cmd_attach}[args.command_name]
    try:
        return handler(args)
    except Failure as exc:
        print(f"review-snapshot: {exc.message}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"review-snapshot: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
