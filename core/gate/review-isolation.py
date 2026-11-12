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
~/.local/state/implement-from-spec. The registering call itself goes ahead (no output). When the state
cannot be written, the Skill call is denied: a reviewer never runs unregistered. The main conversation (no
`agent_id`) and subagents that never loaded a reviewer skill (implementation waves) are never affected: the
hook prints nothing and exits 0 for them.

What a registered reviewer may not do (permissionDecision "deny", with a reason telling it to list the
call under the parts it could not complete; each denial is appended to the session's state file):
  - Write, Edit, MultiEdit, NotebookEdit, WebFetch, WebSearch, Agent, Task, any mcp__* tool, the other
    shells and schedulers in DENIED_TOOLS, and any further Skill call
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
    Every word that can name a file is checked like a Read path (globs are expanded to check every match)

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
DENIED_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task",
                # Not named in the design but equivalent to a shell or a writer.
                "PowerShell", "Monitor", "CronCreate", "CronDelete", "EnterWorktree", "ExitWorktree",
                "Workflow", "RemoteTrigger"}
PATH_TOOLS = {"Read", "Grep", "Glob"}
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

def state_root():
    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not base:
        base = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                            "implement-from-spec")
    return os.path.realpath(base)


def state_dir():
    return os.path.join(state_root(), "review-isolation")


def snapshot_root():
    return os.path.join(state_root(), "review-snapshots")


def snapshot_roots():
    """Every location review-snapshot.py may have chosen by default. Claude Code exports CLAUDE_PLUGIN_DATA to
    hook processes but not to the Bash tool's commands, so a snapshot the orchestrator creates from the shell
    lands under $XDG_STATE_HOME/implement-from-spec (else ~/.local/state/implement-from-spec) while this hook
    sees CLAUDE_PLUGIN_DATA: both are the plugin's own state, and both are allowed."""
    fallback = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                            "implement-from-spec")
    return {os.path.realpath(snapshot_root()), os.path.realpath(os.path.join(fallback, "review-snapshots"))}


def session_key(session_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or "no-session"))


def state_path(session_id):
    return os.path.join(state_dir(), f"{session_key(session_id)}.json")


def read_state(session_id):
    """The session's state, {} when it has none. A state file that exists but does not parse raises."""
    try:
        with open(state_path(session_id), encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
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


def registered_from_raw(session_id, agent_id):
    """When the state cannot be parsed: whether the agent id appears in it at all (fail closed)."""
    try:
        with open(state_path(session_id), encoding="utf-8", errors="replace") as fh:
            return json.dumps(str(agent_id)) in fh.read()
    except OSError:
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
SIMPLE = {
    "ls": {}, "cat": {}, "head": {}, "tail": {}, "wc": {}, "diff": {}, "stat": {},
    "file": {"forbid_short": {"C"}, "forbid_long": {"compile"}},
    "sort": {"forbid_short": {"o", "T"},
             "forbid_long": {"output", "temporary-directory", "compress-program"},
             "short_values": {"t": "skip", "k": "skip", "S": "skip"}},
    "uniq": {},
    "cut": {"short_values": {"d": "skip", "f": "skip", "c": "skip", "b": "skip"},
            "long_values": {"delimiter": "skip", "fields": "skip", "characters": "skip", "bytes": "skip"}},
}
GREP_SPEC = {"short_values": {"e": "skip", "f": "path"}, "long_values": {"regexp": "skip", "file": "path"}}
RG_SPEC = {"short_values": {"e": "skip", "f": "path", "g": "skip"},
           "long_values": {"regexp": "skip", "file": "path", "glob": "skip", "iglob": "skip"},
           "forbid_long": {"pre", "pre-glob"}}
FIND_FORBIDDEN = ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fls")
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


def check_find(ctx, args):
    for w in args:
        text = w.value()
        if w.glob:
            ctx.globbed(w)
        if text.startswith("-"):
            if any(text == f or text.startswith(f) for f in FIND_FORBIDDEN):
                raise Deny(f"find {text} writes or runs commands")
            continue
        if text in ("!", "(", ")", ","):
            continue
        ctx.path(w)


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
    if prog in ("grep", "rg"):
        seen = set()
        operands = parse_args(ctx, args, dict(GREP_SPEC if prog == "grep" else RG_SPEC, seen=seen))
        # -e/--regexp or -f/--file supply the pattern; rg --files lists files and takes no pattern. Otherwise
        # the first operand is the pattern. A misread only makes a pattern a checked path (denies more).
        has_pattern = bool(seen & {"e", "f", "regexp", "file"})
        if prog == "rg" and any(a.value() in ("--files", "--type-list") for a in args):
            has_pattern = True
        if operands and not has_pattern:
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
    invoked = tool_input.get("skill") if isinstance(tool_input, dict) else None
    invoked = str(invoked or "").strip().lstrip("/")
    namespace, _, name = invoked.rpartition(":")
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
        if tool == "Skill":
            role = skill_name(tool_input)
            if not role:
                return None, None
            try:
                with state_txn(session_id) as st:
                    entry = st["agents"].get(str(agent_id))
                    if entry is None:
                        st["agents"][str(agent_id)] = {
                            "role": role, "agent_type": data.get("agent_type"),
                            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            except Exception as exc:  # noqa: BLE001 - a reviewer never runs unregistered
                return (f"review-isolation could not register this reviewer ({type(exc).__name__}: {exc}), so "
                        f"the {role} skill does not load. Tell the user; the state directory is {state_dir()}.",
                        role)
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
        if tool in DENIED_TOOLS or tool.startswith("mcp__"):
            raise Deny(f"the {tool} tool is not available to reviewers")
        roots = allowed_roots(cwd)
        if tool in PATH_TOOLS:
            check_path_tool(tool, tool_input, cwd, roots, role, session_id)
        elif tool == "Bash":
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
            emit_deny(f"review-isolation hook error ({type(exc).__name__}: {exc}). This subagent is a registered "
                      "reviewer; the call is denied because it could not be checked. List it under the parts "
                      "of the review you could not complete.")
            return 0
        print(f"review-isolation: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


def is_registered_failsafe(session_id, agent_id):
    try:
        state = read_state(session_id)
        return str(agent_id) in (state.get("agents") or {})
    except Exception:  # noqa: BLE001 - unreadable state: whether the id appears in it at all
        return registered_from_raw(session_id, agent_id)


# --------------------------------------------------------------------------------- opt-in timing log
# Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form `claude plugin eval` passes to its
# sessions) names a file: then each call appends one line, <start, ISO 8601 UTC>\t<hook>\t<tool or ->\t<agent_id
# or ->\t<duration ms>\t<session_id or ->, for the eval timeline tool. The duration runs from the
# first statement of this file (interpreter start-up is not included) to the end of the decision. The line is
# written with O_APPEND (one write), mode 0600, never through a symlink; a log that cannot be written is
# skipped silently, and nothing is printed: timing never changes or fails a decision. Unset, the hook reads
# one clock value and the two variables, nothing else.
TIMING_ENV = ("IFS_HOOK_TIMING_LOG", "EVAL_IFS_HOOK_TIMING_LOG")


def timing_log_path():
    return next((os.environ[n] for n in TIMING_ENV if os.environ.get(n)), None)


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
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            fd = os.open(log_path, flags, 0o600)
            try:
                os.write(fd, line.encode("utf-8", "replace"))
            finally:
                os.close(fd)
        except Exception:  # noqa: BLE001 - the timing log is best effort; the hook's decision stands
            pass


if __name__ == "__main__":
    _log = timing_log_path()
    sys.exit(run_timed(main, "review-isolation", _log) if _log else main())
