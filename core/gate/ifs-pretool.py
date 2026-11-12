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
                         file or its activation record (ifs_paths.review_marker_file) names the agent (or
                         cannot be read or checked); otherwise the subagent is not a registered reviewer and the check
                         prints nothing. Without "agent_id" (the main conversation) it
                         never decides.
      guard-edit/-bash   run for Write|Edit|MultiEdit|NotebookEdit / Bash when the session's gate state file
                         or its activation record (ifs_paths.gate_marker_file) exists, or cannot be checked
                         (ifs_paths.may_exist: EACCES on a directory above it counts as existing), or the
                         session id is not plain: an ungated session is never gated, and an activated one
                         whose state has gone or cannot be reached is still guarded (the guards then deny).
    Both state files are located by core/gate/ifs_paths.py, the module the gate and the isolation hook locate
    them with (load_paths), so the dispatcher can never look in a different place than the check it skips. When
    that module cannot load or raises, the selection falls back to the full one below: it fails closed.
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

Why every tool blocks on a failure (maintainer's decision, 2026-11-12). The registration matches "*" with
onFailure "block", so when the dispatcher cannot start (python3 missing, broken or below 3.9, a file of the
plugin unreadable) every tool call of every session with the plugin enabled is blocked, Read included, until
python3 is fixed or the plugin is turned off in `enabledPlugins` of the user's settings
(code.claude.com/docs/en/settings-reference), which takes no tool call: "With `"block"` set, a failure does
what exit code 2 does on that event" and "a `PreToolUse` failure blocks the tool call"
(code.claude.com/docs/en/hooks, "Block the action when a hook fails"). Availability was weighed against
fail-closed: the reviewer isolation is an allowlist, so it needs every tool hooked, and a non-blocking
registration for reads would let a registered reviewer use any tool unchecked whenever the hook cannot start;
writes, Bash and Skill would block either way. A failure inside a running dispatcher is narrower: when the fast
selection fails (ifs_paths.py missing or broken included) the full selection runs, and for a call no check can
decide (a Read of the main conversation) its checks print nothing, while a check that cannot load denies.

No bytecode cache. The checks are compiled from their source on every call that runs them
(ifs_paths.load_source): no bytecode is read or written for them, and sys.dont_write_bytecode is set, so the
dispatcher writes no .pyc file anywhere, and the standard library loads from the Python installation as in any
other python3 -I process. (A cache under the plugin data directory, used until 2026-11-12, let a .pyc planted
there, in a session that never started a gated skill, run inside every hook call.) The interpreter runs with -I
(no script directory, PYTHON* variables or user site-packages) and -S (no site module: no site-packages and no
.pth file runs inside the hook); the checks import only the standard library.

Opt-in timing log. Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form `claude plugin eval`
passes to its sessions) names a log in the fixed directory ~/.local/state/implement-from-spec/hook-timing/
(ifs_paths.timing_log_path: a bare <name>.tsv, or an absolute path in that directory; any other value is
refused and nothing is written, so the variable, which a repository's settings env block can set, never makes
a hook append to a file anywhere else). Then each call appends, in one write, one line per check that ran,
<start, ISO 8601 UTC>\\t<check>\\t<tool or ->\\t<agent_id or ->\\t<duration ms>\\t<session_id or ->\\tifs-pretool,
the check named as its separate hook was (review-isolation, spec-approval-gate guard-bash, ...) and its
duration covering loading and running it, then the dispatcher's own line, the same six fields without the
seventh, with check "ifs-pretool" and the duration from its first statement to its decision (interpreter
start-up is not included), so the eval timeline tool attributes each call and each check. The line is written
by ifs_paths.write_timing: one O_APPEND write, the directory reached from HOME through directory descriptors
with no symlink followed, and only to a private (0600) regular file of this user with one link and under 64 MiB,
opened non-blocking (a FIFO cannot hang the hook); a log that cannot be written so is skipped silently and
timing never changes a decision.

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
    return value if value and all(ch in load_paths().PLAIN_ID_CHARS for ch in value) else None


def isolation_may_decide(raw, tool):
    """review-isolation decides only for a payload carrying agent_id: on a Skill call (registration) or for
    an agent its session's state file names."""
    if '"agent_id"' not in raw:
        return False
    agent, session = plain_id(top_string(raw, "agent_id")), plain_id(top_string(raw, "session_id"))
    if tool == "Skill" or agent is None or session is None:
        return True
    paths = load_paths()
    for path in (paths.isolation_state_file(session), paths.review_marker_file(session)):
        # The state file, then the activation record (in a location only HOME moves): a reviewer whose
        # registration has gone from the state but not from the record still reaches the check, which denies.
        # A record that cannot be read (EACCES, a dangling symlink in its place) runs the check, which fails
        # closed on it; only a record lstat finds absent (ifs_paths.may_exist) is skipped.
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                if '"%s"' % agent in fh.read():
                    return True
        except OSError:
            if paths.may_exist(path):
                return True
    return False


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
    return load_paths().may_exist(os.path.join(SKILLS_DIR, name, "gate_rules.json"))


def gate_may_decide(raw):
    """guard-edit and guard-bash decide only in a session whose gate state file or activation record exists
    (plugin mode): a session whose state has gone, or moved with the environment, is still guarded, and the
    guards deny. A file that cannot be checked (a directory above it the hook may not search) counts as
    existing (ifs_paths.may_exist): os.path.lexists said "absent" then, and the session ran ungated."""
    session = plain_id(top_string(raw, "session_id"))
    if session is None:
        return True
    paths = load_paths()
    return paths.may_exist(paths.gate_state_file(session)) or paths.may_exist(paths.gate_marker_file(session))


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
    """The checks to run: the fast selection, or the full one when the fast one cannot be trusted."""
    try:
        steps = fast_plan(raw)
    except Exception:  # noqa: BLE001 - an unexpected payload, file system state or an ifs_paths.py that does
        steps = None  # not load: run the full selection (fail closed)
    return full_plan(raw) if steps is None else steps


# ------------------------------------------------------------------------------------------- running

_MODULES = {}


def load(path):
    """The check's module, loaded by path and compiled from its source (no bytecode is read or written);
    nothing is added to sys.path."""
    name = MODULE_NAMES[os.path.basename(path)]
    mod = _MODULES.get(name)
    if mod is None:
        mod = load_paths().load_source(name, path)
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
    """The text with control characters blanked; never raises (an exception whose str() raises is shown by its
    type's name), so a denial's reason never stops the denial (PR 1 fix round 4, defect 3)."""
    try:
        text = str(text)
    except Exception:  # noqa: BLE001
        text = type(text).__name__
    return "".join(ch if ch.isprintable() else " " for ch in text)


def failed(key, what):
    label = CHECKS[key][0]
    reason = (f"implement-from-spec: the {label} check {printable(what)}, so the call is denied (its failure "
              "blocks the call). Tell the user; the plugin's core/gate/ifs-pretool.py runs it.")
    return ("deny", reason)


def judge(key, rc, out, exc):
    """The check's (decision, reason), or None for no decision."""
    if exc is not None:
        return failed(key, f"failed ({type(exc).__name__}: {printable(exc)})")
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
        load_paths().write_timing(log_path, text)
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


def timing_log_path():
    """The confined timing log (ifs_paths.timing_log_path), or None; never raises."""
    try:
        return load_paths().timing_log_path()
    except Exception:  # noqa: BLE001 - timing never changes a decision
        return None


def main():
    sys.dont_write_bytecode = True  # no .pyc is written for the standard library either
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
