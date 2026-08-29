import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.clipboard_monitor import ClipboardCoordinateMonitor


def test_clipboard_monitor_emits_only_valid_new_coordinates():
    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    monitor = ClipboardCoordinateMonitor(clipboard)
    received = []
    monitor.position_copied.connect(received.append)

    clipboard.setText("ordinary unrelated clipboard text")
    app.processEvents()
    assert received == []

    valid = "88,879.526, 288,696.110, 21,112.882"
    clipboard.setText(valid)
    app.processEvents()
    assert len(received) == 1
    assert received[0].x == 88879.526

    clipboard.setText(valid)
    app.processEvents()
    assert len(received) == 1

    clipboard.setText("-10, 20, 30")
    app.processEvents()
    assert len(received) == 2

