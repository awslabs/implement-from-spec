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

Registered once in hooks/hooks.json, in isolated mode (-I: the script's directory, PYTHONPATH and the
user's site-packages stay off sys.path, so nothing planted there runs in the hook; it imports only the
standard library; when a command runs install.py --apply it loads its siblings depslib.py and install.py
by path from its own resolved directory and adds nothing to sys.path):
  {"matcher": "Bash", "hooks": [{"type": "command",
   "command": "python3 -I \"$CLAUDE_PLUGIN_ROOT/core/deps/install-ask-hook.py\""}]}

Failure policy: a payload that cannot be parsed produces no output (the hook runs on every Bash call
in every session and must never block unrelated work); a command that mentions install.py and --apply
is asked about even when the plan cannot be found or the command cannot be tokenised.

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import List, Optional

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


if __name__ == "__main__":
    sys.exit(main())
