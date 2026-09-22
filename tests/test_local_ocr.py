import base64

import pytest

from core import local_ocr
from core.local_ocr import OcrRecognitionError, OcrUnavailableError, WindowsOcrEngine


class _FakeInput:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.flushed = False

    def write(self, value: str) -> None:
        self.writes.append(value)

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        return None


class _FakeProcess:
    def __init__(self) -> None:
        self.stdin = _FakeInput()
        self.stdout = None

    def poll(self) -> None:
        return None


def _engine(tmp_path) -> WindowsOcrEngine:
    script = tmp_path / "windows_ocr.ps1"
    script.write_text("# test helper", encoding="utf-8")
    return WindowsOcrEngine(script)


def test_ocr_engine_reports_platform_and_missing_dependency_status(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(local_ocr.os, "name", "posix")
    assert engine.support_status() == (
        False,
        "Automatic OCR tracking is available only on Windows.",
    )

    monkeypatch.setattr(local_ocr.os, "name", "nt")
    engine.powershell_path = tmp_path / "missing-powershell.exe"
    assert engine.support_status() == (
        False,
        "The built-in Windows PowerShell executable was not found.",
    )


def test_ocr_engine_decodes_responses_and_sends_in_memory_png(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    process = _FakeProcess()
    engine._process = process  # type: ignore[assignment]
    monkeypatch.setattr(engine, "_ensure_process", lambda: None)
    encoded = base64.b64encode(b"X=10, Y=20, Z=30").decode("ascii")
    monkeypatch.setattr(engine, "_wait_for_response", lambda timeout: f"OK:{encoded}")

    assert engine.recognize_png(b"png-bytes") == "X=10, Y=20, Z=30"
    assert process.stdin.writes == [base64.b64encode(b"png-bytes").decode("ascii") + "\n"]
    assert process.stdin.flushed


@pytest.mark.parametrize("response", ["ERROR:YmFkIGltYWdl", "unexpected", "OK:not-base64"])
def test_ocr_engine_rejects_invalid_or_error_responses(tmp_path, monkeypatch, response):
    engine = _engine(tmp_path)
    engine._process = _FakeProcess()  # type: ignore[assignment]
    monkeypatch.setattr(engine, "_ensure_process", lambda: None)
    monkeypatch.setattr(engine, "_wait_for_response", lambda timeout: response)

    with pytest.raises(OcrRecognitionError):
        engine.recognize_png(b"image")


def test_ocr_engine_rejects_empty_image_and_unsupported_startup(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    with pytest.raises(OcrRecognitionError, match="empty"):
        engine.recognize_png(b"")

    monkeypatch.setattr(engine, "support_status", lambda: (False, "not available"))
    with pytest.raises(OcrUnavailableError, match="not available"):
        engine._ensure_process()
