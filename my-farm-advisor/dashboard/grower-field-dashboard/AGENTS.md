# Grower Field Dashboard — Agent Instructions

## Purpose

This skill generates a single-page decision-support dashboard for any grower
in the data pipeline. It loads all available field data, computes KPI metrics,
creates an interactive Plotly choropleth map (satellite basemap with monthly
pixel overlay), generates multi-panel visualizations, and assembles everything
into a self-contained HTML file with narrative sections.

## Workflow

1. Read `README.md` first, then `GUIDE.md` for step-by-step.
2. Ensure the runtime environment has the required dependencies
   (`plotly`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `rasterio`, `scipy`).
3. The data pipeline must have been run for the target grower (pipeline
   runtime at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`).
4. Run `generate_grower_dashboard()` with the grower slug.
5. Open the generated HTML in a browser.

## Public API

```python
from dashboard.grower_field_dashboard.src import generate_grower_dashboard

path = generate_grower_dashboard(grower_slug="ia-grower")
```

- `grower_slug` — any grower with data in the pipeline (default: "ia-grower")
- `data_root` — pipeline root path (default: standard runtime path)
- `output_path` — optional explicit output path

Returns the absolute path to the generated dashboard HTML.

## Generated Dashboard Sections

| # | Section | Content |
|---|---------|---------|
| 1 | KPI Cards | 9 metrics (fields, acres, avg NDVI, rainfall, GDD, season days, top crop, SHS, SustIdx) |
| 2 | Crop Health Overview | Plotly choropleth (satellite basemap) + monthly NDVI pixel overlay, year/month/field filters |
| 3 | Actionable Insights | Priority recommendations + ranked most important variables |
| 4 | Field Health Ranking & Drivers | Environmental correlations + NDVI variability geo maps |
| 5 | Soil Variability Analysis | SHS methodology, data sources, limitations |

## Important Notes

- The dashboard is fully self-contained (no server needed, no external files).
- All narrative text is computed dynamically from the data.
- The satellite basemap uses free ArcGIS World Imagery tiles (no API key needed).
- Monthly satellite pixels are actual scene data (QA-filtered, field-normalized,
  ~300 pixels per field per scene, with fallback chain).
- All static charts use matplotlib `Agg` backend (headless).
- The generator uses template-based rendering: `templates/dashboard.html`,
  `templates/dashboard.css`, `templates/dashboard.js` are read at build time.

## Architecture

```
grower_dashboard.py (main generator)
  ├── _discover_and_load()      # Scans field directories
  ├── _compute_kpis()            # Aggregates weather, soil, NDVI metrics
  ├── _generate_narrative()      # Builds data-driven text per section
  ├── _build_embedded_data()     # Creates DATA blob for frontend filters
  ├── _build_monthly_pixel_ndvi() # Extracts monthly satellite pixels
  ├── _create_interactive_map()  # Plotly choropleth + Scattermapbox
  ├── _create_field_ranking_chart() # Static matplotlib charts (optional)
  ├── _create_environmental_correlations()
  ├── _create_ndvi_variability_map()
  ├── _create_ndvi_timeseries()  # Static line chart (optional)
  └── _render_html()             # Template assembly + validation
```
