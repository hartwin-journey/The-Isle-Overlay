"""Listen only to ordinary Qt desktop clipboard text changes."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QClipboard

from core.coordinate_parser import CoordinateParseError, parse_coordinates
from core.models import Position

LOGGER = logging.getLogger(__name__)


class ClipboardCoordinateMonitor(QObject):
    """Convert valid manually copied clipboard text into Position objects.

    This class has no process handles, file access, network access, or game
    integration. QClipboard is its sole input.
    """

    position_copied = Signal(object)

    def __init__(self, clipboard: QClipboard) -> None:
        super().__init__()
        self._clipboard = clipboard
        self._last_valid_text: str | None = None
        clipboard.dataChanged.connect(self._on_clipboard_changed)

    @Slot()
    def _on_clipboard_changed(self) -> None:
        mime_data = self._clipboard.mimeData()
        if mime_data is None or not mime_data.hasText():
            return
        text = mime_data.text()
        if text == self._last_valid_text:
            return
        try:
            parsed = parse_coordinates(text)
        except CoordinateParseError as exc:
            # Do not include clipboard contents in logs.
            LOGGER.info("Invalid coordinate parsing error: %s", exc)
            return
        self._last_valid_text = text
        position = Position.now(parsed.x, parsed.y, parsed.z)
        LOGGER.info(
            "Valid coordinate update: x=%.3f y=%.3f z=%.3f",
            position.x,
            position.y,
            position.z,
        )
        self.position_copied.emit(position)
