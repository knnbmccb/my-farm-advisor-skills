---
name: grower-field-dashboard
description: >
  Generates a self-contained HTML decision-support dashboard for any grower
  in the data pipeline. Integrates field boundaries, weather, soil, NDVI,
  monthly satellite pixels, and CDL data into KPI cards, an interactive
  choropleth map (satellite basemap with monthly pixel overlay), 
  environmental correlation charts, and narrative interpretation with
  actionable recommendations.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.1.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.1.0"
---

# Grower Field Dashboard

**Domain:** Agricultural Data Science & Decision Support  
**License:** Apache-2.0  
**Attribution:** Superior Byte Works LLC / borealBytes

## Purpose

Build a comprehensive, single-page HTML dashboard for any grower that:

- Integrates 6 data sources (boundaries, weather, soil, NDVI, monthly satellite scenes, CDL)
- Computes 9 KPI metrics (field count, acreage, NDVI, monthly rainfall, monthly GDD, season days, top crop, Soil Health Score, Sustainability Index)
- Displays an interactive choropleth map (Plotly, ArcGIS satellite basemap, monthly NDVI pixel overlay, year/month/field dropdown filters)
- Shows environmental correlations (NDVI vs rain, GDD, OM%) and NDVI variability geo maps
- Provides narrative interpretation for each section, computed dynamically from field data
- Generates actionable recommendations ranked by data-driven impact
- Extracts actual monthly satellite NDVI pixels (Sentinel-2 / Landsat-9, QA-filtered, field-normalized)

## Start Here

Open [README.md](README.md) for the overview and quickstart, or [GUIDE.md](GUIDE.md) for step-by-step usage.

## Output

Generated dashboard is written to:
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/{grower_slug}/derived/reports/grower_field_dashboard.html`
