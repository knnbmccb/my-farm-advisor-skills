# Local Instructions

## Purpose

This folder owns the **field-level comparison EDA** subskill for My Farm Advisor. It generates static visualizations comparing field boundaries, CDL/cropland data, and weather across growers.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA workflows, or root policy from this subskill.

## Read nearby docs first

Read `GUIDE.md` first, then `README.md` for the overview. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.

To test the EDA module:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/assignment2-field-comparison"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" generate_report.py
```

Then verify outputs in `output/` directory.

## Output policy

Generated PNG and CSV files belong under the runtime root (`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/...`), not in the skill checkout. Do not commit generated artifacts to Git.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
