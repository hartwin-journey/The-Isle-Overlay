"""Load editable, local map-layer JSON without crashing the application."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

LAYER_FILES = {
    "migrations": "migrations.json",
    "patrol_zones": "patrol_zones.json",
    "sanctuaries": "sanctuaries.json",
    "updrafts": "updrafts.json",
    "water": "water.json",
    "locations": "locations.json",
    "food": "food.json",
    "ai": "ai.json",
    "salt_licks": "salt_licks.json",
    "spawns": "spawns.json",
    "custom_markers": "custom_markers.json",
}


class LayerRepository:
    def __init__(
        self,
        data_folder: Path,
        custom_markers_path: Path | None = None,
    ) -> None:
        self.data_folder = data_folder
        self.custom_markers_path = (
            custom_markers_path
            if custom_markers_path is not None
            else data_folder / LAYER_FILES["custom_markers"]
        )
        self.layers: dict[str, list[dict[str, Any]]] = {}
        self.reload()

    def reload(self) -> None:
        self.layers.clear()
        for layer_name, filename in LAYER_FILES.items():
            path = (
                self.custom_markers_path
                if layer_name == "custom_markers"
                else self.data_folder / filename
            )
            # The per-user marker file is generated only after a waypoint is
            # saved. A fresh checkout therefore starts with an empty layer,
            # without reporting the intentional absence as a data error.
            if layer_name == "custom_markers" and not path.exists():
                self.layers[layer_name] = []
            else:
                self.layers[layer_name] = self._load_items(path, layer_name)

    @staticmethod
    def _load_items(path: Path, layer_name: str) -> list[dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            items = value.get("items", value) if isinstance(value, dict) else value
            if not isinstance(items, list):
                raise TypeError("layer must contain an items array")
            return [item for item in items if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            LOGGER.error("Map data loading error for %s: %s", layer_name, exc)
            return []

    def save_custom_markers(self, markers: list[dict[str, Any]]) -> None:
        path = self.custom_markers_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump({"items": markers}, handle, indent=2)
            handle.write("\n")
        temporary_path.replace(path)
        self.layers["custom_markers"] = markers
