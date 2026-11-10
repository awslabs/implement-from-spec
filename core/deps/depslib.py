#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""core/deps/depslib.py — shared code for doctor.py, install.py and their tests.

Owns: loading and validating dependencies.json; platform and package-manager detection; version
detection and comparison; requirement evaluation per stack; recipe selection; variable expansion;
the setup data directory. Everything that touches the machine goes through one System object, so the
tests inject a fake command runner, a fake PATH and a fake downloader and nothing is ever installed or
fetched.

Python 3.9 compatible, standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "dependencies.json"
KEYS_DIR = HERE / "keys"
PROBES_DIR = HERE / "probes"
# Placeholders a detect command may carry, expanded by detect_argv (never by the shell).
DETECT_VARIABLES = {"deps_dir": str(HERE)}

USER_AGENT = "implement-from-spec-setup (python-urllib)"
EX_UNAVAILABLE = 69          # a required dependency is missing or too old (the core scripts' convention)
STACKS = ("terraform", "cdk", "cloudformation", "java", "python", "external-review")
LEVELS = ("required", "optional")
LABELS = ("official", "community")
PLATFORM_KEYS = ("macos", "debian", "rhel", "amzn", "fedora", "linux", "unix", "any")
DISTROS = ("macos", "debian", "rhel", "amzn", "fedora")
STUB_OSES = ("macos",)
STEP_KINDS = ("run", "manual", "download", "sha256", "gpg_key", "gpg_verify", "gpg_dearmor",
              "write_file", "script", "note", "resolve")
# A resolve step reads a file an earlier step downloaded (a checksum list) and binds one name from it, for
# releases whose file names carry the version behind a "latest" directory (Node.js). The later steps of the
# same recipe use it as {name}; the plan shows the placeholder and the pattern, the run shows the value.
RESOLVE_VAR_RE = re.compile(r"^[a-z][a-z_]*$")
# Variables a step may set for its own process (run and script steps), such as an installer's switch to
# leave shell profiles alone. Never a credential: the names are checked like install.py's scrubber.
STEP_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
STEP_ENV_DENY_RE = re.compile(r"TOKEN|SECRET|PASSW|CREDENTIAL|KEY|AUTH|^AWS_|^ANTHROPIC_|^CLAUDE_|^PATH$|^HOME$|^LD_|^DYLD_", re.I)
INTEGRITY_METHODS = ("gpg-signature", "gpg-signed-repository", "sha256", "pkg-signature",
                     "release-signature", "package-manager", "vendor-script", "none-documented")
REVIEW_AUTH = ("aws-profile", "api-key", "off")
OK_STATUSES = ("ok", "project-local", "unknown-version")

PACKAGE_MANAGERS = ("brew", "apt-get", "dnf", "yum", "pipx", "uv", "npm", "cargo", "winget", "winget.exe")


# --------------------------------------------------------------------------- the machine
class System:
    """The only gateway to the machine. Tests subclass it (see tests/fakes.py)."""

    def __init__(self, environ: Optional[Dict[str, str]] = None):
        self.environ = dict(os.environ if environ is None else environ)
        self.path = self.environ.get("PATH", os.defpath)
        self.home = Path(self.environ.get("HOME") or os.path.expanduser("~"))

    def which(self, name: str, extra_dirs: Sequence[str] = ()) -> Optional[str]:
        search = os.pathsep.join([str(d) for d in extra_dirs] + [self.path])
        return shutil.which(name, path=search)

    def run(self, argv: Sequence[str], timeout: int = 30, cwd: Optional[str] = None,
            env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
        """Runs an argument array (never a shell string); returns (exit code, stdout+stderr)."""
        try:
            # Argument array from the manifest and resolved tool paths, no shell: nothing to inject into
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
            proc = subprocess.run(list(argv), cwd=cwd, env=env if env is not None else self.environ,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except FileNotFoundError:
            return 127, f"{argv[0]}: not found"
        except subprocess.TimeoutExpired:
            return 124, f"{argv[0]}: timed out after {timeout}s"
        except OSError as exc:
            return 126, f"{argv[0]}: {exc}"
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

    def fetch(self, url: str, dest: Path) -> None:
        """Downloads one https URL to dest. Raises on any failure."""
        if not url.startswith("https://"):
            raise ValueError(f"refusing a non-https download: {url}")
        import urllib.request  # here, not at the top: the SessionStart notice imports this module and stays cheap
        dest.parent.mkdir(parents=True, exist_ok=True)
        # https-only is enforced above (the scheme check B310 asks for); urllib verifies certificates by default.
        # A named User-Agent: some vendor CDNs (astral.sh for the uv installer) answer urllib's default one
        # with 403 Forbidden.
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:  # noqa: S310  # nosec B310 - https-only URL
            shutil.copyfileobj(resp, out)

    def facts(self) -> Dict[str, str]:
        def read(path: str) -> str:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except OSError:
                return ""
        return {"sys_platform": sys.platform, "machine": _platform.machine(),
                "os_release": read("/etc/os-release"), "proc_version": read("/proc/version"),
                "wsl_distro": self.environ.get("WSL_DISTRO_NAME", "")}


# --------------------------------------------------------------------------- manifest
def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _is_url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def validate_manifest(data: dict, keys_dir: Path = KEYS_DIR) -> List[str]:
    """Returns every schema problem; an empty list means the manifest is valid."""
    errs: List[str] = []
    if data.get("schema") != 1:
        errs.append("schema must be 1")
    stacks = data.get("stacks")
    if not isinstance(stacks, dict) or set(stacks) != set(STACKS):
        errs.append(f"stacks must name exactly {', '.join(STACKS)}")
    keys = data.get("pinned_keys")
    if not isinstance(keys, dict):
        errs.append("pinned_keys must be an object")
        keys = {}
    for kid, key in keys.items():
        fpr = key.get("fingerprint", "")
        long_id = key.get("long_id", "")
        if not re.fullmatch(r"[0-9A-F]{40}", fpr) and not re.fullmatch(r"[0-9A-F]{16}", long_id):
            errs.append(f"pinned_keys.{kid}: needs a 40-hex fingerprint or a 16-hex long_id (upper case, no spaces)")
        if fpr and long_id and not fpr.endswith(long_id):
            errs.append(f"pinned_keys.{kid}: long_id is not the fingerprint's suffix")
        if not _is_url(key.get("source")):
            errs.append(f"pinned_keys.{kid}: source must be the https page that publishes it")
        if not key.get("uid"):
            errs.append(f"pinned_keys.{kid}: uid missing")
        if key.get("file") and not (keys_dir / key["file"]).is_file():
            errs.append(f"pinned_keys.{kid}: file keys/{key['file']} not found")
        if not key.get("file") and not _is_url(key.get("url")):
            errs.append(f"pinned_keys.{kid}: needs a bundled file or an https url")
    deps = data.get("dependencies")
    if not isinstance(deps, dict) or not deps:
        return errs + ["dependencies must be a non-empty object"]
    for name, dep in deps.items():
        p = f"dependencies.{name}"
        for field in ("purpose",):
            if not isinstance(dep.get(field), str) or not dep[field]:
                errs.append(f"{p}.{field} missing")
        nb = dep.get("needed_by")
        if not isinstance(nb, list) or not nb:
            errs.append(f"{p}.needed_by must be a non-empty list")
            nb = []
        for i, entry in enumerate(nb):
            if entry.get("stack") not in STACKS + ("core", "setup"):
                errs.append(f"{p}.needed_by[{i}].stack invalid: {entry.get('stack')}")
            if entry.get("level") not in LEVELS:
                errs.append(f"{p}.needed_by[{i}].level must be required or optional")
            if not entry.get("skill") or not entry.get("when"):
                errs.append(f"{p}.needed_by[{i}] needs skill and when")
        det = dep.get("detect", {})
        if not _str_list(det.get("command")):
            errs.append(f"{p}.detect.command must be a non-empty argument array")
        else:
            try:
                argv = detect_argv(dep)
            except KeyError as exc:
                errs.append(f"{p}.detect.command: {exc.args[0]}")
            else:
                for raw, arg in zip(det["command"], argv):
                    if "{deps_dir}" in raw and not Path(arg).is_file():
                        errs.append(f"{p}.detect.command: bundled file {raw} not found")
        stub = dep.get("stub")
        if stub is not None:
            if not _str_list(stub.get("paths")) or not _str_list(stub.get("probe")):
                errs.append(f"{p}.stub needs paths and a probe argument array")
            if stub.get("os", "macos") not in STUB_OSES:
                errs.append(f"{p}.stub.os must be one of {', '.join(STUB_OSES)}")
        rx = det.get("version_regex")
        if rx is not None:
            try:
                if re.compile(rx).groups < 1:
                    errs.append(f"{p}.detect.version_regex needs one capture group")
            except re.error as exc:
                errs.append(f"{p}.detect.version_regex: {exc}")
        mn = dep.get("minimum")
        if mn is not None:
            if not re.fullmatch(r"\d+(\.\d+)*", str(mn.get("version", ""))):
                errs.append(f"{p}.minimum.version must be dotted digits")
            if not mn.get("source"):
                errs.append(f"{p}.minimum.source missing (the page or decision that sets it)")
            rec = mn.get("recommended")
            if rec is not None:
                if not re.fullmatch(r"\d+(\.\d+)*", str(rec.get("version", ""))):
                    errs.append(f"{p}.minimum.recommended.version must be dotted digits")
                elif re.fullmatch(r"\d+(\.\d+)*", str(mn.get("version", ""))) and \
                        not version_at_least(rec["version"], mn["version"]):
                    errs.append(f"{p}.minimum.recommended.version is below minimum.version")
                if not rec.get("source"):
                    errs.append(f"{p}.minimum.recommended.source missing (the page or decision that sets it)")
                if not rec.get("why"):
                    errs.append(f"{p}.minimum.recommended.why missing (what an older release lacks)")
        if not _str_list(dep.get("verify", ["x"])):
            errs.append(f"{p}.verify must be an argument array")
        if not isinstance(dep.get("windows"), str) or "WSL" not in dep.get("windows", ""):
            errs.append(f"{p}.windows must be WSL2 guidance text")
        recipes = dep.get("recipes", {})
        if not isinstance(recipes, dict):
            errs.append(f"{p}.recipes must be an object")
            recipes = {}
        if dep.get("installable", True) and not recipes:
            errs.append(f"{p}: installable dependency without recipes")
        for pkey, lst in recipes.items():
            if pkey not in PLATFORM_KEYS:
                errs.append(f"{p}.recipes.{pkey}: unknown platform key")
                continue
            if not isinstance(lst, list) or not lst:
                errs.append(f"{p}.recipes.{pkey} must be a non-empty list")
                continue
            for r in lst:
                errs.extend(_validate_recipe(f"{p}.recipes.{pkey}.{r.get('id', '?')}", r, keys, deps))
    return errs


def _validate_recipe(p: str, r: dict, keys: dict, deps: dict) -> List[str]:
    errs: List[str] = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(r.get("id", ""))):
        errs.append(f"{p}: id must be kebab-case")
    if "distros" in r and not (_str_list(r["distros"]) and all(d in DISTROS for d in r["distros"])):
        errs.append(f"{p}: distros must list some of {', '.join(DISTROS)}")
    if r.get("label") not in LABELS:
        errs.append(f"{p}: label must be official or community")
    if not isinstance(r.get("admin"), bool):
        errs.append(f"{p}: admin must be true or false")
    if r.get("scope") not in ("user", "system"):
        errs.append(f"{p}: scope must be user or system")
    if not _is_url(r.get("source")):
        errs.append(f"{p}: source must be the vendor's https page")
    integ = r.get("integrity", {})
    if integ.get("method") not in INTEGRITY_METHODS:
        errs.append(f"{p}: integrity.method must be one of {', '.join(INTEGRITY_METHODS)}")
    if not integ.get("detail"):
        errs.append(f"{p}: integrity.detail missing")
    if integ.get("key") and integ["key"] not in keys:
        errs.append(f"{p}: integrity.key {integ['key']} is not in pinned_keys")
    for req in r.get("requires", []):
        if req not in deps:
            errs.append(f"{p}: requires unknown dependency {req}")
    steps = r.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + [f"{p}: steps must be a non-empty list"]
    has_admin = False
    for i, s in enumerate(steps):
        q = f"{p}.steps[{i}]"
        kind = s.get("kind")
        if kind not in STEP_KINDS:
            errs.append(f"{q}: unknown kind {kind}")
            continue
        if kind in ("run", "manual") and not _str_list(s.get("argv")):
            errs.append(f"{q}: argv must be a non-empty argument array")
        if kind == "run" and s.get("argv", [""])[0] in ("sudo", "doas", "su"):
            errs.append(f"{q}: an elevated command must be a manual step, never run")
        if kind == "manual":
            if not isinstance(s.get("admin"), bool):
                errs.append(f"{q}: manual steps state admin true or false")
            has_admin = has_admin or bool(s.get("admin"))
            if s.get("admin") and s.get("argv", [""])[0] != "sudo":
                errs.append(f"{q}: an admin step starts with sudo")
        if kind in ("download", "script") and not _is_url(s.get("url")):
            errs.append(f"{q}: url must be https")
        if kind in ("download", "script", "write_file", "gpg_dearmor") and not str(s.get("to", "")).startswith("{staging}/"):
            errs.append(f"{q}: to must be under {{staging}}/")
        if kind == "script" and not _str_list(s.get("interpreter")):
            errs.append(f"{q}: script needs an interpreter argument array")
        if kind in ("gpg_key", "gpg_verify") and s.get("key") not in keys:
            errs.append(f"{q}: key must name a pinned key")
        if kind == "sha256" and not (s.get("file") and (s.get("sums") or s.get("expected"))):
            errs.append(f"{q}: sha256 needs file and sums or expected")
        if kind == "write_file" and not isinstance(s.get("content"), str):
            errs.append(f"{q}: write_file needs content")
        if kind == "note" and not s.get("text"):
            errs.append(f"{q}: note needs text")
        if kind == "resolve":
            if not str(s.get("file", "")).startswith("{staging}/"):
                errs.append(f"{q}: resolve reads a file under {{staging}}/")
            if not RESOLVE_VAR_RE.match(str(s.get("var", ""))) or s.get("var") in PLATFORM_VARIABLE_NAMES:
                errs.append(f"{q}: resolve needs a var name (lower case) that is not a platform variable")
            try:
                if re.compile(str(s.get("pattern", ""))).groups != 1:
                    errs.append(f"{q}: resolve pattern needs exactly one capture group")
            except re.error as exc:
                errs.append(f"{q}: resolve pattern: {exc}")
        if "env" in s:
            env = s["env"]
            if kind not in ("run", "script") or not isinstance(env, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) and STEP_ENV_NAME_RE.match(k) and not STEP_ENV_DENY_RE.search(k)
                    for k, v in env.items()):
                errs.append(f"{q}: env is only for run and script steps: upper-case names, string values, no credential or path variables")
    first_manual = next((i for i, s in enumerate(steps) if s.get("kind") == "manual"), None)
    if first_manual is not None and any(s.get("kind") not in ("manual", "note") for s in steps[first_manual:]):
        errs.append(f"{p}: steps after the first manual step must be manual or note steps (install.py hands off there)")
    if r.get("admin") != has_admin:
        errs.append(f"{p}: admin is {r.get('admin')} but the steps {'do' if has_admin else 'do not'} include an admin step")
    if r.get("scope") == "user" and has_admin:
        errs.append(f"{p}: a user-scope recipe cannot need admin")
    for path in r.get("owns", []):
        if not str(path).startswith(("{home}/", "{user_bin}/")):
            errs.append(f"{p}: owns paths must be under {{home}} or {{user_bin}}")
    all_manual = all(s.get("kind") in ("manual", "note") for s in steps)
    if r.get("scope") == "user" and not all_manual and not (r.get("owns") or r.get("uninstall")):
        errs.append(f"{p}: a user-scope recipe records owns paths or uninstall steps")
    for s in r.get("uninstall", []):
        if s.get("kind") != "run" or not _str_list(s.get("argv")) or s["argv"][0] == "sudo":
            errs.append(f"{p}: uninstall steps are unelevated run steps")
    return errs


# --------------------------------------------------------------------------- platform
def _os_release(text: str) -> Dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def detect_platform(facts: Dict[str, str]) -> dict:
    sp = facts.get("sys_platform", "")
    machine = (facts.get("machine") or "").lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine or "unknown")
    info = {"os": "unknown", "distro": "unknown", "arch": arch, "wsl": False, "name": sp,
            "codename": "", "chain": []}
    if sp.startswith("darwin"):
        info.update(os="macos", distro="macos", name="macOS", chain=["macos", "unix", "any"])
    elif sp.startswith("linux"):
        rel = _os_release(facts.get("os_release", ""))
        ids = [rel.get("ID", "").lower()] + rel.get("ID_LIKE", "").lower().split()
        if "amzn" in ids:
            distro = "amzn"
        elif ids[0] == "fedora":
            distro = "fedora"
        elif any(i in ("rhel", "centos", "rocky", "almalinux", "ol", "fedora") for i in ids):
            distro = "rhel"
        elif any(i in ("debian", "ubuntu") for i in ids):
            distro = "debian"
        else:
            distro = "linux"
        chain = {"amzn": ["amzn", "rhel"], "fedora": ["fedora", "rhel"], "rhel": ["rhel"],
                 "debian": ["debian"], "linux": []}[distro] + ["linux", "unix", "any"]
        wsl = "microsoft" in facts.get("proc_version", "").lower() or bool(facts.get("wsl_distro"))
        info.update(os="linux", distro=distro, wsl=wsl, name=rel.get("PRETTY_NAME", "Linux"),
                    codename=rel.get("UBUNTU_CODENAME") or rel.get("VERSION_CODENAME", ""), chain=chain)
    elif sp in ("win32", "cygwin", "msys"):
        info.update(os="windows", distro="windows", name="Windows", chain=[])
    return info


def package_managers(system: System) -> Dict[str, str]:
    found = {}
    for pm in PACKAGE_MANAGERS:
        path = system.which(pm)
        if path:
            found[pm.replace(".exe", "")] = path
    return found


WINDOWS_GUIDANCE = ("Native Windows is not a supported platform for this release. Install WSL2 "
                    "(https://learn.microsoft.com/windows/wsl/install), open your Linux distribution, install "
                    "Claude Code there and run the setup again inside WSL2")


# --------------------------------------------------------------------------- versions
def parse_version(text: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text))


def version_at_least(have: str, need: str) -> bool:
    a, b = list(parse_version(have)), list(parse_version(need))
    width = max(len(a), len(b))
    return a + [0] * (width - len(a)) >= b + [0] * (width - len(b))


def extract_version(regex: Optional[str], output: str) -> Optional[str]:
    if not regex:
        return None
    m = re.search(regex, output, re.M)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- detection
def user_dirs(system: System) -> Dict[str, str]:
    home = str(system.home)
    return {"home": home, "user_local": f"{home}/.local", "user_bin": f"{home}/.local/bin"}


def extra_bin_dirs(manifest: dict, system: System) -> List[str]:
    """Directories setup installs into that may not be on PATH yet (reported, never edited)."""
    dirs = user_dirs(system)
    out = [dirs["user_bin"]]
    for d in manifest.get("extra_bin_dirs", []):
        out.append(expand(d, dirs))
    return out


def check_dep(system: System, name: str, dep: dict, project: Optional[Path],
              extra_dirs: Sequence[str] = ()) -> dict:
    det = dep["detect"]
    rec = (dep.get("minimum") or {}).get("recommended") or {}
    res = {"name": name, "status": "missing", "path": None, "version": None,
           "minimum": (dep.get("minimum") or {}).get("version"), "recommended": rec.get("version"),
           "notes": [], "warnings": []}
    if project is not None:
        for rel in dep.get("project_local", []):
            cand = project / rel
            if cand.is_file() and os.access(str(cand), os.X_OK):
                res.update(status="project-local", path=str(cand))
                res["notes"].append(f"the project's own {rel} is used; setup installs nothing for it")
                return res
    argv = detect_argv(dep)
    path = system.which(argv[0], extra_dirs)
    if not path:
        return res
    res["path"] = path
    stub = (dep.get("stub") or {})
    # The placeholder stubs (/usr/bin/git, python3, java without the Command Line Tools or a JDK) exist
    # only on macOS, and their probes (xcode-select, /usr/libexec/java_home) only there: elsewhere the
    # same path is the real tool and a failed probe means nothing.
    if path in stub.get("paths", []) and detect_platform(system.facts())["os"] == stub.get("os", "macos"):
        rc, _ = system.run(stub["probe"], timeout=10)
        if rc != 0:
            res["notes"].append(f"{path} is a placeholder, not an installation ({' '.join(stub['probe'])} exited {rc})")
            res["path"] = None
            return res
    rc, out = system.run([path] + argv[1:], timeout=30)
    version = extract_version(det.get("version_regex"), out)
    res["version"] = version
    if version is None:
        if rc != 0:
            res["status"] = "unusable"
            res["notes"].append(f"`{render_argv(det['command'])}` exited {rc}: {out.strip()[:200]}")
        elif det.get("version_regex"):
            res["status"] = "unknown-version"
            res["notes"].append("present, version unknown (its output carries no version setup recognises)")
        else:
            res["status"] = "unknown-version"
            res["notes"].append("present; the tool reports no version setup can check")
        return res
    if res["minimum"] and not version_at_least(version, res["minimum"]):
        res["status"] = "too-old"
        return res
    res["status"] = "ok"
    # Below the recommended version the tool works, with a weaker guarantee: a warning, never a gap.
    if res["recommended"] and not version_at_least(version, res["recommended"]):
        res["warnings"].append(f"below recommended {res['recommended']}: {rec['why']}")
    return res


def detect_argv(dep: dict) -> List[str]:
    """The detect command with its {deps_dir} placeholders expanded (a probe file bundled under
    core/deps/, such as the template cloudformation-validate validates because it has no --version)."""
    return [expand(a, DETECT_VARIABLES) for a in dep["detect"]["command"]]


def is_ok(result: Optional[dict]) -> bool:
    return bool(result) and result["status"] in OK_STATUSES


# --------------------------------------------------------------------------- requirements
def project_conditions(project: Optional[Path]) -> List[str]:
    """Conditions read from the project's own files (read-only)."""
    conds: List[str] = []
    if project is None:
        return conds
    cdk = project / "cdk.json"
    if cdk.is_file():
        try:
            app = str(json.loads(cdk.read_text(encoding="utf-8")).get("app", ""))
        except (OSError, ValueError):
            app = ""
        if re.search(r"\b(mvn|mvnw|gradle|gradlew|java)\b", app) or (project / "pom.xml").is_file():
            conds.append("cdk-java")
        if re.search(r"\bpython3?\b", app):
            conds.append("cdk-python")
    if (project / "pom.xml").is_file():
        conds.append("build-maven")
    if (project / "build.gradle").is_file() or (project / "build.gradle.kts").is_file():
        conds.append("build-gradle")
    return conds


def expand_stacks(stacks: Sequence[str]) -> List[str]:
    if not stacks or "all" in stacks:
        return list(STACKS)
    return [s for s in STACKS if s in stacks]


def evaluate(manifest: dict, system: System, stacks: Sequence[str], conditions: Sequence[str],
             project: Optional[Path]) -> dict:
    """Detects every dependency the stacks touch and decides what each stack needs."""
    stacks = expand_stacks(stacks)
    deps = manifest["dependencies"]
    extra = extra_bin_dirs(manifest, system)
    conds = set(conditions)
    rows: Dict[str, dict] = {}
    for name, dep in deps.items():
        entries = [e for e in dep["needed_by"] if e["stack"] in stacks or e["stack"] == "core"]
        if not entries:
            continue
        level = None
        reasons = []
        for e in entries:
            active = not e.get("if") or e["if"] in conds
            eff = e["level"] if active else "conditional"
            reasons.append({"stack": e["stack"], "skill": e["skill"], "level": eff, "when": e["when"],
                            "if": e.get("if")})
            rank = {"required": 3, "optional": 2, "conditional": 1}
            if level is None or rank[eff] > rank[level]:
                level = eff
        row = check_dep(system, name, dep, project, extra)
        row.update(level=level, purpose=dep["purpose"], needed_for=reasons,
                   group=dep.get("group"), installable=dep.get("installable", True),
                   minimum_source=(dep.get("minimum") or {}).get("source"))
        rows[name] = row
    # Alternatives: one member of a group satisfies it (Maven or Gradle; pipx or uv).
    groups: Dict[str, List[str]] = {}
    for name, row in rows.items():
        if row["group"]:
            groups.setdefault(row["group"], []).append(name)
    prefer = manifest.get("group_preference", {})
    for gname, members in groups.items():
        order = sorted(members, key=lambda m: _group_rank(m, prefer.get(gname, {}), conds))
        satisfied = [m for m in order if is_ok(rows[m])]
        lead = satisfied[0] if satisfied else order[0]
        for m in members:
            if m != lead and rows[m]["level"] == "required":
                rows[m]["level"] = "alternative"
                rows[m]["notes"].append(f"one of {', '.join(order)} is needed; {lead} "
                                        f"{'is present' if satisfied else 'is the one offered'}")
    return {"stacks": stacks, "conditions": sorted(conds), "rows": rows}


def _group_rank(member: str, prefs: dict, conds: set) -> int:
    """0 when a project condition names this member (pom.xml prefers Maven), else its default order."""
    for cond, first in prefs.items():
        if cond != "order" and cond in conds and first == member:
            return 0
    order = prefs.get("order", [])
    return 1 + order.index(member) if member in order else 99


# --------------------------------------------------------------------------- recipes
def expand(value: str, variables: Dict[str, str]) -> str:
    def sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in variables:
            raise KeyError(f"unknown variable {{{key}}} in {value!r}")
        return variables[key]
    return re.sub(r"\{([a-z_]+)\}", sub, value)


PLATFORM_VARIABLE_NAMES = ("home", "user_local", "user_bin", "staging", "arch", "arch_aws", "arch_go", "arch_sam",
                           "arch_corretto", "arch_node", "deb_arch", "codename", "rpm_pm", "java_major", "deps_dir")


def platform_variables(plat: dict, system: System, staging: str, java_major: str = "21") -> Dict[str, str]:
    arch = plat["arch"]
    is_arm = arch == "arm64"
    v = dict(user_dirs(system))
    rpm_pm = "dnf" if system.which("dnf") else "yum"
    v.update(staging=staging, arch=arch,
             arch_aws="aarch64" if is_arm else "x86_64",
             arch_go="arm64" if is_arm else "amd64",
             arch_sam="arm64" if is_arm else "x86_64",
             arch_corretto="aarch64" if is_arm else "x64",
             arch_node="arm64" if is_arm else "x64",
             deb_arch="arm64" if is_arm else "amd64",
             codename=plat.get("codename") or "CODENAME-UNKNOWN",
             rpm_pm=rpm_pm, java_major=str(java_major))
    return v


def candidate_recipes(dep: dict, plat: dict) -> List[dict]:
    """The recipes for this platform, most specific first. A recipe with `distros` is offered only on
    those distributions, so a RHEL-only repository never reaches Amazon Linux or Fedora through the
    chain's rhel fallback."""
    out: List[dict] = []
    for key in plat["chain"]:
        for r in dep.get("recipes", {}).get(key, []):
            if "distros" in r and plat.get("distro") not in r["distros"]:
                continue
            out.append(r)
    return out


PLACEHOLDER_RE = re.compile(r"<[a-z][a-z-]*>")


def instructions_only(recipe: dict) -> bool:
    """True when setup cannot run any step of the recipe: notes, and manual steps still carrying a
    <placeholder> the user has to fill in (a release name that carries the version)."""
    return all(s.get("kind") == "note" or (s.get("kind") == "manual" and any(PLACEHOLDER_RE.search(a) for a in s.get("argv", [])))
               for s in recipe.get("steps", []))


def choose_recipe(manifest: dict, name: str, plat: dict, rows: Dict[str, dict], system: System,
                  override: Optional[str] = None, _depth: int = 0) -> Tuple[Optional[dict], List[str], str]:
    """Picks the first viable recipe. Returns (recipe, missing installable prerequisites, reason)."""
    dep = manifest["dependencies"][name]
    if not dep.get("installable", True):
        return None, [], dep.get("install_note", "setup does not install this; see its documentation")
    cands = candidate_recipes(dep, plat)
    if override:
        cands = [r for r in cands if r["id"] == override]
        if not cands:
            return None, [], f"recipe {override} does not exist for {plat['distro']}"
    if not cands:
        return None, [], f"no recipe for {plat['name']}"
    # A recipe setup can run (even one that first needs a prerequisite installed) beats one that only
    # prints instructions: Node.js on Linux is unpacked by setup once tar is there, not handed to the user.
    for group in ([r for r in cands if not instructions_only(r)], [r for r in cands if instructions_only(r)]):
        fallback = None
        for r in group:
            missing = [t for t in r.get("requires", []) if not is_ok(_status(manifest, t, rows, system))]
            if not missing:
                return r, [], ""
            installable = all(_depth < 3 and choose_recipe(manifest, t, plat, rows, system, None, _depth + 1)[0]
                              for t in missing)
            if installable and fallback is None:
                fallback = (r, missing)
        if fallback:
            return fallback[0], fallback[1], ""
    need = sorted({t for r in cands for t in r.get("requires", [])})
    return None, [], f"every recipe needs a tool that is missing and that setup cannot install ({', '.join(need)})"


def _status(manifest: dict, name: str, rows: Dict[str, dict], system: System) -> dict:
    if name not in rows:
        rows[name] = check_dep(system, name, manifest["dependencies"][name], None,
                               extra_bin_dirs(manifest, system))
        rows[name].setdefault("level", "prerequisite")
    return rows[name]


def render_argv(argv: Sequence[str]) -> str:
    import shlex
    return " ".join(shlex.quote(a) for a in argv)


def describe_step(step: dict) -> str:
    kind = step["kind"]
    env = "".join(f"{k}={v} " for k, v in sorted((step.get("env") or {}).items()))
    if kind == "run":
        return f"run:      {env}{render_argv(step['argv'])}"
    if kind == "manual":
        who = "YOU RUN (admin)" if step.get("admin") else "YOU RUN"
        return f"{who}: {render_argv(step['argv'])}"
    if kind == "download":
        return f"download: {step['url']} -> {step['to']}"
    if kind == "sha256":
        src = step.get("sums") or step.get("expected")
        return f"sha256:   {step['file']} against {src}"
    if kind == "gpg_key":
        return f"gpg key:  import {step.get('file') or 'the bundled key'} into a private keyring; require fingerprint {step.get('fingerprint', '?')}"
    if kind == "gpg_verify":
        return f"gpg sig:  {step['signature']} over {step['file']}, signed by {step.get('fingerprint', '?')}"
    if kind == "gpg_dearmor":
        return f"gpg:      dearmor {step['file']} -> {step['to']}"
    if kind == "write_file":
        return f"write:    {step['to']} ({len(step['content'])} bytes): {step['content'].strip()}"
    if kind == "script":
        return (f"script:   {step['url']} (piped remote script; downloaded, shown, sha256 {step.get('sha256', '?')[:16]}…) "
                f"run as {env}{render_argv(step['interpreter'] + [step['to']] + step.get('args', []))}")
    if kind == "resolve":
        return (f"resolve:  {{{step['var']}}} = the name in {Path(step['file']).name} matching {step['pattern']} "
                "(read when the step runs)")
    if kind == "note":
        return f"note:     {step['text']}"
    return kind


# --------------------------------------------------------------------------- data directory
def data_dir(cli_value: Optional[str], system: System) -> Path:
    """The setup state directory: <--data-dir>/setup when given, else
    ${XDG_STATE_HOME:-~/.local/state}/implement-from-spec/setup.

    $CLAUDE_PLUGIN_DATA is deliberately not consulted. Claude Code exports it to hook commands but not to
    the Bash tool (plugins reference, "Where each variable resolves"), so a script run from a skill's Bash
    call cannot read it, and a resolution that read it would put the doctor's result in one place when a
    skill runs the doctor and look for it in another when the SessionStart hook reads it. HOME and
    XDG_STATE_HOME are the same in both, so every script resolves the same directory with no flag."""
    if cli_value:
        return Path(cli_value).expanduser() / "setup"
    state = system.environ.get("XDG_STATE_HOME") or str(system.home / ".local" / "state")
    return Path(state) / "implement-from-spec" / "setup"


# The doctor's last result, read by the SessionStart notice (session-notice.py) so a session start never
# probes a tool. One small JSON object under <data>/setup/.
DOCTOR_CACHE = "doctor-last.json"


def doctor_cache_path(system: System) -> Path:
    """Where a doctor run without --data-dir saves its result, and the only place the notice reads it."""
    return data_dir("", system) / DOCTOR_CACHE


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


Runner = Callable[[Sequence[str]], Tuple[int, str]]


def expand_recipe(manifest: dict, name: str, recipe: dict, variables: Dict[str, str]) -> dict:
    """The recipe with every {placeholder} expanded and the pinned trust material copied into its
    steps, so the plan (and so the digest) carries the exact URLs, commands and fingerprints."""
    keys = manifest.get("pinned_keys", {})
    # A resolve step's name is bound when the step runs: until then it stays {name} in the plan.
    variables = dict(variables, **{s["var"]: "{" + s["var"] + "}" for s in recipe["steps"] if s.get("kind") == "resolve"})

    def ex(value):
        if isinstance(value, str):
            return expand(value, variables)
        if isinstance(value, list):
            return [ex(v) for v in value]
        if isinstance(value, dict):
            return {k: ex(v) for k, v in value.items()}
        return value

    steps = []
    for step in recipe["steps"]:
        s = ex(step)
        if s["kind"] in ("gpg_key", "gpg_verify"):
            key = keys[s["key"]]
            s["fingerprint"] = key.get("fingerprint") or key["long_id"]
            s["pin"] = "fingerprint" if key.get("fingerprint") else "long_id"
            if s["kind"] == "gpg_key" and not s.get("file"):
                s["file"] = str(KEYS_DIR / key["file"])
                s["bundled"] = True
        steps.append(s)
    integrity = dict(recipe["integrity"])
    if integrity.get("key"):
        key = keys[integrity["key"]]
        integrity["pinned"] = key.get("fingerprint") or key["long_id"]
        integrity["key_source"] = key["source"]
    return {"dep": name, "recipe": recipe["id"], "label": recipe["label"], "admin": recipe["admin"],
            "scope": recipe["scope"], "source": recipe["source"], "integrity": integrity,
            "requires": list(recipe.get("requires", [])), "steps": steps,
            "owns": ex(list(recipe.get("owns", []))), "uninstall": ex(list(recipe.get("uninstall", [])))}


def staging_root(setup_dir: Path) -> Path:
    return setup_dir / "staging"


def private_dir(path: Path) -> None:
    """Create path (and its parents) and make the directory itself 0700, as the gate's state directory is: the
    setup state (plans, journal, owned.json, downloaded scripts, the doctor's result) is the user's alone.
    An existing directory is tightened too, so state from an earlier version becomes private (G8)."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def write_private(path: Path, text: str, append: bool = False) -> None:
    """Write (or append to) a file created 0600; an existing file is tightened to 0600 first (G8)."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(str(path), flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        os.close(fd)
        raise
    with os.fdopen(fd, "a" if append else "w", encoding="utf-8") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- sibling modules
def load_sibling(name: str, file: str):
    """core/deps/<file> as module `name`, loaded by file path from this directory, adding nothing to sys.path.

    Setup's scripts run as `python3 -I`, which keeps the script's directory, PYTHONPATH and the user's
    site-packages off sys.path, so no file next to them can stand in for a standard-library module (TM-40);
    they reach their siblings only through this function and the `_depslib` bootstrap that loads this module
    the same way (doctor.py, install.py, install-ask-hook.py, session-notice.py). A module of that name
    already loaded from the same file (the tests import depslib) is reused."""
    import importlib.util  # here, not at the top: the SessionStart notice imports this module and stays cheap
    path = HERE / file
    loaded = sys.modules.get(name)
    if loaded is not None and Path(getattr(loaded, "__file__", "") or ".").resolve() == path:
        return loaded
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
