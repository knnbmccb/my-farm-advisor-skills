---
name: field-level-comparison-guide
description: Step-by-step guide for running field-level EDA comparisons.
version: 1.0.0
---

# Field-Level Comparison Guide

## Prerequisites

1. Data pipeline runtime initialized
2. Growers have completed farm pipeline (boundaries, weather, CDL)
3. Virtualenv activated

## Step 1: Import the Module

```python
import sys
from pathlib import Path

skill_src = Path("/path/to/my-farm-advisor-skills/my-farm-advisor/eda/field-level-comparison/src")
sys.path.insert(0, str(skill_src))

from field_level_comparison import run_all_analyses
```

## Step 2: Configure Paths

```python
DATA_ROOT = Path("/home/coder/my-farm-advisor-runtime/data-pipeline")
OUT_DIR = DATA_ROOT / "eda" / "assignment2-field-comparison" / "output"
GROWERS = ["ia-grower", "il-grower", "ne-grower"]
```

## Step 3: Run All Analyses

```python
run_all_analyses(GROWERS, DATA_ROOT, OUT_DIR)
```

This generates:
- `01_field_area_distribution.png`
- `02_field_count_and_acreage.png`
- `03_area_vs_crop_type.png`
- `04_crop_rotation_heatmap_*.png`
- `05_crop_dominance_by_grower.png`
- `06_crop_consistency_vs_size.png`
- `07_growing_season_temperature.png`
- `08_cumulative_precipitation.png`
- `09_precip_vs_temperature.png`
- `eda_summary.csv`

## Step 4: Review Outputs

All PNG files are static and can be:
- Embedded in reports
- Included in presentations
- Committed to Git (if needed)

## Customization

To run individual analyses:

```python
from field_level_comparison import (
    plot_field_area_distribution,
    plot_growing_season_temperature,
    generate_summary_csv,
)

plot_field_area_distribution(GROWERS, DATA_ROOT, OUT_DIR)
plot_growing_season_temperature(GROWERS, DATA_ROOT, OUT_DIR)
generate_summary_csv(GROWERS, DATA_ROOT, OUT_DIR)
```

## Output Stories

| Output | Story |
|--------|-------|
| 01_field_area_distribution.png | Do fields in Nebraska differ in size from Iowa/Illinois? |
| 02_field_count_and_acreage.png | How does scale vary across the three growers? |
| 03_area_vs_crop_type.png | Do corn fields tend to be larger than soybean fields? |
| 04_crop_rotation_heatmap.png | Which fields rotate crops, and which stay consistent? |
| 05_crop_dominance_by_grower.png | How does crop mix differ across states? |
| 06_crop_consistency_vs_size.png | Are larger fields more or less likely to rotate? |
| 07_growing_season_temperature.png | How do growing season thermal profiles differ? |
| 08_cumulative_precipitation.png | Which state has the wettest/driest growing seasons? |
| 09_precip_vs_temperature.png | Are wetter growing seasons also cooler? |

## Notes

- All weather analyses use **growing season only** (April–October)
- Pearson correlation coefficients include p-values
- Soil analysis is explicitly excluded per assignment requirements
