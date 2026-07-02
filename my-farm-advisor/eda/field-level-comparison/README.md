# Field-Level Comparison EDA

Custom EDA Skill - Assignment 2 - Field-Level Comparison EDA
Skill name: field-level-comparison
Location: my-farm-advisor/eda/field-level-comparison
What it generates: 9 PNGs + Summmary CSV
Output path: eda/assignment2-field-comparison/output/
Report path: ...report/assignment2-eda-report.html
Existing context: Untouched - no rewrites or deletions


Compare field boundaries, CDL/cropland data, and weather across growers for exploratory data analysis.

## What It Does

This subskill generates **9 static visualizations** organized into three categories:

### Field Boundaries (3 outputs)
1. **Field Area Distribution** — box + violin plots per grower
2. **Field Count & Acreage** — grouped bar chart
3. **Area vs. Crop Type** — scatter with correlation

### CDL / Cropland Data Layer (3 outputs)
4. **Crop Rotation Heatmap** — field × year crop matrix
5. **Crop Dominance** — stacked bar by grower
6. **Crop Consistency vs. Size** — scatter with correlation

### Weather (3 outputs)
7. **Growing Season Temperature** — monthly temp profiles
8. **Cumulative Precipitation** — growing season water accumulation
9. **Precip vs. Temperature** — scatter with correlation

Plus a **summary CSV** with key statistics per grower.

## Quick Start

```python
from field_level_comparison import run_all_analyses

GROWERS = ["ia-grower", "il-grower", "ne-grower"]
DATA_ROOT = Path("/path/to/my-farm-advisor-runtime/data-pipeline")
OUT_DIR = DATA_ROOT / "eda" / "assignment2-field-comparison" / "output"

run_all_analyses(GROWERS, DATA_ROOT, OUT_DIR)
```

## Architecture

- **Reusable module:** `src/field_level_comparison.py` — core analysis functions
- **Report script:** `examples/generate_assignment2_report.py` — one-time orchestrator
- **Outputs:** Static PNGs + CSV (no interactive components)

## Requirements

- geopandas
- matplotlib
- seaborn
- pandas
- numpy
- scipy

All available in the data-pipeline virtualenv.
