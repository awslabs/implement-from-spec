#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""spec-approval-gate.py: K22, keeps a project repository read-only until the user approves its plan.

Owner: the implement-from-spec plugin; this file lives in the plugin's core/gate/ directory. Standard
library only (Python 3.9+, the python3 macOS ships).

Plugin mode (--skills-dir), the plugin's mode. The plugin's hooks/hooks.json registers the gate once, in every
session: record (UserPromptSubmit) and plan-changed (PostToolUse) as commands of this file, and activate,
guard-edit and guard-bash through the plugin's one PreToolUse hook, core/gate/ifs-pretool.py, which runs them
in-process (run_event) with the same --skills-dir. It is inert, and writes no state, until the session starts
one of the plugin's gated skills (a skill whose directory holds a gate_rules.json), through the Skill tool
(`activate`) or the user's /<plugin>:<skill> command (`record`). Starting the skill registers the repository
the session is in; writing an `ai-planning/*.plan` in another repository registers that one too. Only
registered repositories are gated; every other repository stays writable. The rules are the union of the gated
skills' rules files. The state belongs to the session and lives in the plugin's data directory
(CLAUDE_PLUGIN_DATA). Plugin hooks also see the tool calls of subagents (their payloads carry `agent_id`), and
those are gated exactly like the main conversation.

What it gates. Until the user approves a registered project's plan, writes inside the project outside
`writable_before_approval` (ai-planning/ and .claude/) are denied, through Write/Edit/NotebookEdit and through
the shell. Paths are resolved through `..` and symlinks first. Inside .claude/, the files that could switch
the gate off (`.claude/settings.json`, `.claude/settings.local.json`, anything under `.claude/hooks/`, and
.claude/ itself) are denied until approval and ask after it, also where a symlink makes them live. The gate's
own state, its directory (core/gate/), the plugin's hooks/, the skills' rules and the whole installed plugin
tree (the plugin root, or its core/, hooks/, bin/, skills/, agents/ and .claude-plugin/ when it holds no
manifest; in plugin mode also the plugin root above --skills-dir) are never writable while the gate is
registered, and neither is the other hooks' state (core/gate/ifs_paths.py state_write_roots: the reviewer
registrations, the activation records, the review snapshots and the timing log), so a tool call cannot lift a
reviewer's isolation or rewrite a snapshot's records; a shell command may not even name the registrations or
the records. An edit of an approved plan revokes the approval when the edit starts (PreToolUse), not only when
it is recorded.

Activation records (plugin mode). Starting a gated skill also writes
~/.local/state/implement-from-spec/active/gate-<session>.json, which names the session's state file and is
located from HOME alone. While it exists, a state file that is missing, unreadable or not the one it names
(the environment moved CLAUDE_PLUGIN_DATA or XDG_STATE_HOME between two calls) never makes the session
ungated: every guard denies, a further activation is refused, and the user starts a new session.

Skill mode (--rules FILE), the alternative registration. A skill's `hooks` frontmatter registers the
gate with that skill's rules file. A project repository is then the nearest enclosing git work tree of a
path, unless that work tree is the Claude configuration directory (~/.claude, or $CLAUDE_CONFIG_DIR), or
any repository the session has enrolled by writing one of its plans (so a moved .git does not ungate it).
Skill hooks stay registered for the rest of the session, so every git repository written to later in the
same session is gated too, and they do not reach subagents.

Approval. Each Write/Edit of `<repo>/ai-planning/*.plan` records the plan, its sha256 and an event
number, and makes it the repository's current plan; a shell write to a plan is denied, so every plan
version passes through this record. The approval reply is the whole message: `approve` or `approved`,
optionally followed by the plan name (its stem) or the repository directory, and at most a closing full
stop or exclamation mark. Anything longer approves nothing. A bare reply approves the one pending plan; a
named reply approves only the plan it names; when several repositories have pending plans the name is
required. Copies of the hook registered by several skills (skill mode) see one reply as one (a 10-second
window). The plan must still have the sha256 it had when it was last written through Write/Edit, so a
change made behind the hook's back is never approved unseen. Approval holds while the plan is unchanged
and is still its repository's current plan; any change revokes it for good (a later restore of the old
bytes does not bring it back). A deleted plan revokes it too. Approval belongs to the session that gave
it; another session stays denied.

Bash. Every segment is analysed and the decisions are aggregated: deny beats ask beats nothing, so a
command rule that asks never lets an unapproved write in the same command through. The shell analysis
covers redirections (>&FILE and <> included), the usual writers (rm, cp, mv sources and destinations, tee,
install, ln, rsync, chmod, sed -i, perl -pi, awk output redirection, find -delete and -exec, xargs, git
after its global options, tar -x and unzip, formatters, Maven and Gradle goals that rewrite the source
tree, dependency tools, curl -o, aws s3 cp), the writes a skill's `write` command rules declare (tools that
write into the directory they work in as a side effect: terraform init writes .terraform/, cdk synth cdk.out/,
a Maven build target/; -chdir, -f, -p and --prefix resolved), a copy into an existing directory through a
symlink in it, a hard link (its source counts as written; a hard-linked file under ai-planning/ stays
read-only), reserved words (then, do, {, function NAME), `bash -c` strings (-lc and other clusters), eval, env -S, here-documents
and here-strings fed to a shell, find -exec bodies, `$(...)` and backtick command substitutions (in unquoted
here-document bodies too), and inline interpreter code that writes files or runs commands, including a
here-document fed to `python3 -` (its path literals and its working directory; the literal command strings
it runs are analysed like a shell command). Quoted operator characters are words, not operators; options
after `--` are operands and one-letter options take attached values (cp -tDIR, tar -xf/ARCHIVE). cd, pushd,
popd and env -C are followed; a cd that may fail or may not run (after && or ||, inside if), cd -, an
unexpanded directory, and cd's logical and physical directory all stay in play. Variables assigned earlier in
the command, `$PWD`, `${VAR:-default}` and the hook's environment are expanded where the shell would expand
them (not inside single quotes; a nested shell also gets the assignments its command line and env pass it); a
write target that still cannot be resolved, a program named by an unresolved variable, the commands a shell
reads from standard input, nesting deeper than MAX_DEPTH, the arguments xargs feeds a writer, and a command
the shell lexer cannot parse (an unterminated quote) count as a write at the working directory and at the
repository holding it, so they are denied inside an unapproved project. Before approval, `ln -s` to a path
that may not be written is refused, and a write under a path an earlier segment of the same command copied,
moved, linked or extracted into the project is denied (the analysis sees the file system before the command
runs). A command that runs the gate's own script or the PreToolUse dispatcher (under any spelling or
symlink), names its state directory, or sets the variable that locates it is denied. It is a guard against
mistakes, not a sandbox: a script file run by an interpreter is not inspected, inline code that writes
through an API the gate does not know is not seen, a hard link made outside the project before the session
is not detected, and a determined
process running as the same user can still reach the state; the approval comes from the user's reply,
recorded only by the UserPromptSubmit hook.

The user's Claude settings. In a gated session the user's settings files and hooks
(<config>/settings.json, settings.local.json, hooks/; <config> is $CLAUDE_CONFIG_DIR or ~/.claude) are
denied until a plan is approved and ask after it, like the project's own, also where a symlink makes them
live (the name a file is reached by and the file it really is are both checked).

Two registration modes (described above):
  --skills-dir DIR   plugin mode, registered by the plugin's hooks/hooks.json
  --rules FILE       skill mode, registered by a skill's `hooks` frontmatter

Subcommands, one per hook event:
  activate      PreToolUse Skill  plugin mode: starting a gated skill registers the current repository
  record        UserPromptSubmit  an approval reply approves the pending plan (plugin mode: a
                                  /<plugin>:<skill> command also registers the repository)
  guard-edit    PreToolUse        Write/Edit/MultiEdit/NotebookEdit
  guard-bash    PreToolUse        Bash
  plan-changed  PostToolUse       a Write/Edit of <repo>/ai-planning/*.plan

Failure policy. A guard that fails (a malformed payload, a hook error, a rules file that is not of the
documented shape in skill mode, a lost state of an activated session) denies in a gated session; in plugin
mode a session that never started a gated skill is never blocked. When the payload is not valid JSON, its
session is read from the raw text so a gated session still fails closed. Starting a gated skill when the gate cannot record the session (its
state directory unwritable) is refused: the Skill call is denied, the /<plugin>:<skill> prompt blocked.
In plugin mode a skill's unreadable or malformed gate_rules.json (or one that has gone after its skill
started) keeps the default writable prefixes, and every shell command in a gated session asks until it is
fixed. Every decision is JSON on stdout with exit
0; Claude Code treats any other exit but 2 as a non-blocking error, so no failure path exits non-zero
from a guard. The paths and commands a reason or notice quotes lose their control characters and bidi
controls first (clean), so text the model supplied cannot start a new line or restyle the text.

Usage (the guard-edit event of a Write in plugin mode, by hand; Claude Code runs it through ifs-pretool.py):
  echo '{"session_id":"s1","cwd":"/repo","tool_name":"Write","tool_input":{"file_path":"/repo/src/a.py"}}' \
    | python3 -I <plugin-root>/core/gate/spec-approval-gate.py guard-edit --skills-dir <plugin-root>/skills
The unit tests, which execute every gate_rules.json example, are kept in the development repository.
"""

import os
import sys
from time import monotonic as _monotonic  # first: the opt-in timing log (run_timed) counts from here; built in

_HOOK_T0 = _monotonic()

# The gate's own directory is not an import location: Python puts a script's directory first on sys.path, so a
# json.py written next to this file would run inside every hook call. os and sys are loaded at interpreter
# startup and need no lookup. PYTHON* variables and the user's site-packages are for the hook command to
# exclude (python3 -I).
if sys.path and os.path.realpath(sys.path[0] or os.getcwd()) == os.path.dirname(os.path.realpath(__file__)):
    del sys.path[0]

import contextlib  # noqa: E402 - after the sys.path guard above; argparse and tempfile load where used
import fcntl
import glob
import hashlib
import json
import re
import shlex
import time

HOOK_FILE = os.path.realpath(__file__)


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


# Copies of this hook registered by several skills receive one reply within milliseconds of each other;
# the same text arriving later is a new reply (re-approving an amended plan).
DUPLICATE_WINDOW_S = 10
# The plugin root is two levels above this file (<plugin-root>/core/gate/); every skill of the plugin
# keeps its gate_rules.json under <plugin-root>/skills/<skill>/, and all of them share the protection.
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HOOK_FILE)))
SKILLS_ROOT = os.path.join(PLUGIN_ROOT, "skills")
# Git work trees that are never project repositories: the Claude configuration directory (often a git
# repository itself, and where memory and settings live). SPEC_GATE_VAULT adds the self-test's throwaway
# root, which plays the part of a non-project working directory.
EXEMPT_ROOTS = {os.path.realpath(os.path.expanduser(p)) for p in
                (os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude", os.environ.get("SPEC_GATE_VAULT"))
                if p}
# Session state lives outside every project, so the gate never dirties a work tree: in the plugin's
# data directory, which Claude Code exports to hook commands as CLAUDE_PLUGIN_DATA and keeps across plugin
# updates; outside Claude Code, in the XDG state directory. No other variable moves it (a repository's settings
# env block can set neither: core/gate/ifs_paths.py). ifs_paths.py computes it, for this file and for the
# PreToolUse dispatcher alike. In plugin mode, starting a gated skill also writes an activation record
# (ifs_paths.gate_marker_file, from HOME alone) naming this state file: when the record exists and the state
# it names is missing, unreadable or elsewhere, the session's guards deny (state_txn raises StateLost).
STATE_DIR = load_paths().gate_state_dir()
# Setup's state (core/deps/depslib.py data_dir, default location): the saved dry runs the setup ask hook reads
# when it describes a plan in the permission prompt, the journal and the record of what setup installed. Setup
# writes it from its own Python process, never through a tool call the gate sees.
SETUP_STATE_DIR = os.path.realpath(os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "implement-from-spec", "setup"))
# Never writable while the gate is registered: its state, its code (the whole directory it runs from, where a
# file could shadow a module it imports, ifs_paths.py included), the plugin's hook registrations, the skills'
# rule files and setup's state (G6); and the other hooks' state (ifs_paths.state_write_roots: the isolation
# hook's reviewer registrations, the activation records, the review snapshots and the timing log), so a tool
# call cannot remove a reviewer's registration or rewrite a snapshot's records and their hashes.
GATE_DIR = os.path.dirname(HOOK_FILE)
STATE_WRITE_ROOTS = load_paths().state_write_roots()
STATE_NAME_ROOTS = load_paths().state_name_roots()
PLUGIN_HOOKS_DIR = os.path.join(PLUGIN_ROOT, "hooks")
PROTECTED_RE = re.compile(r"^(%s|%s|%s|%s)(/|$)|^%s/[^/]+/gate_rules\.json$"
                          % (re.escape(STATE_DIR), re.escape(GATE_DIR), re.escape(PLUGIN_HOOKS_DIR),
                             re.escape(SETUP_STATE_DIR), re.escape(SKILLS_ROOT)))
# The plugin's installed tree is never writable either (TM-40): a gated session that rewrote the setup ask hook
# (core/deps/), the external-review script and its bedrock-gpt wrapper (core/scripts/), an agent or the
# manifest would change what the next hook call or review runs. A plugin root is a directory holding
# .claude-plugin/plugin.json and is protected as a whole; without the manifest, only its component directories.
PLUGIN_MANIFEST = os.path.join(".claude-plugin", "plugin.json")
PLUGIN_DIRS = ("core", "hooks", "bin", "skills", "agents", ".claude-plugin")
HOOK_BASENAME = os.path.basename(HOOK_FILE)
# The PreToolUse dispatcher runs this file's activate, guard-edit and guard-bash events in-process, so running it
# counts as running the gate.
DISPATCHER_FILE = os.path.join(os.path.dirname(HOOK_FILE), "ifs-pretool.py")
DISPATCHER_BASENAME = os.path.basename(DISPATCHER_FILE)
# Setting a variable that locates the gate's state (so a copy of the script would write the real state).
STATE_ENV_RE = re.compile(r"(?<![\w$])(CLAUDE_PLUGIN_DATA|SPEC_GATE_STATE_DIR)['\"\]]*\s*=")
# The user's Claude configuration: its settings files and hooks can switch every hook off (Claude Code's file
# watcher picks up direct edits to hooks in settings files), so in a gated session they are guarded like a
# project's own: denied until a plan is approved, asked after it.
CONFIG_DIR = os.path.realpath(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"))
USER_GUARD_RE = re.compile(r"^%s(/settings(\.local)?\.json|/hooks(/.*)?)?$" % re.escape(CONFIG_DIR))
DEFAULT_WRITABLE = ["ai-planning/", ".claude/"]
DEFAULT_WORDS = ["approve", "approved"]
# Project files that could switch the gate off (disableAllHooks, a disabled plugin, a hook that answers
# for this one): denied until approval even though .claude/ is writable, and asked after it.
GUARD_FILES_RE = re.compile(r"^\.claude(/settings(\.local)?\.json|/hooks(/.*)?)?$")
# Set by main() in plugin mode: only registered repositories are project repositories, and a session
# that has not started a gated skill is not gated at all.
PLUGIN_MODE = {"on": False, "skills": set(), "name": "", "skills_dir": ""}

SEPARATORS = {";", "&&", "||", "|", "|&", "&", ";;"}
REDIRECTS_OUT = {">", ">>", ">|", "&>", "&>>"}
REDIRECTS_IN = {"<", "<<", "<<<", "<>"}
# Wrappers that run the next word as the real program.
WRAPPERS = {"sudo", "env", "time", "nohup", "exec", "nice", "command", "builtin", "xargs"}
# Runners whose first non-option word is the real program (npx prettier --write ...).
RUNNERS = {"npx", "uvx", "pnpx", "bunx"}
# Programs whose every non-option argument is written (mv: the source is removed from where it was).
WRITE_ALL_ARGS = {"rm", "rmdir", "touch", "mkdir", "tee", "truncate", "shred", "unlink", "mv"}
# Programs whose first non-option argument is a mode or owner and the rest are written.
WRITE_AFTER_FIRST_ARG = {"chmod", "chown", "chgrp"}
# Programs whose last non-option argument is the destination.
WRITE_LAST_ARG = {"cp", "ln", "install", "rsync"}
IN_PLACE_EDITORS = {"sed", "gsed", "perl", "ruby"}
GIT_WRITERS = {"add", "apply", "am", "checkout", "cherry-pick", "clean", "commit", "merge", "mv", "pull",
               "rebase", "reset", "restore", "revert", "rm", "stash", "switch",
               "clone", "init", "worktree", "submodule", "sparse-checkout", "format-patch", "update-index",
               "read-tree", "checkout-index"}
AWKS = {"awk", "gawk", "mawk", "nawk"}
AWK_OPTS_WITH_VALUE = {"-F", "-v", "-f", "-i", "-l", "-E", "--field-separator", "--assign", "--file",
                       "--include", "--load", "--exec"}
# awk program text that writes: print/printf redirected to a file or a command, or system().
AWK_WRITE_RE = re.compile(r"\bprintf?\b[^;}]*[>|]|\bsystem\s*\(")
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
# Maven and Gradle goals that rewrite the source tree (formatters, OpenRewrite, version bumps, release
# preparation). The build output routine lifecycle phases write (target/, build/, .gradle/) is declared by the
# skills' `write` command rules (gate_rules.json), like every other side-effect write.
MAVEN = {"mvn", "mvnw", "mvnd"}
GRADLE = {"gradle", "gradlew"}
MAVEN_WRITE_GOALS = {"spotless": re.compile(r"apply$"), "fmt": re.compile(r"format$"),
                     "rewrite": re.compile(r"run$"), "versions": re.compile(r"(?!display-|help$)[\w-]+$"),
                     "release": re.compile(r"(prepare|perform)$")}
GRADLE_WRITE_TASK_RE = re.compile(r"^(spotless\w*Apply|rewriteRun|ktlintFormat)$")
MAVEN_OPTS_WITH_VALUE = {"-f", "--file", "-pl", "--projects", "-P", "--activate-profiles", "-s", "--settings",
                         "-gs", "--global-settings", "-T", "--threads", "-rf", "--resume-from", "-l", "--log-file",
                         "-t", "--toolchains", "-D", "--define", "-b", "--builder"}
GRADLE_OPTS_WITH_VALUE = {"-x", "--exclude-task", "-p", "--project-dir", "-D", "-P", "-I", "--init-script",
                          "-c", "--settings-file", "-b", "--build-file", "-g", "--gradle-user-home",
                          "--console", "--warning-mode", "--max-workers"}
NODE_PKG = {"npm", "pnpm", "yarn", "bun"}
NODE_PKG_WRITERS = {"add", "ci", "i", "install", "link", "remove", "rm", "uninstall", "up", "update"}
UV_WRITERS = {"add", "remove", "lock", "sync", "init", "version"}
SHELLS = {"bash", "sh", "zsh"}
RESERVED_WORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl"}
# Inline interpreter code that writes files. Such code is checked for its path literals and its cwd.
INLINE_WRITE_RE = re.compile(r"open\s*\([^)]*['\"](?:[rwax]\+|[wax])[tb]?['\"]|write_text|write_bytes|shutil\.|"
                             r"os\.(open|write|ftruncate|remove|rename|replace|unlink|makedirs|mkdir|rmdir|symlink|"
                             r"link|chmod|truncate|"
                             r"system|popen|exec\w*|spawn\w*)|subprocess|\bpty\.|\.(touch|unlink|rename|mkdir|rmdir|"
                             r"symlink_to|hardlink_to|chmod)\(|writeFileSync|appendFileSync|\.writeFile\(|rmSync|"
                             r"unlinkSync|child_process|execSync|execFileSync|spawnSync|fs\.\w*(rename|copyFile|mkdir|"
                             r"createWriteStream|symlink|link|truncate|chmod|cp)|File\.write|IO\.popen|\bsystem\(|"
                             r"Kernel\.exec|`[^`]*`")
PATH_LITERAL_RE = re.compile(r"['\"]([^'\"\n]*[/.][^'\"\n]*)['\"]")
AWS_GLOBAL_OPTS_WITH_VALUE = {"--profile", "--region", "--output", "--endpoint-url", "--query",
                              "--ca-bundle", "--color", "--cli-read-timeout", "--cli-connect-timeout",
                              "--cli-binary-format"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


# ---------------------------------------------------------------------------------------------- io

def load_rules(path):
    """A rules file with its defaults filled in. A file that is not a JSON object of the documented shape
    raises ValueError, so a broken file never loads as 'no rules'."""
    rules = {}
    if path:
        with open(path, encoding="utf-8") as fh:
            rules = json.load(fh)
    if not isinstance(rules, dict):
        raise ValueError(f"{path}: the rules file is not a JSON object")
    rules.setdefault("writable_before_approval", DEFAULT_WRITABLE)
    rules.setdefault("approval_words", DEFAULT_WORDS)
    rules.setdefault("command_rules", [])
    validate_rules(rules, path)
    return rules


RULE_MATCH_LISTS = ("programs", "subcommands", "aws_services", "read_only_operations", "read_only_verbs")


def validate_rules(rules, path):
    def strings(value):
        return isinstance(value, list) and all(isinstance(v, str) and v for v in value)

    for key in ("writable_before_approval", "approval_words"):
        if not strings(rules[key]) or not rules[key]:
            raise ValueError(f"{path}: {key} must be a non-empty list of strings")
    if not isinstance(rules["command_rules"], list):
        raise ValueError(f"{path}: command_rules must be a list")
    for rule in rules["command_rules"]:
        if not (isinstance(rule, dict) and isinstance(rule.get("id"), str) and rule.get("decision") in
                {"ask", "deny", "write"} and isinstance(rule.get("message"), str) and
                isinstance(rule.get("match"), dict)):
            raise ValueError(f"{path}: every command rule needs an id, a decision (ask, deny or write), a message "
                             f"and a match object: {json.dumps(rule)[:200]}")
        match = rule["match"]
        for key in RULE_MATCH_LISTS:
            if key in match and not strings(match[key]):
                raise ValueError(f"{path}: rule {rule['id']}: match.{key} must be a list of strings")
        if "args_regex" in match:
            if not isinstance(match["args_regex"], str):
                raise ValueError(f"{path}: rule {rule['id']}: match.args_regex must be a string")
            re.compile(match["args_regex"])
        if "aws_mutating" in match and not isinstance(match["aws_mutating"], bool):
            raise ValueError(f"{path}: rule {rule['id']}: match.aws_mutating must be true or false")
        validate_writes(rule, path)


WRITES_LISTS = ("paths", "directory_options", "file_options", "path_options")


def validate_writes(rule, path):
    """A `write` rule names what the matched command writes: a `writes` object with paths, options whose value
    is written, or operands. Only `write` rules carry one."""
    writes = rule.get("writes")
    if rule["decision"] != "write":
        if writes is not None:
            raise ValueError(f"{path}: rule {rule['id']}: only a rule whose decision is write has a writes object")
        return
    if not isinstance(writes, dict):
        raise ValueError(f"{path}: rule {rule['id']}: a write rule needs a writes object")
    for key in WRITES_LISTS:
        if key in writes and not (isinstance(writes[key], list) and writes[key] and
                                  all(isinstance(v, str) and v for v in writes[key])):
            raise ValueError(f"{path}: rule {rule['id']}: writes.{key} must be a non-empty list of strings")
    if "operands" in writes and not isinstance(writes["operands"], bool):
        raise ValueError(f"{path}: rule {rule['id']}: writes.operands must be true or false")
    if not (writes.get("paths") or writes.get("path_options") or writes.get("operands")):
        raise ValueError(f"{path}: rule {rule['id']}: writes names nothing written (paths, path_options or "
                         "operands)")


# C0 and C1 control characters (newline, carriage return, tab and ESC included) and the Unicode bidirectional
# controls: embeddings and overrides U+202A-U+202E, isolates U+2066-U+2069, and the marks U+200E, U+200F, U+061C.
CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\u200e\u200f\u061c]")


def clean(text):
    """Text the gate shows Claude, without control characters. Reasons and notices quote paths and commands the
    model supplied; a path holding a newline and "</system>", an ESC sequence or a bidi override must not start a
    new line, restyle the text or reorder it once it is quoted. The gate's own wording carries none of them."""
    return CONTROL_RE.sub("", str(text))


def say(text):
    """Plain stdout, which Claude Code adds to Claude's context on UserPromptSubmit."""
    print(clean(text))


def emit_pre_tool(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": clean(reason)}}))


def emit_context(event, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": clean(text)}}))


# ------------------------------------------------------------------------------------------- state

def session_key(data):
    return load_paths().session_key(data.get("session_id"))


@contextlib.contextmanager
def state_txn(data, write):
    """Load the session state under an exclusive lock; save it on exit when `write` is true.

    Several skills may register this hook, so several copies run per event: the lock makes each
    read-modify-write one transaction instead of a lost update."""
    # Owner-only: the directory 0700 and the lock files 0600 (state files are 0600 through mkstemp).
    path = os.path.join(STATE_DIR, f"{session_key(data)}.json")
    marker_state = recorded_state(data) if PLUGIN_MODE["on"] else None
    if marker_state is not None and marker_state != path:
        raise lost(data, marker_state, path)  # the environment moved the state since activation
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    with os.fdopen(os.open(path + ".lock", os.O_RDWR | os.O_CREAT, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(path, encoding="utf-8") as fh:
                state = json.load(fh)
        except FileNotFoundError:
            if marker_state is not None:
                raise lost(data, marker_state, path)  # deleted since activation: never start afresh, ungated
            state = {}
        state.setdefault("seq", 0)
        state.setdefault("plans", {})       # abs plan path -> {"repo", "seq", "sha256"}
        state.setdefault("approvals", {})   # repo -> {"plan", "sha256"}
        state.setdefault("repos", [])       # enrolled project repositories
        state.setdefault("handled", [])     # [prompt digest, time] of replies just recorded
        state["handled"] = [h for h in state["handled"] if isinstance(h, list) and len(h) == 2]
        yield state
        if write:
            import tempfile
            fd, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".state-")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=1)
            os.replace(tmp, path)


def session_active(data):
    """Plugin mode: whether this session has started a gated skill (its state file or, in plugin mode, its
    activation record exists). A file that cannot be checked (EACCES on a directory above it, ELOOP) counts as
    existing (ifs_paths.may_exist), so an unreachable state is guarded and denied, never taken for none."""
    paths = load_paths()
    return paths.may_exist(os.path.join(STATE_DIR, f"{session_key(data)}.json")) or (
        PLUGIN_MODE["on"] and paths.may_exist(paths.gate_marker_file(data.get("session_id"))))


class StateLost(Exception):
    """An activated session's gate state is missing, unreadable or not where its activation record says."""


def recorded_state(data):
    """Plugin mode: the state file this session's activation record names, or None when there is no record.
    Raises StateLost when the record cannot be read."""
    marker = load_paths().gate_marker_file(data.get("session_id"))
    try:
        with open(marker, encoding="utf-8") as fh:
            record = json.load(fh)
    except FileNotFoundError:
        if load_paths().may_exist(marker):  # a dangling symlink in its place: not "no record"
            raise StateLost(f"the activation record {marker} cannot be read (not a regular file)")
        return None
    except (OSError, ValueError) as exc:
        raise StateLost(f"the activation record {marker} cannot be read ({type(exc).__name__})")
    if not isinstance(record, dict) or not isinstance(record.get("state"), str):
        raise StateLost(f"the activation record {marker} is not of the gate's shape")
    return record["state"]


def lost(data, marker_state, path):
    marker = load_paths().gate_marker_file(data.get("session_id"))
    return StateLost(
        f"this session started a gated skill (activation record {marker}), "
        f"but its gate state {marker_state} is missing or not the state this call finds ({path}), "
        "so every write and shell command of the session is denied. Start a new session; the approvals of "
        "this one cannot be restored")


def write_marker(data):
    """Plugin mode, on activation: the activation record, naming this session's state file. Written atomically,
    0600 in a 0700 directory; an existing record is kept (it names the first state)."""
    marker = load_paths().gate_marker_file(data.get("session_id"))
    try:
        os.lstat(marker)
        return  # an existing record is kept
    except (FileNotFoundError, NotADirectoryError):
        pass  # any other error (a record that cannot be checked) raises: activation fails, never unrecorded
    import tempfile
    directory = os.path.dirname(marker)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gate-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"state": os.path.join(STATE_DIR, f"{session_key(data)}.json"),
                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)
    os.replace(tmp, marker)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def current_plan(repo, state):
    plans = [(p, v) for p, v in state["plans"].items() if v["repo"] == repo]
    return max(plans, key=lambda pv: pv[1]["seq"])[0] if plans else None


def approval_status(repo, state):
    """Return (approved, why_not). A failed check latches: the approval entry is removed."""
    entry = state["approvals"].get(repo)
    if not entry:
        return False, "no plan of this project has been approved in this session"
    plan, why = entry["plan"], None
    if not os.path.isfile(plan):
        why = f"the approved plan {os.path.relpath(plan, repo)} no longer exists"
    elif sha256(plan) != entry["sha256"]:
        why = f"{os.path.relpath(plan, repo)} changed after approval, which revoked it"
    elif current_plan(repo, state) != plan:
        why = (f"a newer plan, {os.path.relpath(current_plan(repo, state), repo)}, was written after "
               f"{os.path.relpath(plan, repo)} was approved")
    if why:
        del state["approvals"][repo]
        return False, why
    return True, ""


# --------------------------------------------------------------------------------------- locating

def resolve(path, cwd):
    # realpath before any `..` is folded: link/.. is the link target's parent, as the kernel sees it.
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd, expanded)
    return os.path.realpath(expanded)


def lexical(path, cwd, shell_word=False):
    """The absolute path as named, its last component not resolved (the name a guarded file was reached by):
    the directory part resolved like resolve(), the file name kept. shell_word: a shell word (see resolve_shell)."""
    expanded = os.path.expanduser(path)
    expanded = literal(expanded) if shell_word else expanded
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd, expanded)
    head, tail = os.path.split(expanded.rstrip("/") or "/")
    if tail in ("", ".", ".."):
        return os.path.realpath(expanded)
    return os.path.join(os.path.realpath(head), tail)


def lexical_guard(name, abspath, rules, state):
    """A denial when the path as named (before symlinks are resolved) is the user's or a project's Claude
    settings or hooks, though its resolved form is not: a settings.json symlinked to a dotfiles checkout."""
    if name == abspath:
        return None
    repo = project_repo(name, state)
    rel = repo and ("." if name == repo else os.path.relpath(name, repo))
    if user_guarded(name, explicit=False) or (rel and GUARD_FILES_RE.match(rel)):
        return gated(name, rules, state, explicit=False)
    return None


def under(path, root):
    return path == root or path.startswith(root + os.sep)


def project_repo(abspath, state):
    """The project repository holding abspath: an enrolled repo, else (skill mode only) the nearest
    git work tree outside the exemptions."""
    for repo in sorted(state.get("repos", []), key=len, reverse=True):
        if under(abspath, repo):
            return repo
    return None if PLUGIN_MODE["on"] else git_tree(abspath)


def git_tree(abspath):
    """The nearest enclosing git work tree of abspath, unless it is an exempt root."""
    probe = abspath
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent
    probe = probe if os.path.isdir(probe) else os.path.dirname(probe)
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return None if probe in EXEMPT_ROOTS else probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def plugin_trees():
    """The installed plugin trees (TM-40): the plugin root this script runs from (both modes) and, in plugin
    mode, the parent of --skills-dir when it is a plugin root. A root holding the manifest is protected whole;
    the gate's own root without one keeps its component directories protected; a bare skills directory (not
    inside a plugin root) adds nothing beyond its rules files."""
    trees = []
    for root in (PLUGIN_ROOT, os.path.dirname(PLUGIN_MODE["skills_dir"]) if PLUGIN_MODE["skills_dir"] else ""):
        if not root or root in trees:
            continue
        if os.path.isfile(os.path.join(root, PLUGIN_MANIFEST)):
            trees.append(root)
        elif root == PLUGIN_ROOT:
            trees.extend(os.path.join(root, d) for d in PLUGIN_DIRS)
    return trees


def protected_roots():
    return [STATE_DIR, GATE_DIR, PLUGIN_HOOKS_DIR, SETUP_STATE_DIR] + STATE_WRITE_ROOTS + plugin_trees() + \
        sorted(glob.glob(os.path.join(SKILLS_ROOT, "*", "gate_rules.json")))


def gated(abspath, rules, state, explicit=True):
    """Return a denial reason when abspath may not be written now, else None.

    `explicit` is false for the synthetic 'somewhere under the working directory' target of formatters,
    git and inline code: such a target is checked as a location, not as a directory being replaced."""
    if PROTECTED_RE.search(abspath) or any(under(abspath, root) for root in plugin_trees() + STATE_WRITE_ROOTS) or (
            PLUGIN_MODE["skills_dir"] and re.match(
                r"^%s/[^/]+/gate_rules\.json$" % re.escape(PLUGIN_MODE["skills_dir"]), abspath)):
        return (f"spec-approval-gate (K22): '{abspath}' is the approval gate's own state, code or rules, the "
                "plugin's other hook state (reviewer registrations, review snapshots, activation records, the "
                "timing log) or a file of the installed plugin, which are never written while the gate is "
                "registered. Ask the "
                "user to change it in a session without the implementing skills.")
    if explicit:
        for root in protected_roots():
            if under(root, abspath) and root != abspath:
                return (f"spec-approval-gate (K22): '{abspath}' contains the approval gate's state, code or "
                        "rules; removing, moving or replacing the directory is not allowed while the gate "
                        "is registered.")
        for repo in state.get("repos", []):
            if under(repo, abspath) and repo != abspath:
                return (f"spec-approval-gate (K22): '{abspath}' contains the gated project {repo}; a write "
                        "to the whole directory is not allowed while the gate is registered.")
    if user_guarded(abspath, explicit):
        if any_approved(state):
            return None  # guard_ask() asks instead
        return (f"spec-approval-gate (K22): '{abspath}' is (or holds) the user's Claude settings or hooks, which "
                "can switch the approval gate off, so it stays read-only until a plan is approved. Other files in "
                f"{CONFIG_DIR} stay writable.")
    linked = guard_files_repo(abspath, state)
    repo = linked or project_repo(abspath, state)
    if repo is None:
        return None
    rel = ".claude/settings (through a symlink)" if linked else "." if abspath == repo else \
        os.path.relpath(abspath, repo)
    if linked or GUARD_FILES_RE.match(rel):
        approved, why_not = approval_status(repo, state)
        if approved:
            return None  # guard_ask() asks instead
        return (f"spec-approval-gate (K22): '{rel}' in {repo} can switch the approval gate off (project "
                f"settings or hooks), so it stays read-only until the plan is approved, and {why_not}. "
                "Other files under .claude/ stay writable.")
    for prefix in rules["writable_before_approval"]:
        bare = prefix.rstrip("/")
        if rel == bare or rel.startswith(bare + "/"):
            if hard_linked(abspath) and not approval_status(repo, state)[0]:
                # realpath() sees through symlinks, not hard links: this name may be another project file.
                return (f"spec-approval-gate (K22): '{rel}' in {repo} is a hard-linked file, so writing it may "
                        "change another file of the project; it stays read-only until the plan is approved.")
            return None
    approved, why_not = approval_status(repo, state)
    if approved:
        return None
    return (f"spec-approval-gate (K22): '{rel}' in {repo} is outside "
            f"{', '.join(rules['writable_before_approval'])} and {why_not}. Write or finish the plan in "
            f"{os.path.join(repo, 'ai-planning')}/<slug>.plan, present it with its path, and ask the user "
            "in plain text (not AskUserQuestion) to reply 'approve'. Only that reply unlocks the project; "
            "never route the change through another tool or the shell.")


def user_guarded(abspath, explicit=True):
    """Whether abspath is the user's Claude settings or hooks, or (an explicit target) a directory holding
    them."""
    return bool(USER_GUARD_RE.match(abspath)) or (explicit and under(CONFIG_DIR, abspath)) or \
        behind_link(abspath, CONFIG_DIR)


def behind_link(abspath, base):
    """Whether abspath is where <base>/settings.json, settings.local.json, hooks/ or <base> itself really live
    when they are symlinks (a dotfiles checkout): abspath is already resolved, so the name it was reached by
    is gone, and the file is guarded by its identity instead."""
    for name in ("settings.json", "settings.local.json"):
        real = os.path.realpath(os.path.join(base, name))
        if real != os.path.join(base, name) and abspath == real:
            return True
    hooks = os.path.join(base, "hooks")
    real = os.path.realpath(hooks)
    return (real != hooks and under(abspath, real)) or (os.path.realpath(base) != base and
                                                         abspath == os.path.realpath(base))


def guard_files_repo(abspath, state):
    """The registered repository whose .claude/ settings or hooks abspath really is (through a symlink that
    leads out of the repository), or None."""
    for repo in state.get("repos", []):
        if behind_link(abspath, os.path.join(repo, ".claude")):
            return repo
    return None


def any_approved(state):
    return any(approval_status(repo, state)[0] for repo in list(state.get("repos", [])))


def hard_linked(abspath):
    try:
        st = os.stat(abspath)
    except OSError:
        return False
    return not os.path.isdir(abspath) and st.st_nlink > 1


def guard_ask(abspath, state):
    """After approval, a write to a project's gate-relevant .claude/ files, or to the user's Claude settings
    or hooks, asks: return the reason, or None."""
    if user_guarded(abspath):
        return (f"spec-approval-gate (K22): '{abspath}' is (or holds) the user's Claude settings or hooks, which "
                "can switch the approval gate off. Approve only if you asked for this change.")
    linked = guard_files_repo(abspath, state)
    repo = linked or project_repo(abspath, state)
    if repo is None:
        return None
    rel = ".claude/settings (through a symlink)" if linked else "." if abspath == repo else \
        os.path.relpath(abspath, repo)
    if not linked and not GUARD_FILES_RE.match(rel):
        return None
    return (f"spec-approval-gate (K22): '{rel}' in {repo} holds project settings or hooks that can switch "
            "the approval gate off. Approve only if you asked for this change.")


# -------------------------------------------------------------------------------------- subcommands

def skill_parts(invoked):
    """(namespace, name) of a Skill call's `skill` input, read by ifs_paths.skill_parts, the reading the dispatcher
    and the isolation hook share (whitespace and leading "/" dropped). When ifs_paths.py itself cannot load, a
    reading at least as wide (every Python whitespace character, U+FEFF and "/" stripped from both ends until
    none is left, then the parts) keeps an ungated skill from being refused for a module only the gated path
    needs, and still names a gated skill as gated."""
    try:
        return load_paths().skill_parts(invoked)
    except Exception:  # noqa: BLE001 - ifs_paths.py may be what failed
        text = invoked if isinstance(invoked, str) else ""
        while True:
            stripped = text.strip().strip("\ufeff/")
            if stripped == text:
                break
            text = stripped
        namespace, _, name = text.rpartition(":")
        return namespace.strip().strip("\ufeff"), name.strip().strip("\ufeff")


def cmd_activate(data, rules):
    """Plugin mode, PreToolUse on the Skill tool: starting a gated skill registers the repository."""
    tool_input = data.get("tool_input")
    activate(data, tool_input.get("skill") if isinstance(tool_input, dict) else None)


def activate(data, invoked):
    """Register the session's current repository when `invoked` names one of the plugin's gated skills
    (`<plugin>:<skill>`, or the bare skill name; read by ifs_paths.skill_parts, as the dispatcher and the
    isolation hook read it, so `/<skill>` and a padded name activate too). Returns the repository, or None."""
    namespace, name = skill_parts(invoked)
    if name not in PLUGIN_MODE["skills"] or (namespace and namespace != PLUGIN_MODE["name"]):
        return None
    repo = git_tree(resolve(data.get("cwd") or os.getcwd(), os.getcwd()))
    with state_txn(data, write=True) as state:
        state.setdefault("active_skills", [])
        if name not in state["active_skills"]:
            state["active_skills"].append(name)
        if repo and repo not in state["repos"]:
            state["repos"].append(repo)
    write_marker(data)  # a failure here refuses the skill (run_event): activation is always recorded
    return repo


def cmd_record(data, rules):
    prompt = (data.get("prompt") or "").strip()
    if PLUGIN_MODE["on"]:
        slash = re.match(r"/([\w.:-]+)", prompt)
        if slash:
            repo = activate(data, slash.group(1))
            if repo:
                say(f"[spec-approval-gate K22] {repo} is gated for this session: until its plan is "
                    "approved, only ai-planning/ and .claude/ may be written (not .claude/settings*.json "
                    "or .claude/hooks/).")
        if not session_active(data):
            return
    words = "|".join(re.escape(w) for w in rules["approval_words"])
    if not re.match(r"(?i)(%s)\b" % words, prompt):
        return
    # The whole reply must be the approval: a bare approval word, or one followed by the plan name, with at
    # most a closing full stop or exclamation mark. "approve? no" or "approved once tests pass" is a
    # conversation, not consent.
    grammar = re.fullmatch(r"(?i)(%s)(?:\s+([A-Za-z0-9][\w.-]*?))?\s*[.!]?" % words, prompt)
    if not grammar:
        say("[spec-approval-gate K22] The reply starts with an approval word but says more than "
            "'approve' or 'approve <plan name>', so nothing was approved. If the user meant to approve, ask "
            "them to reply exactly that; otherwise answer what they said.")
        return
    name = grammar.group(2) or ""
    name = name[:-5] if name.endswith(".plan") else name
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    now = time.time()
    with state_txn(data, write=True) as state:
        # Several skills may register this hook, so one reply arrives several times within milliseconds.
        # A repeat of the same reply later (re-approving an amended plan) is a new reply.
        if any(d == digest and now - t < DUPLICATE_WINDOW_S for d, t in state["handled"]):
            return
        state["handled"] = [[d, t] for d, t in state["handled"] if now - t < DUPLICATE_WINDOW_S] + [[digest, now]]
        pending = []
        for repo in state["repos"]:
            plan = current_plan(repo, state)
            if plan and not approval_status(repo, state)[0]:
                pending.append((repo, plan))
        if name:
            named = [(r, p) for r, p in pending if name in {os.path.basename(p)[:-5], os.path.basename(r)}]
            if len(named) != 1:
                known = ", ".join(f"{os.path.basename(p)[:-5]} ({r})" for r, p in pending) or "none"
                say(f"[spec-approval-gate K22] '{name}' does not name exactly one plan awaiting approval "
                    f"(awaiting: {known}). Nothing was approved.")
                return
            pending = named
        elif len(pending) > 1:
            listing = "; ".join(f"{os.path.basename(p)} in {r}" for r, p in pending)
            say(f"[spec-approval-gate K22] Several plans await approval ({listing}). Nothing was "
                "approved: ask the user to reply 'approve <plan name>'.")
            return
        if not pending:
            say("[spec-approval-gate K22] Approval word received, but no ai-planning/*.plan awaits "
                "approval in this session (a plan becomes approvable when it is written or edited with "
                "Write/Edit here). Nothing was approved.")
            return
        repo, plan = pending[0]
        if not os.path.isfile(plan) or sha256(plan) != state["plans"][plan]["sha256"]:
            say(f"[spec-approval-gate K22] {os.path.relpath(plan, repo)} changed since it was last written "
                "through Write/Edit, so the user has not seen this version. Nothing was approved: re-read "
                "it, present it again and ask.")
            return
        state["approvals"][repo] = {"plan": plan, "sha256": state["plans"][plan]["sha256"]}
        # Plain stdout on UserPromptSubmit is added to Claude's context.
        say(f"[spec-approval-gate K22] Approved {os.path.relpath(plan, repo)} (sha256 "
            f"{state['plans'][plan]['sha256'][:12]}) for {repo}. The plan is frozen from here: editing it, "
            "or writing a newer plan, revokes approval.")


def cmd_guard_edit(data, rules):
    if PLUGIN_MODE["on"] and not session_active(data):
        return
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not path:
        if data.get("tool_name") in EDIT_TOOLS:
            emit_pre_tool("deny", "spec-approval-gate (K22): the edit names no file path, so it cannot be "
                                  "checked; retry with an explicit file_path.")
        return
    cwd = data.get("cwd") or os.getcwd()
    abspath, name = resolve(path, cwd), lexical(path, cwd)
    with state_txn(data, write=True) as state:
        reason = gated(abspath, rules, state) or lexical_guard(name, abspath, rules, state)
        ask = None if reason else (guard_ask(abspath, state) or (name != abspath and guard_ask(name, state)))
        if not reason and abspath.endswith(".plan") and os.path.basename(os.path.dirname(abspath)) == "ai-planning":
            # An edit of a plan revokes its repository's approval now, not when PostToolUse records it: a
            # write running alongside the amendment must not pass under the approval it is ending.
            repo = os.path.dirname(os.path.dirname(abspath))
            if repo in state["approvals"]:
                del state["approvals"][repo]
                state.setdefault("revoking", [])
                if repo not in state["revoking"]:
                    state["revoking"].append(repo)
    if reason:
        emit_pre_tool("deny", reason)
    elif ask:
        emit_pre_tool("ask", ask)


def cmd_guard_bash(data, rules):
    if PLUGIN_MODE["on"] and not session_active(data):
        return
    command = (data.get("tool_input") or {}).get("command") or ""
    if not isinstance(command, str):
        raise ValueError("tool_input.command is not a string")
    cwd0 = data.get("cwd") or os.getcwd()
    denials, asks = [], []
    with state_txn(data, write=True) as state:
        unknown = list(dict.fromkeys([resolve(cwd0, os.getcwd())] + list(state["repos"])))
        side_rules = [r for r in rules["command_rules"] if r["decision"] == "write"]
        segments = list(analyse(command, cwd0, unknown_dirs=unknown, side_rules=side_rules))
        touches = touches_gate(command, segments)
        if touches:
            denials.append(touches)
        # A gated skill this session started whose rules file has gone (a plugin update, a file moved by hand)
        # is as unknown as a broken one.
        broken = list(rules.get("broken") or []) + [
            f"{os.path.join(PLUGIN_MODE['skills_dir'], s, 'gate_rules.json')} (missing)"
            for s in state.get("active_skills", []) if PLUGIN_MODE["on"] and s not in PLUGIN_MODE["skills"]]
        if broken:
            asks.append("spec-approval-gate (K22): a skill's gate rules file cannot be read ("
                        + "; ".join(broken) + "), so the gate cannot tell whether this command deploys, "
                        "changes live state or installs a dependency. Every shell command asks until the file is "
                        "fixed. Approve only if you know what this command does.")
        # Paths an earlier segment of this command may turn into a link (ln, cp -P, mv, tar -x, ...) inside a
        # project that is not approved: the analysis sees the file system before the command runs, so a later
        # write through such a path cannot be resolved now.
        made = []
        for words, targets, cwd in segments:
            notes, before = [], len(denials)
            for rule in rules["command_rules"]:
                if rule_matches(rule, words):
                    msg = f"spec-approval-gate rule '{rule['id']}': {rule['message']}"
                    # A write rule decides nothing itself: analyse() added what it writes to the targets, which
                    # are judged like any write below; its message explains a denial they cause.
                    (notes if rule["decision"] == "write" else denials if rule["decision"] == "deny"
                     else asks).append(msg)
            prog = os.path.basename(words[0]) if words else ""
            link = symlink_reason(prog, words, cwd, rules, state)
            if link:
                denials.append(link)
            later = []
            for target in targets:
                if target.startswith(UNRESOLVED):
                    # Where it writes is unknown: count it as a write at the working directory, and at the
                    # repository holding it (an exempt working directory does not make `../x` exempt).
                    here = resolve(cwd, cwd)
                    home = project_repo(here, state)
                    reason = gated(here, rules, state) or (home and gated(home, rules, state, explicit=False))
                    if reason:
                        denials.append(reason + f" (the shell command writes {target[len(UNRESOLVED):]}, which "
                                                "the gate cannot resolve, so it counts as a write at the "
                                                "working directory and its repository)")
                    continue
                explicit = not target.startswith(SYNTHETIC)
                word = target if explicit else target[len(SYNTHETIC):]
                abspath, name = resolve_shell(word, cwd), lexical(word, cwd, shell_word=True)
                through = [m for m in made if under(name, m) or under(abspath, m)]
                if through:
                    denials.append(f"spec-approval-gate (K22): '{literal(word)}' lies under {through[0]}, which an "
                                   "earlier part of this command may turn into a link, and the project's plan is not "
                                   "approved. Run the commands as separate Bash calls so each write is checked "
                                   "against the file system it really meets.")
                    continue
                if explicit and abspath.endswith(".plan") and \
                        os.path.basename(os.path.dirname(abspath)) == "ai-planning" and project_repo(abspath, state):
                    denials.append(f"spec-approval-gate (K22): write plans with Write/Edit, not the shell, so the "
                                   f"gate records the version the user sees ('{target}')")
                    continue
                reason = gated(abspath, rules, state, explicit) or lexical_guard(name, abspath, rules, state)
                if reason:
                    denials.append(reason + f" (the shell command writes '{literal(target.lstrip(SYNTHETIC))}')")
                elif explicit and (guard_ask(abspath, state) or (name != abspath and guard_ask(name, state))):
                    asks.append(guard_ask(abspath, state) or guard_ask(name, state))
                if prog in LINK_MAKERS:
                    repo = project_repo(abspath, state)
                    if repo and not approval_status(repo, state)[0]:
                        later += [name, abspath]
            made += later
            if len(denials) > before:
                denials.extend(notes)
    if denials:
        emit_pre_tool("deny", " | ".join(dict.fromkeys(denials)))
    elif asks:
        emit_pre_tool("ask", " | ".join(dict.fromkeys(asks)))


def cmd_plan_changed(data, rules):
    path = (data.get("tool_input") or {}).get("file_path")
    if not path:
        return
    abspath = resolve(path, data.get("cwd") or os.getcwd())
    if not abspath.endswith(".plan") or os.path.basename(os.path.dirname(abspath)) != "ai-planning":
        return
    repo = os.path.dirname(os.path.dirname(abspath))
    if git_tree(abspath) != repo or not os.path.isfile(abspath):
        return
    if PLUGIN_MODE["on"] and not session_active(data):
        return
    with state_txn(data, write=True) as state:
        revoking = state.get("revoking", [])
        was_approved = repo in state["approvals"] or repo in revoking
        state["revoking"] = [r for r in revoking if r != repo]
        state["seq"] += 1
        state["plans"][abspath] = {"repo": repo, "seq": state["seq"], "sha256": sha256(abspath)}
        if repo not in state["repos"]:
            state["repos"].append(repo)
        revoked = was_approved and not approval_status(repo, state)[0]
    if revoked:
        emit_context("PostToolUse",
                     f"[spec-approval-gate K22] {os.path.relpath(abspath, repo)} changed after approval, so "
                     "approval is revoked. If this is an amendment the user asked for, or one the work needs "
                     "(new files, a dependency, a scope change), present the revised plan and ask for "
                     "approval again. A judgment call that changes none of those belongs in the ledger, "
                     "not the plan.")


# --------------------------------------------------------------------------------- shell analysis

# The word after << (or <<-): the here-document delimiter, quoted or not. A quoted delimiter means the body
# is not expanded; an unquoted one means $(...) and `...` in the body run.
HEREDOC_WORD_RE = re.compile(r"(-?)[ \t]*((?:'[^'\n]*'|\"[^\"\n]*\"|\\.|[^\s;&|()<>'\"\\])+)")
# How deep bash -c, eval, env -S, here-documents fed to a shell and substitutions are followed. Deeper
# nesting is a write the analysis cannot resolve.
MAX_DEPTH = 6
TOO_DEEP = "\x01commands nested deeper than the gate follows"


def scan_heredocs(command):
    """Split here-documents out of a command: (the command without their bodies, [(body, quoted)]).

    A << inside quotes, a comment, a here-string (<<<) or arithmetic ($((a<<b)), ((x<<2))) starts no
    here-document; a purely numeric word after << is taken as arithmetic too. A body ends at the line that
    is exactly the delimiter (tabs stripped for <<-), as in the shell."""
    lines = command.split("\n")
    out, bodies, quote, i = [], [], None, 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        pending, j, n, arith = [], 0, len(line), 0
        while j < n:
            ch = line[j]
            if quote == "'":
                quote = None if ch == "'" else quote
                j += 1
                continue
            if ch == "\\":
                j += 2
                continue
            if quote == '"':
                quote = None if ch == '"' else quote
                j += 1
                continue
            if ch in "'\"":
                quote, j = ch, j + 1
                continue
            if ch == "#" and (j == 0 or line[j - 1] in " \t;&|("):
                break
            if line.startswith("$((", j) or (line.startswith("((", j) and (j == 0 or line[j - 1] in " \t;&|(")):
                arith, j = arith + 1, j + (3 if ch == "$" else 2)
                continue
            if arith and line.startswith("))", j):
                arith, j = arith - 1, j + 2
                continue
            if line.startswith("<<<", j):
                j += 3
                continue
            if line.startswith("<<", j) and not arith:
                m = HEREDOC_WORD_RE.match(line, j + 2)
                if m and not m.group(2).isdigit():
                    word = m.group(2)
                    pending.append((re.sub(r"['\"\\]", "", word), bool(re.search(r"['\"\\]", word)),
                                    bool(m.group(1))))
                    j = m.end()
                    continue
            j += 1
        for delim, quoted, tabs in pending:
            body = []
            while i < len(lines) and (lines[i].lstrip("\t") if tabs else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append(("\n".join(body), quoted))
    return "\n".join(out), bodies


def strip_heredocs(command):
    """Drop here-document bodies so their text is not mistaken for commands."""
    return scan_heredocs(command)[0]


OPERATORS = ["&&", "||", ";;", "|&", "&>>", "&>", ">>", ">|", "<<<", "<<", "<>", ";", "&", "|", "(", ")",
             "<", ">"]
# Options of wrapper programs that take a value (env -u NAME, nice -n 10, sudo -u user, xargs -I {}).
WRAPPER_OPTS_WITH_VALUE = {"-u", "-n", "-g", "-p", "-C", "--chdir", "-I", "-P", "-L", "-s", "-d", "-E",
                           "--unset", "--user", "--group"}
SYNTHETIC = "\x00"  # prefix of a "somewhere under this directory" target (formatters, git, inline code)
UNRESOLVED = "\x01"  # prefix of a write target the analysis cannot resolve; the rest describes it
EXISTING = "\x03"  # prefix of a candidate written only if it names an existing file once expanded (sed -i)
# Text the shell takes literally: a $ or ~ inside single quotes, a ~ inside double quotes, a backslash-escaped
# $ or ~. shlex drops the quotes, so such characters travel as sentinels and are never expanded.
Q_DOLLAR, Q_TILDE = "\x04", "\x05"
# A backslash-escaped operator character (find's \( \) \;, echo \>) is a literal word, not an operator.
# shlex drops the backslash and loses that distinction, so such characters travel as sentinels.
ESCAPES = {";": "S", "&": "A", "|": "P", "(": "L", ")": "R", "<": "I", ">": "O"}
UNESCAPES = {v: k for k, v in ESCAPES.items()}
ESCAPE_RE = re.compile(r"\x02([SAPLRIO])\x02")
VAR_DEFAULT_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?[-=]([^}]*)\}")
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
# What is still dynamic after expansion: a variable, a parameter, a substitution. A lone $ is literal.
DYNAMIC_RE = re.compile(r"\$[A-Za-z_{(0-9@*#?$!-]|`")
ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
GLOB_LIMIT = 500  # more matches than this: the pattern's directory is checked instead
WALK_LIMIT = 2000  # entries searched for symlinks under a directory a recursive copy writes into


def loc(directory="."):
    return SYNTHETIC + directory


def unescape(token):
    return ESCAPE_RE.sub(lambda m: UNESCAPES[m.group(1)], token)


def literal(text):
    """The text as the shell passes it on: quoted $ and ~ restored."""
    return text.replace(Q_DOLLAR, "$").replace(Q_TILDE, "~")


def resolve_shell(path, cwd):
    """resolve() for a shell word: only an unquoted leading ~ is the home directory."""
    expanded = literal(os.path.expanduser(path))
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd, expanded)
    return os.path.realpath(expanded)


def protect(text):
    """Mark the $ and ~ characters the shell takes literally (see Q_DOLLAR)."""
    out, quote, i, n = [], None, 0, len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            quote = None if ch == "'" else quote
            out.append(quoted_char(ch, dollar=True) if quote else ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            out.append({"$": Q_DOLLAR, "~": Q_TILDE}.get(nxt) or text[i:i + 2])
            i += 2
            continue
        if quote == '"':
            quote = None if ch == '"' else quote
            out.append(quoted_char(ch, dollar=False) if quote else ch)
            i += 1
            continue
        if ch in "'\"":
            quote = ch
        out.append(ch)
        i += 1
    return "".join(out)


def quoted_char(ch, dollar):
    """A character inside quotes as the lexer should see it: $ (single quotes only) and ~ as literal sentinels,
    an operator character (printf '%s' '>' file) as the escaped-literal sentinel, never an operator."""
    if ch == "~" or (dollar and ch == "$"):
        return Q_TILDE if ch == "~" else Q_DOLLAR
    if ch in ESCAPES:
        return "\x02%s\x02" % ESCAPES[ch]
    return ch


def expand(word, cwd, variables):
    """Expand $NAME, ${NAME} and ${NAME:-default} from the command's own assignments, $PWD (the
    segment's directory) and the hook's environment. Unknown variables are left in place."""
    def lookup(name):
        if name == "PWD":
            return cwd
        return variables[name] if name in variables else os.environ.get(name)

    word = VAR_DEFAULT_RE.sub(lambda m: lookup(m.group(1)) or m.group(2), word)
    return VAR_RE.sub(lambda m: (lambda v: m.group(0) if v is None else v)(lookup(m.group(1) or m.group(2))),
                      word)


def settle(targets, cwd, variables):
    """Expand every write target; one that still holds a variable or a substitution becomes UNRESOLVED."""
    out = []
    for target in targets:
        synthetic = target.startswith(SYNTHETIC)
        body = target[len(SYNTHETIC):] if synthetic else target
        if body.startswith(UNRESOLVED):
            out.append(body)
            continue
        existing = body.startswith(EXISTING)
        body = body[len(EXISTING):] if existing else body
        expanded = expand(body, cwd, variables)
        if DYNAMIC_RE.search(expanded):
            out.append(f"{UNRESOLVED}'{literal(body)}'")
        elif existing:
            # sed -i, perl -i: the arguments that are files once the shell has expanded them are written.
            pattern = os.path.join(cwd, literal(os.path.expanduser(expanded)))
            candidates = sorted(glob.glob(pattern)) if glob.has_magic(literal(expanded)) else [pattern]
            out.extend(c for c in candidates if os.path.isfile(c))
        elif not synthetic and glob.has_magic(literal(expanded)):
            # The shell expands the pattern when the command runs; expand it now (rm -rf * in a directory
            # that holds the project). No match: the shell passes the word unchanged. Too many matches:
            # the directory before the pattern.
            pattern = os.path.join(cwd, literal(os.path.expanduser(expanded)))
            matches = sorted(glob.glob(pattern)) or [expanded]
            if len(matches) > GLOB_LIMIT:
                head = expanded.split("/")
                matches = ["/".join(head[:next(k for k, part in enumerate(head) if glob.has_magic(part))])
                           or ("/" if expanded.startswith("/") else ".")]
            out.extend(matches)
        else:
            out.append((SYNTHETIC if synthetic else "") + expanded)
    return out


def parses(command):
    """Whether the shell lexer can read the command (an unterminated quote cannot be read)."""
    try:
        lexer = shlex.shlex(strip_heredocs(command), posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        list(lexer)
        return True
    except ValueError:
        return False


def scan_substitutions(text, quotes=True):
    """The text of every $(...) and `...` command substitution in text, outside single quotes (quotes=False:
    a here-document body, where quote characters are literal and substitutions run anyway)."""
    out, i, quote, n = [], 0, None, len(text)
    while i < n:
        ch = text[i]
        if quote == "'":
            quote = None if ch == "'" else quote
            i += 1
        elif ch == "\\":
            i += 2
        elif quotes and ch == "'" and quote is None:
            quote, i = "'", i + 1
        elif quotes and ch == '"':
            quote, i = (None if quote == '"' else '"'), i + 1
        elif text.startswith("$(", i) and not text.startswith("$((", i):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(text[i + 2:j - 1] if depth == 0 else text[i + 2:])
            i = j
        elif ch == "`":
            j = text.find("`", i + 1)
            out.append(text[i + 1:] if j < 0 else text[i + 1:j])
            i = n if j < 0 else j + 1
        else:
            i += 1
    return out


def substitutions(command):
    """The text of every command substitution that runs: in the command outside single quotes, and in the
    body of every here-document whose delimiter is unquoted."""
    stripped, bodies = scan_heredocs(command)
    out = scan_substitutions(stripped)
    for body, quoted in bodies:
        if not quoted:
            out += scan_substitutions(body, quotes=False)
    return out


def split_operators(run):
    """Decompose a run of shell punctuation (');', '))&&') into operators, longest first."""
    out, i = [], 0
    while i < len(run):
        for op in OPERATORS:
            if run.startswith(op, i):
                out.append(op)
                i += len(op)
                break
        else:
            out.append(run[i])
            i += 1
    return out


SUBST_PLACEHOLDER = "${__spec_gate_substitution__}"  # never assigned, so a word holding it stays unresolved


def collapse_substitutions(text):
    """Replace every unquoted $(...) and $((...)) in protected text by SUBST_PLACEHOLDER. The lexer splits on
    '(', so /tmp$(printf /..$PWD)/src/a.py arrived as '/tmp$', '(', ... and resolved outside the project while
    the shell writes src/a.py in it; D=$(mktemp -d) stored '$'. The substitution's own commands are analysed
    separately (substitutions()). In protected text a quoted or escaped $ or ( is a sentinel, so every
    literal "$(" left is unquoted."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            out.append(SUBST_PLACEHOLDER)
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def tokenize(text):
    text = re.sub(r"\\([;&|()<>])", lambda m: "\x02%s\x02" % ESCAPES[m.group(1)], protect(text))
    text = collapse_substitutions(text)
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        raw = list(lexer)
    except ValueError:  # unbalanced quotes: fall back to a whitespace split, still conservative
        raw = re.findall(r"[;&|()<>]+|[^\s;&|()<>]+", text)
    tokens = []
    for tok in raw:
        tokens.extend(split_operators(tok) if tok and set(tok) <= set(";&|()<>") else [tok])
    # Rejoin fd redirections split by the lexer: "2", ">&" stays; "2>&1" arrives as "2", ">", "&", "1".
    joined, i = [], 0
    while i < len(tokens):
        if tokens[i] in {">", ">>"} and i + 1 < len(tokens) and tokens[i + 1] == "&":
            joined.append(tokens[i] + "&")
            i += 2
            continue
        joined.append(tokens[i])
        i += 1
    return joined


def parse_segments(command):
    """Split a shell command into segments (words, redirect targets, meta); '(' and ')' become markers. meta:
    the separator before the segment (sep), its here-string operands (herestrings), whether it has a
    here-document (heredoc) or reads a file on standard input (stdin)."""
    tokens = tokenize(strip_heredocs(command).replace("\n", " ; "))
    segments, words, targets, i = [], [], [], 0

    def fresh(sep):
        return {"sep": sep, "herestrings": [], "heredoc": False, "stdin": False}

    meta = fresh(None)
    while i < len(tokens):
        tok = tokens[i]
        if tok in SEPARATORS or tok in {"(", ")"}:
            segments.append((words, targets, meta))
            if tok in {"(", ")"}:
                segments.append(([tok], [], fresh(meta["sep"])))
            words, targets, meta = [], [], fresh(tok if tok in SEPARATORS else meta["sep"])
        elif tok in {">&", ">>&"}:
            # 2>&1 and >&- duplicate or close a descriptor; >&FILE (no number) writes FILE, like &>FILE.
            if i + 1 < len(tokens):
                operand = unescape(tokens[i + 1])
                if not (operand.isdigit() or operand == "-" or re.fullmatch(r"\d+-", operand)) and \
                        operand not in {"/dev/null", "/dev/stdout", "/dev/stderr"}:
                    targets.append(operand)
                i += 1
            if words and words[-1].isdigit():
                words.pop()
        elif tok in REDIRECTS_OUT or tok == "<>":  # <> opens the file read-write and creates it
            if i + 1 < len(tokens):
                target = unescape(tokens[i + 1])
                if target not in {"/dev/null", "/dev/stdout", "/dev/stderr"}:
                    targets.append(target)
                i += 1
            if words and words[-1].isdigit():  # the fd number in 2>file belongs to the redirect
                words.pop()
            meta["stdin"] = meta["stdin"] or tok == "<>"
        elif tok in REDIRECTS_IN:
            if tok == "<<<" and i + 1 < len(tokens):
                meta["herestrings"].append(unescape(tokens[i + 1]))
            meta["heredoc"] = meta["heredoc"] or tok == "<<"
            meta["stdin"] = meta["stdin"] or tok == "<"
            if words and words[-1].isdigit():
                words.pop()
            i += 1
        else:
            words.append(unescape(tok))
        i += 1
    segments.append((words, targets, meta))
    return [s for s in segments if s[0] or s[1]]


def shell_invocation(args):
    """For bash/sh/zsh arguments: (the -c command string or None, whether the shell reads its commands from
    standard input). -c may sit in a cluster (-lc, -ec); -o/-O and --rcfile take a value."""
    has_c, stdin, i = False, False, 0
    while i < len(args):
        arg = args[i]
        if arg in {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}:
            i += 2
            continue
        if arg == "--":
            i += 1
            break
        if re.match(r"^[-+][A-Za-z]+$", arg):
            has_c = has_c or (arg[0] == "-" and "c" in arg)
            stdin = stdin or (arg[0] == "-" and "s" in arg)
            i += 1
            continue
        if arg.startswith("--"):
            i += 1
            continue
        break
    if has_c:
        return (args[i] if i < len(args) else ""), False
    return None, stdin or i >= len(args)


def change_directory(prog, args, cwds, previous, dirstack, unknown):
    """cd, pushd, popd: (the directories the next segment may run in, the previous ones, the stack).

    A cd to a directory that does not exist (yet) may fail, so the old directory stays possible; cd -, a
    variable left unexpanded, popd on an empty stack or pushd +N are unknown, so the session's working
    directory and every registered repository become possible."""
    rest, options = list(args), set()
    while rest and rest[0] in {"-P", "-L", "-e", "-@", "-n"}:
        options.add(rest.pop(0))
    if rest and rest[0] == "--":
        rest.pop(0)
    target = rest[0] if rest else None
    if prog == "popd":
        return (dirstack.pop() if dirstack and target is None else unknown()), cwds, dirstack
    if prog == "pushd" and target is None:
        if not dirstack:
            return unknown(), cwds, dirstack
        top = dirstack.pop()
        dirstack.append(cwds)
        return top, cwds, dirstack
    if target is None:
        new = [os.path.expanduser("~")]
    elif target == "-":
        new = previous or unknown()
    elif re.fullmatch(r"[+-]\d+", target) or DYNAMIC_RE.search(target):
        new = unknown()
    else:
        new = []
        for cwd in cwds:
            where = resolve_shell(target, cwd)
            # cd is logical by default: cd link; cd .. returns to where the link is, not to its target's parent.
            # Both the logical and the physical directory stay possible (cd -P: the physical one only).
            text = literal(os.path.expanduser(target))
            logical = os.path.normpath(text if os.path.isabs(text) else os.path.join(cwd, text))
            new += [where] if "-P" in options else [logical, where]
            if not os.path.isdir(where):
                new.append(cwd)  # the cd fails when it runs and the commands after it stay here
    if prog == "pushd":
        dirstack.append(cwds)
    return list(dict.fromkeys(new)), cwds, dirstack


def analyse(command, cwd, depth=0, variables=None, unknown_dirs=None, side_rules=None):
    """Yield (program words, write targets, cwd) for every simple command, following cd, pushd, popd and
    subshells, bash -c (and -lc), eval, env -S, here-documents and here-strings fed to a shell, find -exec
    bodies, the command strings inline interpreter code runs, and substitutions.

    Every execution layer of a wrapped command (env, uv run --with, npx, python -m) is yielded so the
    command rules see each one; the write targets come with the innermost program. A segment that may run in
    several directories (after a cd that may fail or may not run, cd's logical and physical directory, env -C)
    is yielded once per directory. Words are expanded (variables assigned earlier in the command, $PWD, the
    environment; for a nested shell also the assignments its command line and env pass it) where the shell
    would expand them; write targets that cannot be resolved come back prefixed with UNRESOLVED. side_rules: the
    `write` command rules, whose side-effect writes (side_effect_targets) join the innermost program's targets."""
    variables = dict(variables or {})
    unknown_dirs = list(unknown_dirs or [cwd])
    _stripped, bodies = scan_heredocs(command)
    inline = inline_targets(command)
    inline_runs = inline_commands(command)
    # An unparsable command (an unterminated quote) is still split conservatively, and every one of its
    # segments also counts as a write at its working directory.
    unparsed = [] if parses(command) else [UNRESOLVED + "a command the shell lexer cannot parse"]
    cwds, previous, dirstack, stack, seen = [cwd], None, [], [], [cwd]
    # The directories a cd after && left behind: they come back at the end of the && chain, where the commands
    # run whether or not the cd did (false && cd /tmp; touch x writes x here).
    fallback, prev_heredoc = [], False

    def unknown():
        return list(dict.fromkeys(cwds + unknown_dirs))

    def nested(inner, dirs=None, extra_vars=None):
        dirs = dirs or cwds
        if depth >= MAX_DEPTH:
            for where in dirs:
                yield [], [TOO_DEEP], where
            return
        inner_vars = dict(variables, **(extra_vars or {}))
        for where in dirs:
            yield from analyse(inner, where, depth + 1, inner_vars, unknown_dirs, side_rules)

    for words, targets, meta in parse_segments(command):
        if fallback and meta["sep"] != "&&":
            cwds, fallback = list(dict.fromkeys(cwds + fallback)), []
        piped_heredoc = meta["sep"] in {"|", "|&"} and prev_heredoc
        prev_heredoc = meta["heredoc"]
        if words == ["("]:
            stack.append((cwds, previous, list(dirstack)))
            continue
        if words == [")"]:
            if stack:
                cwds, previous, dirstack = stack.pop()
            continue
        guarded_by_keyword = bool(words) and words[0] in {"then", "else", "elif", "do"}
        words = [expand(w, cwds[0], variables) for w in words]
        layers = program_layers(words)
        if not layers:  # only assignments (f=src/a.py): later words of the command can expand them
            for word in words:
                match = ASSIGNMENT_RE.match(word)
                if match:
                    variables[match.group(1)] = match.group(2)
        env_vars, here = passed_environment(words, layers), cwds
        chdir = wrapper_chdir(layers)
        if chdir is not None:
            here = list(dict.fromkeys(cwd if DYNAMIC_RE.search(chdir) else resolve_shell(chdir, cwd)
                                      for cwd in cwds))
            if DYNAMIC_RE.search(chdir):
                here = unknown()
        for layer in layers[:-1]:
            for where in here:
                yield [literal(w) for w in layer], [], where
        words = layers[-1] if layers else []
        if words and words[0] == "export":
            for word in words[1:]:
                match = ASSIGNMENT_RE.match(word)
                if match:
                    variables[match.group(1)] = match.group(2)
        shown = [literal(w) for w in words]
        prog = os.path.basename(shown[0]) if shown else ""
        extra = []
        if words and DYNAMIC_RE.search(words[0]):
            extra.append(UNRESOLVED + f"the program '{shown[0]}', which the gate cannot resolve")
        if prog in {"cd", "pushd", "popd"}:
            # a redirection on cd writes before the directory changes
            for where in here:
                yield shown, settle(targets, where, variables) + unparsed, where
            before = list(cwds)
            cwds, previous, dirstack = change_directory(prog, words[1:], cwds, previous, dirstack, unknown)
            if meta["sep"] == "||" or guarded_by_keyword:
                cwds = list(dict.fromkeys(cwds + before))  # the cd may not run at all
            elif meta["sep"] == "&&":
                fallback = list(dict.fromkeys(fallback + before))
            seen.extend(cwds)
            continue
        if prog in SHELLS:
            inner, reads_stdin = shell_invocation(words[1:])
            if inner is not None:
                for where in here:
                    yield shown, settle(targets, where, variables) + unparsed, where
                yield from nested(literal(inner), here, env_vars)
                continue
            if reads_stdin:
                # What this shell reads: its own here-strings, its own here-document (or one piped into it from
                # the segment before); a file, a pipe from any other command or nothing visible is unknown.
                fed = False
                for text in meta["herestrings"]:
                    yield from nested(literal(text), here, env_vars)
                    fed = True
                if bodies and (meta["heredoc"] or piped_heredoc):
                    for body, _quoted in bodies:
                        yield from nested(body, here, env_vars)
                    fed = True
                if not fed or meta["stdin"]:
                    extra.append(UNRESOLVED + f"the commands {prog} reads from its standard input")
        if prog == "eval":
            for where in here:
                yield shown, settle(targets, where, variables) + unparsed, where
            yield from nested(" ".join(shown[1:]), here, env_vars)
            continue
        if prog == "find":
            for body in find_exec_bodies(shown[1:]):
                yield from nested(" ".join(shlex.quote(w) for w in body), here)
        if is_interpreter(prog):
            extra += inline
            for text in inline_runs:
                yield from nested(text, here)
        if any(os.path.basename(layer[0]) == "xargs" for layer in layers[:-1]) and writes_files(words):
            extra.append(UNRESOLVED + f"the arguments xargs passes to {prog}")
        for where in here:
            side = side_effect_targets(side_rules, layers, words, where, dict(variables, **env_vars)) \
                if side_rules else []
            yield shown, settle(targets + write_targets(words, where) + extra + side, where, variables) + unparsed, \
                where
    # $(...) and `...` run too, quoted or not; where they run is not tracked, so every directory the
    # command visits is assumed.
    subs = substitutions(command)
    if subs and depth >= MAX_DEPTH:
        yield [], [TOO_DEEP], cwd
    elif subs:
        for inner in subs:
            for where in dict.fromkeys(seen + fallback):
                yield from analyse(inner, where, depth + 1, variables, unknown_dirs, side_rules)


def passed_environment(words, layers):
    """The variables a command line passes to its program's environment: leading assignments
    (HOME=x bash -c ...) and env's NAME=VALUE arguments."""
    out = {}
    for word in words:
        match = ASSIGNMENT_RE.match(word)
        if not match:
            break
        out[match.group(1)] = match.group(2)
    for layer in layers[:-1]:
        if os.path.basename(layer[0]) == "env":
            for word in layer[1:]:
                match = ASSIGNMENT_RE.match(word)
                if match:
                    out[match.group(1)] = match.group(2)
    return out


def wrapper_chdir(layers):
    """The directory env -C/--chdir runs its program in, or None."""
    for layer in layers[:-1]:
        if os.path.basename(layer[0]) != "env":
            continue
        args = layer[1:]
        for i, arg in enumerate(args):
            if arg in {"-C", "--chdir"} and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith("--chdir="):
                return arg.split("=", 1)[1]
            if arg.startswith("-C") and len(arg) > 2:
                return arg[2:]
            if not arg.startswith("-") and not ASSIGNMENT_RE.match(arg):
                break
    return None


def find_exec_bodies(args):
    """The commands find -exec/-execdir/-ok/-okdir runs: the words up to ; or +."""
    out, i = [], 0
    while i < len(args):
        if args[i] in FIND_EXEC:
            j = i + 1
            while j < len(args) and args[j] not in {";", "+"}:
                j += 1
            if j > i + 1:
                out.append(args[i + 1:j])
            i = j
        i += 1
    return out


# Inline interpreter code that runs a command: os.system("..."), subprocess.run([...]), execSync('...').
INLINE_RUN_RE = re.compile(r"(?:\bos\.(?:system|popen|exec\w*|spawn\w*)|\bsubprocess\.\w+|\b(?:Popen|check_output|"
                           r"check_call|execSync|execFileSync|spawnSync|spawn|exec|execFile|system)|IO\.popen)\s*\(\s*"
                           r"(\[[^\]]*\]|'[^'\n]*'|\"[^\"\n]*\")")
QUOTED_RE = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")


def inline_commands(command):
    """The command lines inline interpreter code runs, when they are literal strings or lists of strings, so
    command rules see them (python3 -c 'import os; os.system("terraform apply")')."""
    if not re.search(r"(?:^|[;&|(]\s*|\s)(?:\S*/)?(python[23]?(\.\d+)?|node|ruby|perl)\b", command):
        return []
    out = []
    for m in INLINE_RUN_RE.finditer(command):
        arg = m.group(1)
        if arg.startswith("["):
            parts = [a or b for a, b in QUOTED_RE.findall(arg)]
            if parts:
                out.append(" ".join(shlex.quote(p) for p in parts))
        else:
            out.append(arg[1:-1])
    return out


def is_interpreter(prog):
    return prog in INTERPRETERS or re.fullmatch(r"python[23]?(\.\d+)?", prog) is not None


def in_place(prog, args):
    """Whether sed/perl/ruby edit their file arguments in place (-i, -i.bak, --in-place=SUF, -pi, -0pi)."""
    if prog in {"sed", "gsed"}:
        return any(re.match(r"^-[A-Za-z]*i", a) or a.startswith("--in-place") for a in args)
    if prog in {"perl", "ruby"}:
        return any(re.match(r"^-(?![IMmeExdCV-])[0-9A-Za-z.]*?i", a) for a in args)
    return False


def writes_files(words):
    """Whether the program writes the files named by its arguments (so arguments from xargs or find
    -exec are written)."""
    prog = os.path.basename(words[0]) if words else ""
    if prog in WRITE_ALL_ARGS | WRITE_AFTER_FIRST_ARG | WRITE_LAST_ARG:
        return True
    if prog in IN_PLACE_EDITORS:
        return in_place(prog, words[1:])
    if prog in AWKS:
        return any(a in {"--inplace", "inplace"} for a in words[1:])
    return False


def inline_targets(command):
    """Targets of inline interpreter code (-c, -e or a here-document) that writes files or runs commands:
    its path literals, and its working directory."""
    if not re.search(r"(?:^|[;&|(]\s*|\s)(?:\S*/)?(python[23]?(\.\d+)?|node|ruby|perl)\b", command):
        return []
    if not re.search(r"\s-[A-Za-z]*(c|e)\s|<<", command) or not INLINE_WRITE_RE.search(command):
        return []
    return [loc()] + [m for m in PATH_LITERAL_RE.findall(command) if not re.match(r"^[\w.+-]+://", m)]


def touches_gate(command, segments):
    """A denial when the command runs the gate's own entrypoint (which could record a forged approval) or
    names its state directory; else None. The gate's code may still be read (cat, git diff)."""
    data_root = os.environ.get("CLAUDE_PLUGIN_DATA") or "\0"
    state_dirs = {STATE_DIR, os.path.join(data_root, "spec-approval-gate"),
                  os.path.join(data_root, "review-isolation")}
    state_dirs |= set(STATE_NAME_ROOTS)
    texts = [command] + [" ".join(w) for w, _t, _c in segments] + [t for _w, ts, _c in segments for t in ts]
    if any(d in text for d in state_dirs for text in texts) or STATE_ENV_RE.search(command) or any(
            STATE_ENV_RE.search(w) for ws, _t, _c in segments for w in ws):
        return (f"spec-approval-gate (K22): the command names the gate's state directory ({STATE_DIR}), the "
                "isolation hook's reviewer registrations or the activation records, or sets the variable that "
                "locates them, which only the hooks themselves read and write.")
    runners = SHELLS | {"source", ".", "exec", HOOK_BASENAME, DISPATCHER_BASENAME}
    names = (HOOK_BASENAME, HOOK_FILE, DISPATCHER_BASENAME, DISPATCHER_FILE)
    named = any(n in command for n in names)
    for words, _targets, cwd in segments:
        # The words as the shell passes them on (quotes joined, variables expanded), and what each names on
        # disk: spec-approval-''gate.py, "$g-gate.py" and a symlink to the script are all the script.
        named = named or any(any(n in w for n in names) or (
            ("/" in w or w.endswith(".py")) and resolve_shell(w, cwd) in (HOOK_FILE, DISPATCHER_FILE))
            for w in words)
    if named:
        for words, _targets, _cwd in segments:
            prog = os.path.basename(words[0]) if words else ""
            if prog in runners or is_interpreter(prog):
                return ("spec-approval-gate (K22): the command runs the approval gate's own script, whose "
                        "events only Claude Code may send; an approval comes only from the user's reply.")
    return None


def program_layers(words):
    """Every execution layer of a command: after assignments, after each wrapper (env -S splits its
    string), after each runner (npx, uvx, uv run, npm exec, pnpm dlx) and after python -m. The last layer is
    the real program."""
    def drop_assignments(seq):
        # Leading assignments, the reserved words that precede a command (then rm ..., do touch ...), and a
        # function definition's `function NAME` (its body is the command analysed here).
        while seq and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seq[0]) or seq[0] in RESERVED_WORDS or
                       seq[0] == "function"):
            seq = seq[2:] if seq[0] == "function" else seq[1:]
        return seq

    out = drop_assignments(list(words))
    layers = [out] if out else []
    changed = True
    while out and changed:
        changed = False
        base = os.path.basename(out[0])
        if base in WRAPPERS:
            rest, split = out[1:], None
            while rest and (rest[0].startswith("-") and rest[0] != "--" or
                            re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[0])):
                opt = rest[0]
                if base == "env" and opt in {"-S", "--split-string"}:
                    split, rest = (rest[1] if len(rest) > 1 else ""), rest[2:]
                    break
                if base == "env" and (opt.startswith("--split-string=") or (opt.startswith("-S") and len(opt) > 2)):
                    split, rest = opt.split("=", 1)[1] if opt.startswith("--") else opt[2:], rest[1:]
                    break
                rest = rest[2:] if opt in WRAPPER_OPTS_WITH_VALUE else rest[1:]
            if split is not None:
                try:
                    rest = shlex.split(literal(split)) + rest
                except ValueError:
                    rest = ["`env -S string the gate cannot split`"] + rest
            rest = drop_assignments(rest)
            if rest and rest[0] == "--":
                rest = rest[1:]
            out, changed = rest, True
        elif base in RUNNERS or (base in {"uv", "npm", "pnpm"} and len(out) > 1 and out[1] in {"run", "exec", "dlx"}
                                 and not (base in {"npm", "pnpm"} and out[1] == "run")):
            rest = out[1:] if base in RUNNERS else out[2:]
            while rest and rest[0].startswith("-") and rest[0] != "--":
                rest = rest[2:] if rest[0] in {"--with", "--from", "--package", "-p", "--python", "--with-requirements"} \
                    else rest[1:]
            if rest and rest[0] == "--":
                rest = rest[1:]
            out, changed = rest, bool(rest)
        elif len(out) > 2 and is_interpreter(base) and out[1] == "-m":
            out, changed = out[2:], True
        if changed and out:
            layers.append(out)
    return layers


def program_words(words):
    """The real program of a command (the last execution layer)."""
    layers = program_layers(words)
    return layers[-1] if layers else []


def non_options(args):
    """The operands: words that are not options, and every word after `--` (touch -- -name)."""
    out = []
    for i, arg in enumerate(args):
        if arg == "--":
            return out + list(args[i + 1:])
        if not arg.startswith("-"):
            out.append(arg)
    return out


def option_value(args, *names):
    """The value of the first of the named options: `-t DIR`, `--opt=VALUE`, and a one-letter option's attached
    value (`-tDIR`)."""
    for i, arg in enumerate(args):
        if arg == "--":
            break
        for name in names:
            if arg == name and i + 1 < len(args):
                return args[i + 1]
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
            if len(name) == 2 and name[0] == "-" and name[1] != "-" and arg.startswith(name) and len(arg) > 2:
                return arg[2:]
    return None


GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}


def git_targets(args, cwd="."):
    """git writes anywhere in its work tree for a writing subcommand: --work-tree, else the work tree that
    holds the directory git runs in (-C, else the working directory), so git -C ai-planning restore ../x writes
    the repository, not ai-planning/. Global options and their values come before the subcommand."""
    where, work, i = None, None, 0
    while i < len(args) and args[i].startswith("-"):
        arg = args[i]
        name, eq, value = arg.partition("=")
        if arg in GIT_OPTS_WITH_VALUE:
            value = args[i + 1] if i + 1 < len(args) else ""
            if arg == "-C":
                where = value if where is None or os.path.isabs(value) else os.path.join(where, value)
            elif arg == "--work-tree":
                work = value
            i += 2
            continue
        if eq and name == "--work-tree":
            work = value
        i += 1
    rest = args[i:]
    sub, tail = (rest[0] if rest else ""), non_options(rest[1:])
    if sub == "stash" and tail[:1] in (["list"], ["show"]):
        return []
    if sub == "worktree" and tail[:1] == ["list"]:
        return []
    if sub == "submodule" and (not tail or tail[0] in {"status", "summary"}):
        return []
    if sub not in GIT_WRITERS:
        return []
    if work:
        return [loc(work)]
    return [loc(work_tree_root(resolve_shell(where or ".", cwd)))]


def work_tree_root(directory):
    """The nearest enclosing directory holding .git (the work tree's top), else the directory itself."""
    probe = directory
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return directory
        probe = parent


def tar_targets(args):
    """tar -x (and x, --extract) writes under -C/--directory, else the working directory; tar -c/-r/-u
    writes its -f archive."""
    mode, archive, where, stdout, command, i = None, None, None, False, False, 0
    while i < len(args):
        arg = args[i]
        if arg in {"-C", "--directory", "-f", "--file"}:
            value = args[i + 1] if i + 1 < len(args) else None
            if arg in {"-C", "--directory"}:
                where = value
            else:
                archive = value
            i += 2
            continue
        name, eq, value = arg.partition("=")
        if eq and name in {"--directory", "--file"}:
            where, archive = (value, archive) if name == "--directory" else (where, value)
        elif arg in {"--extract", "--get"}:
            mode = "x"
        elif arg in {"--create", "--append", "--update", "--concatenate", "--delete"}:
            mode = mode or "c"
        elif arg == "--to-stdout":
            stdout = True
        elif arg == "--to-command" or name == "--to-command":
            command = True
        elif re.match(r"-[A-Za-z]", arg) or (i == 0 and re.fullmatch(r"[A-Za-z]+", arg)):
            # A cluster: -xzf ARCHIVE, -xf/ARCHIVE (the rest of the word is f's value), -xC/DIR; old-style xzf.
            cluster = arg[1:] if arg.startswith("-") else arg
            for k, letter in enumerate(cluster):
                if letter == "x":
                    mode = "x"
                elif letter in "cruA":
                    mode = mode or "c"
                elif letter == "O":
                    stdout = True
                elif letter in "fC":
                    value = cluster[k + 1:] if arg.startswith("-") and cluster[k + 1:] else None
                    if value is None and i + 1 < len(args):
                        value = args[i + 1]
                        i += 1
                    if letter == "f":
                        archive = value
                    else:
                        where = value
                    break
                elif not letter.isalpha():
                    break
        i += 1
    if mode == "x" and command:
        return [UNRESOLVED + "the command tar --to-command runs for each member"]
    if mode == "x" and stdout:
        return []  # -O/--to-stdout writes the members to standard output
    if mode == "x":
        return [loc(where or ".")]
    if mode == "c" and archive and archive != "-":
        return [archive]
    return []


def copy_targets(prog, args, sub, cwd):
    """cp, mv, ln, install, rsync: the destination, and when it is an existing directory, each source's
    name inside it (and, for a recursive copy into an existing subdirectory, every symlink under it, which
    the copy would write through). mv also writes its sources (removed from where they were); a hard link
    (ln without -s) makes its source writable under another name, so it counts as a write to the source."""
    target_dir = option_value(args, "-t", "--target-directory") if prog != "rsync" else None
    if target_dir:
        sources = list(sub)
        if target_dir in sources:
            sources.remove(target_dir)
        dest = target_dir
    elif len(sub) >= 2:
        sources, dest = sub[:-1], sub[-1]
    else:
        sources, dest = sub, None
    hard = prog == "ln" and not any(a == "--symbolic" or re.match(r"^-[A-Za-z]*s", a) for a in args)
    out = []
    if dest is None:
        if prog == "ln" and sources:  # ln TARGET: a link named after it in the working directory
            out.append(os.path.basename(literal(sources[0]).rstrip("/")))
    else:
        out.append(dest)
        dest_abs = resolve_shell(dest, cwd)
        recursive = prog in {"rsync", "mv"} or any(a in {"-r", "-R", "--recursive", "-a", "--archive"} or
                                                    re.match(r"^-[A-Za-z]*[rRa]", a) for a in args)
        if not DYNAMIC_RE.search(dest) and os.path.isdir(dest_abs):
            for src in sources:
                name = os.path.basename(literal(src).rstrip("/"))
                if DYNAMIC_RE.search(src) or not name:
                    continue
                inside = dest_abs if prog == "rsync" and literal(src).endswith("/") else os.path.join(dest_abs, name)
                out.append(inside)
                if recursive and os.path.isdir(inside) and not os.path.islink(inside):
                    out.extend(symlinks_under(inside))
    if prog == "mv" or hard:
        out.extend(sources)
    return out


# Writers that can leave a symlink where they write (ln, a copy or move of a link, an extracted archive, a git
# checkout); a later write in the same command may go through it (see cmd_guard_bash).
LINK_MAKERS = {"ln", "cp", "mv", "rsync", "tar", "unzip", "git"}


def symlink_reason(prog, words, cwd, rules, state):
    """A denial for `ln -s TARGET LINK` whose TARGET may not be written now (a project file before approval, the
    gate's own files): writing through the new link would reach it, in this command or a later one."""
    args = words[1:]
    if prog != "ln" or not any(a == "--symbolic" or re.match(r"^-[A-Za-z]*s", a) for a in args):
        return None
    sub = non_options(args)
    target_dir = option_value(args, "-t", "--target-directory")
    if not sub or (len(sub) < 2 and not target_dir):
        dest = "."
    else:
        dest = target_dir or sub[-1]
    sources = [s for s in (sub if target_dir or len(sub) < 2 else sub[:-1]) if s != target_dir]
    where = resolve_shell(dest, cwd)
    for src in sources:
        text = literal(os.path.expanduser(src))
        if DYNAMIC_RE.search(src):
            continue  # the write through it is checked when it happens, against the real file system
        base = where if os.path.isdir(where) else os.path.dirname(lexical(dest, cwd, shell_word=True))
        pointee = os.path.realpath(text if os.path.isabs(text) else os.path.join(base, text))
        reason = gated(pointee, rules, state, explicit=False)
        if reason:
            return (f"spec-approval-gate (K22): the symbolic link to '{literal(src)}' would lead to {pointee}, which "
                    "may not be written now, so creating it is refused: " + reason)
    return None


def symlinks_under(directory):
    """The symlinks under a directory (not followed), at most WALK_LIMIT entries searched."""
    found, count = [], 0
    for root, dirs, files in os.walk(directory):
        for name in dirs + files:
            count += 1
            path = os.path.join(root, name)
            if os.path.islink(path):
                found.append(path)
            if count >= WALK_LIMIT:
                return found + [loc(directory)]
    return found


def write_targets(words, cwd):
    """Paths a simple command writes, relative to cwd; '.' stands for 'somewhere under cwd'."""
    if not words:
        return []
    prog, args = os.path.basename(words[0]), words[1:]
    sub = non_options(args)
    if prog in WRITE_ALL_ARGS - {"mv"}:
        return sub
    if prog in WRITE_AFTER_FIRST_ARG:
        # chmod --reference=FILE takes the mode from FILE: every operand is written
        return sub if any(a.startswith("--reference") for a in args) else sub[1:]
    if prog == "install" and ("-d" in args or "--directory" in args):
        return sub  # install -d DIR...: every argument is a directory created (a mode value is harmless)
    if prog in WRITE_LAST_ARG or prog == "mv":
        return copy_targets(prog, args, sub, cwd)
    if prog == "find":
        return find_targets(args)
    if prog in AWKS:
        return awk_targets(args, cwd)
    if prog in MAVEN | GRADLE:
        return build_tool_targets(prog, args)
    if prog in IN_PLACE_EDITORS and in_place(prog, args):
        # Every argument that is a file once expanded is edited; the script argument is not a file.
        return [EXISTING + a for a in sub]
    if prog == "git":
        return git_targets(args, cwd)
    if prog == "tar":
        return tar_targets(args)
    if prog == "unzip":
        if {"-l", "-v", "-t", "-Z", "-p", "-c", "-z"} & set(args):
            return []
        return [loc(option_value(args, "-d") or ".")]
    if prog in NODE_PKG:
        return ["package.json"] if sub and sub[0] in NODE_PKG_WRITERS else []
    if prog == "uv":
        where = option_value(args, "--directory", "--project") or "."
        return [loc(where)] if sub and sub[0] in UV_WRITERS else []
    if prog in {"pip", "pip3"} and sub[:1] == ["install"]:
        target = option_value(args, "-t", "--target")
        return [target] if target else []
    if prog == "ruff":
        fixing = sub[:1] == ["format"] and "--check" not in args and "--diff" not in args
        fixing = fixing or (sub[:1] == ["check"] and ("--fix" in args or "--unsafe-fixes" in args))
        return (sub[1:] or [loc()]) if fixing else []
    if prog in {"black", "isort", "autopep8"} and "--check" not in args and "--diff" not in args:
        return sub or [loc()]
    if prog in {"prettier", "eslint"} and ({"--write", "-w", "--fix"} & set(args)):
        return [a for a in sub if a not in {"--write", "-w", "--fix"}] or [loc()]
    if prog in {"terraform", "tofu"}:
        where = option_value(args, "-chdir") or "."
        return [loc(where)] if sub[:1] == ["fmt"] and "-check" not in args else []
    if prog in {"curl", "wget"}:
        out = option_value(args, "-o", "--output", "-O", "--output-document")
        return [out] if out and out != "-" else []
    if prog == "aws":
        pos = aws_positionals(args, limit=None)
        if pos[:1] == ["s3"] and len(pos) >= 4 and pos[1] in {"cp", "mv", "sync"}:
            return [p for p in pos[2:4] if not p.startswith("s3://")][-1:]
        if pos[:2] == ["s3api", "get-object"] and len(pos) >= 3:
            return pos[-1:]
        return []
    if prog == "patch":
        return [loc()]
    if prog == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def find_targets(args):
    """find -delete, or -exec/-ok of a writer, writes under its starting points (default '.')."""
    starts = []
    for arg in args:
        if arg.startswith("-") or arg in {"(", "!", ")"}:
            break
        starts.append(arg)
    for j, arg in enumerate(args):
        if arg == "-delete" or (arg in FIND_EXEC and writes_files(args[j + 1:])):
            return starts or ["."]
    return []


def awk_targets(args, cwd):
    """awk program text that redirects output or calls system() writes: its path literals and its cwd.
    gawk -i inplace writes the files it reads."""
    script, files, has_file_opt, i = None, [], False, 0
    inplace = any(a in {"--inplace"} for a in args) or "inplace" in [
        args[k + 1] for k, a in enumerate(args[:-1]) if a in {"-i", "--include"}]
    while i < len(args):
        arg = args[i]
        if arg in AWK_OPTS_WITH_VALUE:
            has_file_opt = has_file_opt or arg in {"-f", "--file"}
            i += 2
            continue
        if not arg.startswith("-"):
            if script is None and not has_file_opt:
                script = arg
            else:
                files.append(arg)
        i += 1
    if inplace:
        return [f for f in files if os.path.isfile(os.path.join(cwd, os.path.expanduser(f)))] or [loc()]
    if script and AWK_WRITE_RE.search(script):
        return [loc()] + PATH_LITERAL_RE.findall(script)
    return []


def maven_goal_writes(arg):
    """Whether a Maven goal (plugin:goal, group:artifact:goal or group:artifact:version:goal) rewrites
    the source tree."""
    parts = arg.split(":")
    if len(parts) < 2 or len(parts) > 4:
        return False
    plugin = parts[0] if len(parts) == 2 else parts[1]
    plugin = re.sub(r"^maven-(.+)-plugin$", r"\1", re.sub(r"-maven-plugin$", "", plugin))
    goal = MAVEN_WRITE_GOALS.get(plugin)
    return bool(goal and goal.match(parts[-1]))


def build_tool_targets(prog, args):
    """Maven and Gradle goals or tasks that rewrite the source tree write under the project directory."""
    maven = prog in MAVEN
    with_value = MAVEN_OPTS_WITH_VALUE if maven else GRADLE_OPTS_WITH_VALUE
    goals, i = [], 0
    while i < len(args):
        if args[i] in with_value:
            i += 2  # the value of -f, -pl, -D, ... (gradle -x TASK excludes the task: not run)
            continue
        if not args[i].startswith("-"):
            goals.append(args[i])
        i += 1
    if maven:
        writes = any(maven_goal_writes(g) for g in goals)
        where = option_value(args, "-f", "--file")
        where = os.path.dirname(where) or "." if where and where.endswith(".xml") else where
    else:
        writes = any(GRADLE_WRITE_TASK_RE.match(g.rsplit(":", 1)[-1]) for g in goals)
        where = option_value(args, "-p", "--project-dir")
    return [loc(where or ".")] if writes else []


def side_effect_targets(rules, layers, words, cwd, env):
    """What the `write` rules matching this command say it writes as a side effect, as "somewhere under" targets
    relative to cwd (terraform init writes .terraform/ and .terraform.lock.hcl where it runs).

    A rule's `writes` object names: `paths` relative to the directory the command works in (cwd, or the value of
    one of `directory_options`, or the directory of the file one of `file_options` names), "." for anywhere under
    it, expanded like a shell word with the command's assignments and environment (${TF_DATA_DIR:-.terraform});
    an entry that expands to nothing is skipped, and `{program_dir}` is the directory of the first execution layer
    named by a path (.venv/bin/pip), the entry skipped when there is none; `path_options`, whose values are written
    paths; and `operands` (the operands after the matched subcommand). A value the gate cannot expand becomes
    UNRESOLVED in settle(), a write at the working directory. Every execution layer is matched (uv run, npx and
    python -m wrap the program a rule names)."""
    def join(base, text):
        return text if base == "." else os.path.join(base, text)

    out, pairs = [], [(layer, rule) for layer in (layers or [words]) for rule in rules
                      if rule_matches(rule, [literal(w) for w in layer])]
    for layer, rule in pairs:
        args = layer[1:]
        spec = rule["writes"]
        base = option_value(args, *spec["directory_options"]) if spec.get("directory_options") else None
        base = base or "."
        named = option_value(args, *spec["file_options"]) if spec.get("file_options") else None
        if named:
            joined = join(base, named)
            base = joined if os.path.isdir(resolve_shell(joined, cwd)) else (os.path.dirname(joined) or ".")
        for entry in spec.get("paths", []):
            if "{program_dir}" in entry:
                program = next((lay[0] for lay in layers if "/" in lay[0]), None)
                if program is None:
                    continue
                out.append(loc(entry.replace("{program_dir}", os.path.dirname(program) or ".")))
                continue
            text = expand(entry, cwd, env)
            if text:
                out.append(loc(join(base, text)))
        for option in spec.get("path_options", []):
            value = option_value(args, option)
            if value:
                out.append(loc(join(base, value)))
        if spec.get("operands"):
            operands = non_options(args)
            for sub in rule.get("match", {}).get("subcommands", []):
                if " ".join(operands) == sub or " ".join(operands).startswith(sub + " "):
                    operands = operands[len(sub.split()):]
                    break
            out.extend(loc(join(base, o)) for o in operands)
    return out


def rule_matches(rule, words):
    if not words:
        return False
    match = rule.get("match", {})
    prog = os.path.basename(words[0])
    if "programs" in match and prog not in match["programs"]:
        return False
    if "subcommands" in match:
        joined = " ".join(non_options(words[1:]))
        if not any(joined == s or joined.startswith(s + " ") for s in match["subcommands"]):
            return False
    # args_regex sees the words joined by spaces; whitespace inside one word ('-backend-config=key=a -backend=false')
    # becomes NUL, so \s and a space in a rule's regex only ever meet a real word boundary.
    if "args_regex" in match and not re.search(match["args_regex"], " ".join(re.sub(r"\s", "\0", w) for w in words)):
        return False
    if "aws_services" in match:
        service = aws_positionals(words[1:])[:1]
        if not service or service[0] not in match["aws_services"]:
            return False
    if match.get("aws_mutating"):
        positional = aws_positionals(words[1:])
        if len(positional) < 2:
            return False
        operation = positional[1]
        if operation in set(match.get("read_only_operations", [])):
            return False
        if any(operation == v or operation.startswith(v + "-") for v in match.get("read_only_verbs", [])):
            return False
    return True


def aws_positionals(args, limit=2):
    """Positional words of an aws call, global options and their values removed: [service, operation, ...]."""
    positional, i = [], 0
    while i < len(args) and (limit is None or len(positional) < limit):
        arg = args[i]
        if arg in AWS_GLOBAL_OPTS_WITH_VALUE:
            i += 2
            continue
        if not arg.startswith("-"):
            positional.append(arg)
        i += 1
    return positional


# ------------------------------------------------------------------------------------------- main

COMMANDS = {"activate": cmd_activate, "record": cmd_record, "guard-edit": cmd_guard_edit,
            "guard-bash": cmd_guard_bash, "plan-changed": cmd_plan_changed}


def plugin_rules(skills_dir):
    """Plugin mode: the gated skills (those with a gate_rules.json) and the union of their rules."""
    skills, merged = set(), load_rules(None)
    merged["writable_before_approval"], merged["approval_words"], merged["broken"] = [], [], []
    seen = set()
    for path in sorted(glob.glob(os.path.join(skills_dir, "*", "gate_rules.json"))):
        skills.add(os.path.basename(os.path.dirname(path)))
        try:
            rules = load_rules(path)
        except (OSError, ValueError, re.error) as exc:
            # A broken rules file must not disable the gate for every skill: the skill stays gated with
            # the default writable prefixes and approval words, and since its command rules are unknown,
            # every shell command in a gated session asks (cmd_guard_bash) until the file is fixed.
            print(f"spec-approval-gate: unreadable {path}: {exc}", file=sys.stderr)
            merged["broken"].append(f"{path} ({exc})")
            continue
        for key in ("writable_before_approval", "approval_words"):
            merged[key] += [v for v in rules[key] if v not in merged[key]]
        for rule in rules["command_rules"]:
            # Skills may reuse an id with different rules; only an identical rule is a duplicate.
            key = json.dumps(rule, sort_keys=True)
            if key not in seen:
                seen.add(key)
                merged["command_rules"].append(rule)
    merged["writable_before_approval"] = merged["writable_before_approval"] or DEFAULT_WRITABLE
    merged["approval_words"] = merged["approval_words"] or DEFAULT_WORDS
    return skills, merged


def starting_gated_skill(event, data):
    """Plugin mode: the gated skill this activate (Skill tool) or record (/<plugin>:<skill> prompt) event
    starts, or '' when it starts none. Read from the payload and the skills directory alone, so it works
    when loading the rules or the state failed."""
    if not PLUGIN_MODE["on"] or not isinstance(data, dict):
        return ""
    if event == "activate":
        invoked = (data.get("tool_input") or {}).get("skill") if isinstance(data.get("tool_input"), dict) else ""
    elif event == "record":
        slash = re.match(r"/([\w.:-]+)", str(data.get("prompt") or "").strip())
        invoked = slash.group(1) if slash else ""
    else:
        return ""
    namespace, name = skill_parts(invoked)
    if not name or (namespace and namespace != plugin_name()):
        return ""
    # may_exist: an unreadable rules file still names a gated skill, which then does not start ungated.
    return name if load_paths().may_exist(os.path.join(PLUGIN_MODE["skills_dir"], name, "gate_rules.json")) else ""


def gated_skill_named(event, data):
    """The fallback of starting_gated_skill when it raised: the name of the skill of this plugin an activate or
    record event starts, gated or not (whether it is cannot be checked, so it is refused rather than run
    ungated), or '' for any other event or a name with no skills/<name> entry (lstat, no ifs_paths: an error
    other than "no such file" counts as one). Reads the payload, plugin.json and that one entry."""
    try:
        if not PLUGIN_MODE["on"] or not isinstance(data, dict) or event not in ("activate", "record"):
            return ""
        if event == "activate":
            tool_input = data.get("tool_input")
            invoked = tool_input.get("skill") if isinstance(tool_input, dict) else ""
        else:
            slash = re.match(r"/([\w.:-]+)", str(data.get("prompt") or "").strip())
            invoked = slash.group(1) if slash else ""
        namespace, name = skill_parts(invoked)
        if not name or (namespace and namespace != plugin_name()):
            return ""
        try:
            os.lstat(os.path.join(PLUGIN_MODE["skills_dir"], name))
        except (FileNotFoundError, NotADirectoryError):
            return ""
        except OSError:
            pass
        return name
    except Exception:  # noqa: BLE001 - a fallback never raises
        return ""


def describe(exc):
    """str(exc), or its type's name when even that raises: an error message never stops a denial."""
    try:
        return str(exc)
    except Exception:  # noqa: BLE001
        return type(exc).__name__


def plugin_name():
    try:
        with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("name") or "implement-from-spec"
    except (OSError, ValueError):
        return "implement-from-spec"


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="K22 spec approval gate (Claude Code hook; reads hook "
                                                 "JSON on stdin).")
    parser.add_argument("event", choices=sorted(COMMANDS))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rules", help="skill mode: the skill's gate_rules.json (writable prefixes, approval "
                                      "words, command rules)")
    mode.add_argument("--skills-dir", help="plugin mode: the plugin's skills/ directory; every skill there "
                                           "with a gate_rules.json is gated")
    args = parser.parse_args(argv[1:])
    if not args.skills_dir and args.event == "activate":
        parser.error("activate is a plugin-mode event: pass --skills-dir")
    return run_event(args.event, rules_path=args.rules, skills_dir=args.skills_dir)


def run_event(event, rules_path=None, skills_dir=None):
    """One hook event on the payload read from standard input; returns the exit status. main() calls it after
    parsing the command line; the PreToolUse dispatcher (core/gate/ifs-pretool.py) calls it in-process for
    activate, guard-edit and guard-bash with skills_dir set, as hooks.json's --skills-dir did."""
    if skills_dir:
        # Plugin mode is on before anything can fail, so the failure policy below knows the mode.
        PLUGIN_MODE.update(on=True, skills_dir=os.path.realpath(skills_dir))
    raw, data = "", {}
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        if event.startswith("guard") and not data:
            raise ValueError("empty hook payload")
        if not isinstance(data, dict):
            raise ValueError("the hook payload is not a JSON object")
        if skills_dir and event.startswith("guard") and not session_active(data):
            # A guard in a session that never started a gated skill decides nothing (cmd_guard_*): return
            # before the skills' rules files are read.
            return 0
        if skills_dir:
            skills, rules = plugin_rules(skills_dir)
            PLUGIN_MODE.update(skills=skills, name=plugin_name())
        else:
            rules = load_rules(rules_path)
        COMMANDS[event](data, rules)
    except Exception as exc:  # noqa: BLE001 - the gate must never fail silently
        # Nothing in this handler may raise before its decision is printed (PR 1 fix round 4, defect 3): each
        # helper that reads the file system or loads ifs_paths runs best-effort, and its failure fails closed.
        try:
            starting = starting_gated_skill(event, data)
        except Exception:  # noqa: BLE001 - cannot tell whether a gated skill starts: it does not start ungated
            starting = gated_skill_named(event, data)
        if starting:
            # The skill would run with no gate registered: refuse to start it rather than run it ungated.
            reason = (f"spec-approval-gate (K22) could not register the approval gate for {starting} "
                      f"({type(exc).__name__}: {describe(exc)}), so the skill does not start. Tell the user; the "
                      f"gate's state directory is {STATE_DIR}.")
            if event == "activate":
                emit_pre_tool("deny", reason)
            else:
                print(json.dumps({"decision": "block", "reason": clean(reason)}))
            return 0
        if not isinstance(data, dict) or "session_id" not in data:
            # A payload that is not valid JSON still names its session: a gated session fails closed.
            found = re.search(r'"session_id"\s*:\s*"([^"\\]*)"', raw if isinstance(raw, str) else "")
            data = {"session_id": found.group(1)} if found else {}
        try:
            active = session_active(data)
        except Exception:  # noqa: BLE001 - whether the session is gated is unknown: it is guarded
            active = True
        if PLUGIN_MODE["on"] and not active:
            # Plugin mode registers the gate in every session; one that never started a gated skill is
            # not gated, so an error here must not block its tools.
            print(f"spec-approval-gate: {event} failed in an ungated session: {describe(exc)}", file=sys.stderr)
            return 0
        if event.startswith("guard"):
            # Fail closed: a guard that silently opens is worse than one that asks to be fixed.
            if not isinstance(exc, OSError):
                fix = "they can fix core/gate/spec-approval-gate.py or the rules file."
            else:
                try:
                    records = f" or its activation records ({load_paths().active_dir()})"
                except Exception:  # noqa: BLE001 - the denial stands without the location
                    records = " or its activation records (under ~/.local/state/implement-from-spec/active)"
                fix = (f"the gate's state ({STATE_DIR}){records} cannot be reached: restore this user's access to "
                       "them, or start a new session.")
            emit_pre_tool("deny", f"spec-approval-gate hook error ({type(exc).__name__}: {describe(exc)}). Tell "
                                  f"the user; {fix}")
            return 0
        print(f"spec-approval-gate: {event} failed: {describe(exc)}", file=sys.stderr)
        return 1
    return 0


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
    _hook = "spec-approval-gate " + (sys.argv[1] if len(sys.argv) > 1 else "-")
    sys.exit(run_timed(lambda: main(sys.argv), _hook, _log) if _log else main(sys.argv))
