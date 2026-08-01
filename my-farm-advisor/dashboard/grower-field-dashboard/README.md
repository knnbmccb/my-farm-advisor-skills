# Grower Field Dashboard

A reusable skill in the `my-farm-advisor` ecosystem that generates a
self-contained, interactive HTML dashboard for any grower in the data pipeline.

## Overview

This skill integrates **6 field-level datasets** into a single decision-support
dashboard with **7 KPI cards**, an **interactive Plotly map** (satellite
basemap with monthly satellite pixel overlay), and **2 multi-panel data
visualizations** — all accompanied by dynamically computed narrative interpretation.

### Data Sources

| Dataset | Source | Coverage |
|---------|--------|----------|
| Field Boundaries | OpenStreetMap / Overpass | Polygon per field + area |
| Weather | NASA POWER | Daily T2M, T2M_MAX, T2M_MIN, PRECTOTCORR (2021–2025) |
| Soil | USDA NRCS SSURGO | OM%, CEC, AWS, pH, drainage class, texture |
| NDVI | Sentinel-2 + Landsat yearly composites + monthly scenes | Yearly mean + monthly scene NDVI per field (2021–2025) |
| Crop Rotation | USDA NASS CDL | Crop per field per year (2021–2025) |
| Rotation Summary | Derived from CDL | Rotation patterns, diversity score |

### Dashboard Sections

| Section | Content | Type |
|---------|---------|------|
| **KPI Cards** | Total fields, acres, avg NDVI, monthly rainfall, monthly GDD, season days, top crop, Soil Health Score, Sustainability Index | HTML/CSS |
| **Crop Health Overview** | Interactive Plotly map (ArcGIS satellite basemap) with NDVI choropleth + monthly satellite pixel overlay, year/month/field dropdown filters | Plotly |
| **Actionable Insights** | Dynamic recommendations + most important variables ranked by agronomic impact | Text |
| **Field Health Ranking & Drivers** | Environmental correlations (NDVI vs rain, GDD, OM%) + NDVI variability geo maps (mean NDVI + CV%) | Plotly |
| **Soil Variability Analysis** | SHS decomposition, methodology, data sources, limitations | Static + text |

### KPI Methodology

**Soil Health Score (0–10):** Composite of OM% (2.5 pts), CEC (2.5 pts),
Available Water Storage (2.5 pts), Drainage Class (1.5 pts), and pH
Suitability (1.0 pt). Each component is normalized to a target value.

**Sustainability Index (0–10):** Combines crop rotation diversity (3 pts),
normalized Soil Health Score (3 pts), erosion risk (2 pts), and drainage
quality (2 pts). Fields in rotation score higher than monoculture.

## Quickstart

```bash
# Install additional dependencies
pip install plotly kaleido

# Run for the default grower (ia-grower)
python -c "
from my_farm_advisor.dashboard.grower_field_dashboard.src import generate_grower_dashboard
path = generate_grower_dashboard('ia-grower')
print(f'Dashboard: {path}')
"

# Open the generated HTML in a browser
open path      # macOS
xdg-open path  # Linux
```

## Output

The dashboard is written to:
```
{DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/{grower_slug}/derived/reports/grower_field_dashboard.html
```

It is a single self-contained HTML file — no server, no external dependencies
(other than CDN-loaded Plotly.js for the interactive map).

## File Structure

```
grower-field-dashboard/
├── README.md              # This file
├── SKILL.md               # Skill routing entry
├── GUIDE.md               # Step-by-step usage guide
├── AGENTS.md              # Agent instructions
├── src/
│   ├── __init__.py        # Public API export
│   ├── grower_dashboard.py  # Main generator (~2,300 lines)
│   └── run_all.py         # Orchestrator (dashboard + findings.md)
└── templates/
    ├── dashboard.html     # HTML shell with placeholders
    ├── dashboard.css      # Extracted styles
    └── dashboard.js       # All JavaScript logic
```

## Architecture

The generator (`grower_dashboard.py`) follows a **template-based pipeline**:

1. **Discover & Load** — scans field directories for boundaries, weather, soil, NDVI, CDL
2. **Compute KPIs** — aggregates weather, soil, NDVI, rotation metrics
3. **Generate Narratives** — builds data-driven text for each section
4. **Build Embedded Data** — creates DATA blob for frontend filters (year/month/field)
5. **Create Visualizations** — renders Plotly map + static matplotlib charts
6. **Render HTML** — reads templates, interpolates data, outputs single HTML file

## Monthly Satellite Features

The dashboard includes **actual monthly satellite NDVI pixels** extracted from
scene archives:

- **Scene discovery**: Scans `satellite/landsat/<year>/` and `satellite/sentinel/<year>/`
- **Scene selection**: Prefers Sentinel-2 (higher res ~10m), falls back to Landsat-9 (~30m)
- **QA filtering**: Cloud/shadow/water masks via `qa_pixel` (Landsat) and `scl` (Sentinel)
- **Pixel capping**: ~300 pixels per field per scene to keep HTML under 5 MB
- **Fallback chain**: Current month → previous months → yearly composite
- **Per-field normalization**: Pixel colors (0–1) within each field for contrast

## Dependencies

- `pandas`, `numpy`, `scipy` — data manipulation & statistics
- `matplotlib`, `seaborn` — static visualizations
- `plotly>=5.18.0` — interactive map
- `rasterio` — NDVI TIFF reading
- `kaleido>=0.2.1` — optional (for programmatic Plotly image export)

All except `plotly` and `kaleido` are already in the data-pipeline requirements.

## Limitations

- No actual yield data — NDVI serves as a vegetation health proxy
- Soil data from SSURGO may not reflect within-field variability
- 5-year window (2021–2025) limits long-term trend detection
- Weather data from NASA POWER is grid-interpolated, not on-site station
- Monthly satellite scenes unavailable in winter (Jan, Feb, Dec) — only growing season (Apr–Oct) has coverage

## License

Apache-2.0 — Superior Byte Works LLC / borealBytes
