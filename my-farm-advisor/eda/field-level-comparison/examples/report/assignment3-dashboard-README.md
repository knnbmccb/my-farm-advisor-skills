# Assignment 3: Field Dashboard Prototype

## Assignment

**Skill:** `field-level-comparison` — `plot_field_dashboard()` in `src/field_level_comparison.py`

**Strategy references:** `strategy/crop-strategy/resources/2026-usa-corn.md`, `2026-usa-soybean.md`

**Input files (from data-pipeline):**
- `growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360316057/boundary/field_boundary.geojson`
- `growers/ia-grower/farms/ia-grower-iowa/derived/tables/ia_grower_iowa_2023_cdl.csv`
- `growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360316057/satellite/sentinel/2023/*/sentinel_*_ndvi.tif`
- `growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360316057/derived/features/ndvi_year_2023_composite.tif`
- `growers/ia-grower/farms/ia-grower-iowa/fields/osm-1360316057/weather/daily_weather.csv`

**Weather metrics calculated:** T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, GDD (base 10°C), cumulative GDD, cumulative precipitation, SPI-3 (Standardized Precipitation Index), P-PET z-score (Thornthwaite-based moisture deficit)

**Dashboard output:** `eda/assignment3-field-dashboard/output/01_field_dashboard_osm-1360316057_2023.png`

**How to rerun:** See "How to Run" below.

**Known data limitations:**
- Nebraska field boundaries and CDL are synthetic (Overpass API 503 errors during bootstrap). Not used in this prototype.
- Sentinel SCL masking excludes cloud and cloud-shadow pixels; thin cirrus (class 10) is kept.
- Per-scene mean NDVI may include non-crop pixels at field edge due to boundary geometry.

## Selected Field-Year

| Field | Year | CDL Crop | Confidence |
|---|---|---|---|
| `osm-1360316057` | 2023 | **Soybeans** | 100.0% |

### Rationale

- **Year 2023** — Most NDVI scenes available (18 combined Sentinel + Landsat, 9 Sentinel after masking), densest time series for a clear dashboard.
- **Field `osm-1360316057`** — Real OSM field boundary in Kossuth County, IA (43.5 acres). CDL classification at 100% confidence (194 pixels, all Soybeans). Classic corn-soy rotation pattern across the 5-year record.
- **Complete weather** — 365 daily records for 2023 with no gaps across all requested columns (T2M, T2M_MAX, T2M_MIN, PRECTOTCORR).

## Data Sources Used

| Source | Files | Records |
|---|---|---|
| CDL | `derived/tables/ia_grower_iowa_2023_cdl.csv` | Soybeans, 100% dominant |
| Sentinel NDVI | `satellite/sentinel/2023/*/sentinel_*_ndvi.tif` | 9 scene dates (Mar–Nov) |
| Yearly NDVI composite | `derived/features/ndvi_year_2023_composite.tif` | Mean 0.35 |
| Daily weather | `fields/osm-1360316057/weather/daily_weather.csv` | 365 records, complete |
| Field boundary | `fields/osm-1360316057/boundary/field_boundary.geojson` | OSM polygon, 43.5 ac |

### Cloud Masking

Sentinel SCL (Scene Classification Layer) files are used to exclude cloud, cloud-shadow, snow, and no-data pixels before computing per-scene mean NDVI. Falls back to raw NDVI if SCL is missing.

## Dashboard Panels

1. **NDVI Time Series** — 9 per-scene mean NDVI points with yearly composite reference line, peak annotation (gold star), green-up arrows, stress-dip arrows
2. **Daily Precipitation** — Bar chart with heavy rain (>20 mm/d) highlighted in crimson
3. **Temperature & Extremes** — T2M avg line, T2M_MAX/T2M_MIN filled range, hot day markers (>30°C), cool period bands (<10°C)
4. **Cumulative GDD** — Running sum from April 1 with total annotation
5. **Moisture Balance — SPI-3 + P-PET** — Color-coded SPI bars (blue=wet, gray=normal, orange=dry) with Thornthwaite P-PET z-score overlay line

All panels share a common DOY (day-of-year) x-axis aligned to the growing season (April–October).

## How to Run

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment3-field-dashboard"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" generate_dashboard.py
```

Output: `output/01_field_dashboard_osm-1360316057_2023.png`

## Reusability

The `plot_field_dashboard()` function in `field_level_comparison.py` is reusable for any field-year combination across any grower:

```python
from field_level_comparison import plot_field_dashboard

result = plot_field_dashboard(
    grower_slug="ia-grower",
    farm_slug="ia-grower-iowa",
    field_id="osm-1360316057",
    year=2023,
    data_root=Path("/path/to/runtime/data-pipeline"),
    out_dir=Path("/path/to/output"),
    mask_clouds=True,
    heavy_rain_thresh=20.0,
    hot_day_thresh=30.0,
)
```

Returns a dict with all computed values (crop, NDVI stats, weather stats, events, coverage).
