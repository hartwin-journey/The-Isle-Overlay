#!/usr/bin/env sh
# Launch The Isle Companion, setting up its Python environment on first run.
#
# Creates .venv if needed, installs requirements.txt, and on Wayland desktops
# that support the Mini Map overlay (KDE, Sway, Hyprland, niri, COSMIC, ...)
# also installs requirements-wayland.txt. Installs are skipped on later runs
# unless the requirements or the desktop change. Missing system packages
# (Tesseract; grim on wlroots desktops) are installed after asking for your
# password; set ISLE_COMPANION_NO_SYSTEM_INSTALL=1 to skip that.
set -eu
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
    echo "First run: creating a Python environment in .venv ..."
    if ! python3 -m venv .venv; then
        echo "Could not create .venv. On Debian/Ubuntu install it first:" >&2
        echo "    sudo apt install python3-venv" >&2
        exit 1
    fi
fi

STAMP=.venv/.isle-companion-setup
WANT="$(cat requirements.txt requirements-wayland.txt 2>/dev/null | cksum) ${XDG_CURRENT_DESKTOP:-} ${XDG_SESSION_TYPE:-}"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$WANT" ]; then
    echo "Installing Python requirements ..."
    "$PY" -m pip install --disable-pip-version-check -q -r requirements.txt
    if "$PY" -m core.environment wants-pywayland; then
        echo "Wayland overlay desktop detected: installing Mini Map overlay support ..."
        if ! "$PY" -m pip install --disable-pip-version-check -q -r requirements-wayland.txt; then
            echo "Warning: overlay support could not be installed; the Mini Map" >&2
            echo "will use a normal window. See requirements-wayland.txt." >&2
        fi
    fi
    # Tesseract (and grim on wlroots desktops) are system packages: offer to
    # install them now. Asks for your password via sudo, or a graphical
    # prompt (pkexec) when started without a terminal.
    "$PY" -m core.environment install-system || true
    printf '%s' "$WANT" > "$STAMP"
    "$PY" -m core.environment || true
fi

exec "$PY" app.py "$@"
