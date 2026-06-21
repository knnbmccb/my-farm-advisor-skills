# Grower Web Map

A lightweight, grower-level interactive web-map generator for the My Farm Advisor data pipeline.

## Purpose

Produces a single self-contained HTML file per grower that shows **all farms and fields** on an interactive Leaflet map.  The map is designed to be:

- **Small** -- only embedded GeoJSON (no rasters, no base64 images)
- **Portable** -- one file, opens in any browser, can be emailed or hosted statically
- **Interactive** -- zoom, pan, click fields for metadata, sidebar list to jump to fields

## Output

```
growers/<grower-slug>/derived/reports/grower_web_map.html
```

Typical size: 50--200 KB for 3--10 fields.

## How to Run

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"

"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower
```

The script automatically discovers every farm under the grower that has a `boundary/field_boundaries.geojson` file.

## Map Features

- **OpenStreetMap basemap** (loads from internet)
- **Field polygons** coloured per farm
- **Click popup** showing: grower slug, farm name, field ID, area (acres), county
- **Sidebar field list** -- click any field to zoom-to-fit and open its popup
- **Auto-fit bounds** -- map initially zooms to show all fields

## Files

| File | Description |
|------|-------------|
| `src/scripts/reporting/generate_grower_web_map.py` | CLI entrypoint and HTML generator |
| `README.md` | This file |
| `AGENTS.md` | Local agent instructions |
| `GUIDE.md` | Detailed usage guide |

## Dependencies

- `geopandas` (already installed in pipeline venv)
- Leaflet.js loaded from CDN at view time (no build step)
