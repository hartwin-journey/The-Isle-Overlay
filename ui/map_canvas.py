"""Reusable map canvas for the full map and external mini-map window."""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from core.app_state import AppState
from core.coordinate_transform import MapCalibration
from core.data_loader import LayerRepository
from ui.map_fonts import build_map_label_font

LOGGER = logging.getLogger(__name__)
PIXMAP_CACHE: dict[str, QPixmap] = {}

LAYER_COLORS = {
    "water": "#58bde8",
    "locations": "#e5e7eb",
    "food": "#8dd66b",
    "ai": "#d991f0",
    "gastrolith": "#a89cb0",
    "salt_licks": "#e7c574",
    "spawns": "#ff9f68",
    "custom_markers": "#ffd166",
}

# Layers whose markers are drawn as per-category PNG icons, mapped to their
# folder under ui/icons/. Any category without a matching PNG falls back to the
# layer's colored dot.
CATEGORY_ICON_FOLDERS = {
    "ai": "ai",
    "gastrolith": "gastroliths",
}

# Palette sampled from the corresponding Gateway layers on VulnonaMAP.
VULNONA_MIGRATION_FILL = "#00CC77"
VULNONA_MIGRATION_OUTLINE = "#000000"
VULNONA_PATROL_FILL = "#FF0000"
VULNONA_PATROL_OUTLINE = "#EE0000"
VULNONA_SANCTUARY_FILL = "#FF99FF"
VULNONA_SANCTUARY_OUTLINE = "#FFFF99"
VULNONA_UPDRAFT_FILL = "#FF6600"
VULNONA_UPDRAFT_OUTLINE = "#FFFFFF"
WAYPOINT_HIT_RADIUS = 18
WAYPOINT_ITEM_ROLE = 0
WAYPOINT_ITEM_VALUE = "active_waypoint"


class MapCanvas(QGraphicsView):
    waypoint_requested = Signal(float, float)
    waypoint_clear_requested = Signal()

    def __init__(
        self,
        map_path: Path,
        calibration: MapCalibration,
        repository: LayerRepository,
        state: AppState,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__()
        self.map_path = map_path
        self.calibration = calibration
        self.repository = repository
        self.state = state
        self.compact = compact
        self._press_position: QPoint | None = None
        self._groups: dict[str, QGraphicsItemGroup] = {}
        self._poi_labels: list[QGraphicsSimpleTextItem] = []

        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if self.compact:
            # The Mini Map draws its edit controls above this viewport. Partial
            # scroll updates can copy those pixels into the map on some Linux
            # backing stores, leaving a ghost/duplicate control strip after
            # follow mode recenters the scene. Repaint the compact viewport in
            # full so overlaid widgets never become part of its scroll buffer.
            self.setViewportUpdateMode(
                QGraphicsView.ViewportUpdateMode.FullViewportUpdate
            )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#081015"))

        self._load_background()
        self._create_groups()
        self.render_static_layers()
        self.render_breadcrumbs()
        self.render_positions()
        self.render_waypoint()

        state.position_changed.connect(self._on_position_changed)
        state.breadcrumbs_changed.connect(self.render_breadcrumbs)
        state.waypoint_changed.connect(self.render_waypoint)
        state.layers_changed.connect(self.refresh_visibility)
        state.settings_changed.connect(self.on_settings_changed)

    def _load_background(self) -> None:
        cache_key = str(self.map_path.resolve())
        pixmap = PIXMAP_CACHE.get(cache_key, QPixmap())
        if pixmap.isNull():
            pixmap = QPixmap(str(self.map_path))
            if not pixmap.isNull():
                PIXMAP_CACHE[cache_key] = pixmap
        if pixmap.isNull():
            LOGGER.error("Map data loading error: missing or unreadable map image %s", self.map_path)
            pixmap = self._fallback_pixmap()
        self._map_pixmap = pixmap
        item = QGraphicsPixmapItem(pixmap)
        item.setZValue(0)
        self.scene().addItem(item)
        self.scene().setSceneRect(QRectF(pixmap.rect()))

    @staticmethod
    def _fallback_pixmap() -> QPixmap:
        pixmap = QPixmap(1600, 1600)
        pixmap.fill(QColor("#10242a"))
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#28454a"), 2))
        for coordinate in range(0, 1601, 100):
            painter.drawLine(coordinate, 0, coordinate, 1600)
            painter.drawLine(0, coordinate, 1600, coordinate)
        painter.setPen(QColor("#d8edf0"))
        painter.setFont(QFont("Segoe UI", 34, QFont.Weight.DemiBold))
        painter.drawText(
            pixmap.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "OFFLINE MAP PLACEHOLDER\n\nReplace map/gateway.webp\nand adjust map/calibration.json",
        )
        painter.end()
        return pixmap

    def _create_groups(self) -> None:
        for layer in (
            "migrations",
            "patrol_zones",
            "sanctuaries",
            "water",
            "updrafts",
            "locations",
            "food",
            "ai",
            "gastrolith",
            "salt_licks",
            "spawns",
            "custom_markers",
            "breadcrumbs",
            "waypoint_route",
            "player",
            "waypoint",
        ):
            group = QGraphicsItemGroup()
            group.setZValue(
                {
                    "migrations": 5,
                    "patrol_zones": 6,
                    "sanctuaries": 7,
                    "water": 10,
                    "updrafts": 11,
                    "locations": 12,
                    "food": 13,
                    "ai": 14,
                    "gastrolith": 18,
                    "salt_licks": 15,
                    "spawns": 16,
                    "custom_markers": 17,
                    "breadcrumbs": 20,
                    "waypoint_route": 25,
                    "player": 30,
                    "waypoint": 31,
                }[layer]
            )
            self.scene().addItem(group)
            self._groups[layer] = group

    def _clear_group(self, name: str) -> None:
        group = self._groups[name]
        for child in list(group.childItems()):
            self.scene().removeItem(child)

    def render_static_layers(self) -> None:
        self._poi_labels.clear()
        for name in (
            "migrations",
            "patrol_zones",
            "sanctuaries",
            "water",
            "updrafts",
            "locations",
            "food",
            "ai",
            "gastrolith",
            "salt_licks",
            "spawns",
            "custom_markers",
        ):
            self._clear_group(name)
        self._render_migrations()
        self._render_patrol_zones()
        self._render_sanctuaries()
        self._render_water_overlay()
        self._render_updrafts()
        for name in LAYER_COLORS:
            self._render_point_layer(name, LAYER_COLORS[name])
        self.refresh_visibility()
        self._update_detail_visibility()

    def _render_water_overlay(self) -> None:
        """Render Vulnona's optional water raster inside the normal water layer."""

        water_path = self.map_path.with_name(f"{self.map_path.stem}_water.webp")
        if not water_path.exists():
            return
        cache_key = str(water_path.resolve())
        pixmap = PIXMAP_CACHE.get(cache_key, QPixmap())
        if pixmap.isNull():
            pixmap = QPixmap(str(water_path))
            if not pixmap.isNull():
                PIXMAP_CACHE[cache_key] = pixmap
        if pixmap.isNull():
            LOGGER.error("Map data loading error: unreadable water overlay %s", water_path)
            return
        if pixmap.size() != self._map_pixmap.size():
            LOGGER.error(
                "Map data loading error: water overlay dimensions %sx%s do not match map %sx%s",
                pixmap.width(),
                pixmap.height(),
                self._map_pixmap.width(),
                self._map_pixmap.height(),
            )
            return
        item = QGraphicsPixmapItem(pixmap)
        item.setToolTip("Gateway water overlay")
        self._groups["water"].addToGroup(item)

    @staticmethod
    def _updraft_polygon() -> QPolygonF:
        """Return a constant-size arrow matching Vulnona's updraft symbol."""

        return QPolygonF(
            [
                QPointF(0, -17),
                QPointF(-7, -5),
                QPointF(-1, -7),
                QPointF(-3, 1),
                QPointF(0, -1),
                QPointF(3, 1),
                QPointF(1, -7),
                QPointF(7, -5),
            ]
        )

    def _render_updrafts(self) -> None:
        """Render the current offline updraft snapshot as Vulnona-style arrows."""

        group = self._groups["updrafts"]
        for point in self.repository.layers.get("updrafts", []):
            try:
                world_x = float(point["position"][0])
                world_y = float(point["position"][1])
                pixel_x, pixel_y = self.calibration.world_to_pixel(world_x, world_y)
            except (KeyError, TypeError, ValueError, IndexError):
                continue

            name = str(point.get("name", "Updraft"))
            active_hours = str(point.get("active_hours", "Unknown"))
            description = str(point.get("description", "")).strip()
            tooltip = f"{name}\nActive: {active_hours}"
            if description:
                tooltip += f"\n{description}"

            shadow = QGraphicsPolygonItem(self._updraft_polygon())
            shadow.setBrush(QBrush(QColor(0, 0, 0, 190)))
            shadow.setPen(QPen(Qt.PenStyle.NoPen))
            shadow.setPos(pixel_x + 2, pixel_y + 2)
            shadow.setOpacity(0.75)
            shadow.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            shadow.setToolTip(tooltip)
            group.addToGroup(shadow)

            marker = QGraphicsPolygonItem(self._updraft_polygon())
            marker.setBrush(QBrush(QColor(VULNONA_UPDRAFT_FILL)))
            outline = QPen(QColor(VULNONA_UPDRAFT_OUTLINE), 1.5)
            outline.setCosmetic(True)
            marker.setPen(outline)
            marker.setPos(pixel_x, pixel_y)
            marker.setOpacity(0.75)
            marker.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            marker.setToolTip(tooltip)
            group.addToGroup(marker)

    def _polygon_from_world(self, points: Any) -> QPolygonF | None:
        if not isinstance(points, list) or len(points) < 3:
            return None
        polygon = QPolygonF()
        try:
            for point in points:
                pixel = self.calibration.world_to_pixel(float(point[0]), float(point[1]))
                polygon.append(QPointF(*pixel))
        except (TypeError, ValueError, IndexError):
            return None
        return polygon

    def _render_migrations(self) -> None:
        group = self._groups["migrations"]
        individual = self.state.settings.get("individual_migrations", {})
        for zone in self.repository.layers.get("migrations", []):
            name = str(zone.get("name", "Migration zone"))
            if individual.get(name, True) is False:
                continue
            polygon = self._polygon_from_world(zone.get("polygon"))
            if polygon is None:
                continue
            color = QColor(str(zone.get("color", VULNONA_MIGRATION_FILL)))
            fill = QColor(color)
            item = QGraphicsPolygonItem(polygon)
            item.setBrush(QBrush(fill))
            outline = QPen(QColor(VULNONA_MIGRATION_OUTLINE), 2)
            outline.setCosmetic(True)
            item.setPen(outline)
            species = zone.get("species")
            notes = str(zone.get("notes", ""))
            tooltip = name
            if species:
                tooltip += f"\nSpecies: {', '.join(map(str, species)) if isinstance(species, list) else species}"
            if notes:
                tooltip += f"\n{notes}"
            item.setToolTip(tooltip)
            group.addToGroup(item)

    def _world_radius_to_pixels(self, radius: float) -> float:
        p0 = self.calibration.world_to_pixel(0.0, 0.0)
        px = self.calibration.world_to_pixel(radius, 0.0)
        py = self.calibration.world_to_pixel(0.0, radius)
        x_distance = math.hypot(px[0] - p0[0], px[1] - p0[1])
        y_distance = math.hypot(py[0] - p0[0], py[1] - p0[1])
        return (x_distance + y_distance) / 2.0

    def _render_patrol_zones(self) -> None:
        group = self._groups["patrol_zones"]
        individual = self.state.settings.get("individual_patrol_zones", {})
        for zone in self.repository.layers.get("patrol_zones", []):
            name = str(zone.get("name", "Patrol zone"))
            if individual.get(name, True) is False:
                continue
            polygons = zone.get("polygons")
            if not isinstance(polygons, list):
                polygons = [zone.get("polygon")]
            for points in polygons:
                polygon = self._polygon_from_world(points)
                if polygon is None:
                    continue
                item = QGraphicsPolygonItem(polygon)
                item.setBrush(
                    QBrush(QColor(str(zone.get("color", VULNONA_PATROL_FILL))))
                )
                outline = QPen(QColor(VULNONA_PATROL_OUTLINE), 2)
                outline.setCosmetic(True)
                item.setPen(outline)
                notes = str(zone.get("notes", ""))
                item.setToolTip(f"{name}\n{notes}".strip())
                group.addToGroup(item)

    def _render_sanctuaries(self) -> None:
        group = self._groups["sanctuaries"]
        individual = self.state.settings.get("individual_sanctuaries", {})
        for sanctuary in self.repository.layers.get("sanctuaries", []):
            name = str(sanctuary.get("name", "Sanctuary"))
            if individual.get(name, True) is False:
                continue
            item: QGraphicsPolygonItem | QGraphicsEllipseItem | None = None
            if "polygon" in sanctuary:
                polygon = self._polygon_from_world(sanctuary.get("polygon"))
                if polygon is not None:
                    item = QGraphicsPolygonItem(polygon)
            elif "position" in sanctuary and "radius" in sanctuary:
                try:
                    x, y = sanctuary["position"][:2]
                    pixel_x, pixel_y = self.calibration.world_to_pixel(float(x), float(y))
                    radius = self._world_radius_to_pixels(float(sanctuary["radius"]))
                    item = QGraphicsEllipseItem(pixel_x - radius, pixel_y - radius, radius * 2, radius * 2)
                except (TypeError, ValueError, IndexError):
                    item = None
            if item is None:
                continue
            fill = QColor(str(sanctuary.get("color", VULNONA_SANCTUARY_FILL)))
            item.setBrush(QBrush(fill))
            outline = QPen(QColor(VULNONA_SANCTUARY_OUTLINE), 2)
            outline.setCosmetic(True)
            item.setPen(outline)
            item.setToolTip(f"{name}\n{sanctuary.get('description', '')}".strip())
            group.addToGroup(item)

    def _icons_dir(self, subfolder: str) -> Path:
        """Locate a per-layer icon folder in source and frozen builds."""

        if getattr(sys, "frozen", False):
            return self.map_path.parent.parent / "ui" / "icons" / subfolder
        return Path(__file__).resolve().parent / "icons" / subfolder

    def _load_category_icon(
        self, subfolder: str, category: str, size: int
    ) -> QPixmap | None:
        """Return a cached, scaled category PNG, or None to fall back to a dot."""

        slug = category.strip().lower().replace(" ", "_")
        if not slug:
            return None
        cache_key = f"cat_icon::{subfolder}::{slug}::{size}"
        cached = PIXMAP_CACHE.get(cache_key)
        if cached is not None:
            return cached if not cached.isNull() else None
        path = self._icons_dir(subfolder) / f"{slug}.png"
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        PIXMAP_CACHE[cache_key] = pixmap
        return pixmap if not pixmap.isNull() else None

    def _render_point_layer(self, name: str, color_name: str) -> None:
        group = self._groups[name]
        color = QColor(color_name)
        for point in self.repository.layers.get(name, []):
            try:
                world_x = float(point["position"][0])
                world_y = float(point["position"][1])
                pixel_x, pixel_y = self.calibration.world_to_pixel(world_x, world_y)
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            marker: QGraphicsItem | None = None
            if name in CATEGORY_ICON_FOLDERS:
                icon_size = 24 if not self.compact else 18
                icon = self._load_category_icon(
                    CATEGORY_ICON_FOLDERS[name],
                    str(point.get("category", "")),
                    icon_size,
                )
                if icon is not None:
                    pixmap_item = QGraphicsPixmapItem(icon)
                    pixmap_item.setOffset(-icon.width() / 2, -icon.height() / 2)
                    pixmap_item.setPos(pixel_x, pixel_y)
                    pixmap_item.setTransformationMode(
                        Qt.TransformationMode.SmoothTransformation
                    )
                    # Keep icons a constant on-screen size at any map zoom.
                    pixmap_item.setFlag(
                        QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                        True,
                    )
                    marker = pixmap_item
            if marker is None:
                # Fallback: the original colored dot (any layer, or an AI
                # category without a matching PNG in ui/icons/ai).
                radius = 7 if not self.compact else 6
                marker = QGraphicsEllipseItem(
                    pixel_x - radius, pixel_y - radius, radius * 2, radius * 2
                )
                marker.setBrush(QBrush(color))
                marker.setPen(QPen(QColor("#071115"), 2))
            marker.setToolTip(
                f"{point.get('name', name.replace('_', ' ').title())}\n{point.get('description', '')}".strip()
            )
            group.addToGroup(marker)
            show_labels = (
                bool(self.state.settings.get("mini_map_show_poi_labels", False))
                if self.compact
                else True
            )
            if show_labels and bool(point.get("show_label", True)):
                label = QGraphicsSimpleTextItem(str(point.get("name", "")))
                label.setBrush(QBrush(QColor("#e7f1f5")))
                label_outline = QPen(QColor(4, 10, 14, 235), 1.15)
                label_outline.setCosmetic(True)
                label.setPen(label_outline)
                font_key = (
                    "poi_label_font_size_mini"
                    if self.compact
                    else "poi_label_font_size_full"
                )
                label.setFont(
                    build_map_label_font(
                        self.state.settings,
                        int(self.state.settings[font_key]),
                    )
                )
                label.setFlag(
                    QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                    True,
                )
                label.setPos(pixel_x + 9, pixel_y - 8)
                label.setZValue(2)
                group.addToGroup(label)
                self._poi_labels.append(label)

    def render_breadcrumbs(self) -> None:
        self._clear_group("breadcrumbs")
        points = list(self.state.breadcrumbs)
        if not points:
            self.refresh_visibility()
            return
        group = self._groups["breadcrumbs"]
        if self.state.settings["breadcrumb_connect_lines"] and len(points) > 1:
            path = QPainterPath()
            first = self.calibration.world_to_pixel(points[0].x, points[0].y)
            path.moveTo(*first)
            for position in points[1:]:
                path.lineTo(*self.calibration.world_to_pixel(position.x, position.y))
            underlay = QGraphicsPathItem(path)
            underlay_pen = QPen(
                QColor(5, 12, 16, 210),
                7,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            underlay_pen.setCosmetic(True)
            underlay.setPen(underlay_pen)
            group.addToGroup(underlay)
            path_item = QGraphicsPathItem(path)
            trail_pen = QPen(
                QColor("#FFD166"),
                3,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            trail_pen.setCosmetic(True)
            path_item.setPen(trail_pen)
            group.addToGroup(path_item)
        step = max(1, len(points) // 120)
        for position in points[::step]:
            pixel_x, pixel_y = self.calibration.world_to_pixel(position.x, position.y)
            dot = QGraphicsEllipseItem(-3, -3, 6, 6)
            dot.setPos(pixel_x, pixel_y)
            dot.setBrush(QBrush(QColor("#FFE6A1")))
            dot_pen = QPen(QColor("#071115"), 1.5)
            dot_pen.setCosmetic(True)
            dot.setPen(dot_pen)
            dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            group.addToGroup(dot)
        self.refresh_visibility()

    def render_positions(self) -> None:
        self._clear_group("player")
        group = self._groups["player"]
        if self.state.previous_position is not None:
            pixel_x, pixel_y = self.calibration.world_to_pixel(
                self.state.previous_position.x, self.state.previous_position.y
            )
            previous = QGraphicsEllipseItem(-6, -6, 12, 12)
            previous.setPos(pixel_x, pixel_y)
            previous.setBrush(QBrush(QColor(116, 136, 148, 205)))
            previous_pen = QPen(QColor("#F0F5F7"), 2)
            previous_pen.setCosmetic(True)
            previous.setPen(previous_pen)
            previous.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            previous.setToolTip("Previous copied position")
            group.addToGroup(previous)
        if self.state.current_position is not None:
            pixel_x, pixel_y = self.calibration.world_to_pixel(
                self.state.current_position.x, self.state.current_position.y
            )
            shadow = QGraphicsEllipseItem(-16, -16, 32, 32)
            shadow.setPos(pixel_x, pixel_y)
            shadow.setBrush(QBrush(QColor(4, 10, 14, 145)))
            shadow.setPen(QPen(Qt.PenStyle.NoPen))
            shadow.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            halo = QGraphicsEllipseItem(-13, -13, 26, 26)
            halo.setPos(pixel_x, pixel_y)
            halo.setBrush(QBrush(QColor(38, 214, 239, 95)))
            halo_pen = QPen(QColor("#E9FCFF"), 2)
            halo_pen.setCosmetic(True)
            halo.setPen(halo_pen)
            halo.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            player = QGraphicsEllipseItem(-6, -6, 12, 12)
            player.setPos(pixel_x, pixel_y)
            player.setBrush(QBrush(QColor("#19D3EE")))
            player_pen = QPen(QColor("#FFFFFF"), 2)
            player_pen.setCosmetic(True)
            player.setPen(player_pen)
            player.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            player.setToolTip("Current copied player position")
            group.addToGroup(shadow)
            group.addToGroup(halo)
            group.addToGroup(player)
        self.refresh_visibility()

    def render_waypoint(self) -> None:
        self._clear_group("waypoint_route")
        self._clear_group("waypoint")
        waypoint = self.state.active_waypoint
        if waypoint is None:
            return
        pixel_x, pixel_y = self.calibration.world_to_pixel(waypoint.x, waypoint.y)
        current = self.state.current_position
        if current is not None:
            player_x, player_y = self.calibration.world_to_pixel(current.x, current.y)
            route_path = QPainterPath(QPointF(player_x, player_y))
            route_path.lineTo(pixel_x, pixel_y)

            underlay = QGraphicsPathItem(route_path)
            underlay_pen = QPen(
                QColor(5, 12, 16, 220),
                7,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            underlay_pen.setCosmetic(True)
            underlay.setPen(underlay_pen)
            self._groups["waypoint_route"].addToGroup(underlay)

            route = QGraphicsPathItem(route_path)
            route_pen = QPen(
                QColor("#ff5d6c"),
                3,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
            route_pen.setCosmetic(True)
            route.setPen(route_pen)
            route.setToolTip(waypoint.name)
            self._groups["waypoint_route"].addToGroup(route)

        size = 14
        polygon = QPolygonF(
            [
                QPointF(0, -size),
                QPointF(size * 0.75, 0),
                QPointF(0, size),
                QPointF(-size * 0.75, 0),
            ]
        )
        marker = QGraphicsPolygonItem(polygon)
        marker.setPos(pixel_x, pixel_y)
        marker.setBrush(QBrush(QColor("#ff5d6c")))
        waypoint_pen = QPen(QColor("#fff0f1"), 2)
        waypoint_pen.setCosmetic(True)
        marker.setPen(waypoint_pen)
        marker.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
            True,
        )
        marker.setData(WAYPOINT_ITEM_ROLE, WAYPOINT_ITEM_VALUE)
        marker.setToolTip(waypoint.name)
        self._groups["waypoint"].addToGroup(marker)
        if not self.compact:
            label = QGraphicsSimpleTextItem(waypoint.name)
            label.setBrush(QBrush(QColor("#fff3f4")))
            label_outline = QPen(QColor(4, 10, 14, 235), 1.15)
            label_outline.setCosmetic(True)
            label.setPen(label_outline)
            label.setFont(
                build_map_label_font(
                    self.state.settings,
                    max(8, int(self.state.settings["poi_label_font_size_full"]) - 2),
                )
            )
            label.setPos(pixel_x + 13, pixel_y - 12)
            label.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
            label.setData(WAYPOINT_ITEM_ROLE, WAYPOINT_ITEM_VALUE)
            self._groups["waypoint"].addToGroup(label)

    def _update_detail_visibility(self) -> None:
        """Hide dense POI labels at overview zoom levels."""

        threshold = 0.20 if not self.compact else 0.35
        labels_visible = abs(self.transform().m11()) >= threshold
        for label in self._poi_labels:
            label.setVisible(labels_visible)

    def refresh_visibility(self) -> None:
        enabled = self.state.settings["layers"]
        layer_opacity = self.state.settings.get("layer_opacity", {})
        for name, group in self._groups.items():
            if name in {"waypoint", "waypoint_route"}:
                group.setVisible(True)
                group.setOpacity(1.0)
            else:
                group.setVisible(bool(enabled.get(name, True)))
                group.setOpacity(float(layer_opacity.get(name, 1.0)))

    def on_settings_changed(self) -> None:
        self.render_static_layers()
        self.render_breadcrumbs()
        self.render_waypoint()
        self.refresh_visibility()

    def _on_position_changed(self, _current: object, _previous: object) -> None:
        self.render_positions()
        self.render_waypoint()
        if self.compact and self.state.settings["player_centered_mode"]:
            self.recenter_on_player()

    def recenter_on_player(self) -> None:
        position = self.state.current_position
        if position is None:
            return
        self.centerOn(QPointF(*self.calibration.world_to_pixel(position.x, position.y)))
        if self.compact:
            # Queue a clean frame after QGraphicsView has adjusted its scroll
            # position; this also covers Linux compositors that defer the move.
            self.viewport().update()

    def reset_view(self) -> None:
        self.resetTransform()
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._update_detail_visibility()

    def set_calibration(self, calibration: MapCalibration) -> None:
        self.calibration = calibration
        self.render_static_layers()
        self.render_breadcrumbs()
        self.render_positions()
        self.render_waypoint()

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        current_scale = self.transform().m11()
        if (factor > 1 and current_scale < 20.0) or (factor < 1 and current_scale > 0.05):
            self.scale(factor, factor)
            self._update_detail_visibility()

    def cancel_mouse_interaction(self) -> None:
        """Reset local drag bookkeeping when the overlay becomes click-through."""

        self._press_position = None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.viewport().unsetCursor()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def _active_waypoint_hit(self, view_position: QPoint) -> bool:
        waypoint = self.state.active_waypoint
        if waypoint is None:
            return False
        item = self.itemAt(view_position)
        if item is not None and item.data(WAYPOINT_ITEM_ROLE) == WAYPOINT_ITEM_VALUE:
            return True
        scene_position = QPointF(
            *self.calibration.world_to_pixel(waypoint.x, waypoint.y)
        )
        marker_position = self.mapFromScene(scene_position)
        delta = view_position - marker_position
        return delta.x() ** 2 + delta.y() ** 2 <= WAYPOINT_HIT_RADIUS**2

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        press = self._press_position
        super().mouseReleaseEvent(event)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and press is not None
            and (event.position().toPoint() - press).manhattanLength() <= 4
        ):
            view_position = event.position().toPoint()
            if self._active_waypoint_hit(view_position):
                self.waypoint_clear_requested.emit()
            else:
                scene_position = self.mapToScene(view_position)
                if self.sceneRect().contains(scene_position):
                    world_x, world_y = self.calibration.pixel_to_world(
                        scene_position.x(), scene_position.y()
                    )
                    self.waypoint_requested.emit(world_x, world_y)
        self._press_position = None

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self.compact and self.state.current_position is None:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
