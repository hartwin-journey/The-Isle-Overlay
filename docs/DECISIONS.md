# Development notes

A few choices in this project are intentional and worth keeping in mind when changing the code.

## Keep the companion separate from the game

Coordinate updates come from either copied text or a user-selected patch of screen pixels for OCR. The app should not read game memory, inject into the renderer, alter files, or send input to The Isle.

## Prefer boring, local state

Settings, calibration, custom markers, and breadcrumbs live locally. There is no account system or telemetry, and normal use should work offline.

## UI copy should sound like a player wrote it

The interface should be clear without sounding overly formal. Short labels are best in toolbars; dialogs can use plain, practical wording that explains what the player should do next.

## Mini Map editing must be hard to trigger accidentally

The overlay should default to click-through during play. Editing mode exists for zooming, panning, resizing, and toggling follow mode, then it should get out of the way again.

## Keep map tuning grouped

The settings dialog intentionally exposes broad controls such as zone intensity and marker opacity instead of every raw layer value. The raw values still exist in settings, but the user-facing controls should stay simple.
