"""Independent layer and zone visibility controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.app_state import AppState
from core.data_loader import LayerRepository

LAYER_LABELS = {
    "player": "Player position",
    "breadcrumbs": "Breadcrumb trail",
    "migrations": "Migration zones",
    "patrol_zones": "Patrol zones",
    "sanctuaries": "Sanctuaries",
    "water": "Water sources",
    "updrafts": "Updrafts",
    "locations": "Named locations",
    "food": "Food locations",
    "ai": "AI locations",
    "salt_licks": "Salt licks",
    "spawns": "Spawn areas",
    "custom_markers": "Custom markers",
}

LAYER_SECTIONS = (
    ("Tracking", ("player", "breadcrumbs")),
    ("Zones", ("migrations", "patrol_zones", "sanctuaries")),
    (
        "Map details",
        (
            "water",
            "updrafts",
            "locations",
            "food",
            "ai",
            "salt_licks",
            "spawns",
            "custom_markers",
        ),
    ),
)


class LayerPanel(QWidget):
    settings_modified = Signal()
    reload_requested = Signal()

    def __init__(self, state: AppState, repository: LayerRepository) -> None:
        super().__init__()
        self.state = state
        self.repository = repository
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        title = QLabel("Layers")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        subtitle = QLabel("Controls apply to both map views")
        subtitle.setObjectName("panelSubtitle")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 4, 0, 4)
        body_layout.setSpacing(10)

        self.layer_checkboxes: dict[str, QCheckBox] = {}
        for section_name, layer_names in LAYER_SECTIONS:
            group = QGroupBox(section_name)
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(3)
            for key in layer_names:
                checkbox = QCheckBox(LAYER_LABELS[key])
                self.layer_checkboxes[key] = checkbox
                checkbox.setChecked(bool(state.settings["layers"].get(key, True)))
                checkbox.toggled.connect(
                    lambda checked, name=key: self._toggle_layer(name, checked)
                )
                group_layout.addWidget(checkbox)
            body_layout.addWidget(group)

        self.zone_filter_toggle = QToolButton()
        self.zone_filter_toggle.setText("Individual zone filters")
        self.zone_filter_toggle.setCheckable(True)
        self.zone_filter_toggle.setChecked(False)
        self.zone_filter_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.zone_filter_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.zone_filter_toggle.toggled.connect(self._toggle_zone_filters)
        body_layout.addWidget(self.zone_filter_toggle)

        self.zone_filter_body = QWidget()
        zone_filter_layout = QVBoxLayout(self.zone_filter_body)
        zone_filter_layout.setContentsMargins(8, 0, 0, 0)
        zone_filter_layout.setSpacing(8)

        migration_group = QGroupBox("Migration zones")
        migration_layout = QVBoxLayout(migration_group)
        migration_layout.setSpacing(2)
        migrations = repository.layers.get("migrations", [])
        if not migrations:
            migration_layout.addWidget(QLabel("No migration zones loaded"))
        for zone in migrations:
            name = str(zone.get("name", "Migration zone"))
            checkbox = QCheckBox(name)
            checkbox.setChecked(state.settings.get("individual_migrations", {}).get(name, True))
            checkbox.toggled.connect(lambda checked, zone_name=name: self._toggle_individual("individual_migrations", zone_name, checked))
            migration_layout.addWidget(checkbox)
        zone_filter_layout.addWidget(migration_group)

        patrol_group = QGroupBox("Patrol zones")
        patrol_layout = QVBoxLayout(patrol_group)
        patrol_layout.setSpacing(2)
        patrol_zones = repository.layers.get("patrol_zones", [])
        if not patrol_zones:
            patrol_layout.addWidget(QLabel("No patrol zones loaded"))
        for zone in patrol_zones:
            name = str(zone.get("name", "Patrol zone"))
            checkbox = QCheckBox(name)
            checkbox.setChecked(
                state.settings.get("individual_patrol_zones", {}).get(name, True)
            )
            checkbox.toggled.connect(
                lambda checked, zone_name=name: self._toggle_individual(
                    "individual_patrol_zones", zone_name, checked
                )
            )
            patrol_layout.addWidget(checkbox)
        zone_filter_layout.addWidget(patrol_group)

        sanctuary_group = QGroupBox("Sanctuaries")
        sanctuary_layout = QVBoxLayout(sanctuary_group)
        sanctuary_layout.setSpacing(2)
        sanctuaries = repository.layers.get("sanctuaries", [])
        if not sanctuaries:
            sanctuary_layout.addWidget(QLabel("No sanctuaries loaded"))
        for zone in sanctuaries:
            name = str(zone.get("name", "Sanctuary"))
            checkbox = QCheckBox(name)
            checkbox.setChecked(state.settings.get("individual_sanctuaries", {}).get(name, True))
            checkbox.toggled.connect(lambda checked, zone_name=name: self._toggle_individual("individual_sanctuaries", zone_name, checked))
            sanctuary_layout.addWidget(checkbox)
        zone_filter_layout.addWidget(sanctuary_group)
        self.zone_filter_body.setVisible(False)
        body_layout.addWidget(self.zone_filter_body)

        reload_button = QPushButton("Reload map data")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self.reload_requested)
        body_layout.addWidget(reload_button)
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll)
        state.layers_changed.connect(self._sync_layer_controls)
        state.settings_changed.connect(self._sync_layer_controls)

    def _sync_layer_controls(self) -> None:
        for key, checkbox in self.layer_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(self.state.settings["layers"].get(key, True)))
            checkbox.blockSignals(False)

    def _toggle_zone_filters(self, expanded: bool) -> None:
        self.zone_filter_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.zone_filter_body.setVisible(expanded)

    def _toggle_layer(self, name: str, checked: bool) -> None:
        self.state.settings["layers"][name] = checked
        if name == "breadcrumbs":
            self.state.settings["breadcrumbs_enabled"] = checked
        self.state.layers_changed.emit()
        self.settings_modified.emit()

    def _toggle_individual(self, settings_key: str, name: str, checked: bool) -> None:
        self.state.settings.setdefault(settings_key, {})[name] = checked
        self.state.settings_changed.emit()
        self.settings_modified.emit()
