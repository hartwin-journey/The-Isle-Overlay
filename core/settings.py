"""Local JSON settings with validation and safe defaults."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from core.hotkeys import parse_hold_binding
from core.map_fonts import DEFAULT_MAP_LABEL_FONT_PRESET, MAP_LABEL_FONT_PRESETS

LOGGER = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "launch_mini_map_on_startup": False,
    "always_on_top": True,
    "overlay_opacity": 0.88,
    "overlay_size": 360,
    "overlay_borderless": True,
    "overlay_shape": "square",
    "overlay_interaction_hold_key": "M4",
    "player_centered_mode": True,
    "north_up_mode": True,
    "poi_label_font_size_full": 11,
    "poi_label_font_size_mini": 9,
    "map_label_font_preset": DEFAULT_MAP_LABEL_FONT_PRESET,
    "mini_map_show_poi_labels": False,
    "automatic_tracking_enabled": False,
    "automatic_tracking_region": {"x": 0, "y": 0, "width": 0, "height": 0},
    "automatic_tracking_interval_ms": 900,
    "automatic_tracking_confirmation_reads": 2,
    "breadcrumbs_enabled": True,
    "breadcrumb_max_points": 500,
    "breadcrumb_connect_lines": True,
    "layer_opacity": {
        "migrations": 0.42,
        "patrol_zones": 0.33,
        "sanctuaries": 0.60,
        "water": 1.0,
        "updrafts": 1.0,
        "locations": 1.0,
        "food": 1.0,
        "ai": 1.0,
        "salt_licks": 1.0,
        "spawns": 1.0,
        "custom_markers": 1.0,
        "external": 1.0,
    },
    "data_folder": "data",
    "layer_panel_visible": True,
    "layers": {
        "player": True,
        "breadcrumbs": True,
        "migrations": True,
        "patrol_zones": False,
        "sanctuaries": True,
        "water": True,
        "updrafts": True,
        "locations": True,
        "food": True,
        "ai": False,
        "salt_licks": True,
        "spawns": False,
        "custom_markers": True,
        "external": True,
    },
    "integration": {
        "enabled": False,
        "service_name": "",
        "websocket_url": "",
        "room": "default",
        "display_name": "Player",
        "access_token": "",
        "receive_points": False,
        "share_waypoint": False,
        "share_position": False,
        "position_interval_ms": 1000,
        "position_max_age_seconds": 30,
    },
    "individual_migrations": {},
    "individual_patrol_zones": {},
    "individual_sanctuaries": {},
    "hotkeys": {
        "toggle_full_map": "Ctrl+Shift+M",
        "toggle_mini_map": "Ctrl+Shift+O",
        "toggle_layer_panel": "Ctrl+Shift+L",
        "toggle_breadcrumbs": "Ctrl+Shift+B",
        "clear_waypoint": "Ctrl+Shift+W",
        "recenter_player": "Ctrl+Shift+R",
        "toggle_player_centered": "Ctrl+Shift+P",
        "increase_opacity": "Ctrl+Shift+PageUp",
        "decrease_opacity": "Ctrl+Shift+PageDown",
    },
}


def _migrate_loaded_settings(loaded: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Convert legacy overlay keys while preserving every other known setting."""

    migrated = copy.deepcopy(loaded)
    changed = False
    if "overlay_shape" not in migrated:
        migrated["overlay_shape"] = (
            "circle" if bool(migrated.get("overlay_circular_mask", False)) else "square"
        )
        changed = True
    opacity = migrated.get("layer_opacity")
    if not isinstance(opacity, dict):
        opacity = {}
        migrated["layer_opacity"] = opacity
        changed = True
    if "migrations" not in opacity and "migration_opacity" in migrated:
        opacity["migrations"] = migrated["migration_opacity"]
        changed = True
    for legacy_key in ("overlay_circular_mask", "overlay_square_mode", "migration_opacity"):
        if legacy_key in migrated:
            migrated.pop(legacy_key)
            changed = True
    return migrated, changed


def _deep_merge(defaults: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    # Empty default mappings (for example per-zone visibility) are intentionally
    # open-ended because their keys come from editable data files.
    if not defaults:
        return copy.deepcopy(loaded)
    result = copy.deepcopy(defaults)
    for key, value in loaded.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result:
            result[key] = value
    return result


class SettingsStore:
    """Owns settings stored only on the local machine."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.values = copy.deepcopy(DEFAULT_SETTINGS)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.save()
            return self.values
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise TypeError("settings root must be a JSON object")
            loaded, migrated = _migrate_loaded_settings(loaded)
            self.values = _deep_merge(DEFAULT_SETTINGS, loaded)
            self._validate()
            if migrated:
                self.save()
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            LOGGER.error("Configuration error loading settings: %s", exc)
            self.values = copy.deepcopy(DEFAULT_SETTINGS)
            self.save()
        return self.values

    def _validate(self) -> None:
        self.values["overlay_opacity"] = min(1.0, max(0.2, float(self.values["overlay_opacity"])))
        self.values["overlay_size"] = min(1200, max(180, int(self.values["overlay_size"])))
        if self.values.get("overlay_shape") not in {"square", "circle"}:
            self.values["overlay_shape"] = DEFAULT_SETTINGS["overlay_shape"]
        binding = str(self.values.get("overlay_interaction_hold_key", "")).strip()
        try:
            parse_hold_binding(binding)
        except ValueError:
            LOGGER.error("Invalid overlay interaction binding in settings: %r", binding)
            binding = str(DEFAULT_SETTINGS["overlay_interaction_hold_key"])
        self.values["overlay_interaction_hold_key"] = binding
        self.values["poi_label_font_size_full"] = min(
            24, max(6, int(self.values["poi_label_font_size_full"]))
        )
        self.values["poi_label_font_size_mini"] = min(
            18, max(6, int(self.values["poi_label_font_size_mini"]))
        )
        if self.values.get("map_label_font_preset") not in MAP_LABEL_FONT_PRESETS:
            self.values["map_label_font_preset"] = DEFAULT_MAP_LABEL_FONT_PRESET
        self.values["automatic_tracking_enabled"] = bool(
            self.values.get("automatic_tracking_enabled", False)
        )
        region = self.values.get("automatic_tracking_region")
        if not isinstance(region, dict):
            region = {}
        validated_region: dict[str, int] = {}
        defaults_region = DEFAULT_SETTINGS["automatic_tracking_region"]
        for key in ("x", "y", "width", "height"):
            try:
                validated_region[key] = int(region.get(key, defaults_region[key]))
            except (TypeError, ValueError):
                validated_region[key] = int(defaults_region[key])
        validated_region["x"] = min(100_000, max(-100_000, validated_region["x"]))
        validated_region["y"] = min(100_000, max(-100_000, validated_region["y"]))
        width = validated_region["width"]
        height = validated_region["height"]
        validated_region["width"] = 0 if width <= 0 else min(4096, max(32, width))
        validated_region["height"] = 0 if height <= 0 else min(2160, max(16, height))
        self.values["automatic_tracking_region"] = validated_region
        self.values["automatic_tracking_interval_ms"] = min(
            5000,
            max(500, int(self.values.get("automatic_tracking_interval_ms", 900))),
        )
        self.values["automatic_tracking_confirmation_reads"] = min(
            5,
            max(
                2,
                int(self.values.get("automatic_tracking_confirmation_reads", 2)),
            ),
        )
        self.values["breadcrumb_max_points"] = min(
            10_000, max(2, int(self.values["breadcrumb_max_points"]))
        )
        integration = self.values.get("integration")
        if not isinstance(integration, dict):
            integration = copy.deepcopy(DEFAULT_SETTINGS["integration"])
            self.values["integration"] = integration
        integration_defaults = DEFAULT_SETTINGS["integration"]
        for key in ("enabled", "receive_points", "share_waypoint", "share_position"):
            integration[key] = bool(integration.get(key, integration_defaults[key]))
        for key, limit in (
            ("service_name", 128),
            ("websocket_url", 2048),
            ("room", 64),
            ("display_name", 256),
            ("access_token", 4096),
        ):
            value = integration.get(key, integration_defaults[key])
            integration[key] = str(value)[:limit]
        integration["room"] = integration["room"].strip() or "default"
        integration["display_name"] = integration["display_name"].strip() or "Player"
        try:
            position_interval = int(integration.get("position_interval_ms", 1000))
        except (TypeError, ValueError):
            position_interval = 1000
        integration["position_interval_ms"] = min(10_000, max(500, position_interval))
        try:
            position_max_age = int(integration.get("position_max_age_seconds", 30))
        except (TypeError, ValueError):
            position_max_age = 30
        integration["position_max_age_seconds"] = min(300, max(5, position_max_age))
        opacity = self.values.setdefault("layer_opacity", {})
        defaults = DEFAULT_SETTINGS["layer_opacity"]
        for layer_name, default in defaults.items():
            try:
                value = float(opacity.get(layer_name, default))
            except (TypeError, ValueError):
                value = float(default)
            opacity[layer_name] = min(1.0, max(0.1, value))

    def save(self) -> None:
        self._validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(self.values, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary_path.replace(self.path)
