---
name: field-level-comparison
description: Compare field boundaries, CDL/cropland data, and weather across growers. Produces static matplotlib/seaborn visualizations for EDA.
version: 1.0.0
author: Assignment-2
tags: [eda, field-comparison, boundaries, cdl, weather, static-viz]
---

# Skill: field-level-comparison

**Domain:** Agricultural Data Science — Field-Level Exploratory Data Analysis

## Purpose

Use this subskill when you need to compare agricultural fields across multiple dimensions:
- **Field boundaries** (size, shape, location)
- **CDL/cropland data** (crop types, rotation patterns)
- **Weather** (temperature, precipitation, growing season profiles)

Produces **static PNG outputs** (not interactive dashboards) suitable for reports, presentations, and peer review.

## When to Use

- Comparing fields within a grower
- Comparing growers across states
- Analyzing crop rotation consistency
- Exploring weather patterns during growing season
- Generating figures for assignment reports

## When NOT to Use

- Interactive dashboard creation (use admin/interactive-web-map instead)
- Soil analysis (out of scope)
- Real-time data monitoring

## Start Here

Open `GUIDE.md` for the full workflow.

## Data Requirements

- `growers/<slug>/farms/<farm>/boundary/field_boundaries.geojson`
- `growers/<slug>/farms/<farm>/derived/tables/*_cdl_*.csv`
- `growers/<slug>/farms/<farm>/derived/tables/*_weather_*.csv`

## Output

Static PNG files + summary CSV written to a configurable output directory.
