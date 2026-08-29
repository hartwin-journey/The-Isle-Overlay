"""Curated, local font presets for text rendered around the maps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MapLabelFontPreset:
    """A stable settings value and its Windows font presentation."""

    label: str
    family: str
    weight: int


MAP_LABEL_FONT_PRESETS: dict[str, MapLabelFontPreset] = {
    "segoe_semibold": MapLabelFontPreset("Segoe UI Semibold", "Segoe UI", 600),
    "verdana_bold": MapLabelFontPreset("Verdana Bold", "Verdana", 700),
    "tahoma_bold": MapLabelFontPreset("Tahoma Bold", "Tahoma", 700),
    "arial_bold": MapLabelFontPreset("Arial Bold", "Arial", 700),
    "segoe_regular": MapLabelFontPreset("Segoe UI Regular", "Segoe UI", 400),
}

DEFAULT_MAP_LABEL_FONT_PRESET = "segoe_semibold"


def get_map_label_font_preset(value: object) -> MapLabelFontPreset:
    """Return a known preset, falling back to the readable default."""

    return MAP_LABEL_FONT_PRESETS.get(
        str(value),
        MAP_LABEL_FONT_PRESETS[DEFAULT_MAP_LABEL_FONT_PRESET],
    )
