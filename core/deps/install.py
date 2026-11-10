#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""core/deps/install.py — installs the binary dependencies the user approved, dry run first.

Owns: turning the doctor's gaps into an exact install plan (the commands as argument arrays, the
download URLs, the pinned fingerprints and checksums, the steps that need administrator rights); the
plan digest that ties a run to the dry run that was reviewed; executing the approved plan; the journal
and the record of what setup installed, so --uninstall removes only that.

Modes
  dry run (default)   Detects, chooses a recipe per missing dependency, prints the plan and its digest
                      and the exact --apply command. Downloads only piped remote scripts, so they can be
                      shown (path, sha256, first lines) before anyone approves running them. Installs
                      nothing.
  --apply --confirm DIGEST
                      Recomputes the plan and refuses unless its digest equals DIGEST. Refuses to
                      overwrite any path a recipe would create. Runs the steps in order and stops at the
                      first failure. Steps that need administrator rights are never run: they are
                      printed for you to run yourself, and that dependency is reported as handed off.
                      Verifies each install with the dependency's own version command. Re-running when
                      everything is satisfied is a no-op.
  --uninstall [NAME ...]
                      Plans removal of what setup itself installed in user scope (all of it when no
                      name is given); the same --apply --confirm DIGEST runs it. Anything setup did not
                      install is reported and left alone.
  --status            Prints what setup installed and the last journal entries.

Rules: setup never replaces or downgrades an existing install (a too-old tool is reported, not
touched); never installs into a project (project-local tools are reported); never runs sudo, su or a
captured password; never configures credentials. A PreToolUse hook (core/deps/install-ask-hook.py)
asks the user before any --apply runs, even when the digest is supplied.

State: <data>/setup/ where <data> is --data-dir, else ~/.local/state/implement-from-spec
(XDG_STATE_HOME honoured; $CLAUDE_PLUGIN_DATA is not consulted, see depslib.data_dir):
journal.jsonl (one line per step), owned.json (what setup installed), plans/<digest>.json (each dry
run), scripts/<sha256>.sh (downloaded piped scripts), staging/<name>/ (downloads).

Usage
  python3 -I <plugin-root>/core/deps/install.py --stack terraform
  python3 -I <plugin-root>/core/deps/install.py --stack terraform --apply --confirm <digest from the dry run>
  python3 -I <plugin-root>/core/deps/install.py --only tflint --only checkov
  python3 -I <plugin-root>/core/deps/install.py --uninstall tflint

Exit codes: 0 dry run printed, nothing to do, or the plan ran (handed-off steps included); 1 refusal
(digest mismatch, missing --confirm, would overwrite, unknown name); 2 invalid arguments; 4 a step
failed (the journal names it); 69 nothing installable for a required gap (blocked).
With --json, stdout is exactly one JSON object (a refusal is {"refused": "<reason>"}) and the progress
of --apply goes to stderr.

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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

DIGEST_VERSION = 1      # bump when the digest's inputs change, so old confirmations stop matching
DIGEST_LEN = 16         # hex characters of sha256 shown to the user
SCRIPT_PREVIEW_LINES = 30
GAPS = ("missing",)
NOT_REPLACED = ("too-old", "unusable")


class Refusal(Exception):
    """A state or input problem that stops the run with exit 1 and a specific message."""


# --------------------------------------------------------------------------- arguments
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="install.py", allow_abbrev=False,
                                 description="Install the approved binary dependencies of the implement-from-spec skills (dry run first).")
    ap.add_argument("--stack", action="append", choices=list(dl.STACKS) + ["all"], help="stack (repeatable); default all")
    ap.add_argument("--only", action="append", default=[], metavar="NAME", help="install only these dependencies (repeatable); may name optional ones")
    ap.add_argument("--include-optional", action="store_true", help="also plan the optional dependencies that are missing (never opt-in ones such as taskcat)")
    ap.add_argument("--recipe", action="append", default=[], metavar="NAME=ID", help="use a specific recipe for a dependency")
    ap.add_argument("--project", default=".", help="project directory (read only, for wrappers and the CDK app language)")
    ap.add_argument("--review-auth", choices=dl.REVIEW_AUTH, default="off",
                    help="external reviewer authentication: off (default) needs nothing, aws-profile needs the AWS CLI, api-key needs curl and jq")
    ap.add_argument("--if", dest="conditions", action="append", default=[], metavar="CONDITION")
    ap.add_argument("--java-major", default="21", choices=["17", "21", "25"])
    ap.add_argument("--data-dir", default="", help="override the state directory (default: ${XDG_STATE_HOME:-~/.local/state}/implement-from-spec)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="run the plan; requires --confirm")
    ap.add_argument("--confirm", metavar="DIGEST", help="the digest the dry run printed")
    ap.add_argument("--uninstall", nargs="*", metavar="NAME", help="remove what setup installed (all when no name)")
    ap.add_argument("--status", action="store_true", help="show what setup installed and the journal's tail")
    return ap


def apply_command(argv: List[str], digest: str) -> str:
    keep, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--confirm":
            skip = True
            continue
        if a.startswith("--confirm=") or a == "--apply":
            continue
        keep.append(a)
    return shlex.join(["python3", "-I", str(Path(__file__).resolve()), *keep, "--apply", "--confirm", digest])


# --------------------------------------------------------------------------- state
class State:
    def __init__(self, setup: Path, system: dl.System):
        self.setup = setup
        self.system = system
        self.run_id = uuid.uuid4().hex[:12]

    def ensure(self) -> None:
        for sub in ("", "plans", "scripts", "staging"):
            dl.private_dir(self.setup / sub)

    def journal(self, **record) -> None:
        self.ensure()
        record = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": self.run_id, **record}
        dl.write_private(self.setup / "journal.jsonl", json.dumps(record, sort_keys=True) + "\n", append=True)

    def owned(self) -> Dict[str, dict]:
        path = self.setup / "owned.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Refusal(f"{path} is unreadable; fix or remove it before installing or uninstalling")

    def save_owned(self, data: Dict[str, dict]) -> None:
        self.ensure()
        tmp = self.setup / "owned.json.tmp"
        dl.write_private(tmp, json.dumps(data, indent=2, sort_keys=True))
        os.replace(tmp, self.setup / "owned.json")

    def save_plan(self, digest: str, plan: dict, summary: str) -> Path:
        self.ensure()
        path = self.setup / "plans" / f"{digest}.json"
        dl.write_private(path, json.dumps({"digest": digest, "plan": plan, "summary": summary}, indent=2, sort_keys=True))
        return path

    def load_plan(self, digest: str) -> Optional[dict]:
        path = self.setup / "plans" / f"{digest}.json"
        if not re.fullmatch(r"[0-9a-f]{%d}" % DIGEST_LEN, digest or "") or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def digest_of(plan: dict) -> str:
    canon = json.dumps({"v": DIGEST_VERSION, "mode": plan["mode"], "platform": plan["platform"],
                        "actions": plan["actions"]}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:DIGEST_LEN]


# --------------------------------------------------------------------------- planning
def conditions(args: argparse.Namespace, project: Optional[Path]) -> List[str]:
    conds = set(dl.project_conditions(project)) | set(args.conditions)
    if args.review_auth == "aws-profile":
        conds.add("review-aws-profile")
    elif args.review_auth == "api-key":
        conds.add("review-api-key")
    return sorted(conds)


def parse_overrides(values: List[str], manifest: dict) -> Dict[str, str]:
    out = {}
    for v in values:
        if "=" not in v:
            raise Refusal(f"--recipe needs NAME=ID, got {v!r}")
        name, rid = v.split("=", 1)
        if name not in manifest["dependencies"]:
            raise Refusal(f"--recipe names an unknown dependency: {name}")
        out[name] = rid
    return out


def build_plan(args: argparse.Namespace, manifest: dict, system: dl.System, state: State,
               script_source) -> dict:
    """script_source(url, step) -> (sha256, path, preview): fetches in a dry run, reads the saved plan on --apply."""
    deps = manifest["dependencies"]
    project = Path(args.project).expanduser().resolve() if args.project else None
    if project is not None and not project.is_dir():
        project = None
    plat = dl.detect_platform(system.facts())
    if plat["os"] == "windows":
        raise Refusal(dl.WINDOWS_GUIDANCE)
    ev = dl.evaluate(manifest, system, args.stack or ["all"], conditions(args, project), project)
    rows = ev["rows"]
    overrides = parse_overrides(args.recipe, manifest)
    for name in args.only:
        if name not in deps:
            raise Refusal(f"--only names an unknown dependency: {name} (known: {', '.join(sorted(deps))})")
        if name not in rows:
            rows[name] = dl.check_dep(system, name, deps[name], project, dl.extra_bin_dirs(manifest, system))
            rows[name].update(level="requested")
    if args.only:
        wanted = list(dict.fromkeys(args.only))
    else:
        levels = ("required", "optional", "alternative") if args.include_optional else ("required",)
        wanted = [n for n in sorted(rows) if rows[n].get("level") in levels and not deps[n].get("opt_in")
                  and not (rows[n].get("level") == "alternative" and not args.include_optional)]
    satisfied, not_replaced, blocked, project_local = [], [], [], []
    order: List[str] = []
    chosen: Dict[str, dict] = {}

    def visit(name: str, chain: Tuple[str, ...]) -> bool:
        if name in chosen:
            return True
        row = rows.get(name) or dl._status(manifest, name, rows, system)
        if row["status"] == "project-local":
            project_local.append({"dep": name, "path": row["path"]})
            return True
        if dl.is_ok(row):
            satisfied.append({"dep": name, "version": row["version"], "path": row["path"]})
            return True
        if row["status"] in NOT_REPLACED:
            not_replaced.append({"dep": name, "status": row["status"], "version": row["version"],
                                 "minimum": row["minimum"], "path": row["path"]})
            return False
        recipe, prereqs, reason = dl.choose_recipe(manifest, name, plat, rows, system, overrides.get(name))
        if recipe is None:
            blocked.append({"dep": name, "reason": reason, "level": row.get("level")})
            return False
        for pre in prereqs:
            if pre in chain or not visit(pre, chain + (name,)):
                blocked.append({"dep": name, "reason": f"needs {pre}, which cannot be installed here", "level": row.get("level")})
                return False
        variables = dl.platform_variables(plat, system, str(dl.staging_root(state.setup) / name), args.java_major)
        action = dl.expand_recipe(manifest, name, recipe, variables)
        for step in action["steps"]:
            if step["kind"] == "script":
                sha, path, _preview = script_source(step["url"], step)
                step["sha256"], step["path"] = sha, path
        action["verify"] = [dl.expand(a, dl.DETECT_VARIABLES)
                            for a in deps[name].get("verify", deps[name]["detect"]["command"])]
        action["minimum"] = (deps[name].get("minimum") or {}).get("version")
        chosen[name] = action
        order.append(name)
        return True

    for name in wanted:
        visit(name, ())
    satisfied = [s for s in satisfied if s["dep"] in wanted]
    plan = {"mode": "install", "platform": f"{plat['chain'][0]}-{plat['arch']}", "platform_name": plat["name"],
            "wsl": plat["wsl"], "actions": [chosen[n] for n in order], "satisfied": satisfied,
            "not_replaced": not_replaced, "blocked": blocked, "project_local": project_local,
            "setup_dir": str(state.setup)}
    guard_paths(plan, project, system)
    return plan


def guard_paths(plan: dict, project: Optional[Path], system: dl.System) -> None:
    """Setup never writes into a project, and user-scope paths stay inside the home directory."""
    home = system.home.resolve()
    for act in plan.get("actions", []):
        targets = list(act.get("owns", []))
        targets += [s["to"] for s in act.get("steps", []) if s.get("to")]
        for t in targets:
            p = Path(t).expanduser().resolve()
            if project is not None and (p == project or project in p.parents):
                raise Refusal(f"{act['dep']}: {p} is inside the project {project}; setup never installs into a project")
        for t in act.get("owns", []):
            p = Path(t).expanduser().resolve()
            if home not in p.parents:
                raise Refusal(f"{act['dep']}: owned path {p} is outside the home directory")


def fetch_script(state: State, system: dl.System):
    def source(url: str, step: dict) -> Tuple[str, str, str]:
        state.ensure()
        tmp = state.setup / "scripts" / f"download-{state.run_id}.part"
        try:
            system.fetch(url, tmp)
        except Exception as exc:  # noqa: BLE001 - any failure: nothing can be shown, so nothing is planned
            raise Refusal(f"could not download the vendor script {url} to show it before approval: {exc}")
        sha = dl.sha256_file(tmp)
        final = state.setup / "scripts" / f"{sha}.sh"
        os.replace(tmp, final)
        text = final.read_text(encoding="utf-8", errors="replace").splitlines()
        state.journal(mode="plan", kind="script-download", url=url, sha256=sha, status="downloaded")
        return sha, str(final), "\n".join(text[:SCRIPT_PREVIEW_LINES])
    return source


def saved_script(saved: Optional[dict]):
    by_url = {}
    if saved:
        for act in saved["plan"].get("actions", []):
            for s in act.get("steps", []):
                if s.get("kind") == "script":
                    by_url[s["url"]] = (s["sha256"], s["path"])

    def source(url: str, step: dict) -> Tuple[str, str, str]:
        if url not in by_url:
            return "not-in-dry-run", "", ""
        sha, path = by_url[url]
        return sha, path, ""
    return source


# --------------------------------------------------------------------------- rendering
def render_plan(plan: dict, previews: Dict[str, str]) -> str:
    lines = [f"Setup plan for {plan['platform_name']}{' (WSL2)' if plan.get('wsl') else ''} ({plan['platform']})",
             f"state and journal: {plan['setup_dir']}", ""]
    if not plan["actions"]:
        lines.append("Nothing to install.")
    for i, act in enumerate(plan["actions"], 1):
        adm = "needs admin: the marked steps are yours to run" if act["admin"] else "no admin"
        lines.append(f"{i}. {act['dep']}: recipe {act['recipe']} [{act['label']}, {act['scope']} scope, {adm}]")
        lines.append(f"   source:    {act['source']}")
        integ = act["integrity"]
        pinned = f" (pinned {integ['pinned']})" if integ.get("pinned") else ""
        lines.append(f"   integrity: {integ['method']}: {integ['detail']}{pinned}")
        if act["requires"]:
            lines.append(f"   requires:  {', '.join(act['requires'])}")
        for s in act["steps"]:
            lines.append(f"   {dl.describe_step(s)}")
            if s["kind"] == "script":
                lines.append(f"      saved at {s['path']} (sha256 {s['sha256']})")
                prev = previews.get(s["url"])
                if prev:
                    lines.append(f"      first {SCRIPT_PREVIEW_LINES} lines:")
                    lines.extend(f"      | {ln}" for ln in prev.splitlines())
        lines.append(f"   verify:    {dl.render_argv(act['verify'])}" + (f" (needs >= {act['minimum']})" if act["minimum"] else ""))
        if act["owns"]:
            lines.append(f"   creates:   {', '.join(act['owns'])} (refused if any already exists)")
    if plan["not_replaced"]:
        lines += ["", "Not replaced (setup never replaces or downgrades an existing install):"]
        for n in plan["not_replaced"]:
            need = f", needs >= {n['minimum']}" if n.get("minimum") else ""
            lines.append(f"  - {n['dep']}: {n['status']} {n.get('version') or ''} at {n['path']}{need}; upgrade it through the channel that installed it")
    if plan["blocked"]:
        lines += ["", "Blocked:"]
        lines += [f"  - {b['dep']}: {b['reason']}" for b in plan["blocked"]]
    if plan["project_local"]:
        lines += ["", "Project-local (used as is; setup installs nothing for these):"]
        lines += [f"  - {p['dep']}: {p['path']}" for p in plan["project_local"]]
    if plan["satisfied"]:
        lines += ["", "Already satisfied: " + ", ".join(s["dep"] for s in plan["satisfied"])]
    return "\n".join(lines)


def summary_line(plan: dict) -> str:
    """One paragraph for the permission prompt the ask hook shows."""
    parts = []
    for act in plan.get("actions", []):
        if plan["mode"] == "uninstall":
            cmds = [dl.render_argv(s["argv"]) for s in act["uninstall"]] + [f"remove {p}" for p in act["owns"]]
            parts.append(f"{act['dep']} ({'; '.join(cmds)})")
            continue
        runs = [dl.render_argv(s["argv"]) for s in act["steps"] if s["kind"] == "run"]
        dls = [s["url"] for s in act["steps"] if s["kind"] in ("download", "script")]
        manual = sum(1 for s in act["steps"] if s["kind"] == "manual")
        bits = []
        if dls:
            bits.append("downloads " + ", ".join(dls))
        if runs:
            bits.append("runs " + "; ".join(runs))
        if any(s["kind"] == "script" for s in act["steps"]):
            bits.append("runs a downloaded vendor script")
        if manual:
            bits.append(f"prints {manual} step(s) for you to run")
        parts.append(f"{act['dep']} via {act['recipe']} [{act['label']}] ({'; '.join(bits)})")
    verb = "uninstall" if plan["mode"] == "uninstall" else "install"
    return f"implement-from-spec setup will {verb}: " + "; ".join(parts) if parts else f"implement-from-spec setup: nothing to {verb}"


# --------------------------------------------------------------------------- execution
class StepFailed(Exception):
    pass


# Variables never passed to an install step, a gpg call or a downloaded vendor script: no recipe needs
# AWS, Bedrock, Claude or Anthropic credentials, or any token, secret, password or key, and a piped vendor
# script must not be able to read them. Mirrors child_env in core/scripts/spec-external-review.py, wider.
# PATH, HOME, the locale, proxies, CA bundles and the package managers' own settings pass through.
SECRET_ENV_RE = re.compile(
    r"^(AWS_.*|ANTHROPIC_.*|CLAUDE_.*|BEDROCK_.*|OPENAI_.*|IMPLEMENT_FROM_SPEC_.*|EVAL_IMPLEMENT_FROM_SPEC_.*)$"
    r"|TOKEN|SECRET|PASSW(OR)?D|CREDENTIAL|(^|_)(API_?)?KEYS?(_|$)|ACCESS_KEY|PRIVATE_KEY|AUTH", re.I)
# Never dropped, even when a name matches above (none does today; this keeps it so).
KEEP_ENV = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG", "LANGUAGE",
            "SSH_AUTH_SOCK")
KEEP_ENV_RE = re.compile(r"^(LC_.*|(HTTPS?|FTP|ALL|NO)_PROXY|SSL_CERT_(FILE|DIR)|REQUESTS_CA_BUNDLE|"
                         r"CURL_CA_BUNDLE|NODE_EXTRA_CA_CERTS|PIP_CERT|GIT_SSL_CAINFO)$", re.I)


def install_env(environ: Dict[str, str], path: str) -> Dict[str, str]:
    """The environment every step runs with: the user's, without credentials, and with PATH given."""
    env = {k: v for k, v in environ.items()
           if k in KEEP_ENV or KEEP_ENV_RE.match(k) or not SECRET_ENV_RE.search(k)}
    env["PATH"] = path
    return env


RESOLVED_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")


def bind(value, bound: Dict[str, str]):
    """A step with the names its recipe's resolve steps bound so far filled in ({name} -> value)."""
    if not bound:
        return value
    if isinstance(value, str):
        for k, v in bound.items():
            value = value.replace("{" + k + "}", v)
        return value
    if isinstance(value, list):
        return [bind(v, bound) for v in value]
    if isinstance(value, dict):
        return {k: bind(v, bound) for k, v in value.items()}
    return value


class Executor:
    def __init__(self, system: dl.System, state: State, manifest: dict, digest: str, out):
        self.system, self.state, self.manifest, self.digest, self.out = system, state, manifest, digest, out
        extra = dl.extra_bin_dirs(manifest, system)
        self.env = install_env(system.environ, os.pathsep.join(extra + [system.path]))

    def say(self, text: str) -> None:
        print(text, file=self.out)

    def run_action(self, act: dict) -> Tuple[str, List[dict]]:
        """Returns (status, handed-off steps). Raises StepFailed."""
        staging = dl.staging_root(self.state.setup) / act["dep"]
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        gnupg = staging / "gnupg"
        steps = act["steps"]
        if all(s["kind"] == "note" for s in steps):
            # Instructions only (Node.js on Linux, Gradle): nothing for setup to run, so the user gets the
            # text. Running the notes and then "verifying" would report a failure and stop the plan.
            for i, s in enumerate(steps):
                self.state.journal(mode="install", digest=self.digest, dep=act["dep"], recipe=act["recipe"],
                                   step=i, kind="note", status="handed-off", text=s.get("text"))
            return "handed-off", list(steps)
        bound: Dict[str, str] = {}
        for i, raw in enumerate(steps):
            step = bind(raw, bound)
            if step["kind"] == "manual":
                rest = [bind(s, bound) for s in steps[i:] if s["kind"] in ("manual", "note")]
                for s in rest:
                    self.state.journal(mode="install", digest=self.digest, dep=act["dep"], recipe=act["recipe"],
                                       step=steps.index(s), kind=s["kind"], status="handed-off",
                                       argv=s.get("argv"), text=s.get("text"))
                return "handed-off", rest
            detail, status, rc, output = self.do(step, staging, gnupg, bound)
            self.state.journal(mode="install", digest=self.digest, dep=act["dep"], recipe=act["recipe"], step=i,
                               kind=step["kind"], detail=detail, status=status, rc=rc, output=output[-800:])
            if status == "failed":
                raise StepFailed(f"{act['dep']}: step {i + 1} ({detail}) failed: {output.strip()[-400:]}")
        return "ran", []

    def do(self, step: dict, staging: Path, gnupg: Path,
           bound: Optional[Dict[str, str]] = None) -> Tuple[str, str, Optional[int], str]:
        kind = step["kind"]
        env = dict(self.env, **step.get("env", {}))
        if kind == "resolve":
            var, name = step["var"], Path(step["file"]).name
            try:
                text = Path(step["file"]).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return f"resolve {{{var}}}", "failed", None, str(exc)
            m = re.search(step["pattern"], text, re.M)
            if not m:
                return f"resolve {{{var}}}", "failed", None, f"no line of {name} matches {step['pattern']}"
            value = m.group(1)
            # A bound name lands in paths and URLs: one plain file-name component only.
            if not RESOLVED_RE.fullmatch(value):
                return f"resolve {{{var}}}", "failed", None, f"{value!r} from {name} is not a plain file name"
            if bound is not None:
                bound[var] = value
            self.say(f"   resolve: {{{var}}} = {value}")
            return f"resolve {{{var}}} = {value}", "ok", None, value
        if kind == "note":
            self.say(f"   note: {step['text']}")
            return "note", "ok", None, ""
        if kind == "run":
            if step.get("if_tool") and not self.system.which(step["if_tool"]):
                return dl.render_argv(step["argv"]), "skipped", None, f"{step['if_tool']} not installed"
            self.say(f"   run: {dl.render_argv(step['argv'])}")
            rc, out = self.system.run(step["argv"], timeout=1800, cwd=str(staging), env=env)
            if rc != 0:
                return dl.render_argv(step["argv"]), "failed", rc, out
            for rx in step.get("expect", []):
                if not re.search(rx, out, re.M):
                    return dl.render_argv(step["argv"]), "failed", rc, f"expected output matching {rx!r} not found\n{out}"
            return dl.render_argv(step["argv"]), "ok", rc, out
        if kind == "download":
            self.say(f"   download: {step['url']}")
            try:
                self.system.fetch(step["url"], Path(step["to"]))
            except Exception as exc:  # noqa: BLE001 - any download failure stops the run
                return step["url"], "failed", None, str(exc)
            return step["url"], "ok", None, dl.sha256_file(Path(step["to"]))
        if kind == "sha256":
            have = dl.sha256_file(Path(step["file"]))
            want = step.get("expected") or self._sum_from(Path(step["sums"]), step.get("entry"))
            ok = bool(want) and have.lower() == want.lower()
            return f"sha256 {Path(step['file']).name}", "ok" if ok else "failed", None, f"have {have}, want {want}"
        if kind == "write_file":
            Path(step["to"]).write_text(step["content"], encoding="utf-8")
            return f"write {step['to']}", "ok", None, ""
        if kind in ("gpg_key", "gpg_verify", "gpg_dearmor"):
            return self._gpg(step, gnupg)
        if kind == "script":
            path = Path(step["path"])
            if not path.is_file() or dl.sha256_file(path) != step["sha256"]:
                return step["url"], "failed", None, f"{path} is missing or changed since the dry run"
            argv = list(step["interpreter"]) + [str(path)] + list(step.get("args", []))
            self.say(f"   script: {dl.render_argv(argv)}")
            rc, out = self.system.run(argv, timeout=1800, cwd=str(staging), env=env)
            return dl.render_argv(argv), "ok" if rc == 0 else "failed", rc, out
        return kind, "failed", None, f"unknown step kind {kind}"

    @staticmethod
    def _sum_from(path: Path, entry: Optional[str]) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not entry:
            m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
            return m.group(1) if m else ""
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == entry:
                return parts[0]
        return ""

    def _gpg(self, step: dict, gnupg: Path) -> Tuple[str, str, Optional[int], str]:
        gnupg.mkdir(mode=0o700, exist_ok=True)
        # --no-autostart: a key import or a signature check needs no gpg-agent, and gnupg2-minimal (Amazon
        # Linux 2023) has none; without it gpg imports the key but exits 2 on "failed to start gpg-agent".
        base = ["gpg", "--batch", "--no-tty", "--no-autostart", "--homedir", str(gnupg)]
        pin, pin_kind = step.get("fingerprint", ""), step.get("pin", "fingerprint")

        def matches(fpr: str) -> bool:
            return fpr == pin if pin_kind == "fingerprint" else fpr.endswith(pin)

        if step["kind"] == "gpg_key":
            rc, out = self.system.run(base + ["--import", step["file"]], timeout=60, env=self.env)
            if rc != 0:
                return f"import {step['file']}", "failed", rc, out
            rc, out = self.system.run(base + ["--with-colons", "--fingerprint"], timeout=60, env=self.env)
            fprs = [ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr:") and len(ln.split(":")) > 9]
            ok = rc == 0 and any(matches(f) for f in fprs)
            return f"key {step['key']} pinned {pin}", "ok" if ok else "failed", rc, \
                f"fingerprints found: {', '.join(fprs) or 'none'}"
        if step["kind"] == "gpg_verify":
            rc, out = self.system.run(base + ["--status-fd", "1", "--verify", step["signature"], step["file"]],
                                      timeout=120, env=self.env)
            valid = [ln.split() for ln in out.splitlines() if ln.startswith("[GNUPG:] VALIDSIG")]
            ok = rc == 0 and any(matches(f[2]) or matches(f[-1]) for f in valid if len(f) > 2)
            return f"verify {Path(step['file']).name} by {pin}", "ok" if ok else "failed", rc, out
        rc, out = self.system.run(base + ["--yes", "--dearmor", "-o", step["to"], step["file"]], timeout=60, env=self.env)
        return f"dearmor {step['file']}", "ok" if rc == 0 else "failed", rc, out

    def verify(self, act: dict) -> dict:
        dep = self.manifest["dependencies"][act["dep"]]
        return dl.check_dep(self.system, act["dep"], dep, None, dl.extra_bin_dirs(self.manifest, self.system))


# --------------------------------------------------------------------------- modes
def do_install(args, argv, manifest, system, state, out) -> int:
    if not args.apply:
        previews: Dict[str, str] = {}
        fetch = fetch_script(state, system)

        def source(url, step):
            sha, path, prev = fetch(url, step)
            previews[url] = prev
            return sha, path, prev
        plan = build_plan(args, manifest, system, state, source)
        text = render_plan(plan, previews)
        if not plan["actions"]:
            state.journal(mode="plan", status="nothing-to-install")
            emit(args, out, {"plan": plan, "digest": None}, text)
            return dl.EX_UNAVAILABLE if any(b.get("level") == "required" for b in plan["blocked"]) else 0
        digest = digest_of(plan)
        state.save_plan(digest, plan, summary_line(plan))
        state.journal(mode="plan", digest=digest, status="planned", deps=[a["dep"] for a in plan["actions"]])
        cmd = apply_command(argv, digest)
        text += f"\n\ndigest:     {digest}\napply with: {cmd}\n(the command asks for your approval before it runs)"
        emit(args, out, {"plan": plan, "digest": digest, "apply_command": cmd}, text)
        return 0
    if not args.confirm:
        raise Refusal("--apply needs --confirm <digest>; run the dry run first and copy its digest")
    saved = state.load_plan(args.confirm)
    plan = build_plan(args, manifest, system, state, saved_script(saved))
    if not plan["actions"]:
        state.journal(mode="install", digest=args.confirm, status="nothing-to-install")
        emit(args, out, {"plan": plan, "result": "nothing-to-install"},
             "Nothing to install: every selected dependency is satisfied (a re-run is a no-op).")
        return 0
    digest = digest_of(plan)
    if args.confirm != digest:
        raise Refusal(f"digest mismatch: --confirm {args.confirm} but the plan now hashes to {digest}. Something "
                      "changed since the dry run (a tool appeared or vanished, the arguments, the recipes or a "
                      "downloaded script); run the dry run again and review it")
    for act in plan["actions"]:
        for p in act["owns"]:
            if os.path.lexists(p):
                raise Refusal(f"{act['dep']}: {p} already exists; setup never overwrites or replaces an install")
    state.journal(mode="install", digest=digest, status="started", deps=[a["dep"] for a in plan["actions"]])
    # With --json, stdout carries one JSON object only; the step-by-step progress goes to stderr.
    progress = sys.stderr if args.json else out
    ex = Executor(system, state, manifest, digest, progress)
    results, handed, failure = [], {}, None
    owned = state.owned()
    stopped: List[str] = []
    for act in plan["actions"]:
        if failure or any(r in handed or r in stopped for r in act["requires"]):
            stopped.append(act["dep"])
            results.append({"dep": act["dep"], "status": "not-run"})
            continue
        print(f"{act['dep']} ({act['recipe']})", file=progress)
        try:
            status, rest = ex.run_action(act)
        except StepFailed as exc:
            failure = str(exc)
            results.append({"dep": act["dep"], "status": "failed", "reason": failure})
            state.journal(mode="install", digest=digest, dep=act["dep"], status="failed", reason=failure)
            continue
        if status == "handed-off":
            handed[act["dep"]] = rest
            results.append({"dep": act["dep"], "status": "handed-off"})
            continue
        row = ex.verify(act)
        if not dl.is_ok(row):
            failure = f"{act['dep']}: installed, but `{dl.render_argv(act['verify'])}` reports {row['status']} {row.get('version') or ''}".strip()
            results.append({"dep": act["dep"], "status": "failed", "reason": failure})
            state.journal(mode="install", digest=digest, dep=act["dep"], status="verify-failed", reason=failure)
            continue
        if act["scope"] == "user":
            owned[act["dep"]] = {"recipe": act["recipe"], "version": row["version"], "path": row["path"],
                                 "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "digest": digest, "uninstall": act["uninstall"], "owns": act["owns"]}
            state.save_owned(owned)
        results.append({"dep": act["dep"], "status": "installed", "version": row["version"], "path": row["path"]})
        state.journal(mode="install", digest=digest, dep=act["dep"], status="installed", version=row["version"])
    lines = ["", "Result:"]
    for r in results:
        extra = f" {r.get('version') or ''} at {r['path']}" if r["status"] == "installed" else ""
        lines.append(f"  {r['status']:<11} {r['dep']}{extra}")
    for dep, steps in handed.items():
        why = ("setup never runs elevated commands" if any(s["kind"] == "manual" and s.get("admin") for s in steps)
               else "setup has no command it can run for this one here")
        lines.append(f"\n{dep}: run these yourself ({why}), then run the doctor again:")
        for s in steps:
            lines.append(f"  {dl.render_argv(s['argv'])}" if s["kind"] == "manual" else f"  # {s['text']}")
    if failure:
        lines.append(f"\nSTOPPED: {failure}\njournal: {state.setup / 'journal.jsonl'}")
    on_path = system.path.split(os.pathsep)
    missing_dirs = [d for d in dl.extra_bin_dirs(manifest, system) if d not in on_path and Path(d).is_dir()]
    if missing_dirs and any(r["status"] == "installed" for r in results):
        lines.append(f"\nAdd to PATH (setup does not edit shell profiles): {', '.join(missing_dirs)}")
    state.journal(mode="install", digest=digest, status="finished", failure=failure)
    emit(args, out, {"plan": plan, "results": results, "handed_off": handed, "failure": failure}, "\n".join(lines))
    return 4 if failure else 0


def do_uninstall(args, argv, manifest, system, state, out) -> int:
    owned = state.owned()
    names = args.uninstall or sorted(owned)
    left_alone = [n for n in names if n not in owned]
    actions = [{"dep": n, "recipe": owned[n]["recipe"], "uninstall": owned[n].get("uninstall", []),
                "owns": owned[n].get("owns", [])} for n in names if n in owned]
    plan = {"mode": "uninstall", "platform": "any", "actions": actions, "left_alone": left_alone}
    home = system.home.resolve()
    for act in actions:
        for p in act["owns"]:
            rp = Path(p).expanduser()
            if home not in rp.resolve().parents and home not in rp.parent.resolve().parents:
                raise Refusal(f"{act['dep']}: recorded path {p} is outside the home directory; not removing it")
    lines = ["Uninstall plan (only what setup installed):"]
    for act in actions:
        lines.append(f"  {act['dep']} ({act['recipe']})")
        lines += [f"    run:    {dl.render_argv(s['argv'])}" for s in act["uninstall"]]
        lines += [f"    remove: {p}" for p in act["owns"]]
    for n in left_alone:
        lines.append(f"  {n}: not installed by setup; left alone")
    if not actions:
        emit(args, out, {"plan": plan, "digest": None}, "\n".join(lines + ["Nothing to uninstall."]))
        return 0
    digest = digest_of(plan)
    if not args.apply:
        state.save_plan(digest, plan, summary_line(plan))
        state.journal(mode="uninstall-plan", digest=digest, status="planned", deps=[a["dep"] for a in actions])
        cmd = apply_command(argv, digest)
        emit(args, out, {"plan": plan, "digest": digest, "apply_command": cmd},
             "\n".join(lines) + f"\n\ndigest:     {digest}\napply with: {cmd}")
        return 0
    if not args.confirm:
        raise Refusal("--apply needs --confirm <digest>; run the dry run first and copy its digest")
    if args.confirm != digest:
        raise Refusal(f"digest mismatch: --confirm {args.confirm} but the uninstall plan now hashes to {digest}; run the dry run again")
    env = install_env(system.environ, os.pathsep.join(dl.extra_bin_dirs(manifest, system) + [system.path]))
    failure = None
    for act in actions:
        for s in act["uninstall"]:
            rc, output = system.run(s["argv"], timeout=600, env=env)
            state.journal(mode="uninstall", digest=digest, dep=act["dep"], argv=s["argv"], rc=rc,
                          status="ok" if rc == 0 else "failed", output=output[-800:])
            if rc != 0:
                failure = f"{act['dep']}: {dl.render_argv(s['argv'])} exited {rc}"
                break
        if failure:
            break
        for p in act["owns"]:
            path = Path(p).expanduser()
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            state.journal(mode="uninstall", digest=digest, dep=act["dep"], removed=str(path), status="ok")
        owned.pop(act["dep"], None)
        state.save_owned(owned)
        print(f"removed {act['dep']}", file=sys.stderr if args.json else out)
    if args.json:
        print(json.dumps({"plan": plan, "removed": [a["dep"] for a in actions if a["dep"] not in owned],
                          "failure": failure}, indent=2, default=str), file=out)
    elif failure:
        print(f"STOPPED: {failure}", file=out)
    return 4 if failure else 0


def do_status(args, state, out) -> int:
    owned = state.owned()
    journal = state.setup / "journal.jsonl"
    tail = journal.read_text(encoding="utf-8").splitlines()[-10:] if journal.is_file() else []
    if args.json:
        print(json.dumps({"owned": owned, "journal_tail": [json.loads(t) for t in tail], "setup_dir": str(state.setup)}, indent=2), file=out)
        return 0
    print(f"setup state: {state.setup}", file=out)
    if not owned:
        print("setup has installed nothing", file=out)
    for name, rec in sorted(owned.items()):
        print(f"  {name} {rec.get('version') or ''} via {rec['recipe']} at {rec.get('installed_at')}", file=out)
    return 0


def emit(args, out, data: dict, text: str) -> None:
    if args.json:
        print(json.dumps(data, indent=2, default=str), file=out)
    else:
        print(text, file=out)


def main(argv: Optional[List[str]] = None, system: Optional[dl.System] = None,
         manifest: Optional[dict] = None, out=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out = out or sys.stdout
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    manifest = manifest if manifest is not None else dl.load_manifest()
    errors = dl.validate_manifest(manifest)
    if errors:
        print("install.py: dependencies.json is invalid:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    system = system or dl.System()
    state = State(dl.data_dir(args.data_dir, system), system)
    try:
        if args.confirm and not args.apply:
            raise Refusal("--confirm is only meaningful with --apply")
        if args.status:
            return do_status(args, state, out)
        if args.uninstall is not None:
            return do_uninstall(args, argv, manifest, system, state, out)
        return do_install(args, argv, manifest, system, state, out)
    except Refusal as exc:
        if "--json" in argv:
            print(json.dumps({"refused": str(exc)}), file=out)
        else:
            print(f"install.py: REFUSED: {exc}", file=out)
        try:
            state.journal(mode="refusal", status="refused", reason=str(exc))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
