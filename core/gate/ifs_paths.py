# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""ifs_paths.py: the one definition of the state locations the plugin's PreToolUse checks share.

Owner: the implement-from-spec plugin; this file lives in the plugin's core/gate/ directory. Standard library
only (Python 3.9+). It imports only os and sys, both loaded at interpreter start-up, so the PreToolUse
dispatcher's fast path can use it before any other module loads. It is not an import location:
core/gate/ifs-pretool.py, core/gate/spec-approval-gate.py and core/gate/review-isolation.py load it by path
through the same `load_paths` function (the dispatcher's tests check that the three copies are identical), so
they compute every location with the same code and cannot disagree. Before this module the dispatcher kept its
own mirror of the gate's and the isolation hook's locations, and a mirror that drifted would have made it skip
the guards of a gated session or the isolation of a registered reviewer, because it looks for the session's
state file to decide whether those checks can decide. The gate protects this file with the rest of core/gate/
(PROTECTED_RE).

    gate_state_dir()           the approval gate's state:
                               <$CLAUDE_PLUGIN_DATA, else $XDG_STATE_HOME, else ~/.local/state>/spec-approval-gate
    gate_state_file(sid)       <gate_state_dir()>/<session_key(sid)>.json
    plugin_state_root()        the isolation hook's state: $CLAUDE_PLUGIN_DATA, else
                               <$XDG_STATE_HOME, else ~/.local/state>/implement-from-spec
    isolation_state_file(sid)  <plugin_state_root()>/review-isolation/<session_key(sid)>.json
    active_dir()               the activation records: ~/.local/state/implement-from-spec/active, from HOME alone
    gate_marker_file(sid)      <active_dir()>/gate-<session_key(sid)>.json: this session started a gated skill,
                               and where its gate state was then
    review_marker_file(sid)    <active_dir()>/review-<session_key(sid)>.json: the session's registered reviewers
    snapshot_roots()           every default location of review snapshots (review-snapshot.py state_dir)
    state_name_roots()         the state directories a shell command may not even name (the gate's, the
                               isolation hook's under both roots, the activation records)
    state_write_roots()        those plus the snapshot roots (and the HOME one), timing_dir(): never written by a
                               tool call while the gate is registered
    may_exist(path)            False only when lstat says the path is absent (ENOENT, ENOTDIR); a path that
                               cannot be checked (EACCES on an ancestor, ELOOP, EIO) counts as present, so a
                               check that runs only when a state file exists runs (fail closed)
    timing_log_path()          the opt-in hook timing log, or None: always a file in timing_dir()
    write_timing(path, text)   one append to that log, through directory descriptors (no symlink from HOME down)
    load_source(name, path)    a module compiled from its source, with no bytecode read or written (the
                               dispatcher loads its checks this way)

No variable a repository can set moves any of these. A project's or a local settings env block cannot set HOME
or the XDG_* family: "Project and local settings can't set variables that a checked-out repository shouldn't
control", among them "the operating-system directory variables such as `HOME`, `TMPDIR`, `TMP`, `TEMP`, and the
`XDG_*` family" (code.claude.com/docs/en/settings-reference, "Variables Claude Code ignores in `env`", read
2026-11-12); and CLAUDE_PLUGIN_DATA is exported by Claude Code itself to every plugin hook ("both export them as
the environment variables `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, and `CLAUDE_PLUGIN_DATA` on the spawned
process", code.claude.com/docs/en/hooks, read 2026-11-12; on Claude Code 2.1.322 a project env block's
CLAUDE_PLUGIN_DATA did not reach a plugin hook, the maintainer's probe, 2026-11-12). Until 2026-11-12 a further
variable, SPEC_GATE_STATE_DIR, took precedence over both and was not on that list, so a repository's settings
could have moved the gate's state between two calls of one session and made the second call find no state
(an ungated session); it is gone. The tests move the state the way Claude Code does, through
CLAUDE_PLUGIN_DATA and HOME in the environment they start the hooks with.

Activation records. The gate's and the isolation hook's state can move with CLAUDE_PLUGIN_DATA and
XDG_STATE_HOME, and a state file can disappear. A session that has started a gated skill, and a session with a
registered reviewer, therefore also leaves a record in active_dir(), which depends on HOME alone: when the
record exists and the state it names is missing, unreadable or somewhere else, the gate denies every write
and Bash command of the session and the isolation hook denies every call of the reviewer (fail closed), rather
than treating the session as never activated. The gate protects active_dir() like its own state.

Every function reads the environment when it is called.
"""

import os
import sys

PLAIN_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
TIMING_ENV = ("IFS_HOOK_TIMING_LOG", "EVAL_IFS_HOOK_TIMING_LOG")


def session_key(session_id):
    """The file name stem of a session's state: every character outside [A-Za-z0-9_.-] becomes "_"."""
    return "".join(ch if ch in PLAIN_ID_CHARS else "_" for ch in str(session_id or "no-session"))


def xdg_state():
    return os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")


def gate_state_dir():
    return os.path.realpath(os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or xdg_state(), "spec-approval-gate"))


def gate_state_file(session_id):
    return os.path.join(gate_state_dir(), session_key(session_id) + ".json")


def plugin_state_root():
    return os.path.realpath(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(xdg_state(), "implement-from-spec"))


def isolation_state_dir():
    return os.path.join(plugin_state_root(), "review-isolation")


def isolation_state_file(session_id):
    return os.path.join(isolation_state_dir(), session_key(session_id) + ".json")


def home_state():
    """~/.local/state/implement-from-spec from HOME alone (never XDG_STATE_HOME or CLAUDE_PLUGIN_DATA)."""
    return os.path.join(os.path.expanduser("~"), ".local", "state", "implement-from-spec")


def active_dir():
    return os.path.join(home_state(), "active")


def gate_marker_file(session_id):
    return os.path.join(active_dir(), "gate-" + session_key(session_id) + ".json")


def review_marker_file(session_id):
    return os.path.join(active_dir(), "review-" + session_key(session_id) + ".json")


def may_exist(path):
    """Whether path exists or may exist: lstat succeeds, or fails with an error other than "no such file"
    (ENOENT) or "not a directory" (ENOTDIR). os.path.exists and os.path.lexists return False on any OSError, so a
    state file under a directory the hook may not search (EACCES) looked absent, and the dispatcher and the gate
    took a gated session for an ungated one (PR 1 fix round 3). Every "no state, so the check cannot decide"
    test of the gate, the isolation hook and the dispatcher goes through this function."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def snapshot_roots():
    """Every location review-snapshot.py may have chosen by default (its state_dir: $CLAUDE_PLUGIN_DATA, else
    $XDG_STATE_HOME/implement-from-spec, else ~/.local/state/implement-from-spec, each + /review-snapshots).
    Claude Code exports CLAUDE_PLUGIN_DATA to hooks but not to the Bash tool's commands, so a snapshot created
    from the shell lands under the XDG or HOME root while a hook sees CLAUDE_PLUGIN_DATA: all are listed."""
    roots = [os.path.join(plugin_state_root(), "review-snapshots"),
             os.path.join(xdg_state(), "implement-from-spec", "review-snapshots")]
    return sorted({os.path.realpath(r) for r in roots})


def isolation_state_dirs():
    """The isolation hook's state directory under the plugin data root and under the XDG/HOME fallback."""
    return sorted({os.path.realpath(isolation_state_dir()),
                   os.path.realpath(os.path.join(xdg_state(), "implement-from-spec", "review-isolation"))})


def state_name_roots():
    """The directories no shell command of a gated session may name (only the hooks read and write them)."""
    return sorted({gate_state_dir(), os.path.realpath(active_dir())} | set(isolation_state_dirs()))


def state_write_roots():
    """The directories no tool call of a gated session may write, remove or replace: state_name_roots(), the
    review snapshots (written only by the plugin's scripts, which the gate does not see) and the timing log."""
    return sorted(set(state_name_roots()) | set(snapshot_roots()) | {
        os.path.realpath(os.path.join(home_state(), "review-snapshots")), os.path.realpath(timing_dir())})


def timing_dir():
    """The only directory the hook timing log is written to: ~/.local/state/implement-from-spec/hook-timing.
    It is fixed, never taken from the timing variable, and HOME is not a variable a repository can move (see
    the module docstring)."""
    return os.path.join(home_state(), "hook-timing")


TIMING_DIR_PARTS = (".local", "state", "implement-from-spec", "hook-timing")
TIMING_MAX_BYTES = 64 * 1024 * 1024


def timing_log_path():
    """The opt-in timing log, or None. Off unless IFS_HOOK_TIMING_LOG (or EVAL_IFS_HOOK_TIMING_LOG, the form
    `claude plugin eval` passes to its sessions) is set. Its value is a file name ([A-Za-z0-9_.-], not starting
    with a dot, ending in .tsv), or an absolute path whose directory is spelled timing_dir() and whose name is
    such a name; the log is timing_dir()/<name>. Any other value is refused and nothing is logged: the variable
    can be set by a repository's settings env block, and must never make a hook append to a file anywhere else,
    the project included. Only the name is used: write_timing reaches the directory itself."""
    value = next((os.environ[n] for n in TIMING_ENV if os.environ.get(n)), None)
    if not value:
        return None
    fixed = timing_dir()
    if os.sep in value:
        if not os.path.isabs(value) or os.path.normpath(os.path.dirname(value)) != os.path.normpath(fixed):
            return None
        value = os.path.basename(value)
    if value.startswith(".") or not value.endswith(".tsv") or not all(ch in PLAIN_ID_CHARS for ch in value):
        return None
    return os.path.join(fixed, value)


def _timing_dir_fd():
    """A descriptor of timing_dir(), reached from HOME one component at a time with O_NOFOLLOW (a symlink at any
    level below HOME stops it), every level owned by this user, the last one 0700. Creates missing levels
    0700. Raises OSError."""
    dflags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(os.path.expanduser("~"), dflags)
    try:
        for part in TIMING_DIR_PARTS:
            try:
                os.mkdir(part, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, dflags | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            if (st.st_mode & 0o170000) != 0o040000 or st.st_uid != os.getuid():
                raise OSError(f"{part} is not a directory of this user")
        if os.fstat(fd).st_mode & 0o077:
            os.fchmod(fd, 0o700)  # open to others: closed first, else not used
            if os.fstat(fd).st_mode & 0o077:
                raise OSError("the timing directory is open to others")
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_timing(log_path, text):
    """Append text to timing_dir()/<basename of log_path> in one write. The directory is reached through
    descriptors (_timing_dir_fd), the file opened relative to it with O_NOFOLLOW (no symlink), O_NONBLOCK (a
    FIFO without a reader fails at once instead of hanging the hook) and O_APPEND, then checked on the open
    descriptor: a regular file of this user, one link (a hard link to a file elsewhere is refused), mode 0600
    (a file left open to others is refused, not written) and no larger than TIMING_MAX_BYTES once the text is
    appended. Raises OSError; the callers ignore it, since timing never changes a decision.

    The cap is soft under concurrency: hooks of one session run in parallel, and each checks the size it sees
    before its own write, so writers that check at the same moment can each append one record past the cap (at
    most one record per concurrently running hook process). Serialising them (flock) would make a hook wait on
    a lock any process of this user can hold; a bounded overshoot of a debugging log is the smaller cost."""
    name = os.path.basename(log_path)
    if name != log_path.rpartition(os.sep)[2] or name.startswith(".") or not name.endswith(".tsv") or \
            not all(ch in PLAIN_ID_CHARS for ch in name):
        raise OSError("not a timing log name")
    dfd = _timing_dir_fd()
    try:
        base = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(name, base | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dfd)
            os.fchmod(fd, 0o600)  # whatever the umask left
        except FileExistsError:
            fd = os.open(name, base, dir_fd=dfd)
    finally:
        os.close(dfd)
    try:
        data = text.encode("utf-8", "replace")
        st = os.fstat(fd)
        if (st.st_mode & 0o170000) != 0o100000 or st.st_uid != os.getuid() or st.st_nlink != 1 or \
                (st.st_mode & 0o777) != 0o600:
            raise OSError("the timing log is not a private regular file of this user with one link")
        if st.st_size + len(data) > TIMING_MAX_BYTES:
            raise OSError("the timing log would grow past its cap")
        os.write(fd, data)
    finally:
        os.close(fd)


def load_source(name, path):
    """The module at path, compiled from its source: no bytecode is read or written, so no .pyc file anywhere
    can stand in for the plugin's code. It is registered in sys.modules under name while and after it runs."""
    try:
        import _frozen_importlib as bootstrap
        import _frozen_importlib_external as external
    except ImportError:  # an interpreter without the frozen names: the same classes through importlib
        import importlib._bootstrap as bootstrap
        import importlib._bootstrap_external as external

    class SourceOnly(external.SourceFileLoader):
        def get_code(self, fullname):
            return self.source_to_code(self.get_data(self.path), self.path)

    spec = bootstrap.spec_from_loader(name, SourceOnly(name, path))
    mod = bootstrap.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod
