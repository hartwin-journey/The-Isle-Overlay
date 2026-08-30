# The Isle Companion

The Isle Companion is a local desktop map for **The Isle: Evrima** on Windows and Linux. It provides a full map, a separate mini-map window, clipboard tracking, breadcrumbs, editable map layers, waypoints, and local settings. Windows also supports optional pixel-only automatic tracking and global shortcuts.

I started this as a new player who loved exploring Gateway but found it genuinely hard to navigate. The goal is simple: make finding your way around less frustrating without touching the game itself.

The source version is the primary version. It runs directly with Python and does not need an installer during development.

> **Map snapshot:** the project includes a complete 7800 × 7817 Gateway v0.21.772 basemap, matching water overlay, calibrated coordinate transform, and editable offline layer data. A fresh checkout is ready to use immediately without downloading or supplying another map. See [`map/SOURCE.md`](map/SOURCE.md) for its source and version information.

## Security and privacy boundary

Coordinates can enter through two explicitly limited local paths:

1. ordinary desktop clipboard text that the player manually copies with The Isle's built-in **Copy Location** function; or
2. on Windows, optional normal screen capture of a rectangle selected by the user, followed by Windows' installed on-device OCR service.

The application:

- does **not** open, inspect, or communicate with The Isle's executable or process;
- does **not** read game memory or Unreal Engine objects;
- does **not** inject DLLs, install hooks, or draw inside the game renderer;
- does **not** read or modify game files, save files, or configuration files;
- does **not** inspect network traffic or communicate with Steam;
- does **not** send input or hotkeys to The Isle;
- requires no Steam, Discord, or other account; and

The mini map is an ordinary independent desktop window. “Always on top” changes only that window's standard window flag; it is never injected into or attached to the game.

The boundary is visible in the source. [`core/clipboard_monitor.py`](core/clipboard_monitor.py) receives manual text from `QClipboard`. Optional [`core/automatic_tracking.py`](core/automatic_tracking.py) receives only in-memory pixels from [`core/screen_capture.py`](core/screen_capture.py) and sends them to Windows' local OCR service through the readable [`core/windows_ocr.ps1`](core/windows_ocr.ps1) bridge. Both paths must pass [`core/coordinate_parser.py`](core/coordinate_parser.py) before producing a position. There is no game-process integration elsewhere in the project.

## Vulnona reference and offline scope

The local map aims to reproduce the useful map behavior of VulnonaMAP within the stricter boundary of this project. It includes a high-resolution Gateway basemap, an independently toggleable water raster, calibrated player/waypoint placement, pan and zoom, and editable snapshots of the principal Gateway layers.

It deliberately does not reproduce features that would violate or weaken the requested boundary. Automatic tracking sees only the screen rectangle explicitly selected by the user; there is no automatic game detection, process inspection, online location sharing, remote marker sync, live website embedding, or runtime downloading. Updating the map snapshot is a manual development/data-maintenance operation; normal application use remains entirely offline.

## Requirements

- Windows 10/11, or a modern 64-bit Linux desktop
- Python 3.11 or newer
- PySide6 (the only runtime Python dependency)

Automatic Tracking uses the OCR engine and language resources already installed with Windows. It does not require Tesseract, a cloud service, or another downloaded OCR executable.

Create an isolated environment from PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

If PowerShell prevents virtual-environment activation, use the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

On Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

The [official PySide6 wheels](https://doc.qt.io/qtforpython-6/gettingstarted.html) include Qt itself, so a separate Qt SDK is not required.

## Launch from source

From the project folder:

```powershell
python app.py
```

On Windows installations where the Python launcher is available instead:

```powershell
py app.py
```

You can also double-click `run.bat`. It tries `python` first and then the Windows `py` launcher.

On Linux, launch with `python3 app.py` or `sh run.sh`.

Closing the Full Map hides it to the notification area when a system tray is available. Use the tray menu's **Exit** action to stop the program. Without a tray, closing the Full Map exits normally.

## Coordinate tracking

Copy a location in The Isle using the game's own **Copy Location** action. The application listens for the normal desktop clipboard change event and accepts complete coordinate strings such as:

```text
88,879.526, 288,696.110, 21,112.882
-88,879.526, -288,696.110, -21,112.882
X=-88,879.526, Y=288,696.110, Z=21,112.882
```

Thousands separators and negative values are supported. A valid record must contain exactly X, Y, and Z on one line. The parser does not search unrelated clipboard text for embedded coordinates. Non-matching clipboard content is ignored, and its contents are never written to the log.

Until a valid location is received from either local input path, the interface waits and does not invent a position. Consecutive unique positions update:

- current and previous X/Y/Z;
- last update time;
- planar distance travelled;
- compass heading and direction; and
- the session breadcrumb trail when enabled.

World distance is displayed using Unreal's conventional 100 world units per metre. Breadcrumb history is intentionally session-local and is never transmitted.

### Optional Automatic Tracking (Windows only)

Automatic Tracking is managed entirely from the Full Map toolbar. Click the main **Automatic Tracking** button to toggle it. Use the button's arrow and choose **Set up capture area…** or **Change capture area…** to drag around the coordinate line shown in The Isle's Tab menu, adjust the exact X/Y/width/height values, capture a temporary preview, and see the text returned by local OCR. When enabling it for the first time, setup opens automatically.

While enabled, the companion periodically captures only that rectangle through Qt's ordinary `QScreen.grabWindow` API. The image is converted to an in-memory PNG, read by the OCR service included with Windows, and immediately discarded. A result must:

- contain exactly one canonical coordinate record, including the Tab menu's multi-line `Lat / Long / Alt` layout, that can be converted and accepted by the existing strict parser;
- appear in two consecutive captures with a plausible movement delta; and
- differ from the last automatically emitted coordinate.

Failed, ambiguous, or implausibly inconsistent readings are ignored. Predominantly dark captures are inverted in memory to help Windows recognize the game's light UI text; numeric OCR mistakes are never guessed or repaired. OCR text and screenshot pixels are not logged, and screenshots are never written during normal use. Clipboard tracking stays active as a fallback even when Automatic Tracking is enabled.

Automatic Tracking uses Windows' built-in local OCR service and is therefore hidden on Linux. Linux keeps ordinary clipboard tracking as the reliable coordinate source. On Windows, ordinary screen capture may be unavailable for some exclusive-fullscreen configurations; borderless-windowed or windowed display is recommended. If the desktop returns empty or hidden pixels, the companion reports that it is waiting and does not attempt process capture, renderer hooks, injection, or any other fallback.

## Full Map

The Full Map is the main control window. Mouse-wheel zooms, left-drag pans, and a short left click places or moves the active waypoint. Its streamlined toolbar provides layer visibility, Mini Map visibility, fit/recenter, trail clearing, a compact Waypoint menu, and Settings. A dedicated row beneath the map shows the nearest visible, intentionally labeled POI with its planar distance and compass direction.

The layer dock groups independent toggles by Tracking, Zones, and Map details. Individual migration and sanctuary filters are collapsed until requested.

- player position;
- breadcrumb trail;
- migration zones and each individual migration zone;
- patrol zones and each individual patrol zone;
- sanctuaries and each individual sanctuary;
- water sources;
- updrafts;
- named locations;
- food locations;
- AI locations;
- salt licks;
- spawn areas; and
- custom markers.

Layer visibility is saved to `config/settings.json`.

The current player marker and breadcrumb dots retain a clear on-screen size when zoomed out. The breadcrumb line uses a dark contrast edge, and dense POI names hide automatically at overview zoom levels. Map labels have a dark contrast outline and can use one of the curated readable typeface presets in Settings: Segoe UI Semibold, Verdana Bold, Tahoma Bold, Arial Bold, or the original Segoe UI Regular.

## Mini Map Overlay

The Mini Map is a completely separate desktop window. It supports:

- ordinary desktop always-on-top behavior;
- a square map surface with a square or circular visual shape and a compact external POI footer;
- a default top-right placement on first launch;
- toggle-to-interact click-through behavior (`M4` on Windows, toolbar control on Linux);
- a compact control strip for Follow Player and shape switching while interaction is enabled;
- an inset resize handle while interaction is enabled, with a persisted 180–1200 px size;
- a draggable control strip while interaction is enabled;
- borderless or normal window borders;
- adjustable window opacity;
- player-centered mode;
- north-up rendering;
- current player, active waypoint, breadcrumbs, and enabled data layers; and
- the nearest visible named POI, distance, and direction beneath the map surface.

On Windows, pressing the interaction binding toggles the overlay between click-through and interactive states. The companion never suppresses or sends that binding to another application. On Linux, use **Edit Mini Map** in the Full Map toolbar instead. Click-through support is requested through Qt and can vary between X11 and Wayland compositors.

Heading-up rotation is deliberately not implemented yet. North-up is the only rendered orientation, which keeps the coordinate transform predictable.

## Waypoints and custom markers

Click the map to place a waypoint. Clicking elsewhere moves it; clicking the active waypoint marker or its name again removes it. When both a copied player position and waypoint exist, a high-contrast coral route line connects them on the Full Map and Mini Map. The Full Map also shows the waypoint's planar distance, compass direction, and approximate heading. **Remove Waypoint** and `Ctrl+Shift+W` remain available as alternate ways to clear it.

**Save Waypoint** asks for a name and appends a normal local record to `config/custom_markers.json`. Saved custom markers persist between sessions but are ignored by Git because they can reveal personal play locations. They can also be edited manually while the application is stopped, or reloaded with **Reload local map data**.

## Global hotkeys (Windows only)

On Windows, hotkeys use the ordinary user-level `RegisterHotKey` API in [`core/hotkeys.py`](core/hotkeys.py). They listen only; the application never sends keys to The Isle or any other program.

| Default hotkey | Action |
| --- | --- |
| `Ctrl+Shift+M` | Show/hide Full Map |
| `Ctrl+Shift+O` | Show/hide Mini Map |
| `Ctrl+Shift+L` | Show/hide layer panel |
| `Ctrl+Shift+B` | Toggle breadcrumbs |
| `Ctrl+Shift+W` | Clear active waypoint |
| `Ctrl+Shift+R` | Recenter Full Map on player |
| `Ctrl+Shift+P` | Toggle player-centered Mini Map |
| `Ctrl+Shift+PageUp` | Increase overlay opacity |
| `Ctrl+Shift+PageDown` | Decrease overlay opacity |

Hotkeys are editable in Settings. If another application already owns a shortcut, the status bar reports that it could not be registered. Supported keys include letters, digits, F1–F24, PageUp, PageDown, Home, End, Insert, Delete, and Space with Ctrl, Shift, Alt, or Windows modifiers.

Linux does not show the Shortcuts settings tab. This avoids promising system-wide shortcuts that would require desktop-specific APIs or additional native dependencies.

The Mini Map interaction binding is separate from `RegisterHotKey`: it is a physical key state polled with the ordinary Windows `GetAsyncKeyState` API, and each press toggles the overlay interaction state. It is not registered as a global shortcut, hooked, injected, consumed, or forwarded by this application.

## Gateway map calibration

The transform is defined only in `map/calibration.json`; calibration constants are not scattered throughout the UI code.

```json
{
  "world_bounds": {
    "min_x": -607000.0,
    "max_x": 509000.0,
    "min_y": -505000.0,
    "max_y": 607000.0
  },
  "pixel_bounds": {
    "min_x": 0.0,
    "max_x": 7800.0,
    "min_y": 0.0,
    "max_y": 7817.0
  },
  "invert_y": false,
  "invert_x": false,
  "swap_axes": true
}
```

The Gateway reference uses an axis swap: increasing game-world Y moves right across the image, while increasing game-world X moves down. That relationship is represented explicitly by `swap_axes`; it is not hidden in application code.

To recalibrate this snapshot or use another local image:

1. Stop the application and back up your existing `map` folder.
2. Replace `map/gateway.webp` with the intended local Gateway map and replace `map/gateway_water.webp` with a same-size transparent water overlay, if available.
3. Note the image's pixel dimensions and update the four pixel bounds. For a full 4096 × 4096 image, typical full-image bounds are 0 to 4096 on both axes.
4. Identify at least two reliable in-game world reference locations spanning the map. Manually copy their coordinates and locate their pixels in the image.
5. Adjust world and pixel bounds until the reference positions align. Use `swap_axes`, `invert_x`, and `invert_y` to describe the image orientation.
6. Start the application, open Settings → Calibration, and refine the same values while checking additional reference points.

The transform is linear and supports axis swapping and independent X/Y inversion. It assumes the map image has no arbitrary rotation or perspective distortion. Malformed calibration files are logged and replaced in memory with the bundled Gateway defaults instead of crashing the program.

## Map source and snapshot maintenance

The currently bundled snapshot identifies its source, map version, and retrieval date in `map/SOURCE.md`, `map/calibration.json`, and each imported layer file. The runtime does not contain an updater and never contacts that source.

The bundled snapshot is kept together with its source, version, and retrieval information in `map/SOURCE.md` so its origin remains clear and future map changes can be tracked.

When Gateway changes, replace the local rasters, remeasure calibration against copied world coordinates, and refresh affected JSON layers. Keep source/version metadata with every snapshot so stale and current records are easy to distinguish.

## Editing local map data

Each map layer has a separate JSON file under `data/`. Files have an `items` array and can be updated without changing Python code.

### Point locations

`water.json`, `locations.json`, `food.json`, `ai.json`, `salt_licks.json`, and `spawns.json` use point records. User-created markers use the same schema in ignored `config/custom_markers.json`:

```json
{
  "items": [
    {
      "name": "River access",
      "position": [12345.0, -67890.0, 250.0],
      "description": "Optional note"
    }
  ]
}
```

X, Y, and optional Z are world coordinates. Point layers use distinct vector marker colors and tooltips.

### Updrafts

`data/updrafts.json` contains the 21 updrafts visible in VulnonaMAP's Gateway v0.21.772 data on 2026-08-30. Each record stores a source identifier, area, world position, and displayed active hours. Both map views render them as constant-size orange arrows with a white outline and dark shadow, matching the source map's visual language. Hover an arrow while the map is interactive to see its name and active hours. The Updrafts layer is independently toggleable and remains an ordinary offline JSON snapshot; the application never contacts VulnonaMAP at runtime.

### Migration zones

Edit `data/migrations.json`. Polygon vertices are world-coordinate X/Y pairs:

```json
{
  "name": "Example migration",
  "polygon": [[-100000, 120000], [0, 180000], [80000, 90000]],
  "species": ["Species name"],
  "notes": "Optional notes",
  "color": "#00CC77"
}
```

Zones may be toggled together or individually. Migration areas use Vulnona's emerald palette, patrol zones use its translucent red treatment, and sanctuary areas use its pink-lilac fill with a pale yellow outline. The single **Zone intensity** control preserves their relative appearance across both maps. Data is intentionally editable because zone information can change.

### Patrol zones

Patrol geometry is stored in `data/patrol_zones.json` as one or more world-coordinate polygons per named area. It is disabled by default to keep the initial map uncluttered. `tools/build_patrol_snapshot.py` can reproducibly rebuild the bundled local snapshot from the recorded Gateway v0.21.772 vectors without making a network request.

### Sanctuaries

Edit `data/sanctuaries.json`. A sanctuary can be a circle:

```json
{
  "name": "Sanctuary name",
  "position": [25000, 30000],
  "radius": 45000,
  "description": "Optional description"
}
```

Or a polygon:

```json
{
  "name": "Polygon sanctuary",
  "polygon": [[-250000, -10000], [-180000, 40000], [-130000, -30000]],
  "description": "Optional description"
}
```

Malformed or missing layer files produce a local log entry and an empty layer rather than an application crash. After editing data while the application is running, click **Reload map data** in the Layers panel.

## Settings and logs

All settings are local JSON in `config/settings.json`. The Settings window is organized into **Mini Map**, **Map & Tracking**, and **Advanced**, plus **Shortcuts** on Windows. Automatic Tracking and its screen-area setup live in the Windows Full Map toolbar instead of being duplicated here. Layer visibility stays in the Full Map's Layers panel. The data-folder path is intentionally not exposed in the everyday UI; advanced users can still edit the local JSON directly.

`config/settings.json`, `config/custom_markers.json`, and the complete `logs/` directory are ignored by Git. This prevents the selected OCR capture rectangle, personal layer preferences, parsed-coordinate history, and saved play locations from being committed accidentally. A fresh checkout generates default settings on first launch.

Rotating debug logs are written to `logs/companion.log` (maximum approximately 1 MB plus three backups). Logs include startup, shutdown, valid parsed coordinate updates, coordinate rejection reasons without clipboard or OCR text, map-data errors, and configuration errors. General clipboard text, OCR text, and captured pixels are never logged.

## Tests

Install the development requirements and run on either platform:

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

On Linux, use `python -m pip` and `python -m pytest` instead. GitHub Actions runs the same test suite on both Windows and Ubuntu.

The tests cover strict coordinate parsing, clipboard filtering, OCR validation and confirmation, coordinate transform round trips, nearest-POI selection, waypoint interaction and route rendering, font presets, settings recovery, hotkey parsing, and off-screen rendering of both map windows. `tools/render_ui_preview.py` renders the main window, square and circular Mini Maps, a zone-palette check, and Mini Map/Map & Tracking settings previews in `logs/` for visual QA; set `QT_QPA_PLATFORM=windows` for normal Windows font rendering.

## Build an executable locally (optional)

First verify that the source version runs. Then install the documented development dependencies and build an ordinary one-folder application locally.

Windows:

```powershell
py -m pip install -r requirements-dev.txt
py tools\build_exe.py
```

Linux:

```bash
python -m pip install -r requirements-dev.txt
python tools/build_exe.py
```

The build helper uses the correct PyInstaller data-path syntax for the current platform and includes the Windows OCR bridge only on Windows. It deliberately omits `config` so a developer's personal settings, capture rectangle, and markers cannot enter the bundle. The result is `dist\TheIsleCompanion\TheIsleCompanion.exe` on Windows and `dist/TheIsleCompanion/TheIsleCompanion` on Linux. Keep the entire folder together; runtime settings and logs are generated beside the application.

PyInstaller is optional and is not in `requirements.txt`, so it is not needed for normal source operation. The project intentionally does not build or distribute a precompiled executable by default.

## Project structure

```text
app.py                         Application startup, logging, tray, hotkey routing
core/clipboard_monitor.py      Ordinary clipboard event listener
core/automatic_tracking.py     OCR validation, confirmation, and polling
core/local_ocr.py              Local Windows OCR process adapter
core/screen_capture.py         User-region-only Qt screen capture
core/windows_ocr.ps1           Readable bridge to Windows.Media.Ocr
core/coordinate_parser.py      Strict coordinate parser
core/coordinate_transform.py   JSON-backed world/pixel calibration
core/navigation.py             Distance, heading, and nearest-POI calculations
core/map_fonts.py              Curated persistent map-label presets
core/settings.py               Local settings and defaults
core/data_loader.py            Fault-tolerant local layer loading
core/app_state.py              Shared in-memory position/waypoint state
ui/main_window.py              Full Map interface
ui/map_canvas.py               Zoomable/pannable layered map renderer
ui/map_fonts.py                Qt font construction for map labels
ui/mini_map.py                 Separate Mini Map desktop window
ui/ocr_setup_window.py         Capture-area selector and OCR preview
ui/settings_window.py          Settings and calibration UI
data/*.json                    Editable, non-personal offline map layers
data/updrafts.json             Vulnona-referenced updraft positions and hours
map/gateway.webp               Bundled 7800 × 7817 Gateway base raster
map/gateway_water.webp         Bundled matching water overlay
map/calibration.json           Editable calibration values
map/SOURCE.md                  Snapshot provenance and use notes
config/README.md               Runtime-state privacy notes
config/settings.json           Generated local settings (Git-ignored)
config/custom_markers.json     Generated saved markers (Git-ignored)
logs/                          Generated local logs and QA previews (Git-ignored)
tests/                         Unit and Qt smoke tests
run.bat                        No-installer Windows launcher
run.sh                         Simple Linux launcher
.github/workflows/tests.yml    Windows and Ubuntu test matrix
```

## Dependency policy

Normal operation depends only on Python and PySide6. The application does not obfuscate its source, download or execute remote binaries, or contain an update checker. Any future network-based update feature should be a separate, opt-in component that is disabled by default; none exists in this version.


```powershell
git status --short
git add --dry-run --all
git status --short --ignored
```
