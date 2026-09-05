# Release QA checklist

Automated tests use offscreen Qt. Before a release, run these checks on real Windows and Linux desktops; passing unit tests alone does not establish that the app is bug-free.

## Everyday flows

- Launch with a fresh config; fit, pan, zoom, and copy a game location.
- Place a waypoint, move the player, save a marker, and clear the waypoint.
- Toggle layers and breadcrumbs from the panel and shortcuts; confirm both maps and checkboxes agree.
- Hide/show the Full Map and restart; confirm the Layers preference is preserved.
- Check toolbar overflow and navigation text at 820 × 560 and at 125%, 150%, and 200% display scaling.
- Navigate settings and toolbar controls with the keyboard; check visible focus and menu contrast.

## Native desktop integration

- Edit the Mini Map from the toolbar, then press the configured shortcut: the next press should return it to click-through mode.
- Check square/circle layouts, resizing, opacity, player follow, and click-through over a borderless game window.
- Check tray actions and shutdown with and without an available system tray.
- On Windows, configure OCR, cancel setup, change capture area, enable/disable tracking, and verify source/status text and clipboard fallback.
- On Linux, verify the edit shortcut on X11/XWayland and the toolbar fallback on native Wayland.
- Move windows between monitors with different scaling; disconnect the secondary monitor and check recovery.

## Local files

- Run tests with `python -m pytest -q`.
- Confirm saved settings and custom markers survive a restart.
- Check behavior when config/data folders are read-only or files are malformed. Type recovery is tested, but write failures still need native/manual review.
- Build with `tools/build_exe.py` and launch the packaged app on a clean machine.

Keep game integration external: clipboard and user-selected screen pixels only. No process inspection, injected overlays, or game input automation.
