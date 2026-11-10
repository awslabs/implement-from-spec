#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""core/deps/doctor.py — reports the binary dependencies the plugin's skills need. Never installs.

Detects the platform and the package managers present, then checks each dependency the chosen stacks
need: present, missing or too old, with the version found, the minimum and where that minimum comes
from, and for every gap the recipe setup would offer. A version at or above the minimum but below a
dependency's recommended version is reported as a warning and does not change the exit code. Project-local tools (./mvnw, ./gradlew,
node_modules/.bin/cdk) are reported and preferred; nothing is ever installed into a project.

Reads only: PATH, the version output of each tool, /etc/os-release, /proc/version and the project's
cdk.json, pom.xml and build.gradle(.kts). Writes one file: its result summary,
<data>/setup/doctor-last.json (the stacks checked, the required gaps, the time), which the optional
SessionStart notice (session-notice.py) reads instead of probing tools; --no-cache skips it.

Usage:
  python3 -I <plugin-root>/core/deps/doctor.py --stack cdk --json
  python3 -I <plugin-root>/core/deps/doctor.py --stack all
  python3 -I <plugin-root>/core/deps/doctor.py --stack java --project ~/src/service --java-major 25

Exit codes: 0 every required dependency is present; 69 a required dependency is missing, too old or
unusable; 2 invalid arguments; 1 the manifest is invalid.

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


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

GAP_STATUSES = ("missing", "too-old", "unusable")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="doctor.py", allow_abbrev=False,
                                 description="Report the binary dependencies of the implement-from-spec skills; installs nothing.")
    ap.add_argument("--stack", action="append", choices=list(dl.STACKS) + ["all"],
                    help="stack to check (repeatable); default all")
    ap.add_argument("--project", default=".", help="project directory to read for wrappers and CDK app language (default: the current directory)")
    ap.add_argument("--review-auth", choices=dl.REVIEW_AUTH, default="off",
                    help="external reviewer authentication: off (default, the reviewer is off by default) needs nothing, aws-profile needs the AWS CLI, api-key needs curl and jq")
    ap.add_argument("--if", dest="conditions", action="append", default=[], metavar="CONDITION",
                    help="force a condition: cdk-java, cdk-python, build-maven, build-gradle")
    ap.add_argument("--java-major", default="21", choices=["17", "21", "25"], help="the Corretto major version setup offers")
    ap.add_argument("--data-dir", default="", help="override the state directory (default: ${XDG_STATE_HOME:-~/.local/state}/implement-from-spec, the only place the session notice reads)")
    ap.add_argument("--json", action="store_true", help="print one JSON object")
    ap.add_argument("--quiet", action="store_true", help="print one line, only when a required dependency is missing")
    ap.add_argument("--no-cache", action="store_true",
                    help=f"do not save the result summary to <data>/setup/{dl.DOCTOR_CACHE} (the session notice reads it)")
    return ap


def write_cache(setup: Path, res: dict, args: argparse.Namespace) -> None:
    """Saves the result summary for the SessionStart notice. Best effort: a read-only or missing data
    directory never changes the doctor's output or exit code."""
    record = {"schema": 1, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "exit": res["exit"], "stacks": res["stacks"], "review_auth": args.review_auth,
              "platform": res["platform"]["name"], "required_gaps": res["summary"]["required_gaps"],
              "too_old": res["summary"]["too_old"], "optional_missing": res["summary"]["optional_missing"]}
    try:
        dl.private_dir(setup)
        tmp = setup / f".{dl.DOCTOR_CACHE}.{os.getpid()}.tmp"
        dl.write_private(tmp, json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, setup / dl.DOCTOR_CACHE)
    except OSError:
        pass


def conditions_for(args: argparse.Namespace, project: Optional[Path]) -> List[str]:
    conds = set(dl.project_conditions(project)) | set(args.conditions)
    if args.review_auth == "aws-profile":
        conds.add("review-aws-profile")
    elif args.review_auth == "api-key":
        conds.add("review-api-key")
    return sorted(conds)


def report(system: dl.System, args: argparse.Namespace, manifest: dict) -> dict:
    project = Path(args.project).expanduser().resolve() if args.project else None
    if project is not None and not project.is_dir():
        project = None
    plat = dl.detect_platform(system.facts())
    conds = conditions_for(args, project)
    ev = dl.evaluate(manifest, system, args.stack or ["all"], conds, project)
    setup = dl.data_dir(args.data_dir, system)
    rows = ev["rows"]
    out_rows = []
    for name in sorted(rows, key=lambda n: (_rank(rows[n]["level"]), n)):
        row = dict(rows[name])
        if row["level"] == "prerequisite":
            continue
        row["offer"] = None
        if row["status"] in GAP_STATUSES and plat["os"] != "windows":
            row["offer"] = offer(manifest, name, row, plat, rows, system, setup, args.java_major)
        out_rows.append(row)
    required_gaps = [r["name"] for r in out_rows if r["level"] == "required" and r["status"] in GAP_STATUSES]
    on_path = set(system.path.split(":"))
    path_hint = [d for d in dl.extra_bin_dirs(manifest, system) if d not in on_path]
    result = {
        "platform": plat,
        "windows_guidance": dl.WINDOWS_GUIDANCE if plat["os"] == "windows" else None,
        "package_managers": dl.package_managers(system),
        "stacks": ev["stacks"], "conditions": ev["conditions"],
        "project": str(project) if project else None,
        "dependencies": out_rows,
        "summary": {
            "required_gaps": required_gaps,
            "too_old": [r["name"] for r in out_rows if r["status"] == "too-old"],
            "below_recommended": [r["name"] for r in out_rows if r.get("warnings")],
            "optional_missing": [r["name"] for r in out_rows if r["level"] != "required" and r["status"] in GAP_STATUSES],
            "project_local": [r["name"] for r in out_rows if r["status"] == "project-local"],
        },
        "dirs_not_on_path": path_hint,
        "exit": dl.EX_UNAVAILABLE if required_gaps or plat["os"] == "windows" else 0,
    }
    return result


def _rank(level: str) -> int:
    return {"required": 0, "alternative": 1, "optional": 2, "conditional": 3}.get(level, 4)


def offer(manifest: dict, name: str, row: dict, plat: dict, rows: dict, system: dl.System,
          setup: Path, java_major: str) -> dict:
    if row["status"] == "too-old":
        return {"action": "not-replaced",
                "text": f"{name} {row['version']} at {row['path']} is older than {row['minimum']}; setup never "
                        "replaces or downgrades an existing install. Upgrade it through the channel that installed it"}
    if row["status"] == "unusable":
        return {"action": "not-replaced",
                "text": f"{row['path']} is on PATH but does not run; fix or remove it, then run the doctor again"}
    recipe, prereqs, reason = dl.choose_recipe(manifest, name, plat, rows, system)
    if recipe is None:
        return {"action": "blocked", "text": reason}
    variables = dl.platform_variables(plat, system, str(dl.staging_root(setup) / name), java_major)
    plan = dl.expand_recipe(manifest, name, recipe, variables)
    return {"action": "install", "recipe": plan["recipe"], "label": plan["label"], "admin": plan["admin"],
            "scope": plan["scope"], "source": plan["source"], "integrity": plan["integrity"]["detail"],
            "prerequisites": prereqs, "commands": [dl.describe_step(s) for s in plan["steps"]]}


def print_text(res: dict) -> None:
    plat = res["platform"]
    wsl = " (WSL2)" if plat.get("wsl") else ""
    print(f"platform: {plat['name']}{wsl}, {plat['arch']}")
    if res["windows_guidance"]:
        print(res["windows_guidance"])
        return
    pms = ", ".join(sorted(res["package_managers"])) or "none found"
    print(f"package managers: {pms}")
    print(f"stacks: {', '.join(res['stacks'])}" + (f"; conditions: {', '.join(res['conditions'])}" if res["conditions"] else ""))
    print()
    for r in res["dependencies"]:
        ver = r["version"] or ""
        need = f" (needs >= {r['minimum']})" if r["minimum"] else ""
        where = f" {r['path']}" if r["path"] else ""
        print(f"{r['status']:<16}{r['name']:<24}{r['level']:<12}{ver}{need}{where}")
        for note in r["notes"]:
            print(f"{'':16}  {note}")
        for warning in r.get("warnings", []):
            print(f"{'':16}  warning: {r['name']} {ver}: {warning}")
        off = r.get("offer")
        if off:
            if off["action"] == "install":
                adm = "needs admin" if off["admin"] else "no admin"
                print(f"{'':16}  offer: {off['recipe']} [{off['label']}, {off['scope']} scope, {adm}] {off['source']}")
                if off["prerequisites"]:
                    print(f"{'':16}  first: {', '.join(off['prerequisites'])}")
                for c in off["commands"]:
                    print(f"{'':16}    {c}")
            else:
                print(f"{'':16}  {off['text']}")
    s = res["summary"]
    print()
    if s["required_gaps"]:
        print(f"required gaps: {', '.join(s['required_gaps'])}")
    else:
        print("every required dependency is present")
    if s["optional_missing"]:
        print(f"optional or alternative, missing: {', '.join(s['optional_missing'])}")
    if res["dirs_not_on_path"]:
        print(f"not on PATH (setup installs here): {', '.join(res['dirs_not_on_path'])}")


def main(argv: Optional[List[str]] = None, system: Optional[dl.System] = None,
         manifest: Optional[dict] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0) and 2
    manifest = manifest if manifest is not None else dl.load_manifest()
    errors = dl.validate_manifest(manifest)
    if errors:
        print("doctor.py: dependencies.json is invalid:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    system = system or dl.System()
    res = report(system, args, manifest)
    if not args.no_cache:
        write_cache(dl.data_dir(args.data_dir, system), res, args)
    if args.json:
        print(json.dumps(res, indent=2))
    elif args.quiet:
        if res["summary"]["required_gaps"]:
            print(f"implement-from-spec: missing {', '.join(res['summary']['required_gaps'])}; run /implement-from-spec:setup")
    else:
        print_text(res)
    return res["exit"]


if __name__ == "__main__":
    sys.exit(main())
