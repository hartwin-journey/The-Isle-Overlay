"""Transport-only interface used by the integration manager."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class IntegrationTransport(QObject):
    opened = Signal()
    closed = Signal(str)
    text_received = Signal(str)
    failed = Signal(str)

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def send_text(self, text: str) -> bool:
        raise NotImplementedError
