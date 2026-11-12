#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""core/deps/install-ask-hook.py — PreToolUse hook (matcher Bash): a human approves every setup install.

Whenever a Bash command runs install.py with --apply, this hook answers permissionDecision "ask" and
puts the plan's summary in the permission prompt. The summary is rendered from the plan saved by the dry
run (plans/<digest>.json) only after the plan is checked against the digest (install.py's digest_of and
summary_line), never from the saved summary text: the file is ordinary user state, and an edited summary
would misdescribe the plan the user approves (G6). A plan that no longer matches its digest is not
described at all. The digest alone is not consent: the model could copy it from the dry run, so the user
sees the plan and approves the command in the prompt. Every other command gets no output, so the hook is
inert in sessions that never run setup.

Run by the plugin's one PreToolUse hook, core/gate/ifs-pretool.py (registered once in hooks/hooks.json, in
isolated mode: -I keeps the script's directory, PYTHONPATH and the user's site-packages off sys.path, so
nothing planted there runs in the hook), which calls main() in-process for a Bash command that names
install.py. It imports only the standard library (shlex where it is needed); when a command runs
install.py --apply it loads its siblings depslib.py and install.py by path from its own resolved directory
and adds nothing to sys.path. It still runs on its own the same way, for a check by hand:
  python3 -I <plugin-root>/core/deps/install-ask-hook.py < payload.json

Failure policy: a payload that cannot be parsed produces no output (the hook must never block unrelated
work); a command that mentions install.py and --apply is asked about even when the plan cannot be found or
the command cannot be tokenised. A crash that escapes main() denies the command in the dispatcher (fail
closed; it is loaded only for commands that name install.py).

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional
from time import monotonic as _monotonic  # the opt-in timing log (run_timed) counts from here

_HOOK_T0 = _monotonic()

APPLY_RE = re.compile(r"(?<![\w-])--apply(?![\w-])")
INSTALL_RE = re.compile(r"install\.py\b")
MAX_REASON = 1800


def mentions_apply(command: str) -> bool:
    return bool(INSTALL_RE.search(command) and APPLY_RE.search(command))


def option_value(tokens: List[str], name: str) -> Optional[str]:
    for i, tok in enumerate(tokens):
        if tok == name and i + 1 < len(tokens):
            return tokens[i + 1]
        if tok.startswith(name + "="):
            return tok.split("=", 1)[1]
    return None


def setup_dirs(tokens: List[str], environ: dict) -> List[Path]:
    dirs = []
    cli = option_value(tokens, "--data-dir")
    if cli:
        dirs.append(Path(os.path.expanduser(cli)) / "setup")
    home = environ.get("HOME") or os.path.expanduser("~")
    state = environ.get("XDG_STATE_HOME") or os.path.join(home, ".local", "state")
    dirs.append(Path(state) / "implement-from-spec" / "setup")
    return dirs


def _depslib():
    """depslib.py, by file path from this file's own resolved directory. Setup's scripts run as `python3 -I`,
    which keeps their directory off sys.path, and nothing is added back (TM-40). The same function opens
    doctor.py, install.py, install-ask-hook.py and session-notice.py; depslib.load_sibling loads the rest."""
    path = Path(__file__).resolve().parent / "depslib.py"
    loaded = sys.modules.get("depslib")
    if loaded is not None and Path(getattr(loaded, "__file__", "") or ".").resolve() == path:
        return loaded
    spec = importlib.util.spec_from_file_location("depslib", path)
    mod = sys.modules["depslib"] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def installer():
    """install.py as a module, for digest_of and summary_line. Called only for an install.py --apply command,
    so every other Bash call imports nothing beyond the standard library."""
    return _depslib().load_sibling("implement_from_spec_install", "install.py")


def plan_summary(command: str, environ: dict) -> str:
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    digest = option_value(tokens, "--confirm") or ""
    if not re.fullmatch(r"[0-9a-f]{16}", digest):
        return ("implement-from-spec setup wants to run install.py --apply without a valid dry-run digest; "
                "it will refuse, but check the command before approving")
    for d in setup_dirs(tokens, environ):
        path = d / "plans" / f"{digest}.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        inst = installer()
        plan = saved.get("plan") if isinstance(saved, dict) else None
        try:
            matches = isinstance(plan, dict) and saved.get("digest") == digest and inst.digest_of(plan) == digest
        except (KeyError, TypeError, ValueError):
            matches = False
        if not matches:
            return (f"implement-from-spec setup wants to apply plan {digest}, but the saved dry run {path} does not "
                    "match its digest: it was edited after the dry run, so it is not described here. install.py "
                    "recomputes the plan and refuses on any difference. Do not approve; run the dry run again")
        summary = inst.summary_line(plan)
        return (f"{summary[:MAX_REASON]} [plan {digest}: {path}]. Steps that need administrator rights are "
                "printed for you, never run. Approve only if this is what you asked for")
    return (f"implement-from-spec setup wants to apply plan {digest}, but no saved dry run with that digest "
            "was found; install.py recomputes the plan and refuses on any difference. Check the command before approving")


def decide(payload: dict, environ: Optional[dict] = None) -> Optional[dict]:
    """The hook's output for one payload, or None for no output."""
    environ = dict(os.environ if environ is None else environ)
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not mentions_apply(command):
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                   "permissionDecisionReason": plan_summary(command, environ)}}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        out = decide(payload)
    except Exception:  # noqa: BLE001 - a guard bug must still ask, never silently allow
        command = str((payload.get("tool_input") or {}).get("command", ""))
        out = None
        if mentions_apply(command):
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                          "permissionDecisionReason": "implement-from-spec setup install: review the command before approving"}}
    if out:
        print(json.dumps(out))
    return 0


# --------------------------------------------------------------------------------- opt-in timing log
# Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form `claude plugin eval` passes to its
# sessions) names a log in ~/.local/state/implement-from-spec/hook-timing/ (timing_log_path in
# core/gate/ifs_paths.py, loaded by path from the plugin tree; any other value is refused, so no hook appends to
# a file elsewhere, the project included): then each call appends one line,
# <start, ISO 8601 UTC>\t<hook>\t<tool or ->\t<agent_id or ->\t<duration ms>\t<session_id or ->, for the eval
# timeline tool. The duration runs from the
# first statement of this file (interpreter start-up is not included) to the end of the decision. The line is
# written by ifs_paths.write_timing: one O_APPEND write, the directory reached from HOME with no symlink
# followed, only to a private (0600) regular file of this user with one link, opened non-blocking; a log that
# cannot be written so is skipped silently, and nothing is printed: timing never changes or fails a decision.
# Unset, the hook reads one clock value and the two variables, nothing else.
TIMING_ENV = ("IFS_HOOK_TIMING_LOG", "EVAL_IFS_HOOK_TIMING_LOG")


def _gate_paths():
    """core/gate/ifs_paths.py, by path from this file's plugin tree, compiled from source (no bytecode read or
    written); the same module the PreToolUse checks locate their state and the timing log with."""
    path = str(Path(__file__).resolve().parent.parent / "gate" / "ifs_paths.py")
    mod = sys.modules.get("ifs_gate_paths")
    if mod is not None and getattr(mod, "__file__", None) == path:
        return mod
    import importlib.machinery

    class SourceOnly(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            return self.source_to_code(self.get_data(self.path), self.path)

    spec = importlib.util.spec_from_loader("ifs_gate_paths", SourceOnly("ifs_gate_paths", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["ifs_gate_paths"] = mod
    return mod


def timing_log_path():
    if not any(os.environ.get(n) for n in TIMING_ENV):
        return None
    try:
        return _gate_paths().timing_log_path()
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
            _gate_paths().write_timing(log_path, line)
        except Exception:  # noqa: BLE001 - the timing log is best effort; the hook's decision stands
            pass


if __name__ == "__main__":
    _log = timing_log_path()
    sys.exit(run_timed(main, "install-ask-hook", _log) if _log else main())
