"""World-coordinate to map-pixel conversion backed by editable JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


class CalibrationError(ValueError):
    """Raised when calibration data cannot produce a valid transform."""


@dataclass(slots=True)
class MapCalibration:
    world_min_x: float
    world_max_x: float
    world_min_y: float
    world_max_y: float
    pixel_min_x: float
    pixel_max_x: float
    pixel_min_y: float
    pixel_max_y: float
    invert_y: bool = True
    invert_x: bool = False
    swap_axes: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MapCalibration":
        world = value["world_bounds"]
        pixels = value["pixel_bounds"]
        calibration = cls(
            world_min_x=float(world["min_x"]),
            world_max_x=float(world["max_x"]),
            world_min_y=float(world["min_y"]),
            world_max_y=float(world["max_y"]),
            pixel_min_x=float(pixels["min_x"]),
            pixel_max_x=float(pixels["max_x"]),
            pixel_min_y=float(pixels["min_y"]),
            pixel_max_y=float(pixels["max_y"]),
            invert_y=bool(value.get("invert_y", True)),
            invert_x=bool(value.get("invert_x", False)),
            swap_axes=bool(value.get("swap_axes", False)),
        )
        calibration.validate()
        return calibration

    def validate(self) -> None:
        if self.world_max_x == self.world_min_x or self.world_max_y == self.world_min_y:
            raise CalibrationError("world calibration bounds cannot have zero size")
        if self.pixel_max_x == self.pixel_min_x or self.pixel_max_y == self.pixel_min_y:
            raise CalibrationError("pixel calibration bounds cannot have zero size")

    def world_to_pixel(self, x: float, y: float) -> tuple[float, float]:
        x_ratio = (x - self.world_min_x) / (self.world_max_x - self.world_min_x)
        y_ratio = (y - self.world_min_y) / (self.world_max_y - self.world_min_y)
        pixel_x_ratio, pixel_y_ratio = (
            (y_ratio, x_ratio) if self.swap_axes else (x_ratio, y_ratio)
        )
        if self.invert_x:
            pixel_x_ratio = 1.0 - pixel_x_ratio
        if self.invert_y:
            pixel_y_ratio = 1.0 - pixel_y_ratio
        pixel_x = self.pixel_min_x + pixel_x_ratio * (self.pixel_max_x - self.pixel_min_x)
        pixel_y = self.pixel_min_y + pixel_y_ratio * (self.pixel_max_y - self.pixel_min_y)
        return pixel_x, pixel_y

    def pixel_to_world(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        pixel_x_ratio = (pixel_x - self.pixel_min_x) / (self.pixel_max_x - self.pixel_min_x)
        pixel_y_ratio = (pixel_y - self.pixel_min_y) / (self.pixel_max_y - self.pixel_min_y)
        if self.invert_x:
            pixel_x_ratio = 1.0 - pixel_x_ratio
        if self.invert_y:
            pixel_y_ratio = 1.0 - pixel_y_ratio
        x_ratio, y_ratio = (
            (pixel_y_ratio, pixel_x_ratio)
            if self.swap_axes
            else (pixel_x_ratio, pixel_y_ratio)
        )
        x = self.world_min_x + x_ratio * (self.world_max_x - self.world_min_x)
        y = self.world_min_y + y_ratio * (self.world_max_y - self.world_min_y)
        return x, y

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": "Adjust these values to align Gateway world coordinates with the local map image.",
            "world_bounds": {
                "min_x": self.world_min_x,
                "max_x": self.world_max_x,
                "min_y": self.world_min_y,
                "max_y": self.world_max_y,
            },
            "pixel_bounds": {
                "min_x": self.pixel_min_x,
                "max_x": self.pixel_max_x,
                "min_y": self.pixel_min_y,
                "max_y": self.pixel_max_y,
            },
            "invert_y": self.invert_y,
            "invert_x": self.invert_x,
            "swap_axes": self.swap_axes,
        }


DEFAULT_CALIBRATION = MapCalibration(
    world_min_x=-607_000.0,
    world_max_x=509_000.0,
    world_min_y=-505_000.0,
    world_max_y=607_000.0,
    pixel_min_x=0.0,
    pixel_max_x=7800.0,
    pixel_min_y=0.0,
    pixel_max_y=7817.0,
    invert_y=False,
    invert_x=False,
    swap_axes=True,
)


def load_calibration(path: Path) -> MapCalibration:
    """Load calibration, falling back safely when the file is malformed."""

    try:
        with path.open("r", encoding="utf-8") as handle:
            return MapCalibration.from_dict(json.load(handle))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        LOGGER.error("Configuration error loading map calibration: %s", exc)
        return DEFAULT_CALIBRATION


def save_calibration(path: Path, calibration: MapCalibration) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(calibration.to_dict(), handle, indent=2)
        handle.write("\n")
    temporary_path.replace(path)
