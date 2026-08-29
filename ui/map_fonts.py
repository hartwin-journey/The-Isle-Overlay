"""Qt helpers for the curated map-label font presets."""

from __future__ import annotations

from typing import Any, Mapping

from PySide6.QtGui import QFont

from core.map_fonts import get_map_label_font_preset


def build_map_label_font(settings: Mapping[str, Any], point_size: int) -> QFont:
    """Build a QFont from the validated local map-label setting."""

    preset = get_map_label_font_preset(settings.get("map_label_font_preset"))
    font = QFont(preset.family, int(point_size))
    font.setWeight(QFont.Weight(preset.weight))
    return font
