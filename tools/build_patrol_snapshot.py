"""Rebuild the local Gateway patrol-zone snapshot from recorded Vulnona vectors.

The source vectors below are a development-time snapshot.  This script never
contacts Vulnona and is not used by the companion at runtime.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERN = re.compile(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

# SVG coordinates from VulnonaMAP Gateway v0.21.772.
PATHS = {
    "Center Jungle": "M 1377.5,1257.5 1435,1257.5 1435,1382.5 1380,1382.5 1377.5,1257.5",
    "Delta": (
        "M 1670,1505 1725,1502.5 1732.5,1597.5 1677.5,1600 1670,1505 "
        "M 1727.5,1570 1752.5,1535 1890,1622.5 1867.5,1657.5 1727.5,1570 "
        "M 1565,1465 1612.5,1462.5 1620,1592.5 1572.5,1595 1565,1465 "
        "M 1673.2,1382.3 A 35,62.5 46 0 0 1721.8,1432.7 A 35,62.5 46 0 0 1673.2,1382.3 Z "
        "M 1740,1715 A 37.5,37.5 0 0 0 1815,1715 A 37.5,37.5 0 0 0 1740,1715 Z"
    ),
    "Delta River": "M 2015,1197.5 2057.5,1242.5 1987.5,1302.5 1945,1257.5 2015,1197.5",
    "East Coast": (
        "M 2542.5,1112.5 A 70,70 0 0 0 2682.5,1112.5 A 70,70 0 0 0 2542.5,1112.5 Z "
        "M 2457.5,1292.5 A 62.5,70 0 0 0 2582.5,1292.5 A 62.5,70 0 0 0 2457.5,1292.5 Z"
    ),
    "Fork Plains": (
        "M 1902.5,1015 2007.5,1015 2007.5,1115 1902.5,1115 1902.5,1015 "
        "M 1740,1220 1817.5,1220 1820,1342.5 1797.5,1352.5 1745,1357.5 1740,1220"
    ),
    "Highlands": (
        "M 1130,1062.5 1172.5,1112.5 1135,1145 1090,1092.5 1130,1062.5 "
        "M 1207.5,1110 A 37.5,37.5 0 0 0 1282.5,1110 A 37.5,37.5 0 0 0 1207.5,1110 Z "
        "M 950,1160 A 32.5,32.5 0 0 0 1015,1160 A 32.5,32.5 0 0 0 950,1160 Z "
        "M 900,1387.5 A 32.5,32.5 0 0 0 965,1387.5 A 32.5,32.5 0 0 0 900,1387.5 Z"
    ),
    "NE Cape": "M 2352.5,230 2420,247.5 2357.5,482.5 2287.5,457.5 2352.5,230",
    "NE Cape-2": (
        "M 2257.5,330 A 50,50 0 0 0 2357.5,330 A 50,50 0 0 0 2257.5,330 Z "
        "M 2350,437.5 A 55,55 0 0 0 2460,437.5 A 55,55 0 0 0 2350,437.5 Z"
    ),
    "North Plains": (
        "M 1855,442.5 1960,442.5 1962.5,522.5 1947.5,532.5 1855,532.5 1855,442.5 "
        "M 1960,372.5 A 30,30 0 0 0 2020,372.5 A 30,30 0 0 0 1960,372.5 Z "
        "M 2092.5,657.5 A 30,30 0 0 0 2152.5,657.5 A 30,30 0 0 0 2092.5,657.5 Z "
        "M 2140,732.5 A 30,30 0 0 0 2200,732.5 A 30,30 0 0 0 2140,732.5 Z"
    ),
    "Northern Jungle": (
        "M 1527.5,645 1630,645 1630,740 1527.5,740 1527.5,645 "
        "M 1532.5,757.5 1635,757.5 1635,857.5 1532.5,857.5 1532.5,757.5"
    ),
    "Pits": (
        "M 295,1972.5 A 50,50 0 0 0 395,1972.5 A 50,50 0 0 0 295,1972.5 Z "
        "M 352.5,2050 A 40,40 0 0 0 432.5,2050 A 40,40 0 0 0 352.5,2050 Z "
        "M 432.5,2105 A 40,40 0 0 0 512.5,2105 A 40,40 0 0 0 432.5,2105 Z "
        "M 557.5,2152.5 A 52.5,52.5 0 0 0 662.5,2152.5 A 52.5,52.5 0 0 0 557.5,2152.5 Z "
        "M 525,2237.5 A 40,40 0 0 0 605,2237.5 A 40,40 0 0 0 525,2237.5 Z "
        "M 647.5,2227.5 A 52.5,52.5 0 0 0 752.5,2227.5 A 52.5,52.5 0 0 0 647.5,2227.5 Z "
        "M 597.5,2390 A 40,40 0 0 0 677.5,2390 A 40,40 0 0 0 597.5,2390 Z "
        "M 607.5,2532.5 A 57.5,57.5 0 0 0 722.5,2532.5 A 57.5,57.5 0 0 0 607.5,2532.5 Z "
        "M 495,2387.5 A 45,35 0 0 0 585,2387.5 A 45,35 0 0 0 495,2387.5 Z "
        "M 292.5,2447.5 A 57.5,57.5 0 0 0 407.5,2447.5 A 57.5,57.5 0 0 0 292.5,2447.5 Z "
        "M 97.5,2317.5 A 57.5,57.5 0 0 0 212.5,2317.5 A 57.5,57.5 0 0 0 97.5,2317.5 Z"
    ),
    "Sandbank Bay": (
        "M 2207.5,1472.5 2347.5,1512.5 2337.5,1555 2197.5,1517.5 2207.5,1472.5 "
        "M 2092.5,1467.5 2140,1460 2162.5,1607.5 2115,1615 2092.5,1467.5 "
        "M 2105,1592.5 2147.5,1622.5 2060,1755 2017.5,1722.5 2105,1592.5"
    ),
    "South Plains": (
        "M 582.5,1900 A 50,50 0 0 0 682.5,1900 A 50,50 0 0 0 582.5,1900 Z "
        "M 722.5,2185 A 52.5,52.5 0 0 0 827.5,2185 A 52.5,52.5 0 0 0 722.5,2185 Z"
    ),
    "Southern Beach": (
        "M 1270,2352.5 1362.5,2440 1302.5,2497.5 1210,2410 1270,2352.5 "
        "M 1105,2380 1292.5,2525 1237.5,2590 1052.5,2440 1105,2380 "
        "M 967.5,2292.5 A 57.5,57.5 0 0 0 1082.5,2292.5 A 57.5,57.5 0 0 0 967.5,2292.5 Z"
    ),
    "Swamps": (
        "M 1575,1990 1665,1990 1665,2120 1572.5,2120 1572.5,1990 "
        "M 1362.5,2037.5 1447.5,2037.5 1447.5,2170 1362.5,2170 1362.5,2037.5 "
        "M 1160,2245 1290,2245 1290,2332.5 1160,2332.5 1160,2245"
    ),
    "Swamps-q": (
        "M 1215,2135 A 62.5,62.5 0 0 0 1340,2135 A 62.5,62.5 0 0 0 1215,2135 Z "
        "M 1235,2277.5 A 52.5,52.5 0 0 0 1340,2277.5 A 52.5,52.5 0 0 0 1235,2277.5 Z "
        "M 1357.5,2322.5 A 40,40 0 0 0 1437.5,2322.5 A 40,40 0 0 0 1357.5,2322.5 Z "
        "M 1475,2250 A 72.5,72.5 0 0 0 1620,2250 A 72.5,72.5 0 0 0 1475,2250 Z"
    ),
    "West Rail": (
        "M 300,1355 400,1355 400,1555 300,1555 300,1355 "
        "M 405,1580 A 50,50 0 0 0 505,1580 A 50,50 0 0 0 405,1580 Z "
        "M 495,1487.5 A 50,50 0 0 0 595,1487.5 A 50,50 0 0 0 495,1487.5 Z "
        "M 602.5,1582.5 A 40,40 0 0 0 682.5,1582.5 A 40,40 0 0 0 602.5,1582.5 Z "
        "M 655,1532.5 A 42.5,42.5 0 0 0 740,1532.5 A 42.5,42.5 0 0 0 655,1532.5 Z"
    ),
}

ELLIPSES = {
    "Mudflats": (525.0, 1882.5, 37.5, 37.5, 0.0),
    "Port hill": (2362.5, 757.5, 27.5, 27.5, 0.0),
    "Radio Tower": (2587.5, 1000.0, 40.0, 40.0, 0.0),
}


def _browser_to_world(point: tuple[float, float]) -> list[float]:
    x, y = point
    world_x = -607_000.0 + (y / 2790.0) * 1_116_000.0
    world_y = -505_000.0 + (x / 2780.0) * 1_112_000.0
    return [round(world_x, 1), round(world_y, 1)]


def _vector_angle(ux: float, uy: float, vx: float, vy: float) -> float:
    return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)


def _arc_points(
    start: tuple[float, float],
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
    end: tuple[float, float],
) -> list[tuple[float, float]]:
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [end]
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (start[0] - end[0]) / 2.0, (start[1] - end[1]) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    scale = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if scale > 1.0:
        factor = math.sqrt(scale)
        rx *= factor
        ry *= factor
    numerator = max(0.0, rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p)
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coefficient = (-1.0 if large_arc == sweep else 1.0) * math.sqrt(
        numerator / denominator if denominator else 0.0
    )
    cxp = coefficient * rx * y1p / ry
    cyp = coefficient * -ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (start[0] + end[0]) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (start[1] + end[1]) / 2.0
    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    x2p = cos_phi * (end[0] - cx) + sin_phi * (end[1] - cy)
    y2p = -sin_phi * (end[0] - cx) + cos_phi * (end[1] - cy)
    vx, vy = (x2p - cxp) / rx, (y2p - cyp) / ry
    start_angle = _vector_angle(1.0, 0.0, ux, uy)
    delta = _vector_angle(ux, uy, vx, vy)
    if not sweep and delta > 0:
        delta -= math.tau
    if sweep and delta < 0:
        delta += math.tau
    steps = max(4, math.ceil(abs(delta) * max(rx, ry) / 10.0))
    return [
        (
            cx + cos_phi * rx * math.cos(start_angle + delta * index / steps)
            - sin_phi * ry * math.sin(start_angle + delta * index / steps),
            cy + sin_phi * rx * math.cos(start_angle + delta * index / steps)
            + cos_phi * ry * math.sin(start_angle + delta * index / steps),
        )
        for index in range(1, steps + 1)
    ]


def _parse_path(value: str) -> list[list[tuple[float, float]]]:
    tokens = TOKEN_PATTERN.findall(value)
    polygons: list[list[tuple[float, float]]] = []
    polygon: list[tuple[float, float]] = []
    current: tuple[float, float] | None = None
    start: tuple[float, float] | None = None
    command = ""
    index = 0

    def finish() -> None:
        nonlocal polygon, current, start
        if len(polygon) >= 3:
            polygons.append(polygon)
        polygon, current, start = [], None, None

    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command == "M":
            if polygon:
                finish()
            current = (float(tokens[index]), float(tokens[index + 1]))
            index += 2
            start = current
            polygon = [current]
            while index < len(tokens) and not tokens[index].isalpha():
                current = (float(tokens[index]), float(tokens[index + 1]))
                index += 2
                polygon.append(current)
        elif command == "A":
            while index < len(tokens) and not tokens[index].isalpha():
                values = [float(token) for token in tokens[index : index + 7]]
                index += 7
                end = (values[5], values[6])
                if current is not None:
                    polygon.extend(
                        _arc_points(
                            current,
                            values[0],
                            values[1],
                            values[2],
                            bool(values[3]),
                            bool(values[4]),
                            end,
                        )
                    )
                current = end
        elif command.upper() == "Z":
            if start is not None and current != start:
                polygon.append(start)
            finish()
            command = ""
        else:
            raise ValueError(f"Unsupported patrol path command: {command}")
    if polygon:
        finish()
    return polygons


def main() -> int:
    polygons_by_name: dict[str, list[list[list[float]]]] = defaultdict(list)
    for name, value in PATHS.items():
        for polygon in _parse_path(value):
            polygons_by_name[name].append([_browser_to_world(point) for point in polygon])
    for name, (cx, cy, rx, ry, rotation) in ELLIPSES.items():
        angle = math.radians(rotation)
        polygon = []
        for index in range(36):
            theta = index / 36.0 * math.tau
            dx, dy = rx * math.cos(theta), ry * math.sin(theta)
            polygon.append(
                _browser_to_world(
                    (
                        cx + dx * math.cos(angle) - dy * math.sin(angle),
                        cy + dx * math.sin(angle) + dy * math.cos(angle),
                    )
                )
            )
        polygons_by_name[name].append(polygon)

    payload = {
        "format_version": 1,
        "source": {
            "name": "VulnonaMAP",
            "url": "https://vulnona.com/game/map/",
            "map": "Gateway",
            "map_version": "0.21.772",
            "retrieved": "2026-08-29",
        },
        "note": "Editable local snapshot of visible Gateway patrol-zone geometry. Zones may change with game/map updates.",
        "items": [
            {
                "name": name,
                "source_id": name,
                "polygons": polygons,
                "color": "#FF0000",
            }
            for name, polygons in polygons_by_name.items()
        ],
    }
    output = PROJECT_ROOT / "data" / "patrol_zones.json"
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['items'])} patrol zones to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
