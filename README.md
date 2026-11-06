# The Isle Companion

The Isle Companion is a local desktop map for **The Isle: Evrima**, available for Windows and Linux.

I started it while learning Gateway the hard way: losing my bearings, missing migration zones, and forgetting which landmark I meant to head toward next.

The app is meant to be a small second-screen companion rather than anything invasive. It includes the Gateway map, a toggleable Mini Map overlay, position tracking, waypoints, breadcrumbs, migration zones, sanctuaries, patrol zones, water sources, updrafts, named locations, and other practical layers.

Both platforms also support optional Automatic Tracking using local OCR.

## Quick note about the Mini Map

By default, the hotkey for making the Mini Map editable is **Mouse Button 4 (M4)**. You can change it in Settings.

Press the hotkey once to edit the Mini Map: zoom, pan, toggle auto-follow with the small **F** button, or switch between the square and circle layouts. Press it again when you want the Mini Map to go back to click-through mode. On Wayland desktops with overlay support (KDE Plasma, Hyprland, Sway, niri, ...), clicking anywhere outside the Mini Map also leaves edit mode; while editing, the game does not receive mouse input, so a game that holds the cursor cannot keep it off the Mini Map.

You can also use **Edit Mini Map** in the Full Map toolbar on either platform if the shortcut is unavailable.

<img width="2553" height="1420" alt="The Isle Companion main map" src="https://github.com/user-attachments/assets/085b5d09-3a31-4fe7-8440-30f035580986" />

<img width="1917" height="1270" alt="The Isle Companion Mini Map" src="https://github.com/user-attachments/assets/d576b604-d302-420f-963a-304a27d62991" />

## Features

### Full Gateway map

The main map supports zooming, panning, player tracking, breadcrumbs, waypoints, and toggleable information layers.

Available layers include:

* Migration zones
* Patrol zones
* Sanctuaries
* Water sources
* Updrafts
* Named locations
* Food locations
* AI locations
* Gastroliths
* Salt licks
* Spawn areas
* Custom markers

Individual migration and sanctuary zones can also be toggled separately.

### Mini Map overlay

The Mini Map runs as its own desktop window and can remain above the game.

It supports:

* Player position
* Breadcrumb trail
* Active waypoint
* Enabled map layers
* Nearest named POI
* Distance and direction
* Player-centered mode
* Adjustable size and opacity
* Square or circular appearance
* Click-through mode

On Windows and Linux, the Mini Map can be switched between interactive and click-through modes with a configurable input binding.

On Wayland desktops that support the layer-shell protocol (KDE Plasma, COSMIC, and wlroots-based compositors such as Sway, Hyprland, niri and river), the Mini Map is drawn as a desktop overlay: it stays above the game on **every workspace**, including fullscreen games, with no window rules or compositor configuration. In click-through mode the compositor sends all input straight to the game. This uses the optional `pywayland` package, which `run.sh` installs on these desktops; without it the Mini Map uses a normal window. Set `ISLE_COMPANION_LAYER_SHELL=0` to force the normal window.

GNOME does not support layer-shell, so on GNOME Wayland the app runs through XWayland and the Mini Map bypasses the window manager (the way menus and tooltips do). That keeps it above fullscreen games on every workspace without extensions or settings. Set `ISLE_COMPANION_X11_OVERLAY=0` to turn this off. Other X11 desktops keep a normal always-on-top window.

On Linux, the binding is observed without consuming the input. On X11 it works everywhere; on Wayland it works while an XWayland window has focus, which includes The Isle running through Proton, so it works in-game. Wayland does not let apps observe keys typed into native Wayland windows; the **Edit Mini Map** button in the Full Map toolbar works everywhere.

### Waypoints

Click anywhere on the Full Map to create a waypoint.

The waypoint also appears on the Mini Map, making it easier to navigate toward a destination while playing.

When your position is known, the app displays the waypoint distance and direction.

Waypoints can also be saved as custom local markers.

### Position tracking

The app supports normal clipboard tracking on both Windows and Linux.

Use The Isle's built-in **Copy Location** function and the app will detect the copied coordinates and update your position on the Full Map and Mini Map.

The app keeps track of:

* Current position
* Previous position
* Distance travelled
* Heading
* Breadcrumb trail

### Automatic Tracking

Automatic Tracking removes the need to click the coordinates manually.

When enabled, the app watches a small user selected part of the screen containing the coordinates shown in The Isle's Tab menu.

Local OCR reads those visible coordinates and updates your map position. Windows uses its built-in OCR service; Linux (and macOS) use [Tesseract](https://github.com/tesseract-ocr/tesseract).

Simply open the Tab menu and your position can update automatically.

Clipboard tracking remains available everywhere and needs no extra software.

## Completely external to The Isle

Keeping the companion separate from the game itself is an important part of the project.

The application does **not**:

* Access The Isle process
* Read game memory
* Modify game files
* Inject DLLs
* Hook the game renderer
* Inspect game network traffic
* Send input to the game

Coordinate tracking comes from either normal clipboard text or pixels already visible on your screen.

The Mini Map is a normal independent desktop window. It is not injected into The Isle.

No Steam or Discord account is required.

## Offline use

Normal application use is local.

The map, layers, settings, coordinates, markers, and tracking data remain on your computer.

The project includes the Gateway v0.21.772 basemap, matching water overlay, coordinate calibration, and offline map layer data.

See [`assets/map/SOURCE.md`](assets/map/SOURCE.md) for map source and version information. A few project guardrails are captured in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Platform support

| Feature                     | Windows | Linux |
| --------------------------- | :-----: | :---: |
| Full Map                    |    ✅    |   ✅   |
| Mini Map                    |    ✅    |   ✅   |
| Clipboard tracking          |    ✅    |   ✅   |
| Waypoints                   |    ✅    |   ✅   |
| Breadcrumbs                 |    ✅    |   ✅   |
| Map layers                  |    ✅    |   ✅   |
| Automatic OCR tracking      |    ✅    | ✅ (Tesseract) |
| Global shortcuts            |    ✅    |   ❌   |
| Mini Map interaction hotkey |    ✅    | X11/XWayland |
| Mini Map above game on any workspace | ✅ | Wayland (layer-shell desktops, GNOME via XWayland) |

Linux keeps the general Windows shortcut set hidden, while exposing the non-consuming Mini Map interaction binding and a toolbar fallback for native Wayland desktops.

## Requirements

### Windows

* Windows 10 or Windows 11
* Python 3.11 or newer
* PySide6

### Linux

* Modern 64-bit Linux desktop (X11 or Wayland)
* Python 3.11 or newer
* PySide6
* Automatic Tracking also needs Tesseract OCR (and `grim` on wlroots desktops); `run.sh` installs them for you

PySide6 includes Qt, so a separate Qt SDK is not required.

## Windows setup guide

1. Install Python 3.11 or newer from python.org

During setup, check **Add Python to PATH**.

2. Download this project from GitHub using **Code > Download ZIP**.

3. Extract the ZIP.

4. Open the extracted folder.

5. Click the folder address bar, type:

```text
cmd
```

and press Enter.

6. Run:

```text
python -m pip install -r requirements.txt
```

If that does not work, try:

```text
py -m pip install -r requirements.txt
```

7. Close the window.

8. Double click `run.bat`.

After the first setup, just use `run.bat` to start the app.


## Installation

Clone the repository:

```bash
git clone https://github.com/hartwin-journey/The-Isle-Overlay.git
```

Then enter the project directory:

```bash
cd The-Isle-Overlay
```

### Windows

Create a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

Launch:

```powershell
python app.py
```

or:

```powershell
py app.py
```

You can also use:

```text
run.bat
```

### Linux

From the project folder, run:

```bash
sh run.sh
```

That is the whole setup. On the first run `run.sh` detects your distribution and desktop and:

* creates a Python environment in `.venv` and installs the requirements;
* on Wayland desktops with overlay support (KDE Plasma, Hyprland, Sway, niri, river, COSMIC) adds the Mini Map overlay package (`requirements-wayland.txt`), so the Mini Map stays above the game on every workspace;
* installs what Automatic Tracking needs from your package manager: Tesseract OCR with English data, plus `grim` on wlroots desktops (Sway, Hyprland, niri, river). This asks for your password, in the terminal or with a graphical prompt when started from a desktop shortcut.

Later runs skip all of this and start the app straight away; setup runs again only when the requirements or your desktop change. Use `sh run.sh` to start the app every time.

`run.sh` also adds **The Isle Companion** to your app launcher, so after the first run you can start it from your desktop's search bar or app menu (search for "Isle"). The entry and icon are written to `~/.local/share` and updated automatically if you move the project folder. Set `ISLE_COMPANION_NO_LAUNCHER=1` to skip this.

Supported for automatic installs: Arch/CachyOS/Manjaro/EndeavourOS, Debian/Ubuntu/Mint/Pop!_OS, Fedora/Nobara, openSUSE, Void and Alpine. On image-based systems (Fedora Silverblue/Kinoite, Bazzite, SteamOS), NixOS and Gentoo, nothing is installed system-wide; the app shows what to add instead. Set `ISLE_COMPANION_NO_SYSTEM_INSTALL=1` to skip system installs.

Anything still missing is listed in the app (status bar at startup and **Automatic Tracking > Set up capture area…**) with the exact command for your system, and logged in `logs/`.

Screen capture for Automatic Tracking is picked automatically: Qt's normal grab on X11, `grim` on wlroots desktops, and the standard xdg-desktop-portal Screenshot API on GNOME and KDE Plasma. If `tesseract` is not on your `PATH`, set `TESSERACT_CMD` to its full path.

## Using position tracking

### Clipboard tracking

1. Launch The Isle Companion.
2. Open The Isle.
3. Use the game's built-in **Copy Location** function.
4. Your position updates on the Full Map and Mini Map.

### Automatic Tracking

1. Enable **Automatic Tracking** from the Full Map.
2. Select the area of the screen containing the coordinates in the Tab menu. On Wayland, a short countdown (5 seconds by default) gives you time to switch to the game before the screen is captured; then drag around the coordinates on the frozen snapshot.
3. Open the Tab menu while playing.
4. The app reads the visible coordinates using local OCR (Windows OCR or Tesseract) and updates your position.

If screen capture does not work in exclusive fullscreen mode, try borderless windowed mode.

## Windows shortcuts

Windows supports configurable global shortcuts.

| Default               | Action                        |
| --------------------- | ----------------------------- |
| `Ctrl+Shift+M`        | Show or hide Full Map         |
| `Ctrl+Shift+O`        | Show or hide Mini Map         |
| `Ctrl+Shift+L`        | Show or hide Layers           |
| `Ctrl+Shift+B`        | Toggle breadcrumbs            |
| `Ctrl+Shift+W`        | Clear waypoint                |
| `Ctrl+Shift+R`        | Recenter on player            |
| `Ctrl+Shift+P`        | Toggle Mini Map player follow |
| `Ctrl+Shift+PageUp`   | Increase Mini Map opacity     |
| `Ctrl+Shift+PageDown` | Decrease Mini Map opacity     |

Shortcuts can be changed in Settings.

Linux does not currently expose the general global shortcut set. The Mini Map editing binding is available separately on X11/XWayland and can be changed in Settings.

## Local settings

Settings are stored locally.

This includes things such as:

* Mini Map preferences
* Enabled layers
* Saved markers
* Tracking preferences
* OCR capture area

Personal settings, saved markers, and logs are excluded from Git.

## Building locally

Running from source is the primary way to use the project.

A local PyInstaller build can also be created.

### Windows

```powershell
py -m pip install -r requirements-dev.txt
py tools\build_exe.py
```

Output:

```text
dist\TheIsleCompanion\TheIsleCompanion.exe
```

### Linux

```bash
python -m pip install -r requirements-dev.txt
python tools/build_exe.py
```

Output:

```text
dist/TheIsleCompanion/TheIsleCompanion
```

The application is built from the same readable source available in this repository.

## Map data

The project currently targets **Gateway v0.21.772**.

Map data such as migrations, sanctuaries, patrol zones, POIs, and updrafts is stored locally and can be updated as Gateway changes.

The runtime does not contact VulnonaMAP or another external map service.

## Development checks

Install `requirements-dev.txt`, then run:

```bash
python -m pytest -q
```

The suite includes offscreen Qt interaction tests and regression checks for settings recovery, layer visibility, Mini Map edit synchronization, and zoom limits. Offscreen tests do not replace checking native desktop behavior; see [`docs/QA.md`](docs/QA.md) for a manual release checklist.

## Contributing

Issues, fixes, Linux compatibility improvements, map corrections, and other contributions are welcome.

If you find something that is outdated or positioned incorrectly after a Gateway update, feel free to open an issue or pull request.
