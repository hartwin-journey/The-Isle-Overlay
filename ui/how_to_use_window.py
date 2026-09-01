"""Short user instructions for The Isle Companion."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class HowToUseDialog(QDialog):
    """A short, non-technical guide written for someone already in-game."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("How to use The Isle Companion")
        self.setMinimumSize(660, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self._instruction_tab(self._main_map_text()), "Main Map")
        tabs.addTab(self._instruction_tab(self._mini_map_text()), "Mini Map")
        tabs.addTab(self._instruction_tab(self._tracking_text()), "Tracking / OCR")
        tabs.addTab(self._instruction_tab(self._settings_text()), "Settings")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _instruction_tab(text: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 18, 18, 18)
        body_layout.setSpacing(10)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setOpenExternalLinks(False)
        body_layout.addWidget(label)
        body_layout.addStretch()
        scroll.setWidget(body)
        return scroll

    @staticmethod
    def _main_map_text() -> str:
        return """
        <h3>Main Map</h3>
        <ul>
          <li><b>Move around:</b> drag the map with your mouse.</li>
          <li><b>Zoom:</b> use the mouse wheel.</li>
          <li><b>Layers:</b> open <b>Layers</b> to pick which zones, icons, water, spawns, and notes you want visible.</li>
          <li><b>Fit:</b> zooms back out until the whole Gateway map is on screen.</li>
          <li><b>Center Player:</b> jumps back to your latest known position.</li>
          <li><b>Waypoint:</b> right-click the map, or use the Waypoint menu, to place, save, or remove a destination.</li>
          <li><b>Clear Trail:</b> wipes the breadcrumb trail for the current session.</li>
        </ul>
        """

    @staticmethod
    def _mini_map_text() -> str:
        return """
        <h3>Mini Map</h3>
        <ul>
          <li>Use <b>Mini Map</b> to show or hide the overlay.</li>
          <li>It starts click-through by default, so stray clicks still go to the game.</li>
          <li><b>Edit mode:</b> press <b>M4 / mouse button 4</b> to unlock the Mini Map. Press it again when you are done.</li>
          <li>On Linux desktops that block global input observation, use <b>Edit Mini Map</b> in the Full Map toolbar instead.</li>
          <li>While it is unlocked, scroll to zoom and drag to pan.</li>
          <li>Use the small <b>F</b> button to turn player-following on or off.</li>
          <li>The shape button beside <b>F</b> switches between square and circle.</li>
          <li>If M4 is awkward on your mouse, change it in <b>Settings &gt; Shortcuts</b>.</li>
        </ul>
        """

    @staticmethod
    def _tracking_text() -> str:
        return """
        <h3>Tracking and OCR</h3>
        <ul>
          <li><b>Manual tracking:</b> copy coordinates from The Isle and the companion updates from your clipboard.</li>
          <li><b>Automatic Tracking:</b> on Windows, local OCR can read the coordinate text already visible on screen.</li>
          <li>Open The Isle's <b>Tab</b> menu so your coordinates are visible.</li>
          <li>Choose <b>Automatic Tracking &gt; Set up capture area…</b>.</li>
          <li>Box in just the coordinate line. A tight crop is easier for OCR to read.</li>
          <li>Use <b>Capture and preview</b> before saving, especially after changing resolution or UI scale.</li>
          <li>Save the capture area, then turn <b>Automatic Tracking</b> on.</li>
          <li>OCR stays on your PC and is currently Windows-only.</li>
        </ul>
        """

    @staticmethod
    def _settings_text() -> str:
        return """
        <h3>Settings</h3>
        <ul>
          <li><b>Mini Map:</b> change startup behavior, always-on-top, following, shape, size, and opacity.</li>
          <li><b>Map &amp; Tracking:</b> adjust visual clarity, POI labels, and breadcrumb trail length.</li>
          <li><b>Shortcuts:</b> click a shortcut button, then press the key, mouse button, or key combination you want.</li>
          <li><b>Advanced:</b> map calibration. You can ignore this unless you are replacing or realigning the map image.</li>
          <li>Settings are saved locally on your computer.</li>
        </ul>
        """
