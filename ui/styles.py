"""Application-wide dark visual theme."""

DARK_STYLESHEET = """
QWidget {
    background: #101820;
    color: #e2ebf1;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow, QDialog { background: #0b1218; }
QToolBar {
    background: #121f28;
    border: 0;
    border-bottom: 1px solid #273844;
    spacing: 4px;
    padding: 7px 8px;
}
QToolBar::separator {
    background: #31434e;
    width: 1px;
    margin: 6px 7px;
}
QPushButton, QToolButton {
    background: #1a2933;
    border: 1px solid #334955;
    border-radius: 6px;
    padding: 7px 11px;
}
QPushButton:hover, QToolButton:hover { background: #243843; border-color: #568092; }
QPushButton:pressed, QToolButton:pressed { background: #147d98; }
QPushButton:checked, QToolButton:checked { background: #12677d; border-color: #2bb9d6; }
QPushButton#secondaryButton { background: transparent; color: #9bb0bc; }
QToolBar QToolButton { padding: 6px 10px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0b141b;
    border: 1px solid #344a56;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #1689a5;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #36b8d3;
}
QGroupBox {
    border: 1px solid #293c47;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 11px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #f1f6f9; }
QCheckBox { spacing: 9px; padding: 4px 2px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { background: #16242d; padding: 9px; border-bottom: 1px solid #2c414e; }
QTabWidget::pane { border: 1px solid #293c47; border-radius: 7px; top: -1px; }
QTabBar::tab {
    background: transparent;
    color: #8fa5b1;
    padding: 10px 16px;
    border: 0;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #dce9ef; }
QTabBar::tab:selected { color: #eefbfe; border-bottom-color: #35c4df; }
QStatusBar { background: #121f28; border-top: 1px solid #273844; }
QScrollArea { border: 0; }
QGraphicsView { border: 0; background: #081015; }
QToolTip { background: #d9eef5; color: #071218; border: 1px solid #4794a8; }
QWidget#nearestPoiBar {
    background: #0d1921;
    border-top: 1px solid #28404c;
    border-bottom: 1px solid #20343f;
}
QLabel#nearestPoiLabel {
    color: #eefbfe;
    background: transparent;
    padding: 1px 6px;
}
QLabel#privacyNote {
    color: #5eb9ca;
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 2px;
}
QLabel#sectionNote { color: #a8bac4; padding: 2px 0 6px 0; }
QLabel#fieldHint { color: #788e9a; font-size: 9pt; }
QLabel#ocrImagePreview {
    color: #718a96;
    background: #070d12;
    border: 1px solid #2d4551;
    border-radius: 7px;
    padding: 8px;
}
QLabel#sliderValue {
    color: #b9dbe3;
    background: #16252e;
    border-radius: 5px;
    padding: 3px 6px;
}
QLabel#panelTitle { color: #eaf8fb; font-size: 13pt; font-weight: 650; }
QLabel#panelSubtitle { color: #718a96; font-size: 8.5pt; padding-bottom: 5px; }
QSlider::groove:horizontal {
    height: 5px;
    background: #23343e;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #2bb3cf; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 16px;
    margin: -6px 0;
    background: #e6f8fb;
    border: 2px solid #2bb3cf;
    border-radius: 8px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical { background: #344b57; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
