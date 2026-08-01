# Grower Field Dashboard — Usage Guide

## Step 1: Verify Runtime Data

Ensure the data pipeline has been run for your target grower. The expected
path structure is:
```
{DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/{grower_slug}/
  farms/{farm_slug}/
    fields/{field_slug}/
      boundary/field_boundary.geojson
      weather/daily_weather.csv
      soil/ssurgo_summary.csv
      satellite/landsat/{year}/landsat_YYYYMMDD/
      satellite/sentinel/{year}/sentinel_YYYYMMDD/
      derived/features/ndvi_year_*_composite.tif
      derived/summaries/ndvi_yearly_summary.json
    derived/tables/
      *_crop_rotation.csv
      *_cdl_*_full_composition.csv
```

The default runtime root for this environment is:
`/home/coder/my-farm-advisor-runtime/data-pipeline`

## Step 2: Install Dependencies

```bash
# Activate the pipeline venv or create a new one
source /home/coder/my-farm-advisor-runtime/data-pipeline/.venv/bin/activate

# Install additional dependencies not in the base requirements
pip install plotly kaleido
```

## Step 3: Run the Dashboard Generator

### From Python
```python
from dashboard.grower_field_dashboard.src import generate_grower_dashboard

# Default grower
path = generate_grower_dashboard()

# Specific grower
path = generate_grower_dashboard(grower_slug="ia-grower")

# Custom output path
path = generate_grower_dashboard(
    grower_slug="ia-grower",
    output_path="/tmp/my_dashboard.html",
)
```

### From the command line
```bash
cd /home/coder/my-farm-advisor-skills
python my-farm-advisor/dashboard/grower-field-dashboard/src/grower_dashboard.py ia-grower
```

## Step 4: View the Dashboard

Open the output file in any modern browser:
```bash
# The output path is printed at the end of the run, e.g.:
# /home/coder/my-farm-advisor-runtime/data-pipeline/growers/ia-grower/derived/reports/grower_field_dashboard.html

# macOS
open /home/coder/my-farm-advisor-runtime/data-pipeline/growers/ia-grower/derived/reports/grower_field_dashboard.html

# Linux
xdg-open /home/coder/my-farm-advisor-runtime/data-pipeline/growers/ia-grower/derived/reports/grower_field_dashboard.html
```

## Step 5: Interpret the Dashboard

The dashboard is organized into **4 narrative sections**:

1. **Crop Health Overview** — Interactive choropleth map with satellite
   basemap, monthly NDVI pixel overlay, year/month/field filters, and scene
   source information. Toggles between NDVI view and Soil Health Score view.

2. **Actionable Insights** — Priority recommendations computed from field
   data (cover crops, rotation suggestions, drought-tolerant hybrids) plus
   ranked list of the most important agronomic variables.

3. **Field Health Ranking & Drivers** — Environmental correlations
   (scatter plots of NDVI vs rainfall, GDD, soil organic matter) and NDVI
   variability maps (mean NDVI + coefficient of variation) per field.

4. **Soil Variability Analysis** — Detailed methodology for Soil Health
   Score (0–10) and Sustainability Index (0–10), data sources, and
   limitations.

Each section includes a narrative paragraph computed from the actual field data,
highlighting the most significant findings.

## Using the Filters

The dashboard includes **three dropdown filters** in the header banner:

| Filter | Options | Default | Effect |
|--------|---------|---------|--------|
| Year | 2021–2025 | 2025 | Updates all KPIs, narratives, and map to selected year |
| Month | Apr–Oct | Oct | Shows monthly satellite pixels for that month (with fallback chain) |
| Field | All Fields or individual | All Fields | Zooms map to field, updates field-specific KPIs |

**Month filter behavior:**
- If a satellite scene exists for the selected month, actual NDVI pixels from
  that scene are shown on the map (Sentinel-2 preferred, Landsat-9 fallback)
- If no scene exists, the dashboard falls back to the previous month's scene,
  then to the yearly composite
- The map scene info text shows the source satellite and date

## Customization

### Changing the basemap
In `grower_dashboard.py`, the ArcGIS World Imagery raster tiles are configured
in `_create_interactive_map()` via `mapbox.layers`. To switch to a different
basemap, modify the layer `source` URL or use a pre-defined Mapbox style.

### Adding a new grower
Point `DATA_PIPELINE_DATA_ROOT` to a directory with the same grower/farm/field
structure and run:
```python
generate_grower_dashboard(grower_slug="new-grower")
```

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| `FileNotFoundError` | Pipeline not run for this grower | Run the data pipeline first |
| `ModuleNotFoundError` | Missing dependency | `pip install plotly kaleido` |
| Map shows blank/white | Plotly.js version mismatch | Ensure CDN URL matches `plotly-3.0.1.min.js` |
| Monthly pixels don't appear | No scene for selected month | Dashboard auto-falls back to previous month or composite |
| Charts show empty | No NDVI composite TIFFs | Check pipeline NDVI step completed |

## Files

| File | Purpose |
|------|---------|
| `src/grower_dashboard.py` | Main generator — loads data, computes KPIs, renders map/charts, assembles HTML |
| `src/run_all.py` | Orchestrator — generates both dashboard.html and findings.md |
| `templates/dashboard.html` | HTML shell with placeholders for CSS, JS, and chart divs |
| `templates/dashboard.css` | All dashboard styles (KPI cards, sections, map, charts) |
| `templates/dashboard.js` | All frontend logic (filter handling, map updates, narrative builders) |
