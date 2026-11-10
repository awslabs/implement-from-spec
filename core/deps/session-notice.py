#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""core/deps/session-notice.py — the optional SessionStart notice of the implement-from-spec plugin.

Registered in hooks/hooks.json for SessionStart (matcher `startup`). When the plugin's dependency
check (core/deps/doctor.py) has never run on this machine, or its last result had a required gap, it
prints one line of additionalContext suggesting /implement-from-spec:setup. Otherwise it prints nothing.

Cheap by design: it runs no tool and no version probe. It reads the doctor's saved result,
${XDG_STATE_HOME:-~/.local/state}/implement-from-spec/setup/doctor-last.json, resolved by
depslib.data_dir exactly as the doctor resolves it, so a doctor run from a skill's Bash command and this
hook agree with no flag ($CLAUDE_PLUGIN_DATA, which only the hook sees, is not consulted).

It never blocks and never fails a session: every error ends in silence and exit 0. SessionStart cannot
block anyway (code.claude.com/docs/en/hooks, "SessionStart": exit 2 only shows stderr to the user).

Opt-out: the plugin option `setup_session_notice` (userConfig in .claude-plugin/plugin.json, default
on), resolved like core/scripts/spec-external-review.py resolves its settings: the environment,
IMPLEMENT_FROM_SPEC_SETUP_SESSION_NOTICE, then EVAL_IMPLEMENT_FROM_SPEC_SETUP_SESSION_NOTICE, then
CLAUDE_PLUGIN_OPTION_SETUP_SESSION_NOTICE (what Claude Code exports to plugin hooks); then the saved
plugin options (pluginConfigs in the managed or user settings file); then the default, on. false, 0,
no and off turn it off.

Output (code.claude.com/docs/en/hooks, SessionStart "JSON Output Format", read 2026-10-16):
  {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<one line>"}}

Usage (Claude Code runs it as hooks/hooks.json does, in isolated mode; by hand for a check):
  python3 -I <plugin-root>/core/deps/session-notice.py

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

HERE = Path(__file__).resolve().parent


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


dl = _depslib()

KEY = "setup_session_notice"
DEFAULT_ON = True
OFF_VALUES = ("false", "0", "no", "off")
ON_VALUES = ("true", "1", "yes", "on")
SETTINGS_SCRIPT = HERE.parent / "scripts" / "spec-external-review.py"
SETUP_COMMAND = "/implement-from-spec:setup"


def _settings_module():
    """core/scripts/spec-external-review.py, imported for its settings readers (no side effects on import)."""
    spec = importlib.util.spec_from_file_location("spec_external_review_settings", SETTINGS_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _as_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in OFF_VALUES:
        return False
    if text in ON_VALUES:
        return True
    return None


def enabled(environ: Dict[str, str]) -> Tuple[bool, str]:
    """(on or off, where the value came from). An unrecognised value keeps the default."""
    mod = None
    try:
        mod = _settings_module()
        prefixes = (mod.ENV_PREFIX, mod.EVAL_ENV_PREFIX, mod.PLUGIN_OPTION_PREFIX)
    except Exception:  # noqa: BLE001 - a broken settings reader never breaks a session start
        prefixes = ("IMPLEMENT_FROM_SPEC_", "EVAL_IMPLEMENT_FROM_SPEC_", "CLAUDE_PLUGIN_OPTION_")
    for prefix in prefixes:
        var = prefix + KEY.upper()
        if environ.get(var, "").strip():
            value = _as_bool(environ[var])
            return (DEFAULT_ON, f"default ({var} is not a boolean)") if value is None else (value, var)
    if mod is not None:
        try:
            saved = mod.saved_options(mod.Config())
        except Exception:  # noqa: BLE001 - unreadable saved options fall back to the default, never break a session start
            saved = None
        if saved and str(saved[0].get(KEY, "")).strip():
            value = _as_bool(saved[0][KEY])
            if value is not None:
                return value, saved[1]
    return DEFAULT_ON, "default"


def last_result(system: dl.System) -> Optional[dict]:
    """The doctor's saved result; None when the doctor has never run (or left nothing readable)."""
    try:
        data = json.loads(dl.doctor_cache_path(system).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("at"), str) else None


def message(result: Optional[dict]) -> Optional[str]:
    if result is None:
        return (f"implement-from-spec: its dependency check has never run on this machine. If the user starts "
                f"one of its skills, mention once that {SETUP_COMMAND} checks and installs the tools the skills "
                "need (it installs nothing without their approval)")
    gaps = [g for g in result.get("required_gaps") or [] if isinstance(g, str)]
    if not gaps and result.get("exit", 0) == 0:
        return None
    stacks = ", ".join(s for s in result.get("stacks") or [] if isinstance(s, str)) or "unknown"
    found = ", ".join(gaps) if gaps else "a problem (exit code " + str(result.get("exit")) + ")"
    return (f"implement-from-spec: its last dependency check ({result['at'][:10]}, stacks: {stacks}) found "
            f"required tools missing, too old or unusable: {found}. If the user starts one of its skills, "
            f"mention once that {SETUP_COMMAND} can install them (only with their approval)")


def main(environ: Optional[Dict[str, str]] = None, out=None) -> int:
    out = out or sys.stdout
    try:
        env = dict(os.environ if environ is None else environ)
        on, _source = enabled(env)
        if not on:
            return 0
        text = message(last_result(dl.System(env)))
        if text:
            out.write(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                         "additionalContext": text}}) + "\n")
    except Exception:  # noqa: BLE001 - the notice is optional; silence beats a broken session start
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
