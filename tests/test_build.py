import PyInstaller.__main__

from tools import build_exe
from tools.build_exe import build_arguments


def test_windows_build_includes_local_ocr_bridge_and_windows_data_separator():
    arguments = build_arguments("nt")
    assert arguments[:5] == ["--noconfirm", "--clean", "--windowed", "--name", "TheIsleCompanion"]
    assert ["--contents-directory", "."] == arguments[5:7]
    assert "data;data" in arguments
    assert "assets/map;assets/map" in arguments
    assert "core/windows_ocr.ps1;core" in arguments


def test_linux_build_uses_posix_separator_and_omits_windows_ocr_bridge():
    arguments = build_arguments("posix")
    assert "data:data" in arguments
    assert "assets/map:assets/map" in arguments
    assert not any("windows_ocr.ps1" in argument for argument in arguments)


def test_build_entrypoint_runs_pyinstaller_with_the_project_arguments(monkeypatch):
    received = []
    cleaned = []
    working_folders = []
    monkeypatch.setattr(PyInstaller.__main__, "run", received.append)
    monkeypatch.setattr(build_exe, "_clean_native_search_path", lambda: cleaned.append(True))
    monkeypatch.setattr(build_exe.os, "chdir", working_folders.append)

    assert build_exe.main() == 0
    assert cleaned == [True]
    assert working_folders == [build_exe.Path(build_exe.__file__).resolve().parents[1]]
    assert received == [build_arguments()]
