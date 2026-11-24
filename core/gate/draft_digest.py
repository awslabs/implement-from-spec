# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""draft_digest.py: the one definition of a specification draft's digest and of the plan line that records it.

Owner: the implement-from-spec plugin; this file lives in the plugin's core/gate/ directory. Standard library
only (Python 3.9+). A specification draft is the directory `<repo>/ai-planning/<slug>.spec/` (contract section
13): the full text of every specification file the plan adds or changes, at the path it will have in the
repository. The plan records the draft's digest in its `## Specification changes` section, on one line,
`Draft digest: sha256 <64 lowercase hex>`, so the approval of the plan, which is bound to the plan's own sha256,
also binds the draft: a draft edited after the plan was written no longer matches the line. The approval gate
(core/gate/spec-approval-gate.py) and the specification checker (core/scripts/spec-layout.py) both load this
file, by import or by path, so the two can never compute different digests. The gate protects it with the rest
of core/gate/.

    digest(draft_dir)       64 lowercase hex: the sha256 of the sorted lines
                            "<path relative to the draft, POSIX>\t<sha256 hex of the file>\n", one per regular
                            file of the draft, UTF-8. The draft is read through directory descriptors anchored at
                            its top directory: every entry is examined once with lstat, every directory and file
                            is opened relative to its parent's descriptor without following a symlink (files also
                            without blocking, so a FIFO swapped in cannot hang the read), and fstat must show the
                            type, device and inode the listing saw. Files are read streamed. DraftError for a
                            missing directory, a symlink or any other non-regular file anywhere in it (the draft
                            itself included), a name holding a tab, a newline, a carriage return, another C0 or C1
                            control, DEL, a line or paragraph separator, a bidi control or bytes that are not
                            UTF-8 (such names would make two different drafts give the same lines), a directory
                            or file that cannot be read, and an entry swapped between the listing and the read
    manifest(draft_dir)     (digest, [(path, sha256)] sorted): the digest and the files it covers, from one
                            traversal. digest_of(files) is the digest of such a list. The root is normalised
                            first, so a trailing "/" or "/." cannot reach through a symlinked draft
    plan_digest(plan_text)  the hex of the single `Draft digest:` line, which must stand in the plan's
                            `## Specification changes` section (every section of that name is read), or None
                            when there is no such line. Fenced code and HTML comments are masked first
                            (mask_fences), so neither a heading nor a digest line inside one counts. DraftError for a second line, for a
                            line that names a digest in any other form, and for a `Draft digest:` label anywhere
                            else in the plan. List markers, bold, italics and code spans around the label and the
                            value are accepted
    specification_changes(plan_text)  the section's text, fences blanked, or None: the one parse the
                            records (spec-layout.py) and the digest line come from; section_spans(plan_text)
                            gives the sections' offsets
    LINE_RE                 the compiled pattern of that line; group 1 is the hex
    DraftError              the exception every function raises; str() is one short line with every name escaped

Usage (from a script elsewhere in the plugin, by path, as spec-layout.py does):
    spec = importlib.util.spec_from_file_location("ifs_draft_digest", "<plugin-root>/core/gate/draft_digest.py")
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from typing import List, Optional, Tuple

CHUNK = 1 << 20
# Characters a draft name may not hold: they would let two drafts give the same digest lines, or rewrite the
# terminal a reason is printed in. C0 and C1 controls (tab, newline and carriage return among them), DEL, the
# line and paragraph separators, the bidi controls, and the surrogates os.fsdecode uses for bytes that are not
# UTF-8.
UNSAFE_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c\ud800-\udfff]")
SECTION_RE = re.compile(r"^##[ \t]+(?:\d+\.[ \t]*)?specification changes\b.*$", re.I | re.M)
NEXT_SECTION_RE = re.compile(r"^##[ \t]+(?!#)|^#{3,}[ \t]", re.M)
# A line that is about the digest at all: its label, with the decorations the value may carry.
LABEL_RE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?[*_`]*Draft digest[*_`]*[ \t]*:", re.I)
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
LINE_RE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?[*_`]*Draft digest[*_`]*:[*_`]*[ \t]+[*_`]*sha256[ \t]+([0-9a-f]{64})"
                     r"(?![0-9A-Za-z])[*_`]*[ \t]*$")


class DraftError(Exception):
    """A draft that cannot be digested, or a plan whose digest line cannot be read. str() is one short line."""

    def __init__(self, reason: str) -> None:
        super().__init__(" ".join(escape(reason).split()))


def escape(text: str) -> str:
    """Text with every unsafe character (UNSAFE_RE) and the backslash escaped, so a name cannot forge a line."""
    text = text.replace("\\", "\\\\")
    return UNSAFE_RE.sub(lambda m: "\\u%04x" % ord(m.group(0)), text)


def _check_name(rel: str) -> None:
    if UNSAFE_RE.search(rel):
        raise DraftError(f"the draft holds the name {rel}, which carries a control, separator or bidi character "
                         "or bytes that are not UTF-8")


def _reason(exc: OSError) -> str:
    return exc.strerror or exc.__class__.__name__


NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
CLOEXEC = getattr(os, "O_CLOEXEC", 0)
NONBLOCK = getattr(os, "O_NONBLOCK", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _same(opened: os.stat_result, seen: os.stat_result) -> bool:
    return (opened.st_dev, opened.st_ino) == (seen.st_dev, seen.st_ino)


def _file_sha256(name: str, dir_fd: int, rel: str, seen: os.stat_result) -> str:
    """The sha256 of the entry `name` of the directory `dir_fd`, read streamed. Opened relative to the
    directory's descriptor, without following a symlink and without blocking (a FIFO swapped in after the
    listing returns at once instead of waiting for a writer), then fstat must show a regular file with the
    device and inode the listing saw."""
    try:
        fd = os.open(name, os.O_RDONLY | NOFOLLOW | NONBLOCK | CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        raise DraftError(f"the draft's {rel} cannot be read ({_reason(exc)}), or it is no longer a regular file")
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or not _same(opened, seen):
            raise DraftError(f"the draft's {rel} changed while it was read (it is not the file that was listed)")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=True) as fh:
            fd = -1
            for chunk in iter(lambda: fh.read(CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise DraftError(f"the draft's {rel} cannot be read ({_reason(exc)})")
    finally:
        if fd >= 0:
            os.close(fd)


def _open_directory(name: str, dir_fd, rel: str, seen) -> int:
    """A descriptor of a directory, opened without following a symlink and checked against what the listing
    saw, so a directory swapped for a symlink or for another directory after the listing is refused instead
    of being skipped or read in its place."""
    try:
        fd = os.open(name, os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC, dir_fd=dir_fd)
    except OSError as exc:
        raise DraftError(f"the draft's {rel or 'top directory'} cannot be read as a directory ({_reason(exc)}); "
                         "a draft holds regular files and directories only")
    try:
        opened = os.fstat(fd)
    except OSError as exc:
        os.close(fd)
        raise DraftError(f"the draft's {rel or 'top directory'} cannot be read ({_reason(exc)})")
    if not stat.S_ISDIR(opened.st_mode) or (seen is not None and not _same(opened, seen)):
        os.close(fd)
        raise DraftError(f"the draft's {rel or 'top directory'} changed while it was read")
    return fd


def _walk(dir_fd: int, prefix: str, out: list) -> None:
    """Append (path, sha256) for every regular file under the directory `dir_fd`, each entry examined once,
    through descriptors anchored at the draft's top directory."""
    try:
        with os.scandir(dir_fd) as listing:
            names = sorted(entry.name for entry in listing)
    except OSError as exc:
        raise DraftError(f"a directory of the draft cannot be read ({_reason(exc)}: {prefix.rstrip('/') or '.'})")
    for name in names:
        rel = prefix + name
        _check_name(rel)
        try:
            seen = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError as exc:
            raise DraftError(f"the draft's {rel} cannot be read ({_reason(exc)})")
        if stat.S_ISDIR(seen.st_mode):
            child = _open_directory(name, dir_fd, rel, seen)
            try:
                _walk(child, rel + "/", out)
            finally:
                os.close(child)
        elif stat.S_ISREG(seen.st_mode):
            out.append((rel, _file_sha256(name, dir_fd, rel, seen)))
        else:
            raise DraftError(f"the draft holds {rel}, a symlink or a special file; a draft holds regular "
                             "files and directories only")


def manifest(draft_dir: str) -> Tuple[str, List[Tuple[str, str]]]:
    """(digest, [(path, sha256)] sorted by path) of one traversal of the draft: the digest and the files it
    covers always describe the same reading."""
    # "alias.spec/" and "alias.spec/." resolve through a symlinked alias.spec where "alias.spec" does not: the root is
    # normalised first, so the lstat and the no-follow open examine the directory entry itself.
    root = os.path.normpath(draft_dir)
    name = os.path.basename(root)
    try:
        seen = os.lstat(root)
    except OSError:
        raise DraftError(f"the draft {name} does not exist")
    if stat.S_ISLNK(seen.st_mode) or not stat.S_ISDIR(seen.st_mode):
        raise DraftError(f"the draft {name} is not a directory (a symlink is refused)")
    top = _open_directory(root, None, "", seen)
    files: list = []
    try:
        _walk(top, "", files)
    finally:
        os.close(top)
    files.sort()
    return digest_of(files), files


def digest_of(files: List[Tuple[str, str]]) -> str:
    """The digest of a manifest: the sha256 of its sorted "<path>\t<sha256>\n" lines, UTF-8."""
    return hashlib.sha256("".join(f"{rel}\t{sha}\n" for rel, sha in sorted(files)).encode("utf-8")).hexdigest()


def digest(draft_dir: str) -> str:
    """The draft's digest, 64 lowercase hex (see the module docstring for every refusal)."""
    return manifest(draft_dir)[0]


def _blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def mask_fences(text: str) -> str:
    """The text with fenced code blocks (their fence lines included) and HTML comments replaced by spaces,
    offsets and newlines kept, so nothing a reader of the rendered plan does not see as text reads as a heading
    or a line of the plan. CommonMark fences: an opening fence is indented at most three spaces and is three or
    more backticks or tildes (a backtick fence's info string holds no backtick); the closing fence uses the same
    character, is at least as long and is followed only by spaces. An HTML comment runs from `<!--` to the next
    `-->`, across lines. An unclosed fence or comment runs to the end. Inside a fence `<!--` is text; inside a
    comment a fence is text."""
    out, fence, comment = [], None, False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if fence is not None:
            closing = FENCE_CLOSE_RE.match(body)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                fence = None
            out.append(_blank(line))
            continue
        if not comment:
            opening = FENCE_OPEN_RE.match(body)
            if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
                fence = opening.group(1)
                out.append(_blank(line))
                continue
        kept, pos = [], 0
        while pos < len(line):
            if comment:
                close = line.find("-->", pos)
                if close < 0:
                    kept.append(_blank(line[pos:]))
                    pos = len(line)
                else:
                    kept.append(_blank(line[pos:close + 3]))
                    pos, comment = close + 3, False
            else:
                start = line.find("<!--", pos)
                if start < 0:
                    kept.append(line[pos:])
                    pos = len(line)
                else:
                    kept.append(line[pos:start])
                    pos, comment = start, True
                    kept.append(_blank(line[pos:pos + 4]))
                    pos += 4
        out.append("".join(kept))
    return "".join(out)


def section_spans(plan_text: str) -> List[Tuple[int, int]]:
    """(start, end) offsets of the body of every `## Specification changes` section outside fenced code,
    each up to the next ## or ### heading outside fenced code."""
    masked = mask_fences(plan_text)
    spans = []
    for match in SECTION_RE.finditer(masked):
        rest = masked[match.end():]
        end = NEXT_SECTION_RE.search(rest)
        spans.append((match.end(), match.end() + (end.start() if end else len(rest))))
    return spans


def specification_changes(plan_text: str) -> Optional[str]:
    """The plan's `## Specification changes` text with fenced code blanked (every section of that name,
    joined), or None when there is no such section. spec-layout.py reads the records from it, so the records
    and the digest line come from the same parse."""
    spans = section_spans(plan_text)
    if not spans:
        return None
    masked = mask_fences(plan_text)
    return "\n".join(masked[a:b] for a, b in spans)


def plan_digest(plan_text: str) -> Optional[str]:
    """The hex of the plan's one `Draft digest: sha256 <hex>` line, or None (see the module docstring)."""
    masked = mask_fences(plan_text)
    spans = section_spans(plan_text)
    found = []
    offset = 0
    for line in masked.splitlines(keepends=True):
        here, offset = offset, offset + len(line)
        if not LABEL_RE.match(line):
            continue
        if not any(a <= here < b for a, b in spans):
            raise DraftError(f"the line '{line.strip()[:80]}' is outside '## Specification changes'; the draft digest "
                             "is recorded there only")
        value = LINE_RE.match(line.rstrip("\r\n"))
        if not value:
            raise DraftError(f"the line '{line.strip()[:80]}' is not 'Draft digest: sha256 <64 lowercase hex>'")
        found.append(value.group(1))
    if len(found) > 1:
        raise DraftError("the plan's Specification changes carry more than one Draft digest line")
    return found[0] if found else None
