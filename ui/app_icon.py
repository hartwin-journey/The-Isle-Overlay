"""The app's "IC" badge, drawn at any size (window, tray and launcher icon)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

# Designed on a 64 px grid and scaled for other sizes.
_DESIGN_SIZE = 64


def render_app_icon(size: int = _DESIGN_SIZE) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / _DESIGN_SIZE, size / _DESIGN_SIZE)
    painter.setBrush(QColor("#102d38"))
    painter.setPen(QColor("#42d2ea"))
    painter.drawEllipse(3, 3, 58, 58)
    painter.setPen(QColor("#eafcff"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(28)
    painter.setFont(font)
    painter.drawText(
        0, 0, _DESIGN_SIZE, _DESIGN_SIZE, Qt.AlignmentFlag.AlignCenter, "IC"
    )
    painter.end()
    return pixmap


def create_app_icon() -> QIcon:
    return QIcon(render_app_icon())
