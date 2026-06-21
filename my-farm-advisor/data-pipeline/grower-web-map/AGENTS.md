# Local Instructions

## Purpose

This folder owns the **grower-level interactive web-map** subskill for the My Farm Advisor data pipeline.  It generates a single lightweight HTML file per grower that displays all farm field boundaries on an interactive Leaflet map.

## Safe edit scope

Edits should stay in this folder and the related runtime script at `../src/scripts/reporting/generate_grower_web_map.py`.  Do not change parent `SKILL.md`, sibling workflows, or root policy from this subskill task unless explicitly requested.

## Read nearby docs first

Read `README.md` first, then `GUIDE.md` for detailed usage.  If routing context is needed, read `../../SKILL.md` and `../../INDEX.md`.

## Local workflow notes

- The generator discovers farms automatically by looking for `growers/<slug>/farms/*/boundary/field_boundaries.geojson`.
- Output is always a single self-contained HTML file with embedded GeoJSON and Leaflet CDN links.
- No rasters, no base64 imagery, no external data bundles -- keep the HTML small.
- The script follows pipeline conventions: reads `DATA_PIPELINE_DATA_ROOT`, uses `lib/paths.py`, and writes to `derived/reports/`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.  To test the map generator:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py --grower-slug il-grower
```

Then open the produced HTML in a browser:

```bash
xdg-open growers/il-grower/derived/reports/grower_web_map.html
```

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files.  Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
