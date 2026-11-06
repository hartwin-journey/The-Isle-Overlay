"""Show a Qt widget as a Wayland layer-shell overlay.

Wayland compositors decide where ordinary windows go and keep them on one
workspace, so a normal "always on top" window cannot follow the player onto
the game's workspace or float above a fullscreen game. The wlr-layer-shell
protocol exists for exactly this (panels, docks, on-screen displays): an
overlay-layer surface belongs to a monitor rather than a workspace and is
drawn above fullscreen windows. niri, Sway, Hyprland, river, KDE Plasma,
COSMIC and other wlroots compositors support it; GNOME does not.

Qt (as bundled with PySide6) cannot give its own windows that role, so this
host keeps the widget off screen (``WA_DontShowOnScreen``), renders it into a
shared-memory buffer on a separate Wayland connection, and forwards pointer
input back to the widget. Click-through mode is an empty input region, so the
compositor sends every click straight to the game.

Nothing here touches the game: it is an ordinary desktop overlay surface.
"""

from __future__ import annotations

import atexit
import logging
import mmap
import os
import weakref
from typing import Any

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QSocketNotifier,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QGuiApplication,
    QImage,
    QMouseEvent,
    QPainter,
    QRegion,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

LOGGER = logging.getLogger(__name__)

# Linux input event codes (linux/input-event-codes.h).
_BUTTONS = {
    0x110: Qt.MouseButton.LeftButton,
    0x111: Qt.MouseButton.RightButton,
    0x112: Qt.MouseButton.MiddleButton,
    0x113: Qt.MouseButton.BackButton,
    0x114: Qt.MouseButton.ForwardButton,
}

_CURSOR_SHAPES = {
    Qt.CursorShape.ArrowCursor: "default",
    Qt.CursorShape.PointingHandCursor: "pointer",
    Qt.CursorShape.CrossCursor: "crosshair",
    Qt.CursorShape.OpenHandCursor: "grab",
    Qt.CursorShape.ClosedHandCursor: "grabbing",
    Qt.CursorShape.SizeFDiagCursor: "nwse_resize",
    Qt.CursorShape.SizeBDiagCursor: "nesw_resize",
    Qt.CursorShape.SizeAllCursor: "move",
    Qt.CursorShape.IBeamCursor: "text",
    Qt.CursorShape.ForbiddenCursor: "not_allowed",
    Qt.CursorShape.WaitCursor: "wait",
}

_RENDER_INTERVAL_MS = 50
# Coalesce redraws triggered by input/resize to roughly one per frame.
_RENDER_COALESCE_MS = 16


def _input_debug_enabled() -> bool:
    return os.environ.get("ISLE_COMPANION_DEBUG_INPUT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

# pywayland frees proxies from garbage collection. If that happens after the
# display connection is gone (interpreter shutdown), libwayland segfaults, so
# every overlay disconnects explicitly before Python tears down.
_LIVE_OVERLAYS: "weakref.WeakSet[WaylandLayerOverlay]" = weakref.WeakSet()


@atexit.register
def _close_live_overlays() -> None:
    for overlay in list(_LIVE_OVERLAYS):
        overlay.close()


def layer_shell_disabled_by_env() -> bool:
    return os.environ.get("ISLE_COMPANION_LAYER_SHELL", "").strip().lower() in {
        "0",
        "off",
        "false",
        "no",
    }


def layer_shell_candidate() -> bool:
    """Cheap check: could this session use a layer-shell overlay at all?"""

    if os.name == "nt" or layer_shell_disabled_by_env():
        return False
    if not os.environ.get("WAYLAND_DISPLAY"):
        return False
    platform = QGuiApplication.platformName().lower()
    return platform.startswith("wayland") or platform == "xcb"


class _ShmBuffer:
    """One ARGB8888 shared-memory buffer the compositor can read."""

    def __init__(self, shm: Any, width: int, height: int) -> None:
        from pywayland.protocol.wayland import WlShm

        self.width = width
        self.height = height
        self.stride = width * 4
        self.size = self.stride * height
        self.busy = False
        self._fd = os.memfd_create("isle-companion-overlay", os.MFD_CLOEXEC)
        os.ftruncate(self._fd, self.size)
        self.data = mmap.mmap(self._fd, self.size)
        pool = shm.create_pool(self._fd, self.size)
        self.buffer = pool.create_buffer(
            0, width, height, self.stride, WlShm.format.argb8888.value
        )
        pool.destroy()
        self.buffer.dispatcher["release"] = self._released

    def _released(self, _buffer: Any) -> None:
        self.busy = False

    def destroy(self) -> None:
        try:
            self.buffer.destroy()
        finally:
            self.data.close()
            os.close(self._fd)


class WaylandLayerOverlay(QObject):
    """Host ``widget`` on a layer-shell overlay surface instead of a window."""

    NAMESPACE = "isle-companion-minimap"

    def __init__(
        self,
        widget: QWidget,
        globals_: dict[str, Any],
        display: Any,
        *,
        namespace: str = NAMESPACE,
        keyboard: bool = False,
    ) -> None:
        super().__init__(widget)
        self.widget = widget
        self._namespace = namespace
        # Exclusive keyboard focus (e.g. Esc in the area picker). The Mini Map
        # never takes the keyboard, so the game keeps receiving every key.
        self._wants_keyboard = keyboard
        self._keyboard: Any = None
        self._display = display
        self._registry = globals_.pop("_registry")
        self._compositor = globals_["wl_compositor"]
        self._shm = globals_["wl_shm"]
        self._layer_shell = globals_["zwlr_layer_shell_v1"]
        self._cursor_manager = globals_.get("wp_cursor_shape_manager_v1")
        self._relative_manager = globals_.get("zwp_relative_pointer_manager_v1")
        self._relative_pointer: Any = None
        self._outputs: dict[str, Any] = globals_.get("outputs", {})
        self._output_scale: dict[Any, int] = globals_.get("output_scales", {})

        self._surface: Any = None
        self._layer_surface: Any = None
        self._configured = False
        self._buffers: list[_ShmBuffer] = []
        self._buffer_key: tuple[int, int, int] | None = None
        self._last_frame: bytes | None = None
        self._interactive = False
        self._opacity = 1.0
        self._output_name: str | None = None
        self._output_origin = QPoint(0, 0)
        # Where the compositor has actually placed the surface. Pointer
        # coordinates are relative to this, which lags behind widget.pos()
        # while a move is in flight.
        self._confirmed_pos = QPoint(0, 0)
        self._sync_callbacks: list[Any] = []

        self._pointer: Any = None
        self._cursor_device: Any = None
        self._enter_serial = 0
        self._cursor_shape = ""
        self._pointer_inside = False
        self._pointer_pos = QPointF()
        self._buttons = Qt.MouseButton.NoButton
        self._grab_target: QWidget | None = None
        self._wheel_steps = 0.0
        self._wheel_pixels = 0.0
        self._wheel_horizontal = 0.0
        # Drag tracking. Surface-local coordinates cannot be trusted while the
        # surface itself moves (the compositor applies a move some time after
        # the request), so the global pointer position during a press is
        # integrated from relative motion instead. Without relative-pointer
        # support the surface stays put during the press and moves on release.
        self._drag_origin = QPoint()
        self._drag_press_local = QPointF()
        self._drag_global = QPointF()
        self._motion_pending = False

        seat = globals_.get("wl_seat")
        if seat is not None:
            seat.dispatcher["capabilities"] = self._seat_capabilities
            # Apply the capabilities announced while connecting.
            self._seat_capabilities(seat, globals_["seat_capabilities"][0])

        self._notifier = QSocketNotifier(
            display.get_fd(), QSocketNotifier.Type.Read, self
        )
        self._notifier.activated.connect(self._read_events)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(_RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self.render)
        self._render_soon = QTimer(self)
        self._render_soon.setSingleShot(True)
        self._render_soon.setInterval(_RENDER_COALESCE_MS)
        self._render_soon.timeout.connect(self.render)
        self._debug_input = _input_debug_enabled()

        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        widget.installEventFilter(self)
        _LIVE_OVERLAYS.add(self)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.close)
        self._flush()

    # ------------------------------------------------------------------ setup

    @classmethod
    def create(
        cls,
        widget: QWidget,
        *,
        namespace: str = NAMESPACE,
        keyboard: bool = False,
    ) -> "WaylandLayerOverlay | None":
        """Return a host when the compositor supports layer-shell, else None."""

        if not layer_shell_candidate():
            return None
        try:
            from pywayland.client import Display
            from pywayland.protocol.wayland import (
                WlCompositor,
                WlOutput,
                WlSeat,
                WlShm,
            )

            from core.wayland_protocols.wlr_layer_shell_unstable_v1 import (
                ZwlrLayerShellV1,
            )
        except Exception as exc:  # pywayland missing or libwayland unavailable
            LOGGER.info("Layer-shell overlay unavailable: %s", exc)
            return None
        try:
            display = Display()
            display.connect()
        except Exception as exc:
            LOGGER.info("Could not connect to the Wayland display: %s", exc)
            return None

        announced: dict[str, list[tuple[int, int]]] = {}
        registry = display.get_registry()

        def on_global(_registry: Any, name: int, interface: str, version: int) -> None:
            announced.setdefault(interface, []).append((name, version))

        registry.dispatcher["global"] = on_global
        display.roundtrip()
        required = ("wl_compositor", "wl_shm", "zwlr_layer_shell_v1")
        if not all(interface in announced for interface in required):
            LOGGER.info("Compositor has no layer-shell support; using a normal window")
            display.disconnect()
            return None

        def bind(interface: str, proxy_type: Any, max_version: int) -> Any:
            name, version = announced[interface][0]
            return registry.bind(name, proxy_type, min(version, max_version))

        globals_: dict[str, Any] = {
            "_registry": registry,
            "wl_compositor": bind("wl_compositor", WlCompositor, 4),
            "wl_shm": bind("wl_shm", WlShm, 1),
            "zwlr_layer_shell_v1": bind("zwlr_layer_shell_v1", ZwlrLayerShellV1, 4),
        }
        if "wl_seat" in announced:
            # v7: axis_discrete wheel steps; newer seats send value120 instead.
            seat = bind("wl_seat", WlSeat, 7)
            globals_["wl_seat"] = seat
            # The compositor announces capabilities right after the bind, so
            # record them now; the instance creates its pointer from them.
            seat_capabilities = [0]

            def on_capabilities(_seat: Any, capabilities: int) -> None:
                seat_capabilities[0] = capabilities

            seat.dispatcher["capabilities"] = on_capabilities
            globals_["seat_capabilities"] = seat_capabilities
        if "zwp_relative_pointer_manager_v1" in announced:
            from pywayland.protocol.relative_pointer_unstable_v1 import (
                ZwpRelativePointerManagerV1,
            )

            globals_["zwp_relative_pointer_manager_v1"] = bind(
                "zwp_relative_pointer_manager_v1", ZwpRelativePointerManagerV1, 1
            )
        if "wp_cursor_shape_manager_v1" in announced:
            from pywayland.protocol.cursor_shape_v1 import WpCursorShapeManagerV1

            globals_["wp_cursor_shape_manager_v1"] = bind(
                "wp_cursor_shape_manager_v1", WpCursorShapeManagerV1, 1
            )
        outputs: dict[str, Any] = {}
        scales: dict[Any, int] = {}
        for name, version in announced.get("wl_output", []):
            output = registry.bind(name, WlOutput, min(version, 4))
            scales[output] = 1

            def on_name(proxy: Any, value: str) -> None:
                outputs[value] = proxy

            def on_scale(proxy: Any, factor: int) -> None:
                scales[proxy] = max(1, int(factor))

            output.dispatcher["name"] = on_name
            output.dispatcher["scale"] = on_scale
        globals_["outputs"] = outputs
        globals_["output_scales"] = scales
        display.roundtrip()
        display.roundtrip()
        LOGGER.info("Mini Map uses a Wayland layer-shell overlay")
        return cls(widget, globals_, display, namespace=namespace, keyboard=keyboard)

    # ------------------------------------------------------------- wayland io

    def _flush(self) -> None:
        if self._display is not None:
            self._display.flush()

    def _read_events(self) -> None:
        if self._display is None:
            return
        try:
            # The fd is readable, so this reads without blocking.
            if self._display.dispatch(block=True) < 0:
                raise OSError("Wayland connection lost")
        except Exception:
            LOGGER.exception("Layer-shell overlay connection failed")
            self._notifier.setEnabled(False)
            self._render_timer.stop()
            return
        # A mouse can report hundreds of moves per second, while a resize
        # step (layout + redraw) takes tens of milliseconds. Deliver only the
        # latest position from each batch so input can never pile up and
        # keep resizing after the button is released.
        self._flush_motion()
        self._flush()

    # --------------------------------------------------------------- mapping

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.widget:
            kind = event.type()
            if kind == QEvent.Type.Show:
                QTimer.singleShot(0, self._map)
            elif kind == QEvent.Type.Hide:
                self._unmap()
            elif kind == QEvent.Type.Move:
                self._update_position()
            elif kind == QEvent.Type.Resize:
                self._update_size()
        return False

    def _screen_for_widget(self) -> Any:
        center = self.widget.geometry().center()
        return QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()

    def _map(self) -> None:
        if (
            self._display is None
            or self._surface is not None
            or not self.widget.isVisible()
        ):
            return
        from core.wayland_protocols.wlr_layer_shell_unstable_v1 import (
            ZwlrLayerShellV1,
            ZwlrLayerSurfaceV1,
        )

        self._clamp_to_screen()
        screen = self._screen_for_widget()
        self._output_name = screen.name() if screen is not None else None
        self._output_origin = (
            QPoint(screen.geometry().topLeft()) if screen is not None else QPoint()
        )
        output = self._outputs.get(self._output_name or "")
        self._surface = self._compositor.create_surface()
        self._layer_surface = self._layer_shell.get_layer_surface(
            self._surface, output, ZwlrLayerShellV1.layer.overlay.value, self._namespace
        )
        self._layer_surface.set_anchor(
            ZwlrLayerSurfaceV1.anchor.top.value | ZwlrLayerSurfaceV1.anchor.left.value
        )
        self._layer_surface.set_exclusive_zone(-1)
        self._layer_surface.set_keyboard_interactivity(1 if self._wants_keyboard else 0)
        self._layer_surface.dispatcher["configure"] = self._configure
        self._layer_surface.dispatcher["closed"] = self._closed
        self._configured = False
        self._last_frame = None
        self._confirmed_pos = QPoint(self.widget.pos())
        self._apply_size()
        self._apply_margins()
        self._apply_input_region()
        self._surface.commit()
        self._flush()
        self._render_timer.start()

    def _unmap(self) -> None:
        self._render_timer.stop()
        self._render_soon.stop()
        self._release_pointer_grab()
        if self._layer_surface is not None:
            self._layer_surface.destroy()
        if self._surface is not None:
            self._surface.destroy()
        self._layer_surface = None
        self._surface = None
        self._configured = False
        self._destroy_buffers()
        self._flush()

    def _configure(self, layer_surface: Any, serial: int, _w: int, _h: int) -> None:
        layer_surface.ack_configure(serial)
        self._configured = True
        self._last_frame = None
        self._schedule_render()

    def _closed(self, _layer_surface: Any) -> None:
        # The compositor removed the surface (e.g. its monitor went away).
        self._unmap()
        if self.widget.isVisible():
            QTimer.singleShot(500, self._map)

    def _apply_size(self) -> None:
        if self._layer_surface is not None:
            self._layer_surface.set_size(
                max(1, self.widget.width()), max(1, self.widget.height())
            )

    def _apply_margins(self) -> None:
        if self._layer_surface is None:
            return
        offset = self.widget.pos() - self._output_origin
        self._layer_surface.set_margin(max(0, offset.y()), 0, 0, max(0, offset.x()))

    def _clamp_to_screen(self) -> bool:
        """Keep the overlay fully on a monitor. Returns True if it moved."""

        screen = self._screen_for_widget()
        if screen is None:
            return False
        area = screen.geometry()
        pos = self.widget.pos()
        x = min(max(pos.x(), area.left()), area.left() + max(0, area.width() - self.widget.width()))
        y = min(max(pos.y(), area.top()), area.top() + max(0, area.height() - self.widget.height()))
        if (x, y) == (pos.x(), pos.y()):
            return False
        self.widget.move(x, y)  # Re-enters _update_position via a Move event.
        return True

    def _update_position(self) -> None:
        if self._layer_surface is None:
            return
        if self._clamp_to_screen():
            return
        if self._pressed and self._relative_pointer is None:
            # No relative motion: keep the surface still while the button is
            # held so surface-local coordinates stay exact; move on release.
            return
        screen = self._screen_for_widget()
        if screen is not None and screen.name() != self._output_name:
            # Dragged onto another monitor: recreate the surface there.
            self._unmap()
            QTimer.singleShot(0, self._map)
            return
        self._apply_margins()
        self._surface.commit()
        # Requests are processed in order, so once this sync completes the
        # compositor uses the new position for all later pointer events.
        target = QPoint(self.widget.pos())
        callback = self._display.sync()
        self._sync_callbacks.append(callback)

        def confirmed(cb: Any, _data: int) -> None:
            self._confirmed_pos = target
            if cb in self._sync_callbacks:
                self._sync_callbacks.remove(cb)

        callback.dispatcher["done"] = confirmed
        self._flush()

    def _update_size(self) -> None:
        if self._layer_surface is None:
            return
        # Growing near a screen edge: slide the overlay back on screen first.
        # Otherwise the compositor caps the configured size at the edge while
        # the buffer keeps growing, and the map is squeezed unevenly.
        self._clamp_to_screen()
        self._apply_size()
        self._apply_input_region()
        self._last_frame = None
        self._schedule_render()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.05, min(1.0, float(opacity)))
        self._last_frame = None
        self._schedule_render()

    def refresh(self) -> None:
        """Re-apply the input region and redraw (e.g. after a mask change)."""

        if self._surface is None:
            return
        self._apply_input_region()
        self._last_frame = None
        self._schedule_render()
        self._surface.commit()
        self._flush()

    def set_interactive(self, interactive: bool) -> None:
        self._interactive = bool(interactive)
        if not self._interactive:
            self._release_pointer_grab()
        if self._surface is not None:
            self._apply_input_region()
            self._surface.commit()
            self._flush()

    def _apply_input_region(self) -> None:
        if self._surface is None:
            return
        region = self._compositor.create_region()
        if self._interactive:
            mask = self.widget.mask()
            rects = (
                list(mask)
                if not mask.isEmpty()
                else [QRect(0, 0, self.widget.width(), self.widget.height())]
            )
            for rect in rects:
                region.add(rect.x(), rect.y(), rect.width(), rect.height())
        # An empty region makes the overlay click-through.
        self._surface.set_input_region(region)
        region.destroy()

    # -------------------------------------------------------------- rendering

    def _scale(self) -> int:
        output = self._outputs.get(self._output_name or "")
        if output is not None:
            return max(1, self._output_scale.get(output, 1))
        screen = self._screen_for_widget()
        return max(1, round(screen.devicePixelRatio())) if screen is not None else 1

    def _destroy_buffers(self) -> None:
        for buffer in self._buffers:
            buffer.destroy()
        self._buffers = []
        self._buffer_key = None

    def _free_buffer(self, width: int, height: int, scale: int) -> _ShmBuffer | None:
        key = (width, height, scale)
        if self._buffer_key != key:
            self._destroy_buffers()
            self._buffer_key = key
        for buffer in self._buffers:
            if not buffer.busy:
                return buffer
        if len(self._buffers) < 3:
            buffer = _ShmBuffer(self._shm, width * scale, height * scale)
            self._buffers.append(buffer)
            return buffer
        return None

    def _schedule_render(self) -> None:
        if not self._render_soon.isActive():
            self._render_soon.start()

    def _debug(self, message: str, *args: object) -> None:
        if self._debug_input:
            LOGGER.info("overlay input: " + message, *args)

    def render(self) -> None:
        if self._surface is None or not self._configured:
            return
        width, height = self.widget.width(), self.widget.height()
        if width <= 0 or height <= 0:
            return
        scale = self._scale()
        image = QImage(
            width * scale, height * scale, QImage.Format.Format_ARGB32_Premultiplied
        )
        image.setDevicePixelRatio(scale)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setOpacity(self._opacity)
        mask = self.widget.mask()
        self.widget.render(
            painter,
            QPoint(),
            mask if not mask.isEmpty() else QRegion(),
            QWidget.RenderFlag.DrawChildren,
        )
        painter.end()
        frame = bytes(image.constBits())
        if frame == self._last_frame:
            return
        buffer = self._free_buffer(width, height, scale)
        if buffer is None:
            return  # The compositor still holds every buffer; try next tick.
        buffer.data.seek(0)
        if image.bytesPerLine() == buffer.stride:
            buffer.data.write(frame)
        else:
            for row in range(image.height()):
                start = row * image.bytesPerLine()
                buffer.data.write(frame[start : start + buffer.stride])
        self._last_frame = frame
        buffer.busy = True
        self._surface.set_buffer_scale(scale)
        self._surface.attach(buffer.buffer, 0, 0)
        self._surface.damage_buffer(0, 0, buffer.width, buffer.height)
        self._surface.commit()
        self._flush()

    # ------------------------------------------------------------------ input

    def _seat_capabilities(self, seat: Any, capabilities: int) -> None:
        from pywayland.protocol.wayland import WlSeat

        has_pointer = bool(capabilities & WlSeat.capability.pointer.value)
        if has_pointer and self._pointer is None:
            self._pointer = seat.get_pointer()
            dispatcher = self._pointer.dispatcher
            dispatcher["enter"] = self._pointer_enter
            dispatcher["leave"] = self._pointer_leave
            dispatcher["motion"] = self._pointer_motion
            dispatcher["button"] = self._pointer_button
            dispatcher["axis"] = self._pointer_axis
            dispatcher["axis_discrete"] = self._pointer_axis_discrete
            dispatcher["frame"] = self._pointer_frame
            if self._cursor_manager is not None:
                self._cursor_device = self._cursor_manager.get_pointer(self._pointer)
            if self._relative_manager is not None:
                self._relative_pointer = self._relative_manager.get_relative_pointer(
                    self._pointer
                )
                self._relative_pointer.dispatcher["relative_motion"] = (
                    self._pointer_relative_motion
                )
        elif not has_pointer and self._pointer is not None:
            self._pointer = None
            self._cursor_device = None
            self._relative_pointer = None
        has_keyboard = bool(capabilities & WlSeat.capability.keyboard.value)
        if self._wants_keyboard and has_keyboard and self._keyboard is None:
            self._keyboard = seat.get_keyboard()
            self._keyboard.dispatcher["keymap"] = self._keyboard_keymap
            self._keyboard.dispatcher["key"] = self._keyboard_key

    @staticmethod
    def _keyboard_keymap(_kb: Any, _format: int, fd: int, _size: int) -> None:
        # Only Esc is needed, which needs no keymap; just release the fd.
        try:
            os.close(fd)
        except OSError:
            pass

    def _keyboard_key(self, _kb: Any, _serial: int, _time: int, key: int, state: int) -> None:
        # evdev KEY_ESC == 1. Other keys are deliberately ignored.
        if key != 1 or self._surface is None:
            return
        from PySide6.QtGui import QKeyEvent

        kind = QEvent.Type.KeyPress if state == 1 else QEvent.Type.KeyRelease
        QApplication.sendEvent(
            self.widget,
            QKeyEvent(kind, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
        )

    def _ours(self, surface: Any) -> bool:
        return self._surface is not None and surface == self._surface

    def _target_at(self, pos: QPoint) -> QWidget:
        child = self.widget.childAt(pos)
        return child if child is not None else self.widget

    @property
    def _pressed(self) -> bool:
        return self._buttons != Qt.MouseButton.NoButton

    def _global(self, local: QPointF) -> QPointF:
        if self._pressed:
            if self._relative_pointer is not None:
                return QPointF(self._drag_global)
            # The surface is frozen during the press (see _update_position).
            return QPointF(self._drag_origin) + local
        return QPointF(self._confirmed_pos) + local

    def _send_mouse(
        self,
        kind: QEvent.Type,
        button: Qt.MouseButton,
        target: QWidget | None = None,
    ) -> None:
        pos = self._pointer_pos
        if target is None:
            target = self._grab_target or self._target_at(pos.toPoint())
        local = QPointF(target.mapFrom(self.widget, pos.toPoint())) + (
            pos - QPointF(pos.toPoint())
        )
        event = QMouseEvent(
            kind,
            local,
            self._global(pos),
            button,
            self._buttons,
            QGuiApplication.keyboardModifiers(),
        )
        QApplication.sendEvent(target, event)
        self._update_cursor(target)

    def _update_cursor(self, target: QWidget) -> None:
        if self._cursor_device is None or not self._pointer_inside:
            return
        from pywayland.protocol.cursor_shape_v1 import WpCursorShapeDeviceV1

        widget: QWidget | None = target
        shape = Qt.CursorShape.ArrowCursor
        while widget is not None:
            if widget.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
                shape = widget.cursor().shape()
                break
            widget = widget.parentWidget()
        name = _CURSOR_SHAPES.get(shape, "default")
        if name == self._cursor_shape:
            return
        self._cursor_shape = name
        self._cursor_device.set_shape(
            self._enter_serial, getattr(WpCursorShapeDeviceV1.shape, name).value
        )
        self._flush()

    def _pointer_enter(self, _p: Any, serial: int, surface: Any, x: float, y: float) -> None:
        if not self._ours(surface):
            return
        self._debug("enter at %.1f,%.1f", x, y)
        self._pointer_inside = True
        self._enter_serial = serial
        self._cursor_shape = ""
        self._pointer_pos = QPointF(x, y)
        self._update_cursor(self._target_at(self._pointer_pos.toPoint()))

    def _pointer_leave(self, _p: Any, _serial: int, surface: Any) -> None:
        if not self._ours(surface):
            return
        self._debug("leave (buttons=%s)", int(self._buttons.value))
        self._pointer_inside = False
        # Without a grab the release may never arrive; end any drag cleanly.
        self._release_pointer_grab()

    def _pointer_motion(self, _p: Any, _time: int, x: float, y: float) -> None:
        if not self._pointer_inside or not self._interactive:
            return
        self._pointer_pos = QPointF(x, y)
        self._motion_pending = True

    def _pointer_relative_motion(
        self,
        _rp: Any,
        _utime_hi: int,
        _utime_lo: int,
        dx: float,
        dy: float,
        _dx_unaccel: float,
        _dy_unaccel: float,
    ) -> None:
        if self._pressed:
            self._drag_global += QPointF(dx, dy)
            self._motion_pending = True

    def _flush_motion(self) -> None:
        if not self._motion_pending:
            return
        self._motion_pending = False
        if self._pointer_inside and self._interactive:
            if self._pressed:
                self._debug(
                    "drag move local=%.1f,%.1f global=%.1f,%.1f size=%dx%d",
                    self._pointer_pos.x(),
                    self._pointer_pos.y(),
                    self._global(self._pointer_pos).x(),
                    self._global(self._pointer_pos).y(),
                    self.widget.width(),
                    self.widget.height(),
                )
            self._send_mouse(QEvent.Type.MouseMove, Qt.MouseButton.NoButton)

    def _pointer_button(self, _p: Any, _serial: int, _time: int, code: int, state: int) -> None:
        self._debug(
            "button %#x %s inside=%s interactive=%s",
            code,
            "press" if state == 1 else "release",
            self._pointer_inside,
            self._interactive,
        )
        if not self._pointer_inside or not self._interactive:
            return
        button = _BUTTONS.get(code)
        if button is None:
            return
        self._flush_motion()
        if state == 1:
            if self._buttons == Qt.MouseButton.NoButton:
                self._grab_target = self._target_at(self._pointer_pos.toPoint())
                self._drag_origin = QPoint(self._confirmed_pos)
                self._drag_press_local = QPointF(self._pointer_pos)
                self._drag_global = QPointF(self._confirmed_pos) + self._pointer_pos
            self._buttons |= button
            self._send_mouse(QEvent.Type.MouseButtonPress, button)
        else:
            self._buttons &= ~button
            self._send_mouse(QEvent.Type.MouseButtonRelease, button)
            if self._buttons == Qt.MouseButton.NoButton:
                self._grab_target = None
                self._end_press()
        self._schedule_render()

    def _release_pointer_grab(self) -> None:
        if self._buttons != Qt.MouseButton.NoButton and self._grab_target is not None:
            pressed = self._buttons
            self._buttons = Qt.MouseButton.NoButton
            for button in _BUTTONS.values():
                if pressed & button:
                    self._send_mouse(QEvent.Type.MouseButtonRelease, button)
        self._buttons = Qt.MouseButton.NoButton
        self._grab_target = None
        self._end_press()

    def _end_press(self) -> None:
        # Apply a move that was held back while the surface was frozen.
        if self._layer_surface is not None and self.widget.pos() != self._confirmed_pos:
            self._update_position()

    def _pointer_axis(self, _p: Any, _time: int, axis: int, value: float) -> None:
        if axis == 0:
            self._wheel_pixels += value
        else:
            self._wheel_horizontal += value

    def _pointer_axis_discrete(self, _p: Any, axis: int, discrete: int) -> None:
        if axis == 0:
            self._wheel_steps += discrete

    def _pointer_frame(self, _p: Any) -> None:
        steps, pixels, horizontal = (
            self._wheel_steps,
            self._wheel_pixels,
            self._wheel_horizontal,
        )
        self._wheel_steps = self._wheel_pixels = self._wheel_horizontal = 0.0
        if not (steps or pixels or horizontal):
            return
        if not self._pointer_inside or not self._interactive:
            return
        # Wayland: positive = down/right. Qt: 120 per notch, positive = up.
        angle_y = -round(steps * 120) if steps else -round(pixels * 12)
        angle_x = -round(horizontal * 12)
        target = self._grab_target or self._target_at(self._pointer_pos.toPoint())
        local = QPointF(target.mapFrom(self.widget, self._pointer_pos.toPoint()))
        event = QWheelEvent(
            local,
            self._global(self._pointer_pos),
            QPoint(-round(horizontal), -round(pixels)),
            QPoint(angle_x, angle_y),
            self._buttons,
            QGuiApplication.keyboardModifiers(),
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        QApplication.sendEvent(target, event)
        self._schedule_render()

    # --------------------------------------------------------------- teardown

    def close(self) -> None:
        display = self._display
        if display is None:
            return
        try:
            self._unmap()
        except Exception:
            LOGGER.debug("Layer overlay unmap during close failed", exc_info=True)
        self._render_timer.stop()
        self._notifier.setEnabled(False)
        self._pointer = None
        self._cursor_device = None
        self._keyboard = None
        self._sync_callbacks.clear()
        self._display = None
        _LIVE_OVERLAYS.discard(self)
        try:
            # Destroys every child proxy before closing the connection.
            display.disconnect()
        except Exception:
            LOGGER.debug("Wayland disconnect failed", exc_info=True)
