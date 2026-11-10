#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
spec-trace.py — mechanical traceability checks between specification items, an implementation plan
(`ai-planning/<slug>.plan`) and the code and tests that realise it.

Owns one thing: deciding, without judgement, whether every specification item in a plan's scope is
covered by a planned task and by a test, and (after implementation) whether the planned files and tests
exist, cite their items and are not stubs. It is the analysis gate of the implementing-*-from-spec skills,
run before approval (`plan`) and again before the report (`code`, which repeats every plan check). It
changes nothing. What it cannot decide (whether code is really wired into the running system, whether a
test is meaningful) it reports as WARN for the orchestrator's judgement, never as proof.

Plan format it reads (the skills' plan templates produce it):
  ## Scope                    the specification item IDs the plan implements
  ## Global constraints, ## Review focus
  ## Deferred                 records `- <ID> — <reason> (agreed YYYY-MM-DD)`; only records defer
  ## 1. Restated requirements a plan-local ID (SPEC-PLAN-n, for an input without IDs) starts a line here
  ### Task <n> — <title>      one per task, with these field lines (plain or bold labels):
    Implements: <item IDs>    Owns: `<path>`, `<path>` (deleted), ...   Depends: <task numbers> | none
    Wave: <n>                 Tests: `<test path>`, ... | none — <reason>   Verify: <command or observable>

`plan` checks (FAIL unless noted):
  - the required sections exist; Scope names at least one item
  - with --specs: every Scope item is *defined* there (a heading carrying the ID when the files use
    headings), except plan-local IDs, which must be defined in Restated requirements; WARN for each
    concrete path of an item's `Target:` line that no task implementing it owns (patterns are skipped)
  - every Scope item is implemented by a task or deferred by a record, never both; deferred IDs are in
    Scope; a prose mention of an ID under Deferred defers nothing (WARN); every task implements only Scope
    items and at least one
  - task numbers unique; all six fields present, each once; Wave a positive integer; Depends `none` or
    task numbers of earlier waves; a field may wrap: its value runs on to the next field label, blank
    line or heading; Owns and Tests paths repository-relative, normalised, no `..`, not the repository
    root; a backticked Tests span with whitespace or `=`, or with neither `/` nor `.`, is prose, not a
    path; `Tests: none` only with a reason (WARN)
  - no two tasks of one wave own the same file, or a directory holding the other's file
  - no placeholder (TBD, TODO, FIXME, ???, "to be decided"), no scope-reduction wording ("for now",
    "stubbed out", "placeholder", "future enhancement", "simplified version") outside Deferred, no code
    fence (``` or ~~~) outside a section whose heading names commands. Text in backticks or double quotes
    is quotation, and a negated mention ("no placeholder values") is a constraint; neither is checked
`code` checks (needs --repo; --specs is honoured), after every `plan` check:
  - every owned path exists (and an entry marked (deleted) does not), judged by the path's last owner when
    several waves own it (created in one, deleted in a later one); owned directories are expanded and
    must hold a file; owned files are readable, under 2 MB and not empty (package and typing markers,
    keep-files and fixtures excepted); `outside-repo` FAILs an owned path, file or test that resolves
    (through a symlink) outside the repository, and it is not read
  - owned non-test files contain no stub markers (NotImplementedError, TODO, FIXME, "not implemented");
    tests are files under tests/, test/ or src/test/, test_*, *_test.py, *_test.go, *.test.*, *.spec.*,
    conftest.py and *Test, *Tests, *IT, *TestCase .java/.kt/.groovy/.scala
  - every Tests path exists; every item ID the task implements is cited (exact match: not SPEC-QUEUE-10 or
    SPEC-QUEUE-1-extra for SPEC-QUEUE-1) by at least one of the task's tests, and every test cites one
  - WARN when an owned non-test file's stem appears in no other source file (docs, plans and tests
    excluded): a hint that it may be unwired, not a proof either way. Whether code is substantive and wired
    remains the orchestrator's judgement
  - `unowned-change`: every path changed in the working tree against HEAD (modified, staged, deleted,
    renamed or untracked; `git status --porcelain=v1 -z --untracked-files=all`, paths under --repo only),
    and every path changed between the approval baseline commit and HEAD (committed during the run), is
    owned by a task (an Owns entry names the file or a directory holding it) or lies under
    `ai-planning/`. An unowned path FAILs, unless the plan's ledger (`<slug>.ledger.md` next to the plan)
    names that exact path on a line of its `## Amendments` section, or of its `## Baseline` section (a
    change that predates approval): then WARN, for the orchestrator to confirm. A ruling excuses nothing;
    a write outside every Owns is an amendment. The baseline is --base, else the first commit the
    ledger's `## Baseline` names; without one, a `baseline` WARN says committed changes were not checked,
    and a --base that is not a commit FAILs. Not a git work tree: one WARN, and the check is skipped; git
    failing inside a work tree (a corrupt index) FAILs

Usage:
    python3 -I <plugin-root>/core/scripts/spec-trace.py plan <repo>/ai-planning/queue.plan \\
        --specs <repo>/docs/specifications/queue-spec.md
    python3 -I <plugin-root>/core/scripts/spec-trace.py code <repo>/ai-planning/queue.plan --repo <repo>
    python3 -I <plugin-root>/core/scripts/spec-trace.py code <repo>/ai-planning/queue.plan --repo <repo> --base <commit>
    python3 -I <plugin-root>/core/scripts/spec-trace.py plan x.plan --id-regex 'SPEC-F\\d{3}|TC-\\d{3}' --json

Exit codes: 0 no FAIL (WARN lines may print), 1 at least one FAIL, 2 a file could not be read.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Matches SPEC-QUEUE-12, SPEC-API-3 (structured items) and SPEC-F001, SPEC-NF003 (demos kits). A plan
# whose input has no IDs numbers its requirements SPEC-PLAN-1, SPEC-PLAN-2, ... (the contract, section 2).
DEFAULT_ID_RE = r"\bSPEC-(?:[A-Z][A-Z0-9]*-)+\d+\b|\bSPEC-[A-Z]+\d+\b"
FIELDS = ("Implements", "Owns", "Depends", "Wave", "Tests", "Verify")
REQUIRED_SECTIONS = ("scope", "global constraints", "review focus", "deferred")
PLACEHOLDER_RE = re.compile(r"\bTBD\b|\bTODO\b|\bFIXME\b|\?\?\?|\bto be (?:decided|determined)\b", re.I)
# "stubbed client" in a test strategy is legitimate; only a stubbed *deliverable* is a scope cut.
SCOPE_CUT_RE = re.compile(r"\bfor now\b|\bstubbed out\b|\bas a stub\b|\bstub implementation\b|"
                          r"\bplaceholder\b|\bfuture enhancement\b|\bsimplified version\b|\bv1 only\b", re.I)
SCOPE_CUT_OK_SECTION = re.compile(r"^deferred", re.I)
FENCE_OK_SECTION = re.compile(r"command", re.I)
QUOTED_RE = re.compile(r"`[^`]*`|\"[^\"]*\"|“[^”]*”")
STUB_RE = re.compile(r"NotImplementedError|\bTODO\b|\bFIXME\b|not implemented|raise NotImplemented", re.I)
TASK_RE = re.compile(r"^###\s+Task\s+(\S+?)\s*(?:—|-|:|$).*$", re.M)
FIELD_RE = re.compile(r"^\s*[-*]?\s*\**(%s)\**\s*:\**\s*(.*)$" % "|".join(FIELDS), re.M)
OWNS_ENTRY_RE = re.compile(r"`([^`]+)`(\s*\(deleted\))?")
MAX_READ = 2_000_000
# Files that are legitimately empty: package and typing markers, keep-files, fixtures.
EMPTY_OK_RE = re.compile(r"(^|/)(__init__\.py|py\.typed|\.gitkeep|\.keep)$|(^|/)fixtures?/")
# "no placeholder", "never a stub": a negated mention is a constraint, not a scope cut.
NEGATED_RE = re.compile(r"\b(no|not|never|without|nor)\b(\W+\w+){0,2}\W*$", re.I)


class Report:
    def __init__(self) -> None:
        self.lines: list[dict] = []

    def add(self, level: str, check: str, detail: str) -> None:
        self.lines.append({"level": level, "check": check, "detail": detail})

    @property
    def failed(self) -> bool:
        return any(line["level"] == "FAIL" for line in self.lines)


def read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"spec-trace: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) for every ## section; the preamble has heading ''."""
    parts = re.split(r"^(##\s+(?!#).*)$", text, flags=re.M)
    out = [("", parts[0])]
    for i in range(1, len(parts), 2):
        out.append((parts[i].lstrip("#").strip(), parts[i + 1] if i + 1 < len(parts) else ""))
    return out


def section_body(text: str, name: str) -> str | None:
    for heading, body in sections(text):
        if re.match(r"(\d+\.\s*)?%s\b" % re.escape(name), heading, re.I):
            return re.split(r"^#{3,}\s", body, flags=re.M)[0]  # tasks may follow without a ## heading
    return None


def id_cited(item: str, text: str) -> bool:
    """Exact citation: SPEC-QUEUE-1 is cited neither by SPEC-QUEUE-10 nor by SPEC-QUEUE-1-extra."""
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(item), text) is not None


def norm_path(raw: str, rep: Report, where: str) -> str | None:
    path = raw.strip()
    if os.path.isabs(path):
        rep.add("FAIL", "path", f"{where}: `{path}` is absolute; paths are repository-relative")
        return None
    normal = os.path.normpath(path)
    if normal == ".." or normal.startswith(".." + os.sep):
        rep.add("FAIL", "path", f"{where}: `{path}` leaves the repository")
        return None
    if normal == ".":
        rep.add("FAIL", "path", f"{where}: `{path}` is the whole repository; name the files or directories")
        return None
    return normal


def parse_tasks(text: str, id_re: re.Pattern, rep: Report) -> dict[int, dict]:
    tasks: dict[int, dict] = {}
    matches = list(TASK_RE.finditer(text))
    for i, m in enumerate(matches):
        label = m.group(1)
        if not label.isdigit() or int(label) < 1:
            rep.add("FAIL", "task-number", f"'{m.group(0).strip()}': task numbers are positive integers")
            continue
        n = int(label)
        if n in tasks:
            rep.add("FAIL", "task-number", f"Task {n} appears twice")
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = re.split(r"^##\s+(?!#)", text[m.end():end], flags=re.M)[0]
        fields: dict[str, str] = {}
        current = None  # a field's value runs on over wrapped lines, to the next label, blank line or heading
        for line in body.splitlines():
            fm = FIELD_RE.match(line)
            if fm:
                current = None
                if fm.group(1) in fields:
                    rep.add("FAIL", "task-field", f"Task {n} repeats {fm.group(1)}:; keep one line per field")
                    continue
                current = fm.group(1)
                fields[current] = fm.group(2).strip()
            elif not line.strip() or line.lstrip().startswith("#"):
                current = None
            elif current:
                fields[current] = (fields[current] + " " + line.strip()).strip()
        owns = []
        for om in OWNS_ENTRY_RE.finditer(fields.get("Owns", "")):
            path = norm_path(om.group(1), rep, f"Task {n} Owns")
            if path:
                owns.append({"path": path, "deleted": bool(om.group(2))})
        # `none — <reason>` names no test: code quoted in the reason is prose, not a test path.
        tests_raw = "" if re.match(r"none\b", fields.get("Tests", ""), re.I) else fields.get("Tests", "")
        tests = []
        for span in re.findall(r"`([^`]+)`", tests_raw):
            span = span.strip()
            if re.search(r"\s|=", span) or not re.search(r"[/.]", span):
                # Prose quoted in Tests (`command = plan`) is not a path. Caught at plan time, before
                # approval; found by `code`, fixing it would mean editing the approved plan.
                rep.add("FAIL", "task-tests", f"Task {n} Tests: `{span}` is not a path; backtick only test "
                                              "paths and describe the assertions in prose")
                continue
            path = norm_path(span, rep, f"Task {n} Tests")
            if path:
                tests.append(path)
        depends_raw = fields.get("Depends", "")
        tasks[n] = {
            "fields": fields,
            "implements": sorted(set(id_re.findall(fields.get("Implements", "")))),
            "owns": owns,
            "tests": tests,
            "depends_raw": depends_raw,
            "depends": [int(x) for x in re.findall(r"\d+", depends_raw)],
            "wave": int(fields["Wave"]) if re.fullmatch(r"\d+", fields.get("Wave", "")) and
            int(fields["Wave"]) > 0 else None,
        }
    return tasks


def spec_definitions(specs: list[str], id_re: re.Pattern) -> tuple[set[str], set[str], dict[str, list[str]]]:
    """(IDs mentioned anywhere, IDs defined by a heading, Target paths per defined ID)."""
    mentioned, defined, targets = set(), set(), {}
    for s in specs:
        text = read(s)
        mentioned |= set(id_re.findall(text))
        heads = list(re.finditer(r"^#{2,5}\s+.*$", text, flags=re.M))
        for i, h in enumerate(heads):
            ids = id_re.findall(h.group(0))
            if not ids:
                continue
            body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            tline = re.search(r"^\s*[-*]?\s*\**Target:?\**:?\s*(.*)$", body, flags=re.M)
            for item in ids[:1]:
                defined.add(item)
                targets[item] = re.findall(r"`([^`]+)`", tline.group(1)) if tline else []
    return mentioned, defined, targets


def overlaps(a: str, b: str) -> bool:
    if "." in (a, b):  # the repository root contains everything
        return True
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def deferred_records(text: str, id_re: re.Pattern, scope: list[str], rep: Report) -> set[str]:
    """IDs deferred by a record line `- <ID> — <reason> (agreed YYYY-MM-DD)`; prose mentions do not count."""
    body = section_body(text, "deferred") or ""
    deferred = set()
    for line in body.splitlines():
        m = re.match(r"^\s*[-*]\s+(\S+)\s+(—|-|:)\s+.+\bagreed\b.*\b\d{4}-\d{2}-\d{2}\b", line, re.I)
        if m and id_re.fullmatch(m.group(1)):
            deferred.add(m.group(1))
        elif id_re.search(line):
            rep.add("WARN", "deferred", f"'{line.strip()[:100]}' mentions an ID but is not a deferral record "
                                        "('- <ID> — <reason> (agreed YYYY-MM-DD)'), so it defers nothing")
    for item in sorted(deferred - set(scope)):
        rep.add("FAIL", "deferred", f"{item} is deferred but not in Scope")
    return deferred


def strip_quotes(line: str) -> str:
    return QUOTED_RE.sub("", line)


def check_plan(plan_path: str, specs: list[str], id_re: re.Pattern, rep: Report) -> dict[int, dict]:
    text = read(plan_path)
    for name in REQUIRED_SECTIONS:
        if section_body(text, name) is None:
            rep.add("FAIL", "section", f"no '## {name.title()}' section")
    scope = sorted(set(id_re.findall(section_body(text, "scope") or "")))
    deferred = deferred_records(text, id_re, scope, rep)
    tasks = parse_tasks(text, id_re, rep)
    if not scope:
        rep.add("FAIL", "scope", "the Scope section names no specification item IDs")
    if not tasks:
        rep.add("FAIL", "tasks", "no '### Task <n> — <title>' sections")
    # Plan-local IDs (an input without IDs) are defined in Restated requirements, not in the --specs files.
    restated = section_body(text, "1. restated requirements") or section_body(text, "restated requirements") or ""
    local = [i for i in scope if i.startswith("SPEC-PLAN-")]
    for item in local:
        if not re.search(r"^\s*(?:[-*]\s*)?\**%s\b" % re.escape(item), restated, re.M):
            rep.add("FAIL", "scope-local", f"{item} is a plan-local ID but no line of Restated requirements "
                                           "starts with it (its definition and source)")
    if specs:
        mentioned, defined, targets = spec_definitions(specs, id_re)
        for item in scope:
            if item in local:
                continue
            if item not in mentioned:
                rep.add("FAIL", "scope-unknown", f"{item} is in Scope but in none of the --specs files")
            elif defined and item not in defined:
                rep.add("FAIL", "scope-undefined", f"{item} is mentioned in the --specs files but no heading "
                                                   "defines it")
            elif targets.get(item) and item not in deferred:
                owned = [o["path"] for t in tasks.values() if item in t["implements"] for o in t["owns"]]
                for target in targets[item]:
                    if re.search(r"[<>*{}\[\]?]", target):
                        continue  # a pattern, not a path: not checked mechanically
                    wanted = os.path.normpath(target.rstrip("/"))
                    if owned and not any(overlaps(o, wanted) for o in owned):
                        rep.add("WARN", "target", f"{item}: no task implementing it owns its Target path "
                                                  f"`{target}` (another plan may own it)")
    implemented = {i for t in tasks.values() for i in t["implements"]}
    for item in sorted(deferred & implemented):
        rep.add("FAIL", "deferred", f"{item} is both deferred and implemented by a task")
    for item in scope:
        if item not in implemented and item not in deferred:
            rep.add("FAIL", "uncovered", f"{item} is in Scope but no task implements it (or record it under "
                                         "Deferred as '- <ID> — <reason> (agreed YYYY-MM-DD)')")
    for n, t in sorted(tasks.items()):
        for field in FIELDS:
            if not t["fields"].get(field):
                rep.add("FAIL", "task-field", f"Task {n} has no {field}: line")
        if t["fields"].get("Implements") and not t["implements"]:
            rep.add("FAIL", "task-implements", f"Task {n} Implements: names no item ID")
        for item in t["implements"]:
            if scope and item not in scope:
                rep.add("FAIL", "unmapped", f"Task {n} implements {item}, which is not in Scope")
        if t["fields"].get("Wave") and t["wave"] is None:
            rep.add("FAIL", "wave", f"Task {n} Wave: '{t['fields']['Wave']}' is not a positive integer")
        if t["fields"].get("Owns") and not t["owns"]:
            rep.add("FAIL", "task-owns", f"Task {n} Owns: names no `path`")
        tests_field = t["fields"].get("Tests", "")
        if tests_field and not t["tests"]:
            if re.match(r"none\s*(—|-|:)\s*\S", tests_field, re.I):
                rep.add("WARN", "task-tests", f"Task {n} has no test: {tests_field}")
            else:
                rep.add("FAIL", "task-tests", f"Task {n} Tests: names no `path` (use 'none — <reason>' "
                                              "only when no test can prove the task)")
        dep = t["depends_raw"].strip()
        if dep and dep.lower() != "none" and not re.fullmatch(r"(Task\s*)?\d+(\s*,\s*(Task\s*)?\d+)*", dep, re.I):
            rep.add("FAIL", "depends", f"Task {n} Depends: '{dep}' is neither 'none' nor task numbers")
        for d in t["depends"]:
            if d not in tasks:
                rep.add("FAIL", "depends", f"Task {n} depends on Task {d}, which does not exist")
            elif t["wave"] and tasks[d]["wave"] and tasks[d]["wave"] >= t["wave"]:
                rep.add("FAIL", "depends", f"Task {n} (wave {t['wave']}) depends on Task {d} "
                                           f"(wave {tasks[d]['wave']}); dependencies must be in an earlier wave")
    waves: dict[int, list[int]] = {}
    for n, t in tasks.items():
        if t["wave"]:
            waves.setdefault(t["wave"], []).append(n)
    # Paths that already exist are also compared by what they are on disk: b.py -> a.py owned by two tasks of
    # one wave is one file with two writers. The repository is the plan's (<repo>/ai-planning/<slug>.plan).
    plan_dir = os.path.dirname(os.path.abspath(plan_path))
    repo_root = os.path.dirname(plan_dir) if os.path.basename(plan_dir) == "ai-planning" else None
    # A test file the task writes is one of its files: `code` fails a written path no task owns, and after
    # approval that costs an amendment and a second approval, so catch it here. A test that already exists
    # may be cited unchanged, so that is a WARN.
    owned_all = [o["path"] for t in tasks.values() for o in t["owns"]]
    for n, t in sorted(tasks.items()):
        for test in t["tests"]:
            if any(overlaps(o, test) for o in owned_all):  # also a Tests directory holding an owned test file
                continue
            exists = repo_root is not None and os.path.lexists(os.path.join(repo_root, test))
            if exists:
                rep.add("WARN", "tests-unowned", f"Task {n} Tests: `{test}` exists and no task owns it; if the task "
                                                 "edits it, add it to the task's Owns:")
            else:
                rep.add("FAIL", "tests-unowned", f"Task {n} Tests: `{test}` does not exist yet and no task owns it; "
                                                 "a test file the task writes goes in its Owns: as well")

    def physical(rel: str) -> str:
        if repo_root is None or not os.path.lexists(os.path.join(repo_root, rel)):
            return rel
        return os.path.realpath(os.path.join(repo_root, rel))

    for wave, members in sorted(waves.items()):
        members = sorted(members)
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                for pa in tasks[a]["owns"]:
                    for pb in tasks[b]["owns"]:
                        if overlaps(pa["path"], pb["path"]) or (
                                os.path.isabs(physical(pa["path"])) and os.path.isabs(physical(pb["path"])) and
                                overlaps(physical(pa["path"]), physical(pb["path"]))):
                            rep.add("FAIL", "wave-conflict", f"wave {wave}: Task {a} and Task {b} both own "
                                                             f"{max(pa['path'], pb['path'], key=len)}")
    for heading, body in sections(text):
        for line in body.splitlines():
            bare = strip_quotes(line)
            for regex, check, hint in ((PLACEHOLDER_RE, "placeholder", ""),
                                       (SCOPE_CUT_RE, "scope-cut", " (record it under Deferred with the user's "
                                                                   "agreement, or deliver it)")):
                for m in regex.finditer(bare):
                    if NEGATED_RE.search(bare[:m.start()]):
                        continue  # "no placeholder", "never stubbed out": a constraint, not a gap
                    if check == "scope-cut" and SCOPE_CUT_OK_SECTION.search(heading):
                        continue
                    rep.add("FAIL", check, f"[{heading or 'preamble'}] {line.strip()[:120]}{hint}")
                    break
        if re.search(r"^\s*(```|~~~)", body, flags=re.M) and not FENCE_OK_SECTION.search(heading):
            rep.add("FAIL", "code-in-plan", f"[{heading or 'preamble'}] code fence; the plan is prose only")
    return tasks


def git(repo: Path, *args: str) -> subprocess.CompletedProcess | None:
    """Run git with REPO as the working directory, no shell; None when git cannot start."""
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, check=False)
    except OSError:
        return None


def repo_files(repo: Path) -> list[Path]:
    proc = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if proc is not None and proc.returncode == 0:
        return [repo / p for p in proc.stdout.split("\0") if p]  # -z: names unquoted, any characters
    return [p for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts]


class ScanError(Exception):
    """git could not list the changes of a repository it recognises as a work tree."""


def changed_paths(repo: Path, base: str | None = None) -> list[str] | None:
    """Paths (relative to REPO) changed in the working tree or index against HEAD, untracked files included,
    and, with a base commit, every path changed between it and HEAD (committed during the run); None when
    REPO is not inside a git work tree. Raises ScanError when git fails inside one."""
    inside = git(repo, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    prefix_proc = git(repo, "rev-parse", "--show-prefix")
    if prefix_proc is None or prefix_proc.returncode != 0:
        raise ScanError(f"git rev-parse --show-prefix failed: {(prefix_proc.stderr if prefix_proc else '').strip()}")
    prefix = prefix_proc.stdout.strip()
    proc = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", ".")
    if proc is None or proc.returncode != 0:
        raise ScanError(f"git status failed: {(proc.stderr if proc else 'git did not start').strip()[:300]}")
    # -z format: "XY path\0", and for a rename or copy "XY new\0orig\0"; paths are relative to the top level.
    entries = proc.stdout.split("\0")
    found: list[str] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, paths = entry[:2], [entry[3:]]
        if "R" in status or "C" in status:
            if i < len(entries) and entries[i]:
                paths.append(entries[i])
            i += 1
        found.extend(paths)
    if base:
        diff = git(repo, "diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--", ".")
        if diff is None or diff.returncode != 0:
            raise ScanError(f"git diff {base} HEAD failed: {(diff.stderr if diff else '').strip()[:300]}")
        found.extend(p for p in diff.stdout.split("\0") if p)
    out: list[str] = []
    seen: set[str] = set()
    for p in found:
        if p.startswith(prefix):
            rel = p[len(prefix):].rstrip("/")
            if rel and rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out


def resolve_base(repo: Path, plan_path: str, given: str | None, rep: Report) -> str | None:
    """The approval baseline commit: --base, else the first commit the ledger's ## Baseline names. A --base
    that is not a commit FAILs; a ledger without a commit that resolves WARNs (committed changes unchecked)."""
    def commit(ref: str) -> str | None:
        proc = git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
        return proc.stdout.strip() if proc is not None and proc.returncode == 0 and proc.stdout.strip() else None

    if given:
        sha = commit(given)
        if not sha:
            rep.add("FAIL", "baseline", f"--base {given} is not a commit of {repo}; nothing was compared with it")
        return sha
    for token in re.findall(r"\b[0-9a-f]{7,40}\b", ledger_sections(plan_path)["baseline"]):
        sha = commit(token)
        if sha:
            return sha
    rep.add("WARN", "baseline", "no baseline commit (--base, or a commit in the ledger's ## Baseline): changes "
                                "committed since approval were not checked against the plan's Owns")
    return None


def path_named(path: str, text: str) -> bool:
    """`docs/costs.md` names that exact path: not docs/costs.md.bak, not old-docs/costs.md."""
    return re.search(r"(?<![\w./-])%s(?![\w/-]|\.\w)" % re.escape(path), text) is not None


def ledger_sections(plan_path: str) -> dict[str, str]:
    """The ledger's Amendments and Baseline section bodies ('' when the ledger or a section is absent)."""
    plan = Path(plan_path)
    ledger = plan.with_name(plan.stem + ".ledger.md")
    try:
        text = ledger.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"amendments": "", "baseline": ""}
    found = {"amendments": "", "baseline": ""}
    for heading, body in sections(text):
        if re.match(r"amendments?\b", heading, re.I):
            found["amendments"] += body
        elif re.match(r"baseline\b", heading, re.I):
            found["baseline"] += body
    return found


def check_unowned(plan_path: str, repo: Path, tasks: dict[int, dict], rep: Report,
                  base: str | None = None) -> None:
    inside = git(repo, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        rep.add("WARN", "unowned-change", f"{repo} is not a git work tree; writes outside every task's Owns "
                                          "were not checked")
        return
    sha = resolve_base(repo, plan_path, base, rep)
    try:
        changed = changed_paths(repo, sha) or []
    except ScanError as exc:
        rep.add("FAIL", "unowned-change", f"the changes of {repo} could not be listed ({exc}), so writes outside "
                                          "every task's Owns were not checked")
        return
    owned = [o["path"] for t in tasks.values() for o in t["owns"]]
    ledger = ledger_sections(plan_path)
    for rel in changed:
        if rel == "ai-planning" or rel.startswith("ai-planning/"):
            continue
        if any(rel == o or rel.startswith(o + "/") for o in owned):
            continue
        amended = any(path_named(rel, line) for line in ledger["amendments"].splitlines())
        baseline = any(path_named(rel, line) for line in ledger["baseline"].splitlines())
        if amended:
            rep.add("WARN", "unowned-change", f"{rel} is changed and no task owns it; the ledger's Amendments "
                                              "name it, so check that the amended plan was approved")
        elif baseline:
            rep.add("WARN", "unowned-change", f"{rel} is changed and no task owns it; the ledger's Baseline "
                                              "lists it as changed before approval, so check it was not edited since")
        else:
            rep.add("FAIL", "unowned-change", f"{rel} is changed but no task owns it (a write outside every "
                                              "task's Owns is an amendment: snapshot the plan, amend it, ask)")


def is_test(rel: str) -> bool:
    name = os.path.basename(rel)
    return rel.startswith(("tests/", "test/", "src/test/")) or any(
        part in rel for part in ("/tests/", "/__tests__/", "/src/test/")) or name.startswith("test_") \
        or name.endswith(("_test.py", "_test.go")) or ".test." in name or ".spec." in name or name == "conftest.py" \
        or re.search(r"(Test|Tests|IT|TestCase)\.(java|kt|groovy|scala)$", name) is not None


def is_source_corpus(rel: str) -> bool:
    """Files that count as 'wiring' evidence: code and configuration, not plans, docs or tests."""
    return not (rel.startswith(("ai-planning/", "docs/")) or rel.endswith((".md", ".lock", ".plan"))
                or is_test(rel))


def check_code(plan_path: str, repo: Path, id_re: re.Pattern, rep: Report, specs: list[str],
               base: str | None = None) -> None:
    tasks = check_plan(plan_path, specs, id_re, rep)
    files = repo_files(repo)
    cache: dict[Path, str | None] = {}

    def text_of(p: Path) -> str | None:
        if p not in cache:
            try:
                cache[p] = p.read_text(encoding="utf-8", errors="replace") if p.stat().st_size <= MAX_READ else None
            except OSError:
                cache[p] = None
        return cache[p]

    corpus = [f for f in files if is_source_corpus(os.path.relpath(f, repo))]
    real_repo = os.path.realpath(str(repo))

    def outside(p: Path, n: int, what: str) -> bool:
        """A path that resolves (through a symlink) outside the repository is not the project's file."""
        real = os.path.realpath(str(p))
        if real == real_repo or real.startswith(real_repo + os.sep):
            return False
        rep.add("FAIL", "outside-repo", f"Task {n}: {what} {os.path.relpath(p, repo)} resolves outside the "
                                        f"repository, to {real}")
        return True

    # A path owned in several waves (created in one, deleted in a later one) is checked against the
    # expectation of its last owner only.
    last_owner: dict[str, tuple[int, int]] = {}
    deletions: list[tuple[tuple[int, int], str]] = []
    for n, t in tasks.items():
        for owned in t["owns"]:
            key = (t["wave"] or 0, n)
            if owned["path"] not in last_owner or key > last_owner[owned["path"]]:
                last_owner[owned["path"]] = key
            if owned["deleted"]:
                deletions.append((key, owned["path"]))

    def entries(directory: Path, n: int, what: str) -> list[Path]:
        """The files under a directory. A symlink found on the way (a file, or a directory rglob does not
        enter) is checked against the repository first: one leading outside FAILs and is not read."""
        out = []
        for p in directory.rglob("*"):
            if p.is_symlink() and outside(p, n, what):
                continue
            if p.is_file():
                out.append(p)
        return out

    for n, t in sorted(tasks.items()):
        for owned in t["owns"]:
            path = repo / owned["path"]
            if last_owner.get(owned["path"], (0, n))[1] != n:
                continue
            key = (t["wave"] or 0, n)
            if any(k > key and (owned["path"] == d or owned["path"].startswith(d + "/")) for k, d in deletions):
                continue  # a later wave deletes the directory that holds it
            if owned["deleted"]:
                if path.exists():
                    rep.add("FAIL", "owned-not-deleted", f"Task {n}: {owned['path']} should be deleted but exists")
                continue
            if not path.exists():
                rep.add("FAIL", "owned-missing", f"Task {n}: {owned['path']} does not exist")
                continue
            if outside(path, n, "owned path"):
                continue
            members = entries(path, n, "owned file") if path.is_dir() else [path]
            if path.is_dir() and not members:
                rep.add("FAIL", "empty", f"Task {n}: directory {owned['path']} holds no file")
            for member in members:
                rel = os.path.relpath(member, repo)
                if member != path and outside(member, n, "owned file"):
                    continue
                body = text_of(member)
                if body is None:
                    rep.add("FAIL", "unreadable", f"Task {n}: {rel} is unreadable or over {MAX_READ} bytes")
                    continue
                if not body.strip():
                    if not EMPTY_OK_RE.search(rel):
                        rep.add("FAIL", "empty", f"Task {n}: {rel} is empty")
                    continue
                if is_test(rel):
                    continue
                for lineno, line in enumerate(body.splitlines(), 1):
                    if STUB_RE.search(line):
                        rep.add("FAIL", "stub", f"Task {n}: {rel}:{lineno}: {line.strip()[:100]}")
                stem = member.stem
                if stem not in {"__init__", "index", "main", "app", "handler"} and not any(
                        f != member and stem in (text_of(f) or "") for f in corpus):
                    rep.add("WARN", "unwired", f"Task {n}: no other source file mentions '{stem}' (check that "
                                               "something that runs reaches it)")
        test_bodies: dict[str, str] = {}
        for test in t["tests"]:
            path = repo / test
            if not path.exists():
                rep.add("FAIL", "test-missing", f"Task {n}: test {test} does not exist")
                continue
            if outside(path, n, "test"):
                continue
            test_bodies[test] = "".join(text_of(p) or "" for p in entries(path, n, "test file")) \
                if path.is_dir() else (text_of(path) or "")
        if test_bodies:
            for item in t["implements"]:
                if not any(id_cited(item, b) for b in test_bodies.values()):
                    rep.add("FAIL", "test-uncited", f"Task {n}: none of its tests cites {item}")
            for test, body in test_bodies.items():
                if t["implements"] and not any(id_cited(i, body) for i in t["implements"]):
                    rep.add("FAIL", "test-uncited", f"Task {n}: {test} cites none of {', '.join(t['implements'])}")
    check_unowned(plan_path, repo, tasks, rep, base)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__.split("Usage:", 1)[1])
    parser.add_argument("mode", choices=["plan", "code"])
    parser.add_argument("plan", help="the ai-planning/<slug>.plan file")
    parser.add_argument("--specs", nargs="+", default=[], help="specification files the Scope items come from")
    parser.add_argument("--repo", help="the project repository root (required for `code`)")
    parser.add_argument("--base", help="code mode: the approval baseline commit (default: the first commit the "
                                       "ledger's ## Baseline names); changes committed since it are checked too")
    parser.add_argument("--id-regex", default=DEFAULT_ID_RE, help="regex for specification item IDs")
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args()
    id_re = re.compile(args.id_regex)
    rep = Report()
    if args.mode == "plan":
        check_plan(args.plan, args.specs, id_re, rep)
    else:
        if not args.repo:
            parser.error("code mode needs --repo")
        check_code(args.plan, Path(args.repo).expanduser().resolve(), id_re, rep, args.specs, args.base)
    if args.json:
        print(json.dumps({"mode": args.mode, "plan": args.plan, "failed": rep.failed, "findings": rep.lines},
                         indent=1))
    else:
        for line in rep.lines:
            print(f"{line['level']} {line['check']}: {line['detail']}")
        fails = sum(1 for x in rep.lines if x["level"] == "FAIL")
        print(f"spec-trace {args.mode}: {fails} FAIL, {len(rep.lines) - fails} WARN")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
