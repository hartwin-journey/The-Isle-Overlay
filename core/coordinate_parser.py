"""Strict parser for manually copied The Isle coordinate text.

The parser accepts only a complete three-number coordinate record. It never
searches arbitrary clipboard text for embedded coordinates, which reduces the
chance of treating unrelated clipboard content as a position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class CoordinateParseError(ValueError):
    """Raised when clipboard text is not a valid coordinate record."""


@dataclass(frozen=True, slots=True)
class ParsedCoordinates:
    x: float
    y: float
    z: float


# A component is either an ordinary number or one with correctly placed
# thousands separators. Scientific notation is intentionally not accepted.
_NUMBER = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_PLAIN_PATTERN = re.compile(
    rf"^\s*(?P<x>{_NUMBER})\s*,\s*(?P<y>{_NUMBER})\s*,\s*(?P<z>{_NUMBER})\s*$"
)
_LABELED_PATTERN = re.compile(
    rf"^\s*(?:X\s*[:=]\s*)?(?P<x>{_NUMBER})\s*[,;]\s*"
    rf"(?:Y\s*[:=]\s*)?(?P<y>{_NUMBER})\s*[,;]\s*"
    rf"(?:Z\s*[:=]\s*)?(?P<z>{_NUMBER})\s*$",
    re.IGNORECASE,
)


def _to_float(component: str) -> float:
    return float(component.replace(",", ""))


def parse_coordinates(text: str) -> ParsedCoordinates:
    """Parse a complete clipboard string into X, Y and Z.

    Accepted examples include ``88,879.526, 288,696.110, 21,112.882`` and
    ``X=-88,879.526, Y=288,696.110, Z=21,112.882``.
    """

    if not isinstance(text, str):
        raise CoordinateParseError("clipboard value is not text")
    if not text or len(text) > 256 or "\n" in text or "\r" in text:
        raise CoordinateParseError("clipboard text is not a single coordinate line")

    match = _PLAIN_PATTERN.fullmatch(text) or _LABELED_PATTERN.fullmatch(text)
    if match is None:
        raise CoordinateParseError("clipboard text does not match the coordinate format")

    try:
        values = ParsedCoordinates(
            x=_to_float(match.group("x")),
            y=_to_float(match.group("y")),
            z=_to_float(match.group("z")),
        )
    except (TypeError, ValueError) as exc:
        raise CoordinateParseError("coordinate contains a non-numeric value") from exc

    # These generous limits catch accidental parsing and infinities while not
    # imposing knowledge of a particular map calibration.
    if any(abs(value) > 10_000_000 for value in (values.x, values.y, values.z)):
        raise CoordinateParseError("coordinate is outside supported numeric limits")
    return values

