import shutil
import subprocess
import sys

import pytest

from core.launcher import APP_ID, ICON_SIZES, desktop_entry, ensure_launcher

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux launcher")


def _fake_icons(calls):
    def write(paths):
        calls.append(sorted(paths))
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png")

    return write


def _ensure(root, data, calls):
    return ensure_launcher(
        root,
        environ={"XDG_DATA_HOME": str(data)},
        write_icons=_fake_icons(calls),
        run=lambda *a, **k: None,
    )


def test_creates_once_then_leaves_it_alone(tmp_path):
    root, data, calls = tmp_path / "Isle Companion", tmp_path / "data", []
    root.mkdir()
    assert _ensure(root, data, calls) == "created"
    entry = data / "applications" / f"{APP_ID}.desktop"
    assert entry.read_text() == desktop_entry(root.resolve())
    assert calls == [list(ICON_SIZES)]
    assert _ensure(root, data, calls) == "unchanged"
    assert len(calls) == 1  # icons not redrawn


def test_moved_folder_updates_the_entry_but_keeps_icons(tmp_path):
    data, calls = tmp_path / "data", []
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    _ensure(tmp_path / "old", data, calls)
    assert _ensure(tmp_path / "new", data, calls) == "updated"
    assert str(tmp_path / "new") in (data / "applications" / f"{APP_ID}.desktop").read_text()
    assert len(calls) == 1


def test_missing_icon_is_redrawn(tmp_path):
    root, data, calls = tmp_path / "app", tmp_path / "data", []
    root.mkdir()
    _ensure(root, data, calls)
    (data / "icons/hicolor/128x128/apps" / f"{APP_ID}.png").unlink()
    assert _ensure(root, data, calls) == "updated"
    assert calls[-1] == [128]


def test_opt_out(tmp_path):
    result = ensure_launcher(
        tmp_path,
        environ={"XDG_DATA_HOME": str(tmp_path / "d"), "ISLE_COMPANION_NO_LAUNCHER": "1"},
        write_icons=_fake_icons([]),
    )
    assert result == "skipped" and not (tmp_path / "d").exists()


def test_exec_line_quotes_awkward_paths():
    text = desktop_entry(__import__("pathlib").Path('/home/a b/$x "q"/Isle'))
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    assert exec_line == 'Exec=sh "/home/a b/\\\\$x \\\\"q\\\\"/Isle/run.sh"'


@pytest.mark.skipif(shutil.which("desktop-file-validate") is None, reason="no validator")
def test_entry_passes_desktop_file_validate(tmp_path):
    root = tmp_path / "my games" / "Isle $Companion"
    root.mkdir(parents=True)
    entry = tmp_path / f"{APP_ID}.desktop"
    entry.write_text(desktop_entry(root))
    result = subprocess.run(["desktop-file-validate", str(entry)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
