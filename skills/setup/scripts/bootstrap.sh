#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
#
# bootstrap.sh — the setup skill's first step: checks that a usable python3 (3.9 or later) exists
# before any Python runs, then hands every argument to core/deps/doctor.py. Without python3 it prints
# how to get one on this platform and exits 69; it never installs anything itself.
#
# Usage:
#   bash <plugin-root>/skills/setup/scripts/bootstrap.sh --stack cdk --json
#   bash <plugin-root>/skills/setup/scripts/bootstrap.sh --check     only the python3 check, no doctor
#
# On macOS, /usr/bin/python3 is a placeholder until the Command Line Tools are installed; running it
# opens Apple's install dialog, so the script asks xcode-select first and never triggers the dialog.
set -euo pipefail

MIN_PY_MAJOR=3
MIN_PY_MINOR=9          # docs/design-notes.md, "Python minimum": the python3 macOS ships by default
EX_UNAVAILABLE=69       # the core scripts' exit code for a missing prerequisite

src="${BASH_SOURCE[0]}"
[[ "$src" == */* ]] || src="./$src"
here="$(cd "${src%/*}" && pwd)"     # no dirname: this must work on a PATH that lacks coreutils
root="$(cd "$here/../../.." && pwd)"
doctor="$root/core/deps/doctor.py"

die()  { printf 'bootstrap: %s\n' "$1" >&2; exit "${2:-1}"; }

guidance() {
  case "${OSTYPE:-}" in
    darwin*)
      cat >&2 <<'EOF'
Install Apple's Command Line Tools, which provide python3 (3.9) and git:
  xcode-select --install
or install Python from https://www.python.org/downloads/macos/ (needs administrator rights).
EOF
      ;;
    linux*)
      if [[ -r /etc/os-release ]] && grep -qiE '^(ID|ID_LIKE)=.*(debian|ubuntu)' /etc/os-release; then
        printf 'Install python3 with your package manager (needs sudo):\n  sudo apt-get install -y python3\n' >&2
      else
        printf 'Install python3 with your package manager (needs sudo):\n  sudo dnf install -y python3    (sudo yum install -y python3 on Amazon Linux 2)\n' >&2
      fi
      ;;
    *)
      printf 'Native Windows is not supported in this release: install WSL2 (https://learn.microsoft.com/windows/wsl/install) and run setup inside it.\n' >&2
      ;;
  esac
}

# ------------------------------------------------------------------------------------ prerequisites
py="$(command -v python3 2>/dev/null || true)"
if [[ -z "$py" ]]; then
  printf 'bootstrap: python3 not found on PATH (%s.%s or later is required).\n' "$MIN_PY_MAJOR" "$MIN_PY_MINOR" >&2
  guidance
  exit "$EX_UNAVAILABLE"
fi
if [[ "${OSTYPE:-}" == darwin* && "$py" == "/usr/bin/python3" ]] && ! xcode-select -p >/dev/null 2>&1; then
  printf 'bootstrap: /usr/bin/python3 is a placeholder until the Command Line Tools are installed.\n' >&2
  guidance
  exit "$EX_UNAVAILABLE"
fi
"$py" -I -c "import sys; sys.exit(0 if sys.version_info >= ($MIN_PY_MAJOR, $MIN_PY_MINOR) else 1)" 2>/dev/null || {
  printf 'bootstrap: python3 is %s; %s.%s or later is required.\n' "$("$py" -V 2>&1)" "$MIN_PY_MAJOR" "$MIN_PY_MINOR" >&2
  guidance
  exit "$EX_UNAVAILABLE"
}

[[ "${1:-}" == "--check" ]] && { printf 'python3 ok: %s (%s)\n' "$("$py" -V 2>&1)" "$py"; exit 0; }
[[ -f "$doctor" ]] || die "core/deps/doctor.py not found under $root; the plugin is incomplete"
exec "$py" -I "$doctor" "$@"
