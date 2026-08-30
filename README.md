# The Isle Companion

The Isle Companion is a local desktop map for **The Isle: Evrima**, available for Windows and Linux.

I started this as a new player who loved exploring Gateway but found it genuinely difficult to navigate, keep track of migration zones and sanctuaries, and remember where I was heading.

So I threw this together to make getting around a little easier.

It includes a full Gateway map, a toggleable Mini Map overlay, position tracking, waypoints, breadcrumbs, migration zones, sanctuaries, patrol zones, water sources, updrafts, named locations, and other useful map layers.

Windows also supports optional Automatic Tracking using local OCR.

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
* Player centered mode
* Adjustable size and opacity
* Square or circular appearance
* Click through mode

On Windows, the Mini Map can be switched between interactive and click through modes with a configurable input binding.

On Linux, Mini Map editing is controlled from the Full Map toolbar. Click through behaviour can vary between X11 and Wayland desktop environments.

### Waypoints

Click anywhere on the Full Map to create a waypoint.

The waypoint also appears on the Mini Map, making it easier to navigate toward a destination while playing.

When your position is known, the app displays the waypoint distance and direction.

Waypoints can also be saved as custom local markers.

### Position tracking

The app supports normal clipboard tracking on both Windows and Linux.

Use The Isle's built in **Copy Location** function and the app will detect the copied coordinates and update your position on the Full Map and Mini Map.

The app keeps track of:

* Current position
* Previous position
* Distance travelled
* Heading
* Breadcrumb trail

### Automatic Tracking

**Windows only**

Automatic Tracking removes the need to click the coordinates manually.

When enabled, the app watches a small user selected part of the screen containing the coordinates shown in The Isle's Tab menu.

Windows' local OCR reads those visible coordinates and updates your map position.

Simply open the Tab menu and your position can update automatically.

Automatic Tracking is not available on Linux because it currently uses Windows' built in OCR service.

Clipboard tracking remains fully available on Linux.

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

Coordinate tracking comes from either normal clipboard text or, on Windows, pixels already visible on your screen.

The Mini Map is a normal independent desktop window. It is not injected into The Isle.

No Steam or Discord account is required.

## Offline use

Normal application use is local.

The map, layers, settings, coordinates, markers, and tracking data remain on your computer.

The project includes the Gateway v0.21.772 basemap, matching water overlay, coordinate calibration, and offline map layer data.

See [`map/SOURCE.md`](map/SOURCE.md) for map source and version information.

## Platform support

| Feature                     | Windows | Linux |
| --------------------------- | :-----: | :---: |
| Full Map                    |    ✅    |   ✅   |
| Mini Map                    |    ✅    |   ✅   |
| Clipboard tracking          |    ✅    |   ✅   |
| Waypoints                   |    ✅    |   ✅   |
| Breadcrumbs                 |    ✅    |   ✅   |
| Map layers                  |    ✅    |   ✅   |
| Automatic OCR tracking      |    ✅    |   ❌   |
| Global shortcuts            |    ✅    |   ❌   |
| Mini Map interaction hotkey |    ✅    |   ❌   |

Linux intentionally hides Windows specific features rather than replacing them with intrusive or desktop specific alternatives.

## Requirements

### Windows

* Windows 10 or Windows 11
* Python 3.11 or newer
* PySide6

### Linux

* Modern 64 bit Linux desktop
* Python 3.11 or newer
* PySide6

PySide6 includes Qt, so a separate Qt SDK is not required.

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

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Launch:

```bash
python app.py
```

or:

```bash
sh run.sh
```

## Using position tracking

### Clipboard tracking

1. Launch The Isle Companion.
2. Open The Isle.
3. Use the game's built in **Copy Location** function.
4. Your position updates on the Full Map and Mini Map.

### Automatic Tracking on Windows

1. Enable **Automatic Tracking** from the Full Map.
2. Select the area of the screen containing the coordinates in the Tab menu.
3. Open the Tab menu while playing.
4. The app reads the visible coordinates using Windows OCR and updates your position.

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

Linux does not currently expose global shortcuts.

## Local settings

Settings are stored locally.

This includes things such as:

* Mini Map preferences
* Enabled layers
* Saved markers
* Tracking preferences
* Windows OCR capture area

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

## Contributing

Issues, fixes, Linux compatibility improvements, map corrections, and other contributions are welcome.

If you find something that is outdated or positioned incorrectly after a Gateway update, feel free to open an issue or pull request.
