#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""review-isolation.py: keeps a reviewer subagent read-only (docs/design-notes.md, "Review model", section 3).

Owner: the implement-from-spec plugin; this file lives in the plugin's core/gate/ directory. Standard
library only (Python 3.9+, the python3 macOS ships). It runs on every tool call through the plugin's one
PreToolUse hook, core/gate/ifs-pretool.py (matcher "*", onFailure "block"), which calls main() in-process; a
crash of this check denies the call there. glob, shlex and tempfile are imported where they are needed, so
the checks most calls take load only json, re and the modules imported below.

Registration. A Skill call made inside a subagent (the payload carries `agent_id`) that loads one of the
reviewer skills (REVIEWER_SKILLS, as `implement-from-spec:<name>` or the bare `<name>`) records the agent
and its role in <state>/review-isolation/<session_id>.json, written atomically under an exclusive lock on a
sidecar lock file. <state> is $CLAUDE_PLUGIN_DATA when set, else $XDG_STATE_HOME/implement-from-spec, else
~/.local/state/implement-from-spec. The agent and its role are first added to the session's activation
record, ~/.local/state/implement-from-spec/active/review-<session_id>.json (core/gate/ifs_paths.py
review_marker_file; HOME alone locates it): a reviewer the record names but the state file no longer does
(the state was removed, damaged and reset, or moved with CLAUDE_PLUGIN_DATA or XDG_STATE_HOME) has every call
denied, so the isolation is never lifted by losing the state. In a gated session the approval gate also
protects both directories from tool calls (ifs_paths.state_write_roots). The registering call itself goes
ahead (no output). When the record or the state cannot be written, the Skill call is denied: a reviewer never
runs unregistered. The main conversation (no
`agent_id`) and subagents that never loaded a reviewer skill (implementation waves) are never affected: the
hook prints nothing and exits 0 for them.

What a registered reviewer may do is an allowlist; everything else is denied (permissionDecision "deny",
with a reason telling it to list the call under the parts it could not complete; each denial is appended to
the session's state file):
  - Allowed: Read, Grep and Glob within the roots below, Bash within the allowlist below, and the bookkeeping
    tools in REVIEWER_TOOLS that touch no file and start nothing (TodoWrite and its successors TaskCreate,
    TaskGet, TaskList and TaskUpdate, ToolSearch, SubagentHandback). Any other tool is denied, including one
    Claude Code adds later: Write, Edit, MultiEdit, NotebookEdit, WebFetch, WebSearch, Agent, Task, every
    mcp__* tool, the other shells and schedulers, and any further Skill call. (Until 2026-11-12 this was a
    denylist, so a tool it did not name was allowed.)
  - Read, Grep and Glob outside the allowed roots (the git top level of the payload's cwd, the plugin
    root, <state>/review-snapshots under both of review-snapshot.py's default roots, snapshot_roots) or on
    a credential path anywhere (CREDENTIAL_DIRS, CREDENTIAL_FILES,
    any path component `.env` or `.env.*`); paths are checked as named and after symlinks are resolved.
    One exception, for the running-external-review role only: Read of its own session's background Bash
    task output, <tmp>/claude-<uid>/<project>/<session_id>/tasks/<id>.output (is_task_output), because it
    runs spec-external-review.py in the background and reads the result there; its command may carry
    `--external-review off|bedrock-gpt`, the mode the user asked for (contract section 9), and no other
    setting flag
  - Bash, unless every command of the line (split on `|`, `&&` and `||`) is on the read-only allowlist
    (check_bash). The line is scanned character by character with the shell's quoting rules, so a `|` or
    `>` inside quotes is a word, not an operator; each segment's words are then re-split with shlex and
    must agree. Two exceptions: `2>&1` as a whole word (no file target), and `${CLAUDE_PLUGIN_ROOT}` or
    `$CLAUDE_PLUGIN_ROOT` (bare or inside double quotes) starting the script path python3 -I runs, expanded
    from the hook's environment. Anything else the scanner cannot classify with certainty denies: any other
    `>` or `<`, every other `$`, backticks,
    `;`, a single `&`, `(`, `)`, `{`, `}`, a comment, a newline or control character, an unterminated
    quote, a leading assignment, an unquoted `~` after `=` or `:`, a glob component starting with a dot.
    Every word that can name a file is checked like a Read path (globs are expanded to check every match).
    grep, rg, sort, wc, file and diff take only the read-only options OPTION_SPECS lists, and find only the
    primaries FIND_SPEC lists, each matched by its full name: an abbreviation, an unlisted option (`rg
    --hostname-bin`, `--pre`, `-z`, `-L`; `grep -R`, `--filter`; `sort` and `wc --files0-from`, `file -f`;
    `find -files0-from`, `-L`, `-H`, `-follow`, `-rm`) and a value given to an option that takes none are
    denied (until 2026-11-12 grep and rg had a short denylist, and sort, wc, file, diff and find until the
    seventh round of the PR 1 security work). diff compares two directories only with --no-dereference, and
    for a directory and a file checks the file it reads in the directory (check_diff); ls takes no -L

Failure policy. Every decision is JSON on stdout with exit 0. On an internal error the hook denies when the
caller is (or, from a state file it cannot parse, may be) a registered reviewer, and prints nothing for
anyone else; a payload that is not JSON is searched for its session and agent ids so a registered reviewer
still fails closed. Because hooks.json sets onFailure "block", a crash of this script would block the
call for everyone, so no path exits non-zero.

It is enforcement inside Claude Code's tool layer, not an operating-system sandbox: the allowlisted
programs run with the user's permissions, the external-review script still sends what it documents, and
Grep, grep -r or rg over an allowed directory can still read a .env file inside it.

Claude Code hooks reference relied on (https://code.claude.com/docs/en/hooks, read 2026-10-26):
  - "Hooks from settings files, managed policy settings, and plugins also run inside subagents. When a
    subagent calls a tool, tool events such as `PreToolUse` and `PostToolUse` fire the same configured hooks
    as in the main conversation, and the input carries the `agent_id` and `agent_type` common input fields
    that identify the subagent."
  - Common input fields: "`agent_id` | Unique identifier for the subagent or in-process teammate the hook
    fires in." and "`cwd` | Current working directory when the hook is invoked".
  - "In addition to the common input fields, PreToolUse hooks receive `tool_name`, `tool_input`, and
    `tool_use_id`."
  - Matchers: "`\"*\"`, `\"\"`, or omitted | Match all | fires on every occurrence of the event".
  - Read: "`file_path` | string | ... | Absolute path to the file to read"; Glob: "`pattern` ... Glob
    pattern to match files against" and "`path` ... Optional directory to search in. Defaults to current
    working directory"; Grep: "`path` ... Optional file or directory to search in" and "`glob` ...
    Optional glob pattern to filter files"; WebSearch: "`query`".
  - Decision: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
    "permissionDecisionReason": "..."}}; "Exit 0 means success, and is the intended exit code when you print
    JSON for structured control."
  - onFailure: "Set `\"onFailure\": \"block\"` on a `command` or `http` hook" to block the action "when a
    hook fails or times out"; failure includes "your hook exits with any other code" than 0 or 2.
  The reference does not document the Skill tool's input; its field is `skill`, as the Skill tool's own
  input schema names it and core/gate/spec-approval-gate.py (cmd_activate) already reads it.

Usage (by hand; Claude Code runs it through ifs-pretool.py):
  echo '{"session_id":"s1","agent_id":"a1","cwd":"/repo","tool_name":"Write","tool_input":{}}' \\
    | python3 -I <plugin-root>/core/gate/review-isolation.py
"""

import os
import sys
from time import monotonic as _monotonic  # first: the opt-in timing log (run_timed) counts from here; built in

_HOOK_T0 = _monotonic()

# The gate's own directory is not an import location (see spec-approval-gate.py): a json.py written next to
# this file would otherwise run inside every hook call.
if sys.path and os.path.realpath(sys.path[0] or os.getcwd()) == os.path.dirname(os.path.realpath(__file__)):
    del sys.path[0]

import contextlib  # noqa: E402 - after the sys.path guard above
import fcntl  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402

HOOK_FILE = os.path.realpath(__file__)
DERIVED_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HOOK_FILE)))
PLUGIN_NAME = "implement-from-spec"
REVIEWER_SKILLS = ("code-reviewer", "iac-security-reviewer", "reviewing-terraform-code",
                   "reviewing-terraform-security", "running-external-review")
EXTERNAL_ROLE = "running-external-review"
PATH_TOOLS = {"Read", "Grep", "Glob"}
# The only tools a registered reviewer may call besides PATH_TOOLS and Bash (each checked below): bookkeeping
# that writes no file and starts no process or agent. Tool names from code.claude.com/docs/en/tools-reference
# ("The tool names are the exact strings you use in permission rules, subagent tool lists, and hook matchers",
# read 2026-11-12): TodoWrite is "Disabled by default in favor of `TaskCreate`, `TaskGet`, `TaskList`, and
# `TaskUpdate`"; ToolSearch loads a deferred tool's schema (calling the tool is then checked here);
# SubagentHandback returns the subagent's report to its caller.
REVIEWER_TOOLS = frozenset({"TodoWrite", "TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "ToolSearch",
                            "SubagentHandback"})
CREDENTIAL_DIRS = ("~/.aws", "~/.ssh", "~/.config/gcloud", "~/.azure")
CREDENTIAL_FILES = ("~/.docker/config.json", "~/.netrc")
# Names in a Glob pattern or a Grep glob filter that aim at credentials.
CREDENTIAL_NAME_RE = re.compile(r"\.env|\.aws|\.ssh|\.netrc|\.azure|gcloud|\.docker")
# The same names as a path component or glob in a shell word (`--include=.env*`, `*/.aws/*`), which a recursive
# grep would otherwise read inside an allowed directory.
CREDENTIAL_WORD_RE = re.compile(r"(?:^|[/=*])\.(?:env|aws|ssh|netrc|azure|docker)(?![A-Za-z0-9_-])")
GLOB_CHARS = set("*?[")
GLOB_LIMIT = 500
CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]")
NAME_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")


class Deny(Exception):
    """A registered reviewer's call is refused; the message says why."""


# ------------------------------------------------------------------------------------------- state

def load_paths():
    """core/gate/ifs_paths.py, the state locations every check shares, loaded by path from the directory this
    file runs from, compiled from source, once per process. Identical in ifs-pretool.py, spec-approval-gate.py
    and review-isolation.py, so in-process the three share one module object."""
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "ifs_paths.py")
    mod = sys.modules.get("ifs_gate_paths")
    if mod is not None and getattr(mod, "__file__", None) == path:
        return mod
    try:
        import _frozen_importlib as bootstrap
        import _frozen_importlib_external as external
    except ImportError:
        import importlib._bootstrap as bootstrap
        import importlib._bootstrap_external as external

    class SourceOnly(external.SourceFileLoader):
        def get_code(self, fullname):
            return self.source_to_code(self.get_data(self.path), self.path)

    spec = bootstrap.spec_from_loader("ifs_gate_paths", SourceOnly("ifs_gate_paths", path))
    mod = bootstrap.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["ifs_gate_paths"] = mod
    return mod


def state_root():
    return load_paths().plugin_state_root()


def state_dir():
    return load_paths().isolation_state_dir()


def snapshot_root():
    return os.path.join(state_root(), "review-snapshots")


def snapshot_roots():
    """Every location review-snapshot.py may have chosen by default (ifs_paths.snapshot_roots). Claude Code
    exports CLAUDE_PLUGIN_DATA to hook processes but not to the Bash tool's commands, so a snapshot the
    orchestrator creates from the shell lands under $XDG_STATE_HOME/implement-from-spec (else
    ~/.local/state/implement-from-spec) while this hook sees CLAUDE_PLUGIN_DATA: all are the plugin's own
    state, and all are allowed."""
    return set(load_paths().snapshot_roots())


def session_key(session_id):
    return load_paths().session_key(session_id)


def state_path(session_id):
    return load_paths().isolation_state_file(session_id)


def read_state(session_id):
    """The session's state, {} when it has none. A state file that exists, or cannot be checked, but does not
    open or parse raises (a dangling symlink in its place included: ifs_paths.may_exist)."""
    path = state_path(session_id)
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
        if load_paths().may_exist(path):
            raise
        return {}
    if not isinstance(state, dict):
        raise ValueError("review-isolation state is not a JSON object")
    return state


@contextlib.contextmanager
def state_txn(session_id):
    """Read-modify-write of the session state under an exclusive lock, saved atomically on exit."""
    directory = state_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = state_path(session_id)
    with os.fdopen(os.open(path + ".lock", os.O_RDWR | os.O_CREAT, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(path, encoding="utf-8") as fh:
                state = json.load(fh)
        except FileNotFoundError:
            state = {}
        except ValueError:
            # A damaged file is kept for inspection and a fresh state started; registrations in it are lost,
            # but lookups on the damaged file failed closed until now (registered_from_raw).
            os.replace(path, f"{path}.corrupt-{int(time.time())}")
            state = {}
        state.setdefault("agents", {})
        state.setdefault("denials", [])
        yield state
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)
        os.replace(tmp, path)


def marker_path(session_id):
    return load_paths().review_marker_file(session_id)


def marker_role(session_id, agent_id):
    """The role the session's activation record gives the agent, or None. The record (ifs_paths.
    review_marker_file) lives where only HOME moves it, so a registration that has gone from the state file,
    or a state that moved with CLAUDE_PLUGIN_DATA or XDG_STATE_HOME, is still known. Raises OSError or
    ValueError when the record exists but cannot be read."""
    path = marker_path(session_id)
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        if load_paths().may_exist(path):
            raise
        return None
    agents = record.get("agents") if isinstance(record, dict) else None
    if not isinstance(agents, dict):
        raise ValueError("review-isolation activation record is not of the hook's shape")
    role = agents.get(str(agent_id))
    return str(role) if role is not None else None


def record_marker(session_id, agent_id, role):
    """Adds the agent to the session's activation record, atomically; called under the state lock."""
    import tempfile
    path = marker_path(session_id)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        record = {}
    if not isinstance(record, dict) or not isinstance(record.get("agents", {}), dict):
        raise ValueError("review-isolation activation record is not of the hook's shape")
    record.setdefault("agents", {})[str(agent_id)] = role
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".review-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    os.replace(tmp, path)


def registered_from_raw(session_id, agent_id):
    """When the state cannot be parsed: whether the agent id appears in the state file or the activation record
    at all (fail closed). A file that exists, or cannot be checked (ifs_paths.may_exist: EACCES on it or on a
    directory above it, ELOOP, a dangling symlink), but cannot be read counts as naming the agent: whether it
    does cannot be known, and "unregistered" would lift the isolation of a registered reviewer whose records
    were both made unreadable (PR 1 fix round 3). Only a file lstat finds absent is skipped."""
    for path in (state_path(session_id), marker_path(session_id)):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if json.dumps(str(agent_id)) in fh.read():
                    return True
        except OSError:
            if load_paths().may_exist(path):
                return True
    return False


def record_denial(session_id, agent_id, tool, reason):
    try:
        with state_txn(session_id) as state:
            state["denials"].append({"agent_id": agent_id, "tool": tool, "reason": reason,
                                     "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    except Exception as exc:  # noqa: BLE001 - the denial stands even when it cannot be logged
        print(f"review-isolation: could not log a denial: {exc}", file=sys.stderr)


# ------------------------------------------------------------------------------------------- output

def clean(text):
    return CONTROL_RE.sub("", str(text))


def emit_deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": clean(reason)}}))


def deny_reason(role, what):
    return (f"review-isolation: {what}. This subagent is a registered reviewer ({role}) and reviewers are "
            "read-only. Do not retry another way; list this call under the parts of the review you could "
            "not complete.")


# --------------------------------------------------------------------------------------- paths

def plugin_roots():
    roots = {DERIVED_PLUGIN_ROOT}
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        roots.add(os.path.realpath(os.environ["CLAUDE_PLUGIN_ROOT"]))
    return roots


def git_top(directory):
    """The nearest directory at or above `directory` holding .git (a directory, or a file in a worktree)."""
    probe = os.path.realpath(directory)
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def allowed_roots(cwd):
    roots = set(plugin_roots()) | snapshot_roots()
    top = git_top(cwd) if cwd else None
    if top:
        roots.add(top)
    return roots


def under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def credential_reason(path):
    home_dirs = [os.path.realpath(os.path.expanduser(p)) for p in CREDENTIAL_DIRS]
    home_files = [os.path.realpath(os.path.expanduser(p)) for p in CREDENTIAL_FILES]
    for root in home_dirs + home_files:
        if under(path, root):
            return f"{path} is a credential path"
    for part in path.split(os.sep):
        if part == ".env" or part.startswith(".env."):
            return f"{path} is a credential path (.env)"
    return None


def check_path(path, cwd, roots, label="path"):
    """Raise Deny unless `path` (as named and resolved) is inside an allowed root and no credential path."""
    if not isinstance(path, str) or not path:
        raise Deny(f"{label} is missing or not a string")
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd or os.getcwd(), expanded)
    named = os.path.normpath(expanded)
    real = os.path.realpath(expanded)
    for candidate in (named, real):
        reason = credential_reason(candidate)
        if reason:
            raise Deny(reason)
    if not any(under(real, r) for r in roots) or not any(under(named, r) for r in roots):
        raise Deny(f"{path} is outside the review's allowed roots ({', '.join(sorted(roots))})")


def task_output_dirs(session_id):
    """Where Claude Code writes the output of a background Bash task of this session:
    <tmp>/claude-<uid>/<project>/<session_id>/tasks/, <tmp> being $CLAUDE_CODE_TMPDIR, else /tmp on macOS and
    $TMPDIR (else /tmp) elsewhere (code.claude.com/docs/en/env-vars, CLAUDE_CODE_TMPDIR). Observed layout,
    not documented: each task is one regular file <id>.output; an Agent task's .output is a symlink to that
    subagent's transcript, which stays denied."""
    if not session_id or not re.match(r"^[A-Za-z0-9_.-]+$", str(session_id)) or str(session_id) in (".", ".."):
        return []
    base = os.environ.get("CLAUDE_CODE_TMPDIR") or (
        "/tmp" if sys.platform == "darwin" else (os.environ.get("TMPDIR") or "/tmp"))
    return [os.path.join(os.path.realpath(base), f"claude-{os.getuid()}")]


def is_task_output(path, session_id):
    """True for <tmp>/claude-<uid>/<one component>/<session_id>/tasks/<name>.output, a regular file reached
    through no symlink (the running-external-review role reads its background run's output there)."""
    if not isinstance(path, str) or not os.path.isabs(path) or os.path.islink(path):
        return False
    real = os.path.realpath(path)
    if real != os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path)):
        return False
    for top in task_output_dirs(session_id):
        if not under(real, top) or not os.path.isfile(real):
            continue
        # The resolved path decides: a symlinked tasks directory resolves elsewhere and fails here.
        parts = os.path.relpath(real, top).split(os.sep)
        if (len(parts) == 4 and parts[0] not in (".", "..") and parts[1] == str(session_id)
                and parts[2] == "tasks" and re.match(r"^[A-Za-z0-9_-]+\.output$", parts[3])):
            return True
    return False


def check_path_tool(tool, tool_input, cwd, roots, role=None, session_id=None):
    if not isinstance(tool_input, dict):
        raise Deny(f"{tool} input is not an object")
    if tool == "Read":
        if role == EXTERNAL_ROLE and is_task_output(tool_input.get("file_path"), session_id):
            return
        check_path(tool_input.get("file_path"), cwd, roots, "Read file_path")
        return
    base = tool_input.get("path") or cwd
    check_path(base, cwd, roots, f"{tool} path")
    if tool == "Grep":
        filt = tool_input.get("glob") or ""
        if CREDENTIAL_NAME_RE.search(str(filt)):
            raise Deny(f"Grep glob {filt!r} aims at credential files")
        return
    pattern = tool_input.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        raise Deny("Glob pattern is missing")
    if CREDENTIAL_NAME_RE.search(pattern):
        raise Deny(f"Glob pattern {pattern!r} aims at credential files")
    if ".." in pattern.split("/"):
        raise Deny(f"Glob pattern {pattern!r} climbs with '..'")
    basedir = os.path.expanduser(base)
    basedir = basedir if os.path.isabs(basedir) else os.path.join(cwd, basedir)
    pat = os.path.expanduser(pattern)
    full = pat if os.path.isabs(pat) else os.path.join(basedir, pat)
    prefix = []
    for part in full.split("/"):
        if GLOB_CHARS & set(part) or "{" in part:
            break
        prefix.append(part)
    check_path("/".join(prefix) or "/", cwd, roots, "Glob pattern")


# ------------------------------------------------------------------------------------------- bash

class Word:
    """One shell word: its value, its glob pattern (quoted specials escaped), and `lexed`, the value as
    shlex sees it (with the plugin-root variable left unexpanded) for the cross-check."""
    __slots__ = ("text", "pattern", "lexed", "glob", "tilde", "quoted", "plugin_var")

    def __init__(self):
        self.text, self.pattern, self.lexed = [], [], []
        self.glob = self.tilde = self.quoted = self.plugin_var = False

    def add(self, chars, quoted, lexed=None):
        import glob
        self.text.append(chars)
        self.pattern.append(glob.escape(chars) if quoted else chars)
        self.lexed.append(chars if lexed is None else lexed)
        self.quoted = self.quoted or quoted

    def value(self):
        return "".join(self.text)

    def lexed_value(self):
        return "".join(self.lexed)


# The one variable a reviewer's command may use: the plugin root, as the skills' briefs write it, and only as
# the start of the script path python3 -I runs (check_python). Every other $ denies.
PLUGIN_VAR_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}|\$CLAUDE_PLUGIN_ROOT(?![A-Za-z0-9_])")


def plugin_var_at(command, i, word):
    """At command[i] == '$': the plugin-root variable's spelling and value when it starts `word` (None: no
    word yet); raises Deny for any other expansion."""
    m = PLUGIN_VAR_RE.match(command, i)
    if not m or (word is not None and word.text):
        raise Deny("expansion or command substitution ($, $(, backtick); only ${CLAUDE_PLUGIN_ROOT} may start "
                   "the path of an allowlisted script")
    value = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not value or not os.path.isabs(value) or CONTROL_RE.search(value):
        raise Deny("CLAUDE_PLUGIN_ROOT is not set to an absolute path in the hook's environment")
    return m.group(0), value


def scan(command):
    """Split a shell line into segments of Words on |, && and ||, refusing everything else that is not a
    plain word. Returns [(raw_segment_text, [Word, ...]), ...]."""
    if not isinstance(command, str) or not command.strip():
        raise Deny("the Bash command is empty or not a string")
    segments, words, word = [], [], None
    seg_start, i, n = 0, 0, len(command)
    removed = []  # spans of 2>&1, which shlex would keep as a word

    def finish_word():
        nonlocal word
        if word is not None:
            words.append(word)
            word = None

    def finish_segment(end):
        nonlocal words, seg_start
        finish_word()
        if not words:
            raise Deny("an empty command around a pipe or list operator")
        raw = command[seg_start:end]
        for a, b in reversed(removed):
            if seg_start <= a and b <= end:
                raw = raw[:a - seg_start] + " " + raw[b - seg_start:]
        segments.append((raw, words))
        words = []

    while i < n:
        c = command[i]
        if c in " \t":
            finish_word()
            i += 1
            continue
        if CONTROL_RE.match(c):
            raise Deny("a newline or control character in the command (one command line only)")
        if c == "\\":
            if i + 1 >= n or CONTROL_RE.match(command[i + 1]):
                raise Deny("a trailing backslash or an escaped control character")
            word = word or Word()
            word.add(command[i + 1], True)
            i += 2
            continue
        if c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise Deny("an unterminated single quote")
            if CONTROL_RE.search(command[i + 1:j]):
                raise Deny("a control character inside quotes")
            word = word or Word()
            word.add(command[i + 1:j], True)
            i = j + 1
            continue
        if c == '"':
            j, buf, lexed = i + 1, [], []
            word = word or Word()
            while j < n and command[j] != '"':
                ch = command[j]
                if ch == "$" and not buf and not word.text:
                    spelling, value = plugin_var_at(command, j, word)
                    word.plugin_var = True
                    buf.append(value)
                    lexed.append(spelling)
                    j += len(spelling)
                    continue
                if ch in "$`":
                    raise Deny("expansion ($ or backtick) inside double quotes")
                if CONTROL_RE.match(ch):
                    raise Deny("a control character inside quotes")
                if ch == "\\" and j + 1 < n and command[j + 1] in '"\\':
                    buf.append(command[j + 1])
                    lexed.append(command[j + 1])
                    j += 2
                    continue
                buf.append(ch)
                lexed.append(ch)
                j += 1
            if j >= n:
                raise Deny("an unterminated double quote")
            word.add("".join(buf), True, "".join(lexed))
            i = j + 1
            continue
        if c == "$":
            spelling, value = plugin_var_at(command, i, word)
            if re.search(r"[\s*?\[{}~]", value):
                raise Deny("an unquoted CLAUDE_PLUGIN_ROOT whose value the shell would split or glob")
            word = word or Word()
            word.plugin_var = True
            word.add(value, True, spelling)
            i += len(spelling)
            continue
        if c == "`":
            raise Deny("command substitution (backtick)")
        if c == "|":
            if command[i + 1:i + 2] == "&":
                raise Deny("|& (stderr pipe)")
            step = 2 if command[i + 1:i + 2] == "|" else 1
            finish_segment(i)
            i += step
            seg_start = i
            continue
        if c == "&":
            if command[i + 1:i + 2] != "&":
                raise Deny("& (background job or redirection)")
            finish_segment(i)
            i += 2
            seg_start = i
            continue
        if c == ";":
            raise Deny("; (command list)")
        if c == ">" and word is not None and not word.quoted and word.value() == "2" \
                and command[i:i + 3] == ">&1" and (i + 3 == n or command[i + 3] in " \t|&"):
            removed.append((i - 1, i + 3))
            word = None
            i += 3
            continue
        if c in "<>":
            raise Deny("redirection or process substitution (< or >; only 2>&1 is allowed)")
        if c in "()":
            raise Deny("a subshell or grouping parenthesis")
        if c in "{}":
            raise Deny("braces (grouping or brace expansion)")
        if c == "#" and word is None:
            raise Deny("a shell comment")
        if c == "~":
            if word is not None:
                # Bash expands ~ at a word's start and after = or : (assignment-like words); HEAD~1 stays.
                if command[i - 1] in "=:'\"":
                    raise Deny("an unquoted ~ after = or : (tilde expansion)")
                word.add(c, False)
                i += 1
                continue
            word = Word()
            word.tilde = True
            word.add(c, False)
            i += 1
            continue
        word = word or Word()
        if c in GLOB_CHARS:
            word.glob = True
        word.add(c, False)
        i += 1
    finish_segment(n)
    # Cross-check with the standard library's POSIX lexer: both must agree on every word.
    import shlex
    for raw, ws in segments:
        try:
            lexed = shlex.split(raw, posix=True)
        except ValueError as exc:
            raise Deny(f"the command does not lex ({exc})") from None
        if lexed != [w.lexed_value() for w in ws]:
            raise Deny("the command's words are ambiguous (the scanner and shlex disagree)")
    return segments


class Ctx:
    def __init__(self, cwd, roots, role):
        self.cwd, self.roots, self.role = cwd, roots, role

    def path(self, word):
        # Every word is checked with ~ expanded: for a quoted ~ (which the shell leaves alone) that can only
        # deny more, never less.
        check_path(word.value(), self.cwd, self.roots, "a command argument")

    def globbed(self, word):
        """A word with unquoted glob characters: the shell expands it, so every match is checked."""
        import glob
        pattern = "".join(word.pattern)
        if word.tilde:
            pattern = os.path.expanduser(pattern)
        for part in pattern.split("/"):
            if part.startswith(".") and GLOB_CHARS & set(part):
                raise Deny(f"the glob {word.value()!r} can match '..'")
        full = pattern if os.path.isabs(pattern) else os.path.join(self.cwd, pattern)
        matches = []
        for m in glob.iglob(full):
            matches.append(m)
            if len(matches) > GLOB_LIMIT:
                raise Deny(f"the glob {word.value()!r} matches more than {GLOB_LIMIT} paths")
        for m in matches:
            check_path(m, self.cwd, self.roots, "a glob match")


def long_name(word):
    return word[2:].split("=", 1)[0]


def forbidden_long(name, forbidden):
    """GNU getopt and git accept any unambiguous prefix of a long option: --out is --output."""
    return any(f == name or (name and f.startswith(name)) for f in forbidden)


def parse_args(ctx, args, spec):
    """Generic option parsing for an allowlisted program. spec keys:
      short_values {letter: 'skip'|'path'}, long_values {name: 'skip'|'path'}, forbid_short set,
      forbid_long set. Returns the operand Words (after options and their values are consumed and checked);
    `seen`, when given, collects the value options used. Unknown options are flags; a misread is never a
    bypass: every word not consumed as a 'skip' value is path-checked by the caller or here."""
    short_values = spec.get("short_values", {})
    long_values = spec.get("long_values", {})
    forbid_short = spec.get("forbid_short", set())
    forbid_long = spec.get("forbid_long", set())
    seen = spec.get("seen")
    operands, i, opts_done = [], 0, False
    while i < len(args):
        w = args[i]
        text = w.value()
        if w.glob:
            ctx.globbed(w)
        if opts_done or not text.startswith("-") or text == "-":
            operands.append(w)
            i += 1
            continue
        if text == "--":
            opts_done = True
            i += 1
            continue
        if text.startswith("--"):
            name = long_name(text)
            if forbidden_long(name, forbid_long):
                raise Deny(f"the option --{name} is not read-only")
            kind = long_values.get(name)
            if kind and seen is not None:
                seen.add(name)
            if "=" in text:
                if kind != "skip":
                    check_path(text.split("=", 1)[1], ctx.cwd, ctx.roots, f"the value of --{name}")
            elif kind:
                if i + 1 >= len(args):
                    raise Deny(f"--{name} has no value")
                if kind == "path":
                    ctx.path(args[i + 1])
                i += 1
            i += 1
            continue
        letters = text[1:]
        j = 0
        while j < len(letters):
            letter = letters[j]
            if letter in forbid_short:
                raise Deny(f"the option -{letter} is not read-only")
            kind = short_values.get(letter)
            if kind:
                if seen is not None:
                    seen.add(letter)
                rest = letters[j + 1:]
                if rest:
                    if kind == "path":
                        check_path(rest, ctx.cwd, ctx.roots, f"the value of -{letter}")
                else:
                    if i + 1 >= len(args):
                        raise Deny(f"-{letter} has no value")
                    if kind == "path":
                        ctx.path(args[i + 1])
                    i += 1
                break
            if not letter.isalnum():
                raise Deny(f"the option {text!r} cannot be parsed with certainty")
            j += 1
        i += 1
    return operands


GIT_SUBCOMMANDS = {"diff", "log", "show", "status", "ls-files", "blame", "rev-parse", "cat-file", "merge-base"}
# -c is denied as a git global option (any option before the subcommand is, bar --no-pager and -C <dir>
# inside the allowed roots); after the subcommand it is the combined-diff format of log and show.
GIT_SPEC = {"forbid_long": {"output", "ext-diff", "exec", "upload-pack"},
            "short_values": {"S": "skip", "G": "skip", "O": "path"},
            "long_values": {"grep": "skip", "author": "skip", "committer": "skip", "format": "skip",
                            "pretty": "skip", "since": "skip", "until": "skip", "after": "skip",
                            "before": "skip", "date": "skip", "contents": "path"}}
# ls -L (--dereference) with -R lists the names under a committed symbolic link to a directory outside the roots
# (PR 1 code review, item 5); without -L, -R never follows one, and every operand is checked after resolving.
SIMPLE = {
    "ls": {"forbid_short": {"L"}, "forbid_long": {"dereference"}}, "cat": {}, "head": {}, "tail": {}, "stat": {},
    "uniq": {},
    "cut": {"short_values": {"d": "skip", "f": "skip", "c": "skip", "b": "skip"},
            "long_values": {"delimiter": "skip", "fields": "skip", "characters": "skip", "bytes": "skip"}},
}
# grep, rg, sort, wc, file and diff take only the options listed here (PR 1 review, 2026-11-12: `rg
# --hostname-bin=<program>` runs that program, and getopt takes an unambiguous prefix of a long option, so BSD
# grep read `--regex=` as `--regexp=` while the hook took the next word for the pattern; in the seventh round
# `sort --files0-from=<list>`, `wc --files0-from` and `file -f <list>` read every file a committed list names,
# where only the list was checked, and `diff` of two directories follows the symbolic links inside them).
# find takes the primaries FIND_SPEC lists. An option is looked up by its exact name: an abbreviation,
# an option that is not listed and a value given to an option that takes none are denied. `grep` in Claude
# Code's Bash tool is ugrep (a shell function of the session snapshot runs the claude binary as ugrep), else BSD
# or GNU grep; `rg` is Claude Code's embedded ripgrep 14 or an installed one; `find` is Claude Code's embedded
# bfs (another shell function of the snapshot), else BSD or GNU find; sort, wc, file and diff are the system's
# (BSD and Apple on macOS, GNU on Linux; Homebrew's GNU diff on many Macs). An option is listed only when it
# is read-only, runs and loads nothing, reads no file it is not given as a checked path (no list of names),
# follows no symbolic link out of the paths it is given, and takes a value in every one of those
# implementations or in none (BSD -O is a flag but ugrep's -O takes a value, so a word the hook skipped as a
# value could be read as a file: such options are left out). Kinds:
#   FLAG              no value; `--name=value` is denied
#   NUM               a count (digits; ugrep's -m also takes MIN,MAX), checked as one
#   TEXT              a value that is never a path: a pattern, a glob, a file type name
#   PATH              a file, checked like a Read path (`-` is standard input)
#   ("enum", {...})   a required value from the set
#   ("optenum", {...}) long only: no value, or `=value` from the set (grep's --color, whose value is optional)
#   OPTNUM            long only: no value, or `=<count>` (diff's --context and --unified: GNU's value is optional,
#                     BSD's required, so the next word is never taken for it; it stays an operand and is checked)
FLAG, NUM, TEXT, PATH, OPTNUM = "flag", "num", "text", "path", "optnum"
COLOR_WHEN = ("optenum", frozenset({"never", "always", "auto"}))
OPTION_SPECS = {
    "grep": {
        "short": dict({c: FLAG for c in "abcEFGHhIiLlnoPqrsTvwx0123456789"},
                      A=NUM, B=NUM, C=NUM, m=NUM, e=TEXT, f=PATH),
        "long": dict({n: FLAG for n in (
            "extended-regexp", "fixed-strings", "basic-regexp", "perl-regexp", "ignore-case", "no-ignore-case",
            "invert-match", "word-regexp", "line-regexp", "count", "files-with-matches", "files-without-match",
            "only-matching", "quiet", "silent", "no-messages", "byte-offset", "with-filename", "no-filename",
            "line-number", "recursive", "initial-tab", "text", "line-buffered", "null")},
            **{"after-context": NUM, "before-context": NUM, "context": NUM, "max-count": NUM, "regexp": TEXT,
               "include": TEXT, "exclude": TEXT, "exclude-dir": TEXT, "file": PATH, "color": COLOR_WHEN,
               "colour": COLOR_WHEN}),
    },
    "rg": {
        "short": dict({c: FLAG for c in "isSFwxvcloNnHIbqUPau.0p"},
                      A=NUM, B=NUM, C=NUM, m=NUM, M=NUM, j=NUM, d=NUM, e=TEXT, g=TEXT, t=TEXT, T=TEXT, f=PATH),
        "long": dict({n: FLAG for n in (
            "ignore-case", "case-sensitive", "smart-case", "fixed-strings", "word-regexp", "line-regexp",
            "invert-match", "count", "count-matches", "files-with-matches", "files-without-match",
            "only-matching", "line-number", "no-line-number", "with-filename", "no-filename", "byte-offset",
            "quiet", "multiline", "multiline-dotall", "pcre2", "text", "column", "no-column", "heading",
            "no-heading", "hidden", "no-hidden", "no-ignore", "no-ignore-vcs", "no-ignore-dot", "no-ignore-exclude",
            "no-ignore-files", "no-ignore-global", "no-ignore-parent", "no-require-git", "unrestricted", "files",
            "type-list", "trim", "vimgrep", "json", "stats", "no-messages", "no-ignore-messages", "no-config",
            "null", "crlf", "glob-case-insensitive", "one-file-system", "passthru", "include-zero",
            "line-buffered", "block-buffered", "no-unicode", "max-columns-preview", "pretty", "binary")},
            **{"after-context": NUM, "before-context": NUM, "context": NUM, "max-count": NUM, "max-columns": NUM,
               "max-depth": NUM, "threads": NUM, "regexp": TEXT, "glob": TEXT, "iglob": TEXT, "type": TEXT,
               "type-not": TEXT, "file": PATH,
               "color": ("enum", frozenset({"never", "auto", "always", "ansi"})),
               "sort": ("enum", frozenset({"none", "path", "modified", "accessed", "created"})),
               "sortr": ("enum", frozenset({"none", "path", "modified", "accessed", "created"}))}),
    },
    # Not listed: -o/--output and -T/--temporary-directory (write), --compress-program (runs a program),
    # --files0-from (reads the files a list names), --random-source (reads a file).
    "sort": {
        "short": dict({c: FLAG for c in "bcCdfghiMmnRrsuVz"}, k=TEXT, t=TEXT, S=TEXT),
        "long": dict({n: FLAG for n in (
            "ignore-leading-blanks", "dictionary-order", "ignore-case", "general-numeric-sort",
            "human-numeric-sort", "ignore-nonprinting", "month-sort", "numeric-sort", "random-sort", "reverse",
            "version-sort", "merge", "stable", "unique", "zero-terminated", "debug", "heapsort", "mergesort",
            "radixsort", "qsort", "mmap")},
            **{"key": TEXT, "field-separator": TEXT, "buffer-size": TEXT, "parallel": NUM, "batch-size": NUM,
               "check": ("optenum", frozenset({"quiet", "silent", "diagnose-first"})),
               "sort": ("enum", frozenset({"general-numeric", "human-numeric", "month", "numeric", "random",
                                           "version"}))}),
    },
    # Not listed: --files0-from (reads the files a list names).
    "wc": {
        "short": {c: FLAG for c in "cmlLw"},
        "long": dict({n: FLAG for n in ("bytes", "chars", "lines", "words", "max-line-length")},
                     total=("enum", frozenset({"auto", "always", "only", "never"}))),
    },
    # Not listed: -f/--files-from (reads the files a list names), -m/--magic-file and macOS -M (load a magic
    # file), -C/--compile (writes one), -z/-Z (decompress, possibly through a program), -s (reads devices).
    "file": {
        "short": dict({c: FLAG for c in "bihIkLNnp0"}, e=TEXT, F=TEXT),
        "long": dict({n: FLAG for n in (
            "brief", "mime", "mime-type", "mime-encoding", "extension", "keep-going", "dereference",
            "no-dereference", "no-pad", "no-buffer", "print0", "preserve-date", "apple")},
            **{"exclude": TEXT, "exclude-quiet": TEXT, "separator": TEXT}),
    },
    # Not listed: -l/--paginate (runs pr), --from-file and --to-file (compare against a further file), BSD -A,
    # the GNU line and group formats and the digit context forms. --context and --unified take a value only
    # as `=<n>` (OPTNUM). Two directories are compared only with --no-dereference (check_diff).
    "diff": {
        "short": dict({c: FLAG for c in "abBcdeinNpPqrstTuwy"}, C=NUM, U=NUM, W=NUM, D=TEXT, F=TEXT, I=TEXT,
                      L=TEXT, x=TEXT, S=TEXT, X=PATH),
        "long": dict({n: FLAG for n in (
            "normal", "brief", "report-identical-files", "ed", "rcs", "forward-ed",
            "side-by-side", "left-column", "suppress-common-lines", "show-c-function", "expand-tabs",
            "initial-tab", "suppress-blank-empty", "recursive", "no-dereference", "new-file",
            "unidirectional-new-file", "ignore-file-name-case", "no-ignore-file-name-case", "ignore-case",
            "ignore-tab-expansion", "ignore-trailing-space", "ignore-space-change", "ignore-all-space",
            "ignore-blank-lines", "text", "strip-trailing-cr", "minimal", "speed-large-files")},
            **{"width": NUM, "tabsize": NUM, "horizon-lines": NUM, "show-function-line": TEXT, "label": TEXT,
               "exclude": TEXT, "starting-file": TEXT, "ignore-matching-lines": TEXT, "ifdef": TEXT,
               "exclude-from": PATH, "color": COLOR_WHEN, "context": OPTNUM, "unified": OPTNUM}),
    },
}
# find takes only these primaries and flags, each by its exact name (PR 1 code review, item 4 and 5: GNU and bfs
# -files0-from read the starting points from a committed list, -L, -H and -follow follow committed symbolic links
# out of the roots, and bfs -rm deletes like -delete, which the former denylist did not name). Values by kind as
# in OPTION_SPECS; every other word is a path (bfs takes paths anywhere in the expression) and is checked.
FIND_SPEC = dict(
    {w: FLAG for w in (
        "-P", "-E", "-s", "-x", "-d", "-depth", "-print", "-print0", "-prune", "-empty", "-true", "-false", "-not",
        "-a", "-and", "-o", "-or", "-xdev", "-mount", "-quit", "-ls", "-readable", "-writable", "-executable",
        "-nouser", "-nogroup", "-daystart", "-noleaf", "!", "(", ")", ",")},
    **{w: TEXT for w in (
        "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex", "-lname",
        "-ilname", "-type", "-user", "-group", "-uid", "-gid", "-perm", "-size", "-mtime", "-mmin", "-atime",
        "-amin", "-ctime", "-cmin", "-links", "-inum", "-regextype", "-printf")},
    **{"-maxdepth": NUM, "-mindepth": NUM, "-newer": PATH})
FIND_NEWER_RE = re.compile(r"^-newer[aBcm]([aBcmt])$")
SEARCH_NUM_RE = re.compile(r"^[0-9]{1,9}(?:,[0-9]{0,9})?$")
# The options that supply the pattern, so every operand is a path; rg's --files and --type-list take none.
SEARCH_PATTERN_OPTIONS = {"e", "f", "regexp", "file", "files", "type-list"}
SED_ADDR = r"(?:\d+|\$|/(?:[^/\\]|\\.)*/)"
SED_CMD_RE = re.compile(r"^%s(?:,%s)?!?(?:[p=lqd]|s/(?:[^/\\]|\\.)*/(?:[^/\\]|\\.)*/[gpiI0-9]*)$|^[p=lqd]$|"
                        r"^s/(?:[^/\\]|\\.)*/(?:[^/\\]|\\.)*/[gpiI0-9]*$" % (SED_ADDR, SED_ADDR))


def sed_script_ok(script):
    """Only print, line-number, list, quit, delete and s/// with print/global flags: no w, W, r, R, e."""
    # A ; inside a regular expression splits it too, and the halves then fail to match: denied, never misread.
    parts = [p.strip() for p in script.split(";")]
    return bool(parts) and all(p and SED_CMD_RE.match(p) for p in parts)


def check_sed(ctx, args):
    scripts, quiet, operands, i = [], False, [], 0
    while i < len(args):
        w = args[i]
        text = w.value()
        if w.glob:
            ctx.globbed(w)
        if text.startswith("--") and text != "--":
            name = long_name(text)
            if name in ("quiet", "silent"):
                quiet = True
            elif name == "regexp-extended":
                pass
            elif name == "expression" and "=" in text:
                scripts.append(text.split("=", 1)[1])
            else:
                raise Deny(f"the sed option --{name} is not on the allowlist")
            i += 1
            continue
        if text.startswith("-") and text not in ("-", "--"):
            letters = text[1:]
            for j, letter in enumerate(letters):
                if letter == "n":
                    quiet = True
                elif letter in "Erusz":
                    continue
                elif letter == "e":
                    rest = letters[j + 1:]
                    if rest:
                        scripts.append(rest)
                    elif i + 1 < len(args):
                        scripts.append(args[i + 1].value())
                        i += 1
                    else:
                        raise Deny("sed -e has no script")
                    break
                else:
                    raise Deny(f"the sed option -{letter} is not read-only (only -n, -E, -r, -e)")
            i += 1
            continue
        if text == "--":
            operands.extend(args[i + 1:])
            break
        operands.append(w)
        i += 1
    if not quiet:
        raise Deny("sed is allowed only as sed -n")
    if not scripts:
        if not operands:
            raise Deny("sed has no script")
        scripts.append(operands.pop(0).value())
    for script in scripts:
        if not sed_script_ok(script):
            raise Deny(f"the sed script {script!r} is not a plain print (no w, r, e or other commands)")
    for w in operands:
        ctx.path(w)


def option_value(ctx, prog, label, kind, value):
    """Checks the value of an allowlisted option by its kind (OPTION_SPECS, FIND_SPEC)."""
    if kind == NUM:
        if not SEARCH_NUM_RE.match(value):
            raise Deny(f"the {prog} option {label} takes a count, not {value!r}")
    elif kind == PATH:
        if value != "-":
            check_path(value, ctx.cwd, ctx.roots, f"the value of {prog} {label}")
    elif isinstance(kind, tuple):
        if value not in kind[1]:
            raise Deny(f"the {prog} option {label} takes one of {', '.join(sorted(kind[1]))}, not {value!r}")


def parse_listed_args(ctx, args, prog):
    """The arguments of grep, rg, sort, wc, file or diff against its allowlist (OPTION_SPECS). Returns (operands,
    seen): the operand Words and the names of the options used. Raises Deny for any option that is not listed by
    its exact name."""
    spec = OPTION_SPECS[prog]
    operands, seen, i, opts_done = [], set(), 0, False

    def take(label, kind, attached):
        """The option's value: the attached text, else the next word, which is consumed."""
        nonlocal i
        if attached is not None:
            return attached
        if i + 1 >= len(args):
            raise Deny(f"the {prog} option {label} has no value")
        i += 1
        word = args[i]
        if word.glob:
            ctx.globbed(word)
        return word.value()

    while i < len(args):
        w = args[i]
        text = w.value()
        if w.glob:
            ctx.globbed(w)
        if opts_done or not text.startswith("-") or text == "-":
            operands.append(w)
            i += 1
            continue
        if text == "--":
            opts_done = True
            i += 1
            continue
        if text.startswith("--"):
            name, eq, attached = text[2:].partition("=")
            kind = spec["long"].get(name)
            if kind is None:
                raise Deny(f"the {prog} option --{name} is not on the reviewer's read-only allowlist (options are "
                           "matched by their full name; an abbreviation is not accepted)")
            seen.add(name)
            label = f"--{name}"
            if kind == FLAG:
                if eq:
                    raise Deny(f"the {prog} option {label} takes no value")
            elif isinstance(kind, tuple) and kind[0] == "optenum":
                if eq and attached not in kind[1]:
                    raise Deny(f"the {prog} option {label} takes one of {', '.join(sorted(kind[1]))}")
            elif kind == OPTNUM:
                if eq:
                    option_value(ctx, prog, label, NUM, attached)
            else:
                option_value(ctx, prog, label, kind, take(label, kind, attached if eq else None))
            i += 1
            continue
        letters = text[1:]
        j = 0
        while j < len(letters):
            letter = letters[j]
            kind = spec["short"].get(letter)
            if kind is None:
                raise Deny(f"the {prog} option -{letter} is not on the reviewer's read-only allowlist")
            seen.add(letter)
            if kind != FLAG:
                rest = letters[j + 1:]
                option_value(ctx, prog, f"-{letter}", kind, take(f"-{letter}", kind, rest or None))
                break
            j += 1
        i += 1
    return operands, seen


def check_find(ctx, args):
    """find against FIND_SPEC: listed primaries with their values checked by kind, every other word a path."""
    i = 0
    while i < len(args):
        w = args[i]
        text = w.value()
        if w.glob:
            ctx.globbed(w)
        kind = FIND_SPEC.get(text)
        m = FIND_NEWER_RE.match(text)
        if m:  # -newerXY: Y t takes a date, any other Y a file (GNU find, bfs)
            kind = TEXT if m.group(1) == "t" else PATH
        if kind == FLAG:
            i += 1
            continue
        if kind is not None:
            if i + 1 >= len(args):
                raise Deny(f"the find primary {text} has no value")
            value = args[i + 1]
            if value.glob:
                ctx.globbed(value)
            option_value(ctx, "find", text, kind, value.value())
            i += 2
            continue
        if text.startswith("-") and text != "-":
            raise Deny(f"the find primary {text} is not on the reviewer's read-only allowlist (no -exec, -ok, "
                       "-delete, -rm, -fprint, -fls, -files0-from, -f, -L, -H or -follow)")
        ctx.path(w)
        i += 1


def check_diff(ctx, operands, seen):
    """diff of two plain paths. Two directories (or a directory and an absent path, which -N and -P make an
    empty directory): diff reads every entry inside them and, without
    --no-dereference, follows a committed symbolic link there out of the roots (GNU diff 3.10 and Apple's BSD
    diff alike, with or without -r), so --no-dereference is required. A directory and a file: diff reads
    <directory>/<the file's name>, which is checked like any path (Apple's diff follows a link there even with
    --no-dereference)."""
    if len(operands) != 2 or any(w.glob for w in operands):
        raise Deny("diff compares exactly two paths, named without a glob")
    for w in operands:
        ctx.path(w)
    full = [os.path.join(ctx.cwd, os.path.expanduser(w.value())) for w in operands]
    dirs = [w.value() != "-" and os.path.isdir(f) for w, f in zip(operands, full)]
    # Absent as diff sees it: a missing path or a dangling symbolic link (os.path.exists follows the link; an
    # operand it cannot stat counts as absent too, which only requires --no-dereference).
    absent = [w.value() != "-" and not os.path.exists(f) for w, f in zip(operands, full)]
    if any(dirs) and any(absent):
        # -N (--new-file) or -P makes an absent operand an empty directory beside a directory, and diff then
        # reads the other tree whole (GNU and Apple diff, with or without -r): compared as two directories.
        dirs = [True, True]
    if all(dirs):
        if "no-dereference" not in seen:
            raise Deny("diff of two directories follows the symbolic links inside them: add --no-dereference")
    elif any(dirs):
        directory, other = (full[0], full[1]) if dirs[0] else (full[1], full[0])
        check_path(os.path.join(directory, os.path.basename(os.path.normpath(other))), ctx.cwd, ctx.roots,
                   "the file diff reads in the directory it is given")


EXTERNAL_MODES = ("off", "bedrock-gpt")


def external_mode_words(args):
    """Drops one `--external-review <mode>` (or `--external-review=<mode>`) from the runner's arguments.

    Contract section 9: the orchestrator passes the mode the user asked for in the conversation (`off` to
    keep the change away from the external reviewer, `bedrock-gpt` when the user enables it), and the
    runner runs that command unchanged. Only those two modes are allowed (`command` would run a reviewer
    CLI, so it stays a saved setting); every other setting flag (auth, profile, region, model, command,
    policy, out) stays denied by parse_args, and so do a second mode flag and any other value."""
    out, i, taken = [], 0, False
    while i < len(args):
        text = args[i].value()
        if text == "--":
            return out + list(args[i:])
        if not taken and text == "--external-review" and i + 1 < len(args) \
                and args[i + 1].value() in EXTERNAL_MODES:
            taken = True
            i += 2
            continue
        if not taken and text.startswith("--external-review=") and text.split("=", 1)[1] in EXTERNAL_MODES:
            taken = True
            i += 1
            continue
        out.append(args[i])
        i += 1
    return out


def check_python(ctx, words):
    if len(words) < 3 or words[1].value() != "-I":
        raise Deny("python3 is allowed only as python3 -I <plugin>/core/scripts/review-snapshot.py "
                   "verify|delta|gates")
    script = os.path.realpath(os.path.join(ctx.cwd, os.path.expanduser(words[2].value())))
    snap = {os.path.join(r, "core", "scripts", "review-snapshot.py") for r in plugin_roots()}
    ext = {os.path.join(r, "core", "scripts", "spec-external-review.py") for r in plugin_roots()}
    rest = words[3:]
    if script in {os.path.realpath(p) for p in snap}:
        if not rest or rest[0].value() not in ("verify", "delta", "gates"):
            raise Deny("review-snapshot.py is allowed only with verify, delta or gates")
        for w in parse_args(ctx, rest[1:], {}):
            ctx.path(w)
        return
    if script in {os.path.realpath(p) for p in ext}:
        if ctx.role != EXTERNAL_ROLE:
            raise Deny("spec-external-review.py is for the running-external-review role only")
        spec = {"forbid_long": {"out", "external-review", "external-review-auth", "external-review-aws-profile",
                                "external-review-region", "external-review-model", "external-review-command",
                                "external-review-policy"},
                "long_values": {"base": "skip", "range": "skip"}}
        for w in parse_args(ctx, external_mode_words(rest), spec):
            ctx.path(w)
        return
    allowed = "review-snapshot.py or spec-external-review.py" if ctx.role == EXTERNAL_ROLE else "review-snapshot.py"
    raise Deny(f"python3 -I may run only the plugin's {allowed}, named by its absolute path")


def check_segment(ctx, words):
    prog = words[0].value()
    args = words[1:]
    if NAME_ASSIGN_RE.match(prog):
        raise Deny("a leading variable assignment")
    if words[0].glob or words[0].tilde or "/" in prog:
        raise Deny(f"the program {prog!r} is not named plainly")
    for k, w in enumerate(words):
        if w.plugin_var and not (prog == "python3" and k == 2):
            raise Deny("${CLAUDE_PLUGIN_ROOT} is allowed only at the start of the script path python3 -I runs")
    for w in args:
        if CREDENTIAL_WORD_RE.search(w.value()):
            raise Deny(f"the argument {w.value()!r} names credential files")
    if prog == "git":
        while args and args[0].value() in ("--no-pager", "-C"):
            if args[0].value() == "-C":
                # -C <dir>: design notes section 3 forbids -c, not -C. The directory must be inside the
                # allowed roots, and the words after it are checked relative to it, as git reads them.
                if len(args) < 2 or args[1].glob or args[1].tilde:
                    raise Deny("git -C needs one plain directory")
                check_path(args[1].value(), ctx.cwd, ctx.roots, "the directory of git -C")
                ctx = Ctx(os.path.realpath(os.path.join(ctx.cwd, args[1].value())), ctx.roots, ctx.role)
                args = args[2:]
                continue
            args = args[1:]
        if not args or args[0].value() not in GIT_SUBCOMMANDS:
            raise Deny("git is allowed only with diff, log, show, status, ls-files, blame, rev-parse, cat-file "
                       "or merge-base and no global options but -C <dir> and --no-pager")
        for w in parse_args(ctx, args[1:], GIT_SPEC):
            ctx.path(w)
        return
    if prog in SIMPLE:
        operands = parse_args(ctx, args, SIMPLE[prog])
        if prog == "uniq" and len(operands) > 1:
            raise Deny("uniq with an output file")
        for w in operands:
            ctx.path(w)
        return
    if prog == "tr":
        parse_args(ctx, args, {})  # tr reads standard input only; its operands are character sets
        return
    if prog in OPTION_SPECS:
        operands, seen = parse_listed_args(ctx, args, prog)
        if prog == "diff":
            check_diff(ctx, operands, seen)
            return
        # -e/--regexp or -f/--file supply the pattern; rg --files lists files and takes no pattern. Otherwise
        # the first operand is the pattern. Options are matched by their full name only (OPTION_SPECS), so an
        # abbreviation of --regexp can no longer turn a file into "the pattern".
        if prog in ("grep", "rg") and operands and not seen & SEARCH_PATTERN_OPTIONS:
            operands = operands[1:]  # the pattern: not a path
        for w in operands:
            ctx.path(w)
        return
    if prog == "find":
        check_find(ctx, args)
        return
    if prog == "sed":
        check_sed(ctx, args)
        return
    if prog == "python3":
        check_python(ctx, words)
        return
    raise Deny(f"{prog} is not on the reviewer's read-only allowlist (tests are the orchestrator's quality gate)")


def check_bash(command, cwd, roots, role):
    ctx = Ctx(cwd, roots, role)
    for _raw, words in scan(command):
        check_segment(ctx, words)


# ------------------------------------------------------------------------------------------- main

def skill_name(tool_input):
    """The reviewer role a Skill call loads, or None. The `skill` input is read by ifs_paths.skill_parts, the
    reading the approval gate's activation shares (whitespace and leading "/" dropped)."""
    invoked = tool_input.get("skill") if isinstance(tool_input, dict) else None
    namespace, name = load_paths().skill_parts(invoked)
    if name in REVIEWER_SKILLS and namespace in ("", PLUGIN_NAME):
        return name
    return None


def decide(data):
    """Returns (decision_reason_or_None, role_or_None). Raises on internal errors."""
    agent_id = data.get("agent_id")
    if not agent_id:
        return None, None
    session_id = data.get("session_id")
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    try:
        state = read_state(session_id)
    except (OSError, ValueError):
        if registered_from_raw(session_id, agent_id):
            raise
        state = None
    entry = (state or {}).get("agents", {}).get(str(agent_id)) if state is not None else None
    if entry is None:
        try:
            recorded = marker_role(session_id, agent_id)
        except (OSError, ValueError):
            if registered_from_raw(session_id, agent_id):
                raise
            recorded = None
        if recorded is not None:
            # Registered (the activation record says so) but gone from the state: never lift the isolation.
            return deny_reason(recorded, f"this reviewer's registration is missing from {state_path(session_id)} "
                                         "although its activation record names it (the state was removed or "
                                         "moved), so every call is denied"), recorded
        if tool == "Skill":
            role = skill_name(tool_input)
            if not role:
                return None, None
            try:
                with state_txn(session_id) as st:
                    entry = st["agents"].get(str(agent_id))
                    if entry is None:
                        record_marker(session_id, agent_id, role)  # first: a lost state still denies
                        st["agents"][str(agent_id)] = {
                            "role": role, "agent_type": data.get("agent_type"),
                            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            except Exception as exc:  # noqa: BLE001 - a reviewer never runs unregistered
                try:  # best-effort detail: the denial never depends on it (PR 1 fix round 4, defect 3)
                    where = f"the state directory is {state_dir()}"
                except Exception:  # noqa: BLE001
                    where = "its state directory cannot be named"
                return (f"review-isolation could not register this reviewer ({type(exc).__name__}: "
                        f"{describe(exc)}), so the {role} skill does not load. Tell the user; {where}.", role)
            if entry is None:
                return None, None
            # Registered meanwhile by a concurrent call of the same agent: a further Skill call, denied below.
        else:
            return None, None
    role = str(entry.get("role") or "reviewer") if isinstance(entry, dict) else "reviewer"
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else os.getcwd()
    try:
        if tool == "Skill":
            raise Deny("a further Skill call (a reviewer loads one skill only)")
        if tool in REVIEWER_TOOLS:
            return None, role
        if tool not in PATH_TOOLS and tool != "Bash":
            raise Deny(f"the {clean(tool)[:200]} tool is not available to reviewers (reviewers may use only "
                       "Read, Grep, Glob and read-only Bash)")
        roots = allowed_roots(cwd)
        if tool in PATH_TOOLS:
            check_path_tool(tool, tool_input, cwd, roots, role, session_id)
        else:
            check_bash(tool_input.get("command"), os.path.realpath(cwd), roots, role)
    except Deny as exc:
        return deny_reason(role, str(exc)), role
    return None, role


def main():
    raw, data = "", {}
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("the hook payload is not a JSON object")
        reason, _role = decide(data)
        if reason:
            emit_deny(reason)
            record_denial(data.get("session_id"), data.get("agent_id"), data.get("tool_name"), reason)
        return 0
    except Exception as exc:  # noqa: BLE001 - never crash: onFailure "block" would block every caller
        if not isinstance(data, dict) or "agent_id" not in data:
            found_s = re.search(r'"session_id"\s*:\s*"([^"\\]*)"', raw or "")
            found_a = re.search(r'"agent_id"\s*:\s*"([^"\\]*)"', raw or "")
            data = {"session_id": found_s and found_s.group(1), "agent_id": found_a and found_a.group(1)}
        agent_id, session_id = data.get("agent_id"), data.get("session_id")
        if agent_id and is_registered_failsafe(session_id, agent_id):
            where = ""
            try:
                where = (f" If the session's isolation records cannot be read ({state_path(session_id)}, "
                         f"{marker_path(session_id)}), restore this user's access to them or start a new session.")
            except Exception:  # noqa: BLE001 - the denial stands without the locations
                pass
            emit_deny(f"review-isolation hook error ({type(exc).__name__}: {describe(exc)}). This subagent is, "
                      "or may be (its session's records cannot all be read), a registered reviewer; the call is denied "
                      "because it could not be checked. List it under the parts of the review you could not "
                      "complete." + where)
            return 0
        print(f"review-isolation: {type(exc).__name__}: {describe(exc)}", file=sys.stderr)
        return 0


def describe(exc):
    """str(exc), or its type's name when even that raises: an error message never stops a denial."""
    try:
        return str(exc)
    except Exception:  # noqa: BLE001
        return type(exc).__name__


def is_registered_failsafe(session_id, agent_id):
    """Whether the agent is, or may be, a registered reviewer; never raises. When neither the parsed records
    nor their raw text can be checked (ifs_paths does not load, a path cannot be built), it may be: True, so
    main's handler denies (PR 1 fix round 4, defect 3: the handler must reach its denial)."""
    try:
        state = read_state(session_id)
        return str(agent_id) in (state.get("agents") or {}) or marker_role(session_id, agent_id) is not None
    except Exception:  # noqa: BLE001 - unreadable state or record: whether the id appears in them at all
        try:
            return registered_from_raw(session_id, agent_id)
        except Exception:  # noqa: BLE001 - cannot be checked at all: may be registered
            return True


# --------------------------------------------------------------------------------- opt-in timing log
# Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form `claude plugin eval` passes to its
# sessions) names a log in ~/.local/state/implement-from-spec/hook-timing/ (ifs_paths.timing_log_path; any
# other value is refused, so no hook appends to a file elsewhere, the project included): then each call appends
# one line, <start, ISO 8601 UTC>\t<hook>\t<tool or ->\t<agent_id or ->\t<duration ms>\t<session_id or ->,
# for the eval timeline tool. The duration runs from the
# first statement of this file (interpreter start-up is not included) to the end of the decision. The line is
# written by ifs_paths.write_timing: one O_APPEND write, the directory reached from HOME with no symlink
# followed, only to a private (0600) regular file of this user with one link, opened non-blocking; a log that
# cannot be written so is skipped silently, and nothing is printed: timing never changes or fails a decision.
# Unset, the hook reads one clock value and the two variables, nothing else.
TIMING_ENV = ("IFS_HOOK_TIMING_LOG", "EVAL_IFS_HOOK_TIMING_LOG")


def timing_log_path():
    if not any(os.environ.get(n) for n in TIMING_ENV):
        return None
    try:
        return load_paths().timing_log_path()
    except Exception:  # noqa: BLE001 - timing never changes a decision
        return None


def run_timed(run, hook, log_path):
    """run() with stdin buffered (so the payload's ids can be logged), then the timing line."""
    import io
    raw = sys.stdin.read()
    sys.stdin = io.StringIO(raw)
    try:
        return run()
    finally:
        try:
            import datetime
            import time as clock
            ms = (_monotonic() - _HOOK_T0) * 1000.0
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            payload = payload if isinstance(payload, dict) else {}
            start = datetime.datetime.fromtimestamp(clock.time() - ms / 1000.0, datetime.timezone.utc)
            fields = [start.strftime("%Y-%m-%dT%H:%M:%S.") + f"{start.microsecond // 1000:03d}Z", hook]
            fields += [str(payload.get(k) or "-") for k in ("tool_name", "agent_id")]
            fields += [f"{ms:.1f}", str(payload.get("session_id") or "-")]
            line = "\t".join(" ".join(f.split()) or "-" for f in fields) + "\n"
            load_paths().write_timing(log_path, line)
        except Exception:  # noqa: BLE001 - the timing log is best effort; the hook's decision stands
            pass


if __name__ == "__main__":
    _log = timing_log_path()
    sys.exit(run_timed(main, "review-isolation", _log) if _log else main())
