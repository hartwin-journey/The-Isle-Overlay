"""Build the optional local PyInstaller bundle from a clean DLL search path."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _clean_native_search_path() -> None:
    """Prevent unrelated developer tools on PATH from leaking DLLs into the bundle."""

    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates = [
        Path(sys.executable).resolve().parent,
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(sys.base_prefix).resolve() / "DLLs",
        windows / "System32",
        windows,
    ]
    unique: list[str] = []
    for candidate in candidates:
        value = str(candidate)
        if value.casefold() not in {item.casefold() for item in unique}:
            unique.append(value)
    os.environ["PATH"] = os.pathsep.join(unique)


def main() -> int:
    try:
        from PyInstaller.__main__ import run
    except ImportError:
        print("PyInstaller is not installed. Run: py -m pip install -r requirements-dev.txt")
        return 1

    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    _clean_native_search_path()
    run(
        [
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            "TheIsleCompanion",
            "--contents-directory",
            ".",
            "--add-data",
            "data;data",
            "--add-data",
            "map;map",
            "--add-data",
            "core/windows_ocr.ps1;core",
            "app.py",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
