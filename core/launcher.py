"""Add The Isle Companion to the Linux app launcher (search bar / app menu).

``run.sh`` calls ``python -m core.launcher install`` on every start. It writes
a desktop entry and the app icon into the user's data directory
(``$XDG_DATA_HOME``, normally ``~/.local/share``) when they are missing or
point at an old location, and does nothing otherwise. Nothing is installed
system-wide. Set ``ISLE_COMPANION_NO_LAUNCHER=1`` to skip it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

APP_ID = "the-isle-companion"
ICON_SIZES = (64, 128, 256)
# Characters that require quoting an Exec argument (Desktop Entry spec).
_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')


def data_home(environ: dict[str, str]) -> Path:
    value = environ.get("XDG_DATA_HOME", "").strip()
    if value and Path(value).is_absolute():
        return Path(value)
    return Path(environ.get("HOME", str(Path.home()))) / ".local" / "share"


def _exec_argument(value: str) -> str:
    if any(char in _RESERVED for char in value):
        for char in ('\\', '"', '`', '$'):
            value = value.replace(char, "\\" + char)
        value = f'"{value}"'
    # Desktop entry string values also treat backslash as an escape.
    return value.replace("\\", "\\\\")


def _string_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def desktop_entry(project_root: Path) -> str:
    run_script = project_root / "run.sh"
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=The Isle Companion",
            "GenericName=Map companion",
            "Comment=Gateway map, Mini Map overlay and position tracking for The Isle: Evrima",
            f"Exec=sh {_exec_argument(str(run_script))}",
            f"Path={_string_value(str(project_root))}",
            f"Icon={APP_ID}",
            "Terminal=false",
            "Categories=Game;",
            "Keywords=isle;evrima;map;minimap;overlay;companion;",
            "StartupNotify=true",
            # Matches QGuiApplication.setDesktopFileName in app.py.
            f"StartupWMClass={APP_ID}",
            "",
        ]
    )


def _icon_paths(base: Path) -> dict[int, Path]:
    return {
        size: base / "icons" / "hicolor" / f"{size}x{size}" / "apps" / f"{APP_ID}.png"
        for size in ICON_SIZES
    }


def _write_icons(paths: dict[int, Path]) -> None:
    # Runs in run.sh's own process, so an offscreen Qt platform is safe here.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from ui.app_icon import render_app_icon

    app = QGuiApplication.instance() or QGuiApplication([])
    for size, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not render_app_icon(size).save(str(path), "PNG"):
            raise OSError(f"could not write {path}")
    del app


def _refresh_caches(base: Path, run: Callable[..., object]) -> None:
    commands = [
        ("update-desktop-database", [str(base / "applications")]),
        ("gtk-update-icon-cache", ["-q", "-t", "-f", str(base / "icons" / "hicolor")]),
    ]
    for tool, args in commands:
        executable = shutil.which(tool)
        if executable:
            try:
                run([executable, *args], capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                pass


def ensure_launcher(
    project_root: Path,
    *,
    environ: dict[str, str] | None = None,
    write_icons: Callable[[dict[int, Path]], None] = _write_icons,
    run: Callable[..., object] = subprocess.run,
) -> str:
    """Create or update the launcher entry. Returns what happened."""

    environ = dict(os.environ if environ is None else environ)
    if not sys.platform.startswith("linux"):
        return "skipped"
    if environ.get("ISLE_COMPANION_NO_LAUNCHER", "").strip() not in {"", "0"}:
        return "skipped"
    base = data_home(environ)
    entry_path = base / "applications" / f"{APP_ID}.desktop"
    icons = _icon_paths(base)
    wanted = desktop_entry(project_root.resolve())
    try:
        current = entry_path.read_text(encoding="utf-8")
    except OSError:
        current = None
    missing_icons = {size: path for size, path in icons.items() if not path.is_file()}
    if current == wanted and not missing_icons:
        return "unchanged"
    if missing_icons:
        write_icons(missing_icons)
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = entry_path.with_suffix(".desktop.tmp")
    temporary.write_text(wanted, encoding="utf-8")
    temporary.replace(entry_path)
    _refresh_caches(base, run)
    return "created" if current is None else "updated"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "install":
        print("usage: python -m core.launcher install", file=sys.stderr)
        return 2
    project_root = Path(__file__).resolve().parents[1]
    try:
        result = ensure_launcher(project_root)
    except OSError as exc:
        print(f"Could not add the app launcher entry: {exc}", file=sys.stderr)
        return 0  # Never block starting the app.
    if result in {"created", "updated"}:
        print("The Isle Companion is in your app launcher (search for \"Isle\").")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
