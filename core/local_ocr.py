"""Dependency-free bridges to local, on-device OCR engines.

Windows uses its built-in ``Windows.Media.Ocr`` service. Every other platform
uses the system Tesseract executable, which every major Linux distribution
(and Homebrew on macOS) packages. Neither engine uses the network.
"""

from __future__ import annotations

import base64
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol


class OcrUnavailableError(RuntimeError):
    """Raised when the local Windows OCR service cannot be started."""


class OcrRecognitionError(RuntimeError):
    """Raised when one in-memory image cannot be recognized."""


class OcrEngine(Protocol):
    """The small interface automatic tracking needs from an OCR engine."""

    display_name: str

    def support_status(self) -> tuple[bool, str]: ...

    def recognize_png(self, png_bytes: bytes) -> str: ...

    def close(self) -> None: ...


class WindowsOcrEngine:
    """Send in-memory PNG bytes to Windows.Media.Ocr via local PowerShell.

    The helper process is part of Windows and executes the readable script
    shipped with this project. No image is written to disk and no network API
    or third-party OCR executable is used.
    """

    display_name = "Windows on-device OCR"

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



def _linux_install_hint() -> str:
    """Return the Tesseract install command for the running distribution."""

    from core.environment import _os_release, distro_family, install_command

    return install_command(distro_family(_os_release()), "tesseract")


def tesseract_install_hint() -> str:
    if sys.platform == "darwin":
        return "brew install tesseract"
    if os.name == "nt":
        return "install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki"
    return _linux_install_hint()


class TesseractOcrEngine:
    """Send in-memory PNG bytes to the local Tesseract executable.

    The image is piped through stdin and the text is read from stdout, so no
    capture is written to disk. Set ``TESSERACT_CMD`` to use a binary that is
    not on ``PATH``.
    """

    display_name = "Tesseract OCR"
    language = "eng"

    def __init__(self, executable: str | None = None) -> None:
        self._configured = executable or os.environ.get("TESSERACT_CMD") or None
        self._status: tuple[bool, str] | None = None
        self._lock = threading.Lock()

    def executable(self) -> str | None:
        if self._configured:
            configured = Path(self._configured).expanduser()
            if configured.is_file():
                return str(configured)
            return shutil.which(self._configured)
        found = shutil.which("tesseract")
        if found:
            return found
        candidates: list[Path] = []
        if os.name == "nt":
            for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
                if root:
                    candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")
        else:
            # Desktop launchers sometimes start apps with a minimal PATH.
            candidates += [
                Path("/usr/bin/tesseract"),
                Path("/usr/local/bin/tesseract"),
                Path("/opt/homebrew/bin/tesseract"),
                Path("/run/current-system/sw/bin/tesseract"),
            ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None

    @staticmethod
    def _run_kwargs() -> dict[str, object]:
        env = dict(os.environ)
        # One thread is faster for tiny images and keeps polling light.
        env["OMP_THREAD_LIMIT"] = "1"
        return {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": env,
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        }

    def support_status(self) -> tuple[bool, str]:
        with self._lock:
            if self._status is not None and self._status[0]:
                return self._status
            self._status = self._probe()
            return self._status

    def _probe(self) -> tuple[bool, str]:
        executable = self.executable()
        if executable is None:
            return False, (
                "Tesseract OCR is not installed. To enable Automatic Tracking, "
                f"{tesseract_install_hint()}"
            )
        try:
            result = subprocess.run(
                [executable, "--list-langs"],
                timeout=10.0,
                **self._run_kwargs(),  # type: ignore[arg-type]
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, "Tesseract OCR is installed but could not be started."
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        languages = {line.strip() for line in output.splitlines()}
        if self.language not in languages:
            return False, (
                "Tesseract is installed but its English language data is missing. "
                f"{tesseract_install_hint()}"
            )
        return True, "Tesseract on-device OCR is available."

    def recognize_png(self, png_bytes: bytes) -> str:
        if not png_bytes:
            raise OcrRecognitionError("Screen capture was empty")
        supported, reason = self.support_status()
        if not supported:
            raise OcrUnavailableError(reason)
        executable = self.executable()
        if executable is None:
            with self._lock:
                self._status = None
            raise OcrUnavailableError("Tesseract OCR is no longer installed")
        try:
            result = subprocess.run(
                [
                    executable,
                    "stdin",
                    "stdout",
                    "-l",
                    self.language,
                    # Treat the capture as one uniform block of text; the
                    # coordinate panel may span one or two lines.
                    "--psm",
                    "6",
                    "--dpi",
                    "300",
                ],
                input=png_bytes,
                timeout=10.0,
                **self._run_kwargs(),  # type: ignore[arg-type]
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrRecognitionError("Tesseract did not respond in time") from exc
        except OSError as exc:
            with self._lock:
                self._status = None
            raise OcrUnavailableError("Tesseract OCR could not be started") from exc
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise OcrRecognitionError(
                message.splitlines()[-1] if message else "Tesseract could not read the image"
            )
        return result.stdout.decode("utf-8", errors="replace")

    def close(self) -> None:
        return None


def create_ocr_engine(project_root: Path) -> OcrEngine:
    """Return the local OCR engine appropriate for this platform."""

    if os.name == "nt":
        return WindowsOcrEngine(project_root / "core" / "windows_ocr.ps1")
    return TesseractOcrEngine()
