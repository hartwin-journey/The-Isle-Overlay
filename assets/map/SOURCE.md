# Gateway map source

The local map snapshot was retrieved from [VulnonaMAP](https://vulnona.com/game/map/) on
2026-08-28. The selected map was Gateway v0.21.772 at the site's 7800-pixel quality.

Local assets:

- `gateway.webp`: Gateway base raster, 7800 × 7817 pixels.
- `gateway_water.webp`: matching independently toggleable water raster.
- `calibration.json`: world/pixel transform derived from the site's 2780 × 2790 logical
  canvas and scaled to the local raster dimensions.
- `../data/patrol_zones.json`: visible patrol geometry captured on 2026-08-29; the
  recorded source vectors and offline rebuild helper live in `tools/build_patrol_snapshot.py`.
- `../data/updrafts.json`: 21 visible Gateway updraft markers and their active hours,
  refreshed from the selected Gateway data on 2026-08-30.

`gateway.webp`, `gateway_water.webp`, `calibration.json`, and the editable JSON layer data
are bundled together so a fresh source checkout opens as a complete calibrated map. This
file retains the source and version information needed to identify and refresh that snapshot.

The runtime application never contacts VulnonaMAP. These files and the JSON layer snapshots
are ordinary local inputs. They can become stale when Gateway or VulnonaMAP is updated.
