# Local runtime state

This directory is intentionally free of personal state in source control.

The application creates `settings.json` on first launch and creates
`custom_markers.json` after the first saved waypoint. Both files are ignored by Git because
settings may contain the selected OCR screen rectangle and saved markers may reveal personal
play locations. Deleting either file is safe: settings return to defaults and saved markers
return to an empty list.
