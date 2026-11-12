#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""ifs-pretool.py: the plugin's one PreToolUse hook, a dispatcher for the plugin's PreToolUse checks.

Owner: the implement-from-spec plugin; this file lives in the plugin's core/gate/ directory. Standard library
only (Python 3.9+, the python3 macOS ships). hooks/hooks.json registers it once, on every tool, in exec form
with onFailure "block":
  {"matcher": "*", "hooks": [{"type": "command", "command": "python3",
   "args": ["-I", "-S", "${CLAUDE_PLUGIN_ROOT}/core/gate/ifs-pretool.py",
            "--skills-dir", "${CLAUDE_PLUGIN_ROOT}/skills"], "onFailure": "block"}]}

Why one hook. Five PreToolUse registrations used to start one python3 each per tool call: review-isolation.py
on every tool, spec-approval-gate.py activate (Skill), guard-edit (Write|Edit|MultiEdit|NotebookEdit) and
guard-bash (Bash), and core/deps/install-ask-hook.py (Bash). Claude Code starts them together ("When an event
fires, its matching hooks run in parallel.", code.claude.com/docs/en/hooks), so a Bash call cost three
interpreters, and most of each one's time was compiling the standard-library modules it imports: macOS's
Command Line Tools python3 ships no standard-library bytecode and writes none under -I. This dispatcher reads
the payload once and runs the checks that can decide the call in one process, with their decision logic
unchanged.

Which checks run (the selection never runs fewer checks than could produce a decision; when in doubt it runs
them all):
  - Fast exit, before anything beyond os and sys is imported, for a call none of the checks can affect. It
    reads the raw payload text and trusts it only when it is unambiguous: the payload holds no \\u escape (so
    every key is spelled literally) and "tool_name" occurs once with a plain string value. Then
      review-isolation   runs for a payload carrying "agent_id" when the tool is Skill (registration), when
                         the ids are not plain [A-Za-z0-9_.-] strings, or when the session's isolation state
                         file names the agent (or cannot be read); otherwise the subagent is not a registered
                         reviewer and the check prints nothing. Without "agent_id" (the main conversation) it
                         never decides.
      guard-edit/-bash   run for Write|Edit|MultiEdit|NotebookEdit / Bash when the session's gate state file
                         exists or the session id is not plain: an ungated session is never gated.
      activate           runs for Skill when skills/<name>/gate_rules.json exists for the skill's name (or the
                         name is unusual); no other skill can start the gate.
      install-ask-hook   runs for Bash when the payload contains "install.py": it asks only for install.py
                         --apply.
  - Otherwise the payload is parsed and the checks the old registrations would have started run: review-
    isolation on every tool, plus activate (Skill), guard-edit (the four edit tools) or guard-bash and
    install-ask (Bash). A payload that is not a JSON object runs review-isolation and guard-bash, whose own
    failure paths deny a registered reviewer and a gated session.
Each check runs in-process (review-isolation.py's main, spec-approval-gate.py's run_event, install-ask-hook.py's
main) with the payload as standard input and its standard output captured; every selected check runs even
after another denied, so their state updates match the separate hooks.

Merging. "When multiple PreToolUse hooks return different decisions, precedence is `deny` > `defer` > `ask` >
`allow`." (code.claude.com/docs/en/hooks, PreToolUse decision control, read 2026-10-27). The dispatcher prints
one decision with that precedence; the reasons of the checks that reached it are joined.

Failure policy (fail closed, the gate's principle: a check that could not run never lets its call through
unseen). A check that raises out of its entry point (a module that does not load, an error its own failure
policy does not catch), exits non-zero or prints anything but decision JSON denies the call, as the guards'
onFailure "block" did when they were separate hooks. Two deliberate differences from those separate hooks:
install-ask-hook.py had no onFailure, so its crash let the command run; it now denies, and since it is loaded
only for a Bash command that names install.py, its failure still never blocks unrelated work. The gate's
activate also had none: a crash while starting a gated skill now denies the Skill call (the skill would
otherwise run ungated), while activate's own documented non-blocking error (exit 1 with a stderr note, no
decision) still lets the call go ahead. The dispatcher itself never exits non-zero; its own registration
blocks the call when python3 cannot run it (onFailure "block", Claude Code 2.1.295 or later).

Bytecode cache. Before a check is loaded, sys.pycache_prefix points at <data>/pycache, <data> being
$CLAUDE_PLUGIN_DATA, else the gate's state directory (spec-approval-gate.py STATE_DIR), and bytecode writing is
switched on there, so the standard-library modules and the checks are compiled once, not on every call. The
directory is created 0700 and used only when it is a real directory owned by the user and closed to others
(it is made 0700 when it is not); otherwise nothing is cached and nothing is written. The gate protects it
like its own state: no tool call of a gated session may write there or name it in a shell command, and a
reviewer may not write anywhere. In a session that never started a gated skill it is as writable as the
plugin's own files. IFS_HOOK_PYCACHE=0 switches the cache off (for measurements). The interpreter runs with
-I (no script directory, PYTHON* variables or user site-packages) and -S (no site module: no site-packages
and no .pth file runs inside the hook); the checks import only the standard library.

Opt-in timing log. Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form `claude plugin eval`
passes to its sessions) names a file. Then each call appends, in one write, one line per check that ran,
<start, ISO 8601 UTC>\\t<check>\\t<tool or ->\\t<agent_id or ->\\t<duration ms>\\t<session_id or ->\\tifs-pretool,
the check named as its separate hook was (review-isolation, spec-approval-gate guard-bash, ...) and its
duration covering loading and running it, then the dispatcher's own line, the same six fields without the
seventh, with check "ifs-pretool" and the duration from its first statement to its decision (interpreter
start-up is not included), so the eval timeline tool attributes each call and each check. The line is written
with O_APPEND, mode 0600, never through a symlink; a log that cannot be written is skipped silently and timing
never changes a decision.

Usage (what Claude Code does on a Write):
  echo '{"session_id":"s1","cwd":"/repo","tool_name":"Write","tool_input":{"file_path":"/repo/a.py"}}' \\
    | python3 -I -S <plugin-root>/core/gate/ifs-pretool.py --skills-dir <plugin-root>/skills
"""

import os
import sys
from time import monotonic as _monotonic  # first: the dispatcher's timing counts from here; built in

_HOOK_T0 = _monotonic()

# The gate's directory is not an import location (see spec-approval-gate.py): a json.py written next to this
# file would otherwise run inside every hook call when the interpreter is started without -I.
if sys.path and os.path.realpath(sys.path[0] or os.getcwd()) == os.path.dirname(os.path.realpath(__file__)):
    del sys.path[0]

HOOK_NAME = "ifs-pretool"
HOOK_FILE = os.path.realpath(__file__)
GATE_DIR = os.path.dirname(HOOK_FILE)
PLUGIN_ROOT = os.path.dirname(os.path.dirname(GATE_DIR))
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
PLAIN_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
TIMING_ENV = ("IFS_HOOK_TIMING_LOG", "EVAL_IFS_HOOK_TIMING_LOG")
RANK = {"deny": 3, "defer": 2, "ask": 1, "allow": 0}
# check key -> (the name its separate hook logged under, its file, the gate event or None)
CHECKS = {
    "isolation": ("review-isolation", os.path.join(GATE_DIR, "review-isolation.py"), None),
    "activate": ("spec-approval-gate activate", os.path.join(GATE_DIR, "spec-approval-gate.py"), "activate"),
    "guard-edit": ("spec-approval-gate guard-edit", os.path.join(GATE_DIR, "spec-approval-gate.py"), "guard-edit"),
    "guard-bash": ("spec-approval-gate guard-bash", os.path.join(GATE_DIR, "spec-approval-gate.py"), "guard-bash"),
    "install-ask": ("install-ask-hook", os.path.join(PLUGIN_ROOT, "core", "deps", "install-ask-hook.py"), None),
}
ORDER = ("isolation", "activate", "guard-edit", "guard-bash", "install-ask")
MODULE_NAMES = {"review-isolation.py": "ifs_review_isolation", "spec-approval-gate.py": "ifs_spec_approval_gate",
                "install-ask-hook.py": "ifs_install_ask_hook"}


# ------------------------------------------------------------------------------------------- locations
# Mirrors of the checks' own state locations (review-isolation.py state_path, spec-approval-gate.py STATE_DIR
# and session_key), computed without importing them; the development tests check that they agree.

def _xdg_state():
    return os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")


def session_key(session_id):
    return "".join(ch if ch in PLAIN_ID_CHARS else "_" for ch in str(session_id or "no-session"))


def isolation_state_file(session_id):
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(_xdg_state(), "implement-from-spec")
    return os.path.join(os.path.realpath(base), "review-isolation", session_key(session_id) + ".json")


def gate_state_dir():
    return os.path.realpath(os.environ.get("SPEC_GATE_STATE_DIR") or os.path.join(
        os.environ.get("CLAUDE_PLUGIN_DATA") or _xdg_state(), "spec-approval-gate"))


def gate_state_file(session_id):
    return os.path.join(gate_state_dir(), session_key(session_id) + ".json")


def pycache_dir():
    """<data>/pycache: $CLAUDE_PLUGIN_DATA, else the gate's state directory (spec-approval-gate.py PYCACHE_DIR)."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    return os.path.join(os.path.realpath(data) if data else gate_state_dir(), "pycache")


# ------------------------------------------------------------------------------------------- selection

def top_string(raw, key):
    """The value of "key" when that quoted key occurs exactly once in the raw text, followed by a colon and a
    string with no escape in it; else None (the caller then runs the check)."""
    needle = '"%s"' % key
    i = raw.find(needle)
    if i < 0 or raw.find(needle, i + 1) >= 0:
        return None
    j, n = i + len(needle), len(raw)
    while j < n and raw[j] in " \t\r\n":
        j += 1
    if j >= n or raw[j] != ":":
        return None
    j += 1
    while j < n and raw[j] in " \t\r\n":
        j += 1
    if j >= n or raw[j] != '"':
        return None
    k = raw.find('"', j + 1)
    if k < 0:
        return None
    value = raw[j + 1:k]
    return None if "\\" in value else value


def plain_id(value):
    return value if value and all(ch in PLAIN_ID_CHARS for ch in value) else None


def isolation_may_decide(raw, tool):
    """review-isolation decides only for a payload carrying agent_id: on a Skill call (registration) or for
    an agent its session's state file names."""
    if '"agent_id"' not in raw:
        return False
    agent, session = plain_id(top_string(raw, "agent_id")), plain_id(top_string(raw, "session_id"))
    if tool == "Skill" or agent is None or session is None:
        return True
    try:
        with open(isolation_state_file(session), encoding="utf-8", errors="replace") as fh:
            return '"%s"' % agent in fh.read()
    except FileNotFoundError:
        return False
    except OSError:
        return True


def activate_may_decide(raw):
    """activate acts only for a skill whose directory holds a gate_rules.json."""
    skill = top_string(raw, "skill")
    if skill is None:
        return True
    name = skill.rpartition(":")[2]
    if not name:
        return False
    if "/" in name or name in (".", "..") or "\0" in name:
        return True
    return os.path.lexists(os.path.join(SKILLS_DIR, name, "gate_rules.json"))


def gate_may_decide(raw):
    """guard-edit and guard-bash decide only in a session whose gate state file exists (plugin mode)."""
    session = plain_id(top_string(raw, "session_id"))
    return session is None or os.path.exists(gate_state_file(session))


def fast_plan(raw):
    """The checks to run, read from the raw text without importing anything; None when the text is ambiguous."""
    if "\\u" in raw:
        return None
    tool = top_string(raw, "tool_name")
    if tool is None:
        return None
    steps = []
    if isolation_may_decide(raw, tool):
        steps.append("isolation")
    if tool == "Skill" and activate_may_decide(raw):
        steps.append("activate")
    if tool in EDIT_TOOLS and gate_may_decide(raw):
        steps.append("guard-edit")
    if tool == "Bash" and gate_may_decide(raw):
        steps.append("guard-bash")
    if tool == "Bash" and "install.py" in raw:
        steps.append("install-ask")
    return steps


def full_plan(raw):
    """The checks the separate registrations would have started for this payload (by their matchers)."""
    import json
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return ["isolation", "guard-bash"]
    tool = data.get("tool_name")
    steps = ["isolation"]
    if tool == "Skill":
        steps.append("activate")
    elif tool in EDIT_TOOLS:
        steps.append("guard-edit")
    elif tool == "Bash":
        steps += ["guard-bash", "install-ask"]
    return steps


def plan(raw):
    """The checks to run; the bytecode cache is switched on first whenever anything will be imported."""
    try:
        steps = fast_plan(raw)
    except Exception:  # noqa: BLE001 - an unexpected payload or file system state: run the full selection
        steps = None
    if steps is None or steps:
        enable_bytecode_cache()
    return full_plan(raw) if steps is None else steps


# ------------------------------------------------------------------------------------------- running

def enable_bytecode_cache():
    """Point sys.pycache_prefix at pycache_dir() and allow writing bytecode there; False when it is not a
    directory owned by this user and closed to others (nothing is cached then)."""
    if os.environ.get("IFS_HOOK_PYCACHE") == "0":
        return False
    path = pycache_dir()
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        st = os.lstat(path)
        if (st.st_mode & 0o170000) != 0o040000 or st.st_uid != os.getuid():
            return False
        if st.st_mode & 0o077:
            os.chmod(path, 0o700)
            if os.lstat(path).st_mode & 0o077:
                return False
    except OSError:
        return False
    sys.pycache_prefix = path
    sys.dont_write_bytecode = False
    return True


_MODULES = {}


def load(path):
    """The check's module, loaded by path (its bytecode cached under the prefix); nothing is added to sys.path."""
    name = MODULE_NAMES[os.path.basename(path)]
    mod = _MODULES.get(name)
    if mod is None:
        try:
            import _frozen_importlib as bootstrap
            import _frozen_importlib_external as external
            spec = external.spec_from_file_location(name, path)
            mod = bootstrap.module_from_spec(spec)
        except (ImportError, AttributeError):
            import importlib.util as bootstrap
            spec = bootstrap.spec_from_file_location(name, path)
            mod = bootstrap.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        _MODULES[name] = mod
    return mod


def run_check(key, raw):
    """(exit status, standard output) of one check run in-process on the payload."""
    import io
    _label, path, event = CHECKS[key]
    mod = load(path)
    out, saved = io.StringIO(), (sys.stdin, sys.stdout)
    sys.stdin, sys.stdout = io.StringIO(raw), out
    try:
        rc = mod.run_event(event, skills_dir=SKILLS_DIR) if event else mod.main()
    finally:
        sys.stdin, sys.stdout = saved
    return rc, out.getvalue()


def printable(text):
    return "".join(ch if ch.isprintable() else " " for ch in str(text))


def failed(key, what):
    label = CHECKS[key][0]
    reason = (f"implement-from-spec: the {label} check {printable(what)}, so the call is denied (its failure "
              "blocks the call). Tell the user; the plugin's core/gate/ifs-pretool.py runs it.")
    return ("deny", reason)


def judge(key, rc, out, exc):
    """The check's (decision, reason), or None for no decision."""
    if exc is not None:
        return failed(key, f"failed ({type(exc).__name__}: {exc})")
    if rc not in (0, None):
        if key == "activate":
            return None  # the gate's documented non-blocking error: exit 1, a note on stderr, no decision
        return failed(key, f"exited {rc}")
    found = None
    for line in out.splitlines():
        if not line.strip():
            continue
        import json
        try:
            hso = json.loads(line).get("hookSpecificOutput") or {}
            decision, reason = hso.get("permissionDecision"), hso.get("permissionDecisionReason") or ""
        except (ValueError, AttributeError):
            decision = reason = None
        if decision not in RANK or not isinstance(reason, str):
            return failed(key, "printed output that is not a PreToolUse decision")
        if found is None or RANK[decision] > RANK[found[0]]:
            found = (decision, reason)
    return found


def merge(decisions):
    """One PreToolUse decision: deny > defer > ask > allow, the reasons of the checks that reached it joined."""
    decisions = [d for d in decisions if d]
    if not decisions:
        return None
    best = max(decisions, key=lambda d: RANK[d[0]])[0]
    reasons = [r for d, r in decisions if d == best and r]
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": best,
                                   "permissionDecisionReason": "\n\n".join(dict.fromkeys(reasons))}}


# ------------------------------------------------------------------------------------------- timing

def timing_log_path():
    return next((os.environ[n] for n in TIMING_ENV if os.environ.get(n)), None)


def write_timing(log_path, raw, spans, end):
    """spans: [(check key, start, end)] in monotonic seconds; the dispatcher's own line comes last."""
    try:
        import datetime
        import time as clock
        ids = {k: top_string(raw, k) for k in ("tool_name", "agent_id", "session_id")}
        if any(v is None for v in ids.values()):
            import json
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            payload = payload if isinstance(payload, dict) else {}
            ids = {k: payload.get(k) for k in ids}
        now_epoch = clock.time()

        def line(name, a, b, parent):
            start = datetime.datetime.fromtimestamp(now_epoch - (end - a), datetime.timezone.utc)
            fields = [start.strftime("%Y-%m-%dT%H:%M:%S.") + f"{start.microsecond // 1000:03d}Z", name]
            fields += [str(ids.get(k) or "-") for k in ("tool_name", "agent_id")]
            fields += [f"{(b - a) * 1000.0:.1f}", str(ids.get("session_id") or "-")] + ([parent] if parent else [])
            return "\t".join(" ".join(f.split()) or "-" for f in fields) + "\n"

        text = "".join(line(CHECKS[k][0], a, b, HOOK_NAME) for k, a, b in spans)
        text += line(HOOK_NAME, _HOOK_T0, end, None)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(log_path, flags, 0o600)
        try:
            os.write(fd, text.encode("utf-8", "replace"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 - the timing log is best effort; the decision stands
        pass


# ------------------------------------------------------------------------------------------- main

def skills_dir_from(argv):
    for i, arg in enumerate(argv):
        if arg == "--skills-dir" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--skills-dir="):
            return arg.split("=", 1)[1]
    return os.path.join(PLUGIN_ROOT, "skills")


SKILLS_DIR = os.path.realpath(skills_dir_from(sys.argv[1:] if __name__ == "__main__" else []))


def dispatch(raw):
    """(the decision object or None, [(check key, start, end)])."""
    steps = plan(raw)
    spans, decisions = [], []
    for key in steps:
        a = _monotonic()
        rc, out, exc = None, "", None
        try:
            rc, out = run_check(key, raw)
        except BaseException as caught:  # noqa: BLE001 - one check's crash must not silence the others
            exc = caught
        decisions.append(judge(key, rc, out, exc))
        spans.append((key, a, _monotonic()))
    return merge(decisions), spans


def main():
    log_path = timing_log_path()
    raw = ""
    try:
        raw = sys.stdin.read()
        result, spans = dispatch(raw)
    except BaseException as exc:  # noqa: BLE001 - never exit non-zero: deny instead
        reason = (f"implement-from-spec: the PreToolUse dispatcher failed ({type(exc).__name__}: "
                  f"{printable(exc)}), so the call is denied. Tell the user.")
        result = merge([("deny", reason)])
        spans = []
    if result:
        import json
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
    if log_path:
        write_timing(log_path, raw, spans, _monotonic())
    return 0


if __name__ == "__main__":
    sys.exit(main())
