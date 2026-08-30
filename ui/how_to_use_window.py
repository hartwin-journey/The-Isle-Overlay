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
    """Simple, non-technical quick-start guide."""

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
          <li><b>Layers:</b> click <b>Layers</b> to show or hide icons, zones, water, spawns, and other map info.</li>
          <li><b>Fit:</b> zooms back out so the whole map is visible.</li>
          <li><b>Center Player:</b> jumps the map to your latest known position.</li>
          <li><b>Waypoint:</b> right-click the map or use the Waypoint menu to place, save, or remove a waypoint.</li>
          <li><b>Clear Trail:</b> removes the breadcrumb trail from this session.</li>
        </ul>
        """

    @staticmethod
    def _mini_map_text() -> str:
        return """
        <h3>Mini Map</h3>
        <ul>
          <li>Click <b>Mini Map</b> to show or hide the overlay.</li>
          <li>By default the Mini Map is click-through so it does not block the game.</li>
          <li><b>Edit mode:</b> press <b>M4 / mouse button 4</b> to make the Mini Map interactable. Press it again to return to click-through mode.</li>
          <li>While editable, use the mouse wheel to zoom and drag to pan.</li>
          <li>Click <b>F</b> in the Mini Map to toggle auto-following your player icon.</li>
          <li>Click the shape button beside <b>F</b> to switch between square and circle.</li>
          <li>You can change the M4 edit shortcut in <b>Settings &gt; Shortcuts</b>.</li>
        </ul>
        """

    @staticmethod
    def _tracking_text() -> str:
        return """
        <h3>Tracking and OCR</h3>
        <ul>
          <li><b>Manual tracking:</b> copy coordinates from The Isle. The app reads your clipboard and updates your position.</li>
          <li><b>Automatic Tracking:</b> Windows can read the coordinate text on screen using local OCR.</li>
          <li>Open The Isle's <b>Tab</b> menu so your coordinates are visible.</li>
          <li>Click <b>Automatic Tracking &gt; Set up capture area…</b>.</li>
          <li>Select only the coordinate line. Keep the box tight and avoid extra text.</li>
          <li>Use <b>Capture and preview</b> to check that the app can read valid coordinates.</li>
          <li>Save the capture area, then turn <b>Automatic Tracking</b> on.</li>
          <li>OCR is processed locally on your PC and is currently Windows-only.</li>
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
          <li><b>Advanced:</b> map calibration. Leave this alone unless you are replacing or realigning the map image.</li>
          <li>Settings are saved locally on your computer.</li>
        </ul>
        """
