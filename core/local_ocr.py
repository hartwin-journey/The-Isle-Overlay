"""Dependency-free bridge to Windows' installed, on-device OCR service."""

from __future__ import annotations

import base64
import os
import queue
import subprocess
import threading
from pathlib import Path


class OcrUnavailableError(RuntimeError):
    """Raised when the local Windows OCR service cannot be started."""


class OcrRecognitionError(RuntimeError):
    """Raised when one in-memory image cannot be recognized."""


class WindowsOcrEngine:
    """Send in-memory PNG bytes to Windows.Media.Ocr via local PowerShell.

    The helper process is part of Windows and executes the readable script
    shipped with this project. No image is written to disk and no network API
    or third-party OCR executable is used.
    """

    def __init__(self, script_path: Path) -> None:
        self.script_path = script_path.resolve()
        windows_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        self.powershell_path = (
            windows_root
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def support_status(self) -> tuple[bool, str]:
        if os.name != "nt":
            return False, "Automatic OCR tracking is available only on Windows."
        if not self.powershell_path.is_file():
            return False, "The built-in Windows PowerShell executable was not found."
        if not self.script_path.is_file():
            return False, "The local Windows OCR helper script is missing."
        return True, "Windows on-device OCR is available."

    def recognize_png(self, png_bytes: bytes) -> str:
        if not png_bytes:
            raise OcrRecognitionError("Screen capture was empty")
        with self._lock:
            self._ensure_process()
            assert self._process is not None and self._process.stdin is not None
            try:
                request = base64.b64encode(png_bytes).decode("ascii")
                self._process.stdin.write(request + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._stop_process()
                raise OcrRecognitionError("Windows OCR helper stopped unexpectedly") from exc

            response = self._wait_for_response(timeout=10.0)
            if response is None:
                self._stop_process()
                raise OcrRecognitionError("Windows OCR did not respond in time")
            if response.startswith("OK:"):
                return self._decode_payload(response[3:])
            if response.startswith("ERROR:"):
                raise OcrRecognitionError(self._decode_payload(response[6:]))
            raise OcrRecognitionError("Windows OCR returned an invalid response")

    def _ensure_process(self) -> None:
        supported, reason = self.support_status()
        if not supported:
            raise OcrUnavailableError(reason)
        if self._process is not None and self._process.poll() is None:
            return

        self._stop_process()
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(
                [
                    str(self.powershell_path),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script_path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=creation_flags,
            )
        except OSError as exc:
            self._process = None
            raise OcrUnavailableError("Could not start Windows on-device OCR") from exc

        self._responses = queue.Queue()
        self._reader_thread = threading.Thread(
            target=self._read_responses,
            name="windows-ocr-output",
            daemon=True,
        )
        self._reader_thread.start()
        response = self._wait_for_response(timeout=5.0)
        if response == "READY":
            return
        self._stop_process()
        if response and response.startswith("ERROR:"):
            reason = self._decode_payload(response[6:])
        else:
            reason = "Windows on-device OCR did not initialize"
        raise OcrUnavailableError(reason)

    def _read_responses(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._responses.put(None)
            return
        try:
            for line in process.stdout:
                self._responses.put(line.rstrip("\r\n"))
        finally:
            self._responses.put(None)

    def _wait_for_response(self, timeout: float) -> str | None:
        try:
            return self._responses.get(timeout=timeout)
        except queue.Empty:
            return None

    @staticmethod
    def _decode_payload(value: str) -> str:
        try:
            return base64.b64decode(value, validate=True).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError) as exc:
            raise OcrRecognitionError("Windows OCR returned unreadable text") from exc

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def close(self) -> None:
        with self._lock:
            self._stop_process()

