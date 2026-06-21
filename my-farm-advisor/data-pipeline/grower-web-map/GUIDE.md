---
name: grower-web-map
description: Generate lightweight grower-level interactive HTML web maps from pipeline field boundaries. Self-contained single-file output with Leaflet.js, sidebar field list, and per-farm colouring.
version: 1.0.0
author: Assignment-1
tags: [web-map, leaflet, grower, visualization, interactive]
---

# Workflow: grower-web-map

## Description

Generate a **grower-level interactive web map** that displays every field belonging to a grower.  The output is a single HTML file that can be opened directly in any browser, emailed, or deployed to a static host.

### Key Features

- **Self-contained** -- one HTML file with embedded GeoJSON
- **Lightweight** -- no embedded rasters, no base64 images (typically 50--200 KB)
- **Per-farm colouring** -- each farm gets a distinct colour
- **Sidebar field list** -- click to zoom to any field
- **Click popups** -- show grower, farm, field ID, area (acres), county
- **Dual base layers** -- Satellite (Esri World Imagery) default with CartoDB Voyager street fallback
- **Responsive** -- sidebar collapses gracefully on mobile

## When to Use

- Sharing a quick interactive overview of a grower's fields
- Field-work reference on a tablet
- Inclusion in reports or presentations

## Prerequisites

The pipeline virtualenv must have `geopandas` installed (it already does).

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"

# Generate map for one grower
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower

# Output:
#   growers/il-grower/derived/reports/grower_web_map.html
```

## Custom Output Path

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower \
  --output /tmp/il-grower-map.html
```

## Programmatic Usage

```python
from pathlib import Path
import sys

# Ensure pipeline lib is on path
sys.path.insert(0, "/home/coder/my-farm-advisor-runtime/data-pipeline/src/scripts/lib")

from paths import farm_boundary_path, grower_dir

# The script auto-discovers farms, but you can also call the generator
# directly by importing the module (not intended for external use).
```

## Output Format

The HTML contains:

1. Leaflet CSS + JS from unpkg CDN
2. Embedded GeoJSON `FeatureCollection` with all fields
3. JavaScript that:
   - Groups fields by farm
   - Renders polygons with per-farm colours
   - Builds a sidebar field list
   - Handles click-to-zoom and popups
   - Auto-fits map bounds to all fields

## Performance Notes

- Tested comfortably with 50+ fields.
- For 200+ fields, consider simplifying geometries before embedding:
  ```python
  gdf['geometry'] = gdf['geometry'].simplify(tolerance=0.001)
  ```

## Resources

- [Leaflet Documentation](https://leafletjs.com/)
- [OpenStreetMap](https://www.openstreetmap.org/)
