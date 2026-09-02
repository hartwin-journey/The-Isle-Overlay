"""Build an optional local PyInstaller bundle on Windows or Linux."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _clean_native_search_path() -> None:
    """Prevent unrelated developer tools on PATH from leaking DLLs into the bundle."""

    if os.name != "nt":
        return
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


def build_arguments(platform_name: str | None = None) -> list[str]:
    """Return platform-correct PyInstaller arguments without personal config data."""

    platform_name = os.name if platform_name is None else platform_name
    data_separator = ";" if platform_name == "nt" else ":"
    arguments = [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "TheIsleCompanion",
        "--contents-directory",
        ".",
        "--add-data",
        f"data{data_separator}data",
        "--add-data",
        f"map{data_separator}map",
        "--add-data",
        f"ui/icons{data_separator}ui/icons",
    ]
    if platform_name == "nt":
        arguments.extend(
            [
                "--add-data",
                f"core/windows_ocr.ps1{data_separator}core",
            ]
        )
    arguments.append("app.py")
    return arguments


def main() -> int:
    try:
        from PyInstaller.__main__ import run
    except ImportError:
        print("PyInstaller is not installed. Run: py -m pip install -r requirements-dev.txt")
        return 1

    project_root = Path(__file__).resolve().parents[1]
    os.chdir(project_root)
    _clean_native_search_path()
    run(build_arguments())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
