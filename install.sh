#!/usr/bin/env bash
# Set up a Luminary base station. Idempotent -- safe to re-run.
#
#   ./install.sh              # everything
#   ./install.sh --no-sudo    # skip the parts that need root
#
# Afterwards `luminary` is on PATH inside .venv, and the boards are reachable
# without re-granting access after every flash.

set -euo pipefail
cd "$(dirname "$0")"

WANT_SUDO=1
[ "${1:-}" = "--no-sudo" ] && WANT_SUDO=0

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- python env

say "Python environment"
if [ ! -x .venv/bin/python ]; then
  if python3 -c 'import ensurepip' 2>/dev/null; then
    python3 -m venv .venv
  else
    # Debian/Ubuntu split ensurepip into python3-venv, and PEP 668 blocks
    # installing it with pip. The standalone zipapp needs neither.
    warn "python3-venv missing; bootstrapping with virtualenv.pyz"
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/virtualenv.pyz" https://bootstrap.pypa.io/virtualenv.pyz
    python3 "$tmp/virtualenv.pyz" .venv
    rm -rf "$tmp"
  fi
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e '.[dev]'
echo "    luminary -> $(pwd)/.venv/bin/luminary"

# ------------------------------------------------------------ board access

if [ "$WANT_SUDO" = 1 ] && [ "$(uname)" = "Linux" ]; then
  say "Board access"
  if id -nG "$USER" | tr ' ' '\n' | grep -qx dialout; then
    echo "    already in the dialout group"
  else
    sudo usermod -aG dialout "$USER"
    warn "added $USER to dialout -- log out and back in for it to take effect"
  fi

  # A board gets a new device node every time it is flashed, so a one-off
  # chmod does not survive. uaccess re-applies on each plug-in.
  rule=/etc/udev/rules.d/60-luminary-scorpio.rules
  sudo tee "$rule" >/dev/null <<'RULES'
# Scorpio in application mode.
SUBSYSTEM=="tty", ATTRS{idVendor}=="239a", ATTRS{idProduct}=="8121", MODE="0660", GROUP="dialout", TAG+="uaccess"
# RP2040 ROM bootloader (BOOTSEL), so `luminary flash` can write the UF2.
SUBSYSTEM=="block", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0003", MODE="0660", GROUP="dialout", TAG+="uaccess"
RULES
  sudo udevadm control --reload-rules
  echo "    installed $rule"
fi

# -------------------------------------------------------------- conformance

say "Conformance toolchain"
missing=""
command -v g++ >/dev/null || missing="$missing g++"
command -v make >/dev/null || missing="$missing make"
if command -v node >/dev/null; then
  # The repo has no package.json, so decoder.js reads as CommonJS and its
  # `export` is a syntax error below Node 22, which auto-detects ESM.
  [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || missing="$missing node>=22"
else
  missing="$missing node>=22"
fi
if [ -n "$missing" ]; then
  warn "missing:$missing"
  warn "without these the JS and C++ decoder conformance tests SKIP rather than"
  warn "fail, so a green run silently omits them. On Debian/Ubuntu:"
  warn "  sudo apt install g++ make   # node 22+ from nodejs.org or nvm"
else
  echo "    complete"
fi

say "Done"
echo "    . .venv/bin/activate    # then: luminary --help"
