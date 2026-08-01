#!/usr/bin/env python3
"""Field-level EDA comparison module for agricultural data.

Compares field boundaries, CDL/cropland data, and weather across growers.
Produces static matplotlib/seaborn visualizations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import calendar
from datetime import date, timedelta

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
import seaborn as sns
from scipy.stats import gamma, norm, pearsonr

matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# Styling defaults
# ---------------------------------------------------------------------------
sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["figure.figsize"] = (10, 6)

GROWER_COLORS = {
    "ia-grower": "#2E7D32",
    "il-grower": "#1565C0",
    "ne-grower": "#C62828",
}

GROWER_NAMES = {
    "ia-grower": "Iowa",
    "il-grower": "Illinois",
    "ne-grower": "Nebraska",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_boundary(grower_slug: str, farm_slug: str, data_root: Path) -> gpd.GeoDataFrame:
    path = data_root / "growers" / grower_slug / "farms" / farm_slug / "boundary" / "field_boundaries.geojson"
    return gpd.read_file(path)


def _load_cdl(grower_slug: str, farm_slug: str, data_root: Path) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    comp_files = list(tables_dir.glob("*cdl*_full_composition.csv"))
    if not comp_files:
        return None
    return pd.read_csv(comp_files[0])


def _load_weather(grower_slug: str, farm_slug: str, data_root: Path) -> pd.DataFrame | None:
    tables_dir = data_root / "growers" / grower_slug / "farms" / farm_slug / "derived" / "tables"
    weather_files = list(tables_dir.glob("*weather*.csv"))
    if not weather_files:
        return None
    df = pd.read_csv(weather_files[0], parse_dates=["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    return df


def _growing_season(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["month"] >= 4) & (df["month"] <= 10)].copy()


def _savefig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def _annotate_corr(ax, x, y, data: pd.DataFrame):
    """Add Pearson r + p-value text to an axis."""
    valid = data[[x, y]].dropna()
    if len(valid) < 3:
        return
    r, p = pearsonr(valid[x], valid[y])
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    ax.annotate(
        f"r={r:.3f}, p={p:.4f} {sig}",
        xy=(0.05, 0.95),
        xycoords="axes fraction",
        fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )


# ---------------------------------------------------------------------------
# Category A: Field Boundaries
# ---------------------------------------------------------------------------

def plot_field_area_distribution(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Box + violin plot of field areas per grower."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            gdf = _load_boundary(g, farm_dir.name, data_root)
            for _, row in gdf.iterrows():
                records.append({
                    "grower": GROWER_NAMES.get(g, g),
                    "field_id": row.get("field_id", "unknown"),
                    "area_acres": float(row.get("area_acres", 0)),
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No boundary data found.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Box plot
    for i, g in enumerate(df["grower"].unique()):
        subset = df[df["grower"] == g]
        color = [GROWER_COLORS.get(k, "#888888") for k, v in GROWER_NAMES.items() if v == g][0]
        sns.boxplot(data=subset, x="grower", y="area_acres", color=color, ax=axes[0], width=0.5)
    axes[0].set_title("Field Area Distribution by Grower", fontweight="bold")
    axes[0].set_ylabel("Area (acres)")
    axes[0].set_xlabel("")

    # Violin plot
    for i, g in enumerate(df["grower"].unique()):
        subset = df[df["grower"] == g]
        color = [GROWER_COLORS.get(k, "#888888") for k, v in GROWER_NAMES.items() if v == g][0]
        sns.violinplot(data=subset, x="grower", y="area_acres", color=color, ax=axes[1], inner="box", width=0.5)
    axes[1].set_title("Field Area Density by Grower", fontweight="bold")
    axes[1].set_ylabel("Area (acres)")
    axes[1].set_xlabel("")

    _savefig(out_dir / "01_field_area_distribution.png")


def plot_field_count_and_acreage(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Grouped bar chart: total fields + total acreage per grower."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            gdf = _load_boundary(g, farm_dir.name, data_root)
            records.append({
                "grower": GROWER_NAMES.get(g, g),
                "field_count": len(gdf),
                "total_acres": gdf["area_acres"].astype(float).sum(),
            })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No boundary data found.")
        return

    fig, ax1 = plt.subplots(figsize=(10, 6))
    x = np.arange(len(df))
    width = 0.35

    bars1 = ax1.bar(x - width / 2, df["field_count"], width, label="Field Count", color="#1565C0")
    ax1.set_ylabel("Number of Fields", color="#1565C0")
    ax1.tick_params(axis="y", labelcolor="#1565C0")

    ax2 = ax1.twinx()
    bars2 = ax2.bar(x + width / 2, df["total_acres"], width, label="Total Acres", color="#2E7D32")
    ax2.set_ylabel("Total Area (acres)", color="#2E7D32")
    ax2.tick_params(axis="y", labelcolor="#2E7D32")

    ax1.set_xticks(x)
    ax1.set_xticklabels(df["grower"])
    ax1.set_title("Field Count and Total Acreage by Grower", fontweight="bold")

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    _savefig(out_dir / "02_field_count_and_acreage.png")


def plot_area_vs_crop_type(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Scatter: field area vs. dominant crop type."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            gdf = _load_boundary(g, farm_dir.name, data_root)
            cdl = _load_cdl(g, farm_dir.name, data_root)
            if cdl is None:
                continue

            # Get dominant crop per field (latest year)
            latest_year = cdl["year"].max()
            latest = cdl[cdl["year"] == latest_year]
            dominant = latest.loc[latest.groupby("field_id")["pct"].idxmax()]

            for _, row in gdf.iterrows():
                fid = row["field_id"]
                crop = dominant[dominant["field_id"] == fid]["crop_name"].values
                crop = crop[0] if len(crop) > 0 else "Unknown"
                records.append({
                    "grower": GROWER_NAMES.get(g, g),
                    "field_id": fid,
                    "area_acres": float(row.get("area_acres", 0)),
                    "crop_type": crop,
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No boundary + CDL data found.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    for g in df["grower"].unique():
        subset = df[df["grower"] == g]
        color = [GROWER_COLORS.get(k, "#888888") for k, v in GROWER_NAMES.items() if v == g][0]
        ax.scatter(subset["crop_type"], subset["area_acres"], label=g, color=color, s=100, alpha=0.7)
    ax.set_title("Field Area vs. Dominant Crop Type", fontweight="bold")
    ax.set_ylabel("Area (acres)")
    ax.set_xlabel("Crop Type")
    ax.legend(title="Grower")
    plt.xticks(rotation=45)

    _savefig(out_dir / "03_area_vs_crop_type.png")


# ---------------------------------------------------------------------------
# Category B: CDL / Cropland Data Layer
# ---------------------------------------------------------------------------

def plot_crop_rotation_heatmap(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Heatmap: crop code per field × year."""
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            cdl = _load_cdl(g, farm_dir.name, data_root)
            if cdl is None:
                continue

            # Get dominant crop per field per year
            dominant = cdl.loc[cdl.groupby(["field_id", "year"])["pct"].idxmax()]
            pivot = dominant.pivot(index="field_id", columns="year", values="crop_name")

            if pivot.empty or pivot.isna().all().all():
                print(f"  Skipping heatmap for {g} — no CDL data.")
                continue

            fig, ax = plt.subplots(figsize=(10, 8))
            # Encode crop names as numbers for color mapping
            unique_crops = sorted(pivot.stack().dropna().unique())
            if not unique_crops:
                print(f"  Skipping heatmap for {g} — no crop types found.")
                continue
            crop_map = {c: i for i, c in enumerate(unique_crops)}
            numeric = pivot.map(lambda x: crop_map.get(x, -1))

            sns.heatmap(numeric, cmap="tab10", annot=pivot, fmt="", cbar=False, ax=ax, linewidths=0.5)
            ax.set_title(f"Crop Rotation Heatmap — {GROWER_NAMES.get(g, g)}", fontweight="bold")
            ax.set_ylabel("Field ID")
            ax.set_xlabel("Year")

            _savefig(out_dir / f"04_crop_rotation_heatmap_{g}.png")


def plot_crop_dominance_by_grower(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Stacked bar chart: acreage by crop per grower."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            cdl = _load_cdl(g, farm_dir.name, data_root)
            gdf = _load_boundary(g, farm_dir.name, data_root)
            if cdl is None:
                continue

            latest_year = cdl["year"].max()
            latest = cdl[cdl["year"] == latest_year]
            dominant = latest.loc[latest.groupby("field_id")["pct"].idxmax()]

            for _, row in dominant.iterrows():
                fid = row["field_id"]
                area = gdf[gdf["field_id"] == fid]["area_acres"].values
                area = float(area[0]) if len(area) > 0 else 0
                records.append({
                    "grower": GROWER_NAMES.get(g, g),
                    "crop_type": row["crop_name"],
                    "area_acres": area,
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No CDL data found.")
        return

    grouped = df.groupby(["grower", "crop_type"])["area_acres"].sum().reset_index()
    pivot = grouped.pivot(index="grower", columns="crop_type", values="area_acres").fillna(0)

    fig, ax = plt.subplots(figsize=(10, 6))
    pivot.plot(kind="bar", stacked=True, ax=ax, colormap="tab10")
    ax.set_title("Total Acreage by Crop Type and Grower", fontweight="bold")
    ax.set_ylabel("Area (acres)")
    ax.set_xlabel("")
    plt.xticks(rotation=0)
    ax.legend(title="Crop", bbox_to_anchor=(1.05, 1), loc="upper left")

    _savefig(out_dir / "05_crop_dominance_by_grower.png")


def plot_crop_consistency_vs_size(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Scatter: crop consistency score vs. field area."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            cdl = _load_cdl(g, farm_dir.name, data_root)
            gdf = _load_boundary(g, farm_dir.name, data_root)
            if cdl is None:
                continue

            for fid in cdl["field_id"].unique():
                field_cdl = cdl[cdl["field_id"] == fid]
                # Consistency = % of years with same dominant crop
                dominant_per_year = field_cdl.loc[field_cdl.groupby("year")["pct"].idxmax()]
                mode_crop = dominant_per_year["crop_name"].mode()
                if len(mode_crop) == 0:
                    continue
                consistency = (dominant_per_year["crop_name"] == mode_crop[0]).mean() * 100

                area = gdf[gdf["field_id"] == fid]["area_acres"].values
                area = float(area[0]) if len(area) > 0 else 0
                records.append({
                    "grower": GROWER_NAMES.get(g, g),
                    "field_id": fid,
                    "area_acres": area,
                    "consistency_pct": consistency,
                })

    df = pd.DataFrame(records)
    if df.empty:
        print("  No CDL data found.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    for g in df["grower"].unique():
        subset = df[df["grower"] == g]
        color = [GROWER_COLORS.get(k, "#888888") for k, v in GROWER_NAMES.items() if v == g][0]
        ax.scatter(subset["area_acres"], subset["consistency_pct"], label=g, color=color, s=100, alpha=0.7)
    ax.set_title("Crop Consistency vs. Field Area", fontweight="bold")
    ax.set_xlabel("Area (acres)")
    ax.set_ylabel("Consistency (% years with same dominant crop)")
    ax.legend(title="Grower")
    _annotate_corr(ax, "area_acres", "consistency_pct", df)

    _savefig(out_dir / "06_crop_consistency_vs_size.png")


# ---------------------------------------------------------------------------
# Category C: Weather
# ---------------------------------------------------------------------------

def plot_growing_season_temperature(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Line plot: monthly avg/min/max temp during growing season."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            weather = _load_weather(g, farm_dir.name, data_root)
            if weather is None:
                continue
            gs = _growing_season(weather)
            monthly = gs.groupby(["year", "month"]).agg({
                "T2M": "mean",
                "T2M_MAX": "mean",
                "T2M_MIN": "mean",
            }).reset_index()
            monthly["grower"] = GROWER_NAMES.get(g, g)
            records.append(monthly)

    if not records:
        print("  No weather data found.")
        return

    df = pd.concat(records, ignore_index=True)
    df["year_month"] = df["year"].astype(str) + "-" + df["month"].astype(str).str.zfill(2)

    fig, ax = plt.subplots(figsize=(12, 6))
    for g in df["grower"].unique():
        subset = df[df["grower"] == g]
        monthly_avg = subset.groupby("month")["T2M"].mean().reset_index()
        ax.plot(monthly_avg["month"], monthly_avg["T2M"], marker="o", label=g, linewidth=2)

    ax.set_title("Average Growing Season Temperature by Month", fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xticks(range(4, 11))
    ax.set_xticklabels(["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"])
    ax.legend(title="Grower")

    _savefig(out_dir / "07_growing_season_temperature.png")


def plot_cumulative_precipitation(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Line plot: cumulative precipitation during growing season per year."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            weather = _load_weather(g, farm_dir.name, data_root)
            if weather is None:
                continue
            gs = _growing_season(weather)
            # Aggregate to grower-level daily mean
            daily = gs.groupby(["year", "month", "date"])["PRECTOTCORR"].mean().reset_index()
            daily["grower"] = GROWER_NAMES.get(g, g)
            records.append(daily)

    if not records:
        print("  No weather data found.")
        return

    df = pd.concat(records, ignore_index=True)

    fig, ax = plt.subplots(figsize=(12, 6))
    for g in df["grower"].unique():
        subset = df[df["grower"] == g]
        yearly = []
        for year in sorted(subset["year"].unique()):
            year_data = subset[subset["year"] == year].sort_values("date")
            year_data["cum_precip"] = year_data["PRECTOTCORR"].cumsum()
            year_data["doy"] = (year_data["date"] - pd.Timestamp(f"{year}-04-01")).dt.days
            yearly.append(year_data)
        
        if yearly:
            combined = pd.concat(yearly)
            mean_cum = combined.groupby("doy")["cum_precip"].mean().reset_index()
            ax.plot(mean_cum["doy"], mean_cum["cum_precip"], label=g, linewidth=2)

    ax.set_title("Mean Cumulative Growing Season Precipitation", fontweight="bold")
    ax.set_xlabel("Days since April 1")
    ax.set_ylabel("Cumulative Precipitation (mm)")
    ax.legend(title="Grower")

    _savefig(out_dir / "08_cumulative_precipitation.png")


def plot_precip_vs_temperature(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Scatter: total growing season precip vs. avg growing season temp."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            weather = _load_weather(g, farm_dir.name, data_root)
            if weather is None:
                continue
            gs = _growing_season(weather)
            yearly = gs.groupby("year").agg({
                "PRECTOTCORR": "sum",
                "T2M": "mean",
            }).reset_index()
            yearly["grower"] = GROWER_NAMES.get(g, g)
            records.append(yearly)

    if not records:
        print("  No weather data found.")
        return

    df = pd.concat(records, ignore_index=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    for g in df["grower"].unique():
        subset = df[df["grower"] == g]
        color = [GROWER_COLORS.get(k, "#888888") for k, v in GROWER_NAMES.items() if v == g][0]
        ax.scatter(subset["T2M"], subset["PRECTOTCORR"], label=g, color=color, s=100, alpha=0.7)
    ax.set_title("Growing Season Precipitation vs. Temperature", fontweight="bold")
    ax.set_xlabel("Average Temperature (°C)")
    ax.set_ylabel("Total Precipitation (mm)")
    ax.legend(title="Grower")
    _annotate_corr(ax, "T2M", "PRECTOTCORR", df)

    _savefig(out_dir / "09_precip_vs_temperature.png")


# ---------------------------------------------------------------------------
# Summary CSV
# ---------------------------------------------------------------------------

def generate_summary_csv(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Generate a summary CSV of key statistics per grower."""
    records = []
    for g in growers:
        farms_dir = data_root / "growers" / g / "farms"
        for farm_dir in farms_dir.iterdir():
            if not farm_dir.is_dir():
                continue
            
            # Boundaries
            gdf = _load_boundary(g, farm_dir.name, data_root)
            field_count = len(gdf)
            total_acres = gdf["area_acres"].astype(float).sum() if not gdf.empty else 0
            
            # Weather
            weather = _load_weather(g, farm_dir.name, data_root)
            if weather is not None:
                gs = _growing_season(weather)
                avg_temp = gs["T2M"].mean()
                total_precip = gs["PRECTOTCORR"].sum()
            else:
                avg_temp = np.nan
                total_precip = np.nan

            records.append({
                "grower": GROWER_NAMES.get(g, g),
                "field_count": field_count,
                "total_acres": round(total_acres, 1),
                "avg_growing_temp_c": round(avg_temp, 2) if not np.isnan(avg_temp) else None,
                "total_growing_precip_mm": round(total_precip, 1) if not np.isnan(total_precip) else None,
            })

    df = pd.DataFrame(records)
    out_path = out_dir / "eda_summary.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")
    print(df.to_string(index=False))


# ---------------------------------------------------------------------------
# Category D: Geospatial Map
# ---------------------------------------------------------------------------

def plot_field_locations_map(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Geospatial map showing field polygon locations per grower on lat/lon axes."""
    n = len(growers)
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 6))

    if n == 1:
        axes = [axes]

    for idx, g in enumerate(growers):
        ax = axes[idx]
        farms_dir = data_root / "growers" / g / "farms"

        for farm_dir in sorted(farms_dir.iterdir()):
            if not farm_dir.is_dir():
                continue
            gdf = _load_boundary(g, farm_dir.name, data_root)
            if gdf.empty:
                continue

            name = GROWER_NAMES.get(g, g)
            color = GROWER_COLORS.get(name, "#888")
            gdf.plot(ax=ax, color=color, edgecolor="white", linewidth=1, alpha=0.6)

            # Annotate centroids with field IDs
            for _, row in gdf.iterrows():
                cent = row.geometry.centroid
                fid_short = str(row.get("field_id", ""))[-12:]
                ax.annotate(
                    fid_short,
                    xy=(cent.x, cent.y),
                    fontsize=5,
                    ha="center",
                    va="center",
                    color="white",
                    fontweight="bold",
                )

        ax.set_title(f"{name} — Field Locations", fontweight="bold")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, alpha=0.3)
        ax.set_aspect("auto")

    plt.tight_layout()
    _savefig(out_dir / "12_field_locations_map.png")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_all_analyses(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Run all 10 visualizations + summary CSV."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== Category A: Field Boundaries ===")
    plot_field_area_distribution(growers, data_root, out_dir)
    plot_field_count_and_acreage(growers, data_root, out_dir)
    plot_area_vs_crop_type(growers, data_root, out_dir)

    print("\n=== Category B: CDL / Cropland Data Layer ===")
    plot_crop_rotation_heatmap(growers, data_root, out_dir)
    plot_crop_dominance_by_grower(growers, data_root, out_dir)
    plot_crop_consistency_vs_size(growers, data_root, out_dir)

    print("\n=== Category C: Weather ===")
    plot_growing_season_temperature(growers, data_root, out_dir)
    plot_cumulative_precipitation(growers, data_root, out_dir)
    plot_precip_vs_temperature(growers, data_root, out_dir)

    print("\n=== Category D: Geospatial Map ===")
    plot_field_locations_map(growers, data_root, out_dir)

    print("\n=== Summary ===")
    generate_summary_csv(growers, data_root, out_dir)

    print(f"\n✓ All 10 visualizations + CSV written to: {out_dir}")


# ---------------------------------------------------------------------------
# Assignment 3 — Field Dashboard
# ---------------------------------------------------------------------------

_DOY_MONTH_STARTS: dict[int, int] | None = None


def _build_doy_month_starts() -> dict[int, int]:
    doy_map = {}
    for m in range(1, 13):
        _, ndays = calendar.monthrange(2023, m)
        for d in range(1, ndays + 1):
            doy = date(2023, m, d).timetuple().tm_yday
            doy_map.setdefault(m, doy)
    return doy_map


def _get_doy(year: int, month: int, day: int) -> int:
    return date(year, month, day).timetuple().tm_yday


def _month_doy(month: int) -> int:
    global _DOY_MONTH_STARTS
    if _DOY_MONTH_STARTS is None:
        _DOY_MONTH_STARTS = _build_doy_month_starts()
    return _DOY_MONTH_STARTS[month]


def _month_doy_end(month: int) -> int:
    """Return the last day-of-year for a given month (1–12)."""
    _, ndays = calendar.monthrange(2023, month)
    return _month_doy(month) + ndays - 1


def _load_field_boundary(grower_slug: str, farm_slug: str, field_id: str,
                         data_root: Path) -> tuple:
    """Load a single field's boundary GeoJSON.  Returns (gdf, props_dict)."""
    path = (data_root / "growers" / grower_slug / "farms" / farm_slug
            / "fields" / field_id / "boundary" / "field_boundary.geojson")
    gdf = gpd.read_file(path)
    if gdf.empty:
        return gdf, {}
    props = gdf.iloc[0].to_dict()
    return gdf, props


def _load_field_cdl(grower_slug: str, farm_slug: str, field_id: str,
                    year: int, data_root: Path) -> tuple[str | None, float]:
    """Return (dominant_crop, confidence_pct) for a single field-year."""
    tables = (data_root / "growers" / grower_slug / "farms" / farm_slug
              / "derived" / "tables")
    year_csv = tables / f"{grower_slug}_{farm_slug.replace('-', '_')}_{year}_cdl.csv"
    if year_csv.exists():
        cdl = pd.read_csv(year_csv)
        row = cdl[cdl["field_id"] == field_id]
        if row.empty:
            return None, 0
        best = row.loc[row["pct"].idxmax()]
        return best["crop_name"], float(best["pct"])

    comp_csv = list(tables.glob("*cdl*_full_composition.csv"))
    if not comp_csv:
        return None, 0
    cdl = pd.read_csv(comp_csv[0])
    row = cdl[(cdl["field_id"] == field_id) & (cdl["year"] == year)]
    if row.empty:
        return None, 0
    best = row.loc[row["pct"].idxmax()]
    return best["crop_name"], float(best["pct"])


def _load_field_weather(grower_slug: str, farm_slug: str, field_id: str,
                        year: int, data_root: Path) -> pd.DataFrame:
    """Load field-level daily_weather.csv, filter to year, add doy + gs flags."""
    wpath = (data_root / "growers" / grower_slug / "farms" / farm_slug
             / "fields" / field_id / "weather" / "daily_weather.csv")
    if not wpath.exists():
        return pd.DataFrame()
    df = pd.read_csv(wpath, parse_dates=["date"])
    df = df[df["date"].dt.year == year].copy()
    if df.empty:
        return df
    df["doy"] = df["date"].dt.dayofyear
    return df


def _load_field_ndvi_scenes(grower_slug: str, farm_slug: str, field_id: str,
                            year: int, data_root: Path, *,
                            mask_clouds: bool = True) -> pd.DataFrame:
    """Read per-scene NDVI TIFFs, compute masked mean, return DataFrame."""
    sentinel_root = (data_root / "growers" / grower_slug / "farms" / farm_slug
                     / "fields" / field_id / "satellite" / "sentinel"
                     / str(year))
    records = []
    if not sentinel_root.exists():
        print(f"  WARNING: No Sentinel NDVI for {field_id}/{year}")
        return pd.DataFrame()

    import os
    for scene_dir in sorted(sentinel_root.iterdir()):
        if not scene_dir.is_dir():
            continue
        ndvi_files = [f for f in os.listdir(scene_dir)
                      if f.endswith("_ndvi.tif")]
        if not ndvi_files:
            continue
        ndvi_path = scene_dir / ndvi_files[0]
        scl_path = ndvi_path.parent / ndvi_path.name.replace(
            "_ndvi.tif", "_scl.tif")

        try:
            with rasterio.open(ndvi_path) as ndvi_src:
                ndvi = ndvi_src.read(1).astype(np.float32)

                if mask_clouds and scl_path.exists():
                    with rasterio.open(scl_path) as scl_src:
                        scl = scl_src.read(
                            1,
                            out_shape=(ndvi_src.height, ndvi_src.width),
                            resampling=Resampling.nearest)
                    mask = ((ndvi >= -1) & (ndvi <= 1)
                            & ~np.isin(scl, [0, 1, 3, 8, 9, 11]))
                else:
                    if mask_clouds and not scl_path.exists():
                        print(f"  WARNING: SCL missing for {ndvi_path.name}, "
                              "using raw values")
                    mask = (ndvi >= -1) & (ndvi <= 1)

                if not mask.any():
                    continue
                mean_val = float(ndvi[mask].mean())
        except Exception as exc:
            print(f"  WARNING: Failed to read {ndvi_path.name}: {exc}")
            continue

        # parse date from dir name  sentinel_YYYYMMDD
        dirname = scene_dir.name
        try:
            ds = dirname.split("_")[1]
            d = date(year=int(ds[:4]), month=int(ds[4:6]), day=int(ds[6:8]))
        except Exception:
            continue

        records.append({"scene_date": d, "doy": d.timetuple().tm_yday,
                        "mean_ndvi": mean_val})

    return pd.DataFrame(records)


def _load_field_ndvi_composite(grower_slug: str, farm_slug: str,
                                field_id: str, year: int,
                                data_root: Path) -> float | None:
    """Return mean NDVI from the yearly composite TIFF."""
    tif = (data_root / "growers" / grower_slug / "farms" / farm_slug
           / "fields" / field_id / "derived" / "features"
           / f"ndvi_year_{year}_composite.tif")
    if not tif.exists():
        return None
    with rasterio.open(tif) as src:
        arr = src.read(1).astype(np.float32)
    mask = (arr >= -1) & (arr <= 1)
    return float(arr[mask].mean()) if mask.any() else None


def _compute_gdd(weather: pd.DataFrame, base: float = 10.0) -> np.ndarray:
    """Daily GDD = max(0, T2M - base)."""
    return np.maximum(0, weather["T2M"].values - base)


def _detect_weather_events(weather: pd.DataFrame, *,
                           heavy_rain: float = 20.0,
                           hot_day: float = 30.0,
                           cool_temp: float = 10.0) -> dict:
    """Return dict of event lists with doy, date, value."""
    gs = weather[(weather["doy"] >= _month_doy(4))
                 & (weather["doy"] <= _month_doy_end(10))]
    heavy = []
    for _, r in gs.iterrows():
        if r["PRECTOTCORR"] > heavy_rain:
            heavy.append({"doy": r["doy"], "date": r["date"],
                          "value": float(r["PRECTOTCORR"])})
    hot = []
    for _, r in gs.iterrows():
        if r["T2M_MAX"] > hot_day:
            hot.append({"doy": r["doy"], "date": r["date"],
                        "value": float(r["T2M_MAX"])})

    # cool periods: >=3 consecutive days with T2M < cool_temp
    cool_periods = []
    in_cool = False
    start_doy = None
    count = 0
    for _, r in gs.iterrows():
        if r["T2M"] < cool_temp:
            if not in_cool:
                start_doy = r["doy"]
                in_cool = True
                count = 1
            else:
                count += 1
        else:
            if in_cool and count >= 3:
                cool_periods.append({"start_doy": start_doy,
                                     "end_doy": r["doy"] - 1})
            in_cool = False
            count = 0
    if in_cool and count >= 3:
        cool_periods.append({"start_doy": start_doy,
                             "end_doy": gs.iloc[-1]["doy"]})

    return {"heavy_rain_days": heavy, "hot_days": hot,
            "cool_periods": cool_periods}


def _detect_ndvi_events(ndvi_df: pd.DataFrame, *,
                        rapid_thresh: float = 0.15,
                        dip_thresh: float = -0.10) -> dict:
    """Detect rapid green-up, stress dips, and peak NDVI."""
    if len(ndvi_df) < 2:
        return {"rapid_increases": [], "dips": [], "peak": None}

    sorted_df = ndvi_df.sort_values("doy").reset_index(drop=True)
    rapid = []
    dips = []
    for i in range(1, len(sorted_df)):
        prev = sorted_df.iloc[i - 1]
        cur = sorted_df.iloc[i]
        delta = cur["mean_ndvi"] - prev["mean_ndvi"]
        gap = cur["doy"] - prev["doy"]
        if delta >= rapid_thresh:
            rapid.append({"doy": cur["doy"], "delta": round(delta, 3),
                          "gap_days": gap,
                          "label": f"+{delta:.2f} in {gap}d"})
        elif delta <= dip_thresh:
            dips.append({"doy": cur["doy"], "delta": round(delta, 3),
                         "gap_days": gap,
                         "label": f"{delta:.2f} in {gap}d"})

    peak_idx = sorted_df["mean_ndvi"].idxmax()
    peak = {"doy": sorted_df.loc[peak_idx, "doy"],
            "value": float(sorted_df.loc[peak_idx, "mean_ndvi"]),
            "date": sorted_df.loc[peak_idx, "scene_date"]}

    return {"rapid_increases": rapid, "dips": dips, "peak": peak}


def _check_ndvi_coverage(ndvi_df: pd.DataFrame,
                          gs_start_doy: int, gs_end_doy: int) -> dict:
    """Check for large gaps in NDVI scene coverage."""
    if ndvi_df.empty:
        return {"scene_count": 0, "largest_gap_days": 0,
                "gaps": [], "coverage_note": "No data"}

    sorted_dates = sorted(ndvi_df["doy"].tolist())
    gaps = []
    for i in range(1, len(sorted_dates)):
        gap = sorted_dates[i] - sorted_dates[i - 1]
        if gap > 60:
            gaps.append((sorted_dates[i - 1], sorted_dates[i], gap))

    largest = max((g[2] for g in gaps), default=0)
    coverage = len(sorted_dates) / 4 * 25  # heuristic: 4 scenes = 100%
    note = "Adequate" if len(gaps) == 0 else f"Gap up to {largest}d"
    return {"scene_count": len(sorted_dates), "largest_gap_days": largest,
            "gaps": gaps, "coverage_note": note}


def _load_field_cdl_history(grower_slug: str, farm_slug: str, field_id: str,
                             data_root: Path) -> list[dict]:
    """Return full CDL rotation history for a field.

    Returns sorted list of {year, crop, pct} for all available years.
    """
    tables = (data_root / "growers" / grower_slug / "farms" / farm_slug
              / "derived" / "tables")
    comp_csv = list(tables.glob("*cdl*_full_composition.csv"))
    if not comp_csv:
        return []
    cdl = pd.read_csv(comp_csv[0])
    field_cdl = cdl[cdl["field_id"] == field_id]
    if field_cdl.empty:
        return []
    dominant = field_cdl.loc[field_cdl.groupby("year")["pct"].idxmax()]
    history = []
    for _, r in dominant.iterrows():
        history.append({"year": int(r["year"]),
                        "crop": r["crop_name"],
                        "pct": float(r["pct"])})
    history.sort(key=lambda x: x["year"])
    return history


def _thornthwaite_pet(monthly_temps: pd.Series, lat: float) -> pd.Series:
    """Compute monthly Thornthwaite Potential Evapotranspiration (mm).

    Parameters
    ----------
    monthly_temps : Series of mean monthly temperatures (degC), 12 values.
    lat : latitude in decimal degrees.

    Returns Series of monthly PET in mm, same length as input.
    """
    temps = monthly_temps.values.copy()
    temps[temps < 0] = 0
    I = np.sum((temps / 5) ** 1.514)
    if I < 0.1:
        return pd.Series(np.zeros_like(temps), index=monthly_temps.index)

    a = (6.75e-7 * I ** 3 - 7.71e-5 * I ** 2
         + 1.79e-2 * I + 0.492)

    # Day-length factor by latitude (northern hemisphere, monthly approximation)
    # Simple approximation: max daylight correction at summer solstice
    lat_rad = np.radians(lat)
    mon_doy_mid = [15, 45, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]
    day_hrs = []
    for doy in mon_doy_mid:
        decl = np.radians(23.44 * np.sin(np.radians((doy - 81) * 360 / 365)))
        cos_ha = -np.tan(lat_rad) * np.tan(decl)
        cos_ha = np.clip(cos_ha, -1, 1)
        ha = np.arccos(cos_ha)
        day_hrs.append(ha * 24 / np.pi)
    day_hrs = np.array(day_hrs)

    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    pet = np.zeros(12)
    for m in range(12):
        if temps[m] <= 0:
            pet[m] = 0
        else:
            pet_unadj = 16 * (10 * temps[m] / I) ** a
            pet[m] = pet_unadj * (day_hrs[m] / 12) * (days_in_month[m] / 30)

    return pd.Series(pet, index=monthly_temps.index)


def _compute_p_pet(weather: pd.DataFrame, year: int,
                   lat: float) -> pd.DataFrame | None:
    """Compute monthly P-PET moisture deficit z-scores.

    Uses Thornthwaite PET. Returns DataFrame with month, p_pet_z values
    for the target year, or None if insufficient data.
    """
    if weather.empty or "PRECTOTCORR" not in weather.columns:
        return None

    monthly = weather.copy()
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month

    # Monthly aggregates
    monthly_agg = (
        monthly.groupby(["year", "month"]).agg(
            precip=("PRECTOTCORR", "sum"),
            temp=("T2M", "mean"),
        )
        .reset_index()
        .sort_values(["year", "month"])
    )

    all_years = sorted(monthly_agg["year"].unique())
    if len(all_years) < 3:
        return None

    # PET for each year-month
    pet_records = []
    for yr in all_years:
        yr_data = monthly_agg[monthly_agg["year"] == yr].sort_values("month")
        temps = yr_data.set_index("month")["temp"]
        # Fill missing months with 0
        all_months = pd.Series(0.0, index=range(1, 13))
        for m in temps.index:
            all_months[m] = temps[m]
        pet_vals = _thornthwaite_pet(all_months, lat)
        for m in range(1, 13):
            pet_records.append({"year": yr, "month": m, "pet": pet_vals[m]})

    pet_df = pd.DataFrame(pet_records)
    merged = monthly_agg.merge(pet_df, on=["year", "month"])
    merged["p_minus_pet"] = merged["precip"] - merged["pet"]

    # Compute z-score per calendar month across reference years
    ppet_records = []
    for m in range(1, 13):
        ref = merged[
            (merged["month"] == m) & (merged["year"] != year)
        ]["p_minus_pet"].dropna()
        target = merged[
            (merged["year"] == year) & (merged["month"] == m)
        ]["p_minus_pet"]

        if len(ref) < 2 or len(target) == 0:
            continue

        ref_mean = ref.mean()
        ref_std = ref.std()
        if ref_std < 0.01:
            z = 0.0
        else:
            z = float((target.values[0] - ref_mean) / ref_std)

        ppet_records.append({"month": m, "p_pet_z": round(z, 3),
                             "p_minus_pet_mm": round(float(target.values[0]), 1)})

    if not ppet_records:
        return None

    ppet_df = pd.DataFrame(ppet_records)
    ppet_df["month_name"] = ppet_df["month"].apply(
        lambda m: ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1])
    return ppet_df


def _compute_spi(weather: pd.DataFrame, year: int,
                 timescale: int = 3) -> pd.DataFrame | None:
    """Compute 3-month Standardized Precipitation Index.

    Uses gamma distribution fit per calendar month from the available
    multi-year record.  Returns None if insufficient data.
    """
    if weather.empty or "PRECTOTCORR" not in weather.columns:
        return None

    # Monthly precipitation totals
    monthly = weather.copy()
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.month
    monthly_precip = (
        monthly.groupby(["year", "month"])["PRECTOTCORR"].sum()
        .reset_index()
        .sort_values(["year", "month"])
    )

    all_years = sorted(monthly_precip["year"].unique())
    if len(all_years) < 3:
        return None

    # Rolling 3-month sum across consecutive months
    if timescale > 1:
        monthly_precip["roll_sum"] = (
            monthly_precip["PRECTOTCORR"]
            .rolling(window=timescale, min_periods=timescale)
            .sum()
        )
        precip_col = "roll_sum"
    else:
        precip_col = "PRECTOTCORR"

    # Fit gamma per calendar month, compute SPI for target year
    # The 3-month sum ending in month M represents the precipitation
    # aggregated over M-2, M-1, M (or M, M-1 for 2-month, etc.)
    spi_records = []
    for m in range(1, 13):
        # Reference: all years except target
        ref = monthly_precip[
            (monthly_precip["month"] == m)
            & (monthly_precip["year"] != year)
        ][precip_col].dropna()
        target = monthly_precip[
            (monthly_precip["year"] == year)
            & (monthly_precip["month"] == m)
        ][precip_col]

        if len(ref) < 2 or len(target) == 0:
            continue

        ref_vals = ref.values
        target_val = target.values[0]

        if ref_vals.std() < 0.01:
            spi = (target_val - ref_vals.mean()) / max(ref_vals.std(), 0.001)
        else:
            try:
                params = gamma.fit(ref_vals, floc=0)
                cdf = gamma.cdf(target_val, *params)
                cdf = np.clip(cdf, 1e-6, 1 - 1e-6)
                spi = float(norm.ppf(cdf))
            except Exception:
                continue

        spi_records.append({"month": m, f"spi_{timescale}": round(spi, 3)})

    if not spi_records:
        return None

    spi_df = pd.DataFrame(spi_records)
    spi_df["month_name"] = spi_df["month"].apply(
        lambda m: ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1])
    return spi_df


def _plot_spi_panel(ax, spi_df: pd.DataFrame, ppet_df: pd.DataFrame | None,
                    year: int,
                    gs_start_doy: int, gs_end_doy: int,
                    month_doys: dict) -> None:
    """Bar chart of 3-month SPI with P-PET moisture deficit overlay."""
    gs = spi_df[spi_df["month"].between(4, 10)]
    if gs.empty:
        ax.set_title("5. Moisture Balance (no data)")
        ax.axis("off")
        return

    doys = [month_doys[m] for m in gs["month"]]
    vals = gs["spi_3"].values

    colors = []
    for v in vals:
        if v > 1.0:
            colors.append("#1565C0")
        elif v < -1.0:
            colors.append("#E65100")
        else:
            colors.append("#9E9E9E")

    bars = ax.bar(doys, vals, width=20, color=colors, alpha=0.7, edgecolor="none",
                  label="SPI-3")

    # Overlay P-PET z-score line
    if ppet_df is not None:
        ppet_gs = ppet_df[ppet_df["month"].between(4, 10)]
        if not ppet_gs.empty:
            ppet_doys = [month_doys[m] for m in ppet_gs["month"]]
            ax.plot(ppet_doys, ppet_gs["p_pet_z"].values, "-D",
                    color="#1B5E20", linewidth=1.5, markersize=5, alpha=0.7,
                    label="P-PET z-score")

    ax.axhline(y=0, color="black", linewidth=0.8)
    ax.axhline(y=1.0, color="blue", linestyle=":", alpha=0.3, linewidth=0.8)
    ax.axhline(y=-1.0, color="orange", linestyle=":", alpha=0.3, linewidth=0.8)

    ax.set_ylabel("Index value")
    ax.set_title("5. Moisture Balance — SPI-3 + P-PET "
                 f"(baseline {year - 4}–{year - 1})", fontweight="bold")
    ax.set_xticks(list(month_doys.values()))
    ax.set_xticklabels(["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"])
    ax.set_xlim(gs_start_doy - 5, gs_end_doy + 5)
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, alpha=0.2)

    ax.text(0.98, 0.02,
            "Based on 5-yr field record, not 30-yr climate norm",
            transform=ax.transAxes, fontsize=7, ha="right", va="bottom",
            fontstyle="italic", color="gray")


def plot_field_dashboard(
    grower_slug: str,
    farm_slug: str,
    field_id: str,
    year: int,
    data_root: Path,
    out_dir: Path,
    *,
    gs_start_month: int = 4,
    gs_end_month: int = 10,
    gdd_base: float = 10.0,
    heavy_rain_thresh: float = 20.0,
    hot_day_thresh: float = 30.0,
    cool_temp_thresh: float = 10.0,
    ndvi_rapid_thresh: float = 0.15,
    ndvi_dip_thresh: float = -0.10,
    mask_clouds: bool = True,
    show_spi: bool = True,
) -> dict:
    """4- or 5-panel aligned field dashboard.

    Panels (shared DOY axis, growing-season window):
      1. NDVI Time Series
      2. Daily Precipitation
      3. Temperature & Extremes
      4. Cumulative GDD
      5. SPI Drought Index (if show_spi=True)

    Returns a dict of all computed values.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Field Dashboard: {field_id}  |  {year}")
    print(f"{'='*60}")

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    gdf, props = _load_field_boundary(grower_slug, farm_slug, field_id,
                                      data_root)
    area_acres = props.get("area_acres", 0)
    county = props.get("county_name", "Unknown")
    state_fips = props.get("state_fips", "")
    # Centroid lat for Thornthwaite PET
    if not gdf.empty and gdf.iloc[0].geometry is not None:
        field_lat = float(gdf.iloc[0].geometry.centroid.y)
    else:
        field_lat = 42.0
    print(f"  Field lat: {field_lat:.4f}")

    crop_name, cdl_pct = _load_field_cdl(grower_slug, farm_slug, field_id,
                                         year, data_root)
    if crop_name:
        print(f"  CDL: {crop_name} ({cdl_pct:.0f}%)")
    else:
        print(f"  WARNING: No CDL data for {field_id}/{year}")

    weather = _load_field_weather(grower_slug, farm_slug, field_id, year,
                                  data_root)
    if weather.empty:
        print("  ERROR: No weather data.")
        return {"error": "No weather data"}
    print(f"  Weather: {len(weather)} daily records")

    ndvi_df = _load_field_ndvi_scenes(grower_slug, farm_slug, field_id, year,
                                      data_root, mask_clouds=mask_clouds)
    if ndvi_df.empty:
        print("  WARNING: No NDVI scenes; NDVI panel will be empty.")
    else:
        print(f"  NDVI scenes: {len(ndvi_df)}")

    comp_mean = _load_field_ndvi_composite(grower_slug, farm_slug, field_id,
                                           year, data_root)
    if comp_mean is not None:
        print(f"  Composite mean NDVI: {comp_mean:.4f}")

    # ------------------------------------------------------------------
    # 2. Compute metrics
    # ------------------------------------------------------------------
    weather["gdd"] = _compute_gdd(weather, gdd_base)
    gs_doy_start = _month_doy(gs_start_month)
    gs_doy_end = _month_doy_end(gs_end_month)
    gs = weather[(weather["doy"] >= gs_doy_start)
                 & (weather["doy"] <= gs_doy_end)].copy()
    cum_gdd = gs["gdd"].cumsum()
    gdd_total = float(cum_gdd.iloc[-1]) if len(cum_gdd) > 0 else 0
    gs_temp_avg = float(gs["T2M"].mean()) if len(gs) > 0 else None
    gs_precip = float(gs["PRECTOTCORR"].sum()) if len(gs) > 0 else None

    weather_events = _detect_weather_events(
        weather, heavy_rain=heavy_rain_thresh, hot_day=hot_day_thresh,
        cool_temp=cool_temp_thresh)
    ndvi_events = _detect_ndvi_events(
        ndvi_df, rapid_thresh=ndvi_rapid_thresh, dip_thresh=ndvi_dip_thresh)
    coverage = _check_ndvi_coverage(ndvi_df, gs_doy_start, gs_doy_end)

    peak_ndvi = ndvi_events["peak"]["value"] if ndvi_events["peak"] else None
    peak_date = ndvi_events["peak"]["date"] if ndvi_events["peak"] else None

    print(f"  Growing season T2M avg: {gs_temp_avg:.1f}°C")
    print(f"  Growing season precip: {gs_precip:.0f} mm")
    print(f"  GDD total (base {gdd_base}°C): {gdd_total:.0f}")
    print(f"  Peak NDVI: {peak_ndvi}")

    # SPI + P-PET computation (needs full multi-year weather)
    spi_df = None
    ppet_df = None
    if show_spi:
        wpath = (data_root / "growers" / grower_slug / "farms" / farm_slug
                 / "fields" / field_id / "weather" / "daily_weather.csv")
        if wpath.exists():
            full_weather = pd.read_csv(wpath, parse_dates=["date"])
            spi_df = _compute_spi(full_weather, year, timescale=3)
            if spi_df is not None:
                print(f"  SPI-3 computed: {len(spi_df)} months")
                gs_spi = spi_df[spi_df["month"].between(
                    gs_start_month, gs_end_month)]
                for _, r in gs_spi.iterrows():
                    print(f"    {r['month_name']}: SPI-3 = {r['spi_3']:.2f}")
            ppet_df = _compute_p_pet(full_weather, year, field_lat)
            if ppet_df is not None:
                print(f"  P-PET z-score computed: {len(ppet_df)} months")
                gs_pp = ppet_df[ppet_df["month"].between(
                    gs_start_month, gs_end_month)]
                for _, r in gs_pp.iterrows():
                    print(f"    {r['month_name']}: P-PET z = {r['p_pet_z']:.2f}")

    # ------------------------------------------------------------------
    # 3. Build figure
    # ------------------------------------------------------------------
    n_panels = 5 if show_spi and spi_df is not None else 4
    fig_height = 19 if n_panels == 5 else 16
    fig, axes = plt.subplots(n_panels, 1, figsize=(14, fig_height),
                             sharex=True,
                             gridspec_kw={"hspace": 0.35})
    ax_ndvi = axes[0]
    ax_precip = axes[1]
    ax_temp = axes[2]
    ax_gdd = axes[3]
    ax_spi = axes[4] if n_panels == 5 else None

    month_map = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul",
                 8: "Aug", 9: "Sep", 10: "Oct"}
    month_doys = {m: _month_doy(m) for m in range(gs_start_month,
                                                   gs_end_month + 1)}

    # ---- Panel 1: NDVI ----
    ax_ndvi.axvspan(gs_doy_start, gs_doy_end, color="lightgreen", alpha=0.08,
                    label="Growing season")

    # Growing stage bands
    if crop_name == "Soybeans":
        stages = [
            (155, 185, "#2E7D32", "VEG"),
            (186, 200, "#FDD835", "FLW"),
            (201, 245, "#FB8C00", "POD"),
            (246, 275, "#6D4C41", "MAT"),
        ]
        for start, end, color, label in stages:
            ax_ndvi.axvspan(start, end, color=color, alpha=0.06)
            ax_ndvi.text((start + end) / 2, 0.97, label,
                         transform=ax_ndvi.get_xaxis_transform(),
                         fontsize=7, ha="center", va="top", color=color,
                         fontweight="bold")
    # Could add Corn stage bands here for corn years

    if not ndvi_df.empty:
        sdf = ndvi_df.sort_values("doy")
        ax_ndvi.plot(sdf["doy"], sdf["mean_ndvi"], "-o", color="forestgreen",
                     linewidth=2, markersize=7, zorder=5,
                     label=f"{crop_name or '?'} {year} (observed)")

        if comp_mean is not None:
            ax_ndvi.axhline(y=comp_mean, color="gray", linestyle="--",
                            alpha=0.7, linewidth=1,
                            label=f"Composite mean = {comp_mean:.2f}")

        # Peak NDVI
        if ndvi_events["peak"]:
            pk = ndvi_events["peak"]
            ax_ndvi.annotate(
                f"★ {pk['value']:.2f}",
                xy=(pk["doy"], pk["value"]),
                fontsize=11, color="gold", fontweight="bold",
                ha="center", va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="black",
                          alpha=0.7))

        # Rapid increases — text centered above point, no arrow
        for ev in ndvi_events["rapid_increases"]:
            ndvi_val = ndvi_df[ndvi_df["doy"] == ev["doy"]][
                "mean_ndvi"].values[0]
            ax_ndvi.annotate(
                f"↑ {ev['label']}",
                xy=(ev["doy"], ndvi_val),
                xytext=(ev["doy"], ndvi_val + 0.07),
                fontsize=8, color="darkgreen", fontweight="bold",
                ha="center", va="bottom")

        # Dips — text centered above point, no arrow
        for ev in ndvi_events["dips"]:
            ndvi_val = ndvi_df[ndvi_df["doy"] == ev["doy"]][
                "mean_ndvi"].values[0]
            ax_ndvi.annotate(
                f"↓ {ev['label']}",
                xy=(ev["doy"], ndvi_val),
                xytext=(ev["doy"], ndvi_val + 0.07),
                fontsize=8, color="red", fontweight="bold",
                ha="center", va="bottom")

    ax_ndvi.set_ylim(-0.05, 1.0)
    ax_ndvi.set_ylabel("Mean NDVI")
    ax_ndvi.set_title(f"1. NDVI Time Series — {crop_name or 'Unknown'} "
                      f"({year})", fontweight="bold")
    ax_ndvi.legend(fontsize=7, loc="upper left")
    ax_ndvi.grid(True, alpha=0.3)

    # Strategy reference box
    ndvi_ref = ("N. Corn Belt RM 95-105 | Upper Midwest MG 1.5-3.0\n"
                "Planting window: Apr 25-May 20")
    ax_ndvi.text(0.98, 0.98, ndvi_ref, transform=ax_ndvi.transAxes,
                 fontsize=7, ha="right", va="top",
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                           alpha=0.85, edgecolor="#ccc"))

    # ---- Panel 2: Daily Precipitation ----
    gs_precip_df = weather[(weather["doy"] >= gs_doy_start)
                            & (weather["doy"] <= gs_doy_end)].copy()
    colors_precip = ["crimson" if v > heavy_rain_thresh else "steelblue"
                     for v in gs_precip_df["PRECTOTCORR"]]
    ax_precip.bar(gs_precip_df["doy"], gs_precip_df["PRECTOTCORR"],
                  width=0.8, color=colors_precip, alpha=0.7, edgecolor="none")

    ax_precip.margins(y=0.3)

    ax_precip.axhline(y=heavy_rain_thresh, color="red", linestyle=":",
                      alpha=0.5, linewidth=0.8,
                      label=f"Heavy rain threshold ({heavy_rain_thresh} mm)")

    ax_precip.set_ylabel("Precipitation (mm)")
    ax_precip.set_title("2. Daily Precipitation", fontweight="bold")
    ax_precip.legend(fontsize=7, loc="upper left")
    ax_precip.grid(True, alpha=0.3)

    # In-panel commentary
    n_heavy = len(weather_events["heavy_rain_days"])
    precip_notes = [f"Total: {gs_precip:.0f} mm | {n_heavy} days >{heavy_rain_thresh:.0f} mm"]
    precip_notes.append("NASA POWER daily prec: model-derived, treat with caution")
    ax_precip.text(0.98, 0.90, "\n".join(precip_notes),
                   transform=ax_precip.transAxes, fontsize=7,
                   ha="right", va="top",
                   bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                             alpha=0.85, edgecolor="#ccc"))

    # ---- Panel 3: Temperature & Extremes ----
    gs_temp_df = gs_precip_df  # same GS filter
    ax_temp.fill_between(gs_temp_df["doy"],
                         gs_temp_df["T2M_MIN"], gs_temp_df["T2M_MAX"],
                         color="orange", alpha=0.15,
                         label="T2M min-max range")
    ax_temp.plot(gs_temp_df["doy"], gs_temp_df["T2M"], color="black",
                 linewidth=1.5, label="T2M avg")
    ax_temp.plot(gs_temp_df["doy"], gs_temp_df["T2M_MAX"], color="tomato",
                 linewidth=0.8, alpha=0.6, label="T2M_MAX")
    ax_temp.plot(gs_temp_df["doy"], gs_temp_df["T2M_MIN"], color="royalblue",
                 linewidth=0.8, alpha=0.6, label="T2M_MIN")

    # Hot day markers
    if weather_events["hot_days"]:
        hot_doys = [e["doy"] for e in weather_events["hot_days"]]
        hot_vals = [e["value"] for e in weather_events["hot_days"]]
        ax_temp.scatter(hot_doys, hot_vals, color="darkorange", s=25,
                        zorder=5, label=f"Hot days > {hot_day_thresh} degC")

    # Cool period bands
    for cp in weather_events["cool_periods"]:
        ax_temp.axvspan(cp["start_doy"], cp["end_doy"], color="royalblue",
                        alpha=0.1)

    ax_temp.set_ylabel("Temperature (degC)")
    ax_temp.set_title("3. Temperature - Daily Avg & Extremes",
                      fontweight="bold")
    ax_temp.legend(fontsize=7, loc="upper left", ncol=1)
    ax_temp.grid(True, alpha=0.3)

    # In-panel commentary
    n_hot = len(weather_events["hot_days"])
    temp_notes = [f"Avg {gs_temp_avg:.1f} degC | {n_hot} hot days >{hot_day_thresh:.0f} degC"]
    temp_notes.append("Heat stress risk at R3-R5 pod fill")
    ax_temp.text(0.98, 0.95, "\n".join(temp_notes),
                 transform=ax_temp.transAxes, fontsize=7,
                 ha="right", va="top",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                           alpha=0.85, edgecolor="#ccc"))

    # ---- Panel 4: Cumulative GDD ----
    ax_gdd.plot(gs["doy"], cum_gdd, color="darkgreen", linewidth=2.5,
                label=f"GDD {year} {crop_name or ''} (base {gdd_base:.0f} degC)")
    ax_gdd.axhline(y=0, color="gray", linestyle="-", linewidth=0.5)
    ax_gdd.set_ylabel(f"GDD (base {gdd_base:.0f} degC)")
    ax_gdd.set_title(f"4. Cumulative GDD (Base {gdd_base:.0f} degC)",
                     fontweight="bold")

    ax_gdd.legend(fontsize=8, loc="upper left")
    ax_gdd.grid(True, alpha=0.3)

    # Annotate total GDD
    if len(cum_gdd) > 0:
        last_doy = gs["doy"].iloc[-1]
        ax_gdd.annotate(
            f"Total GDD = {gdd_total:.0f}",
            xy=(last_doy, gdd_total),
            fontsize=10, fontweight="bold", color="darkgreen",
            ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="darkgreen", alpha=0.8))

    # In-panel commentary
    gdd_notes = [f"Total: {gdd_total:.0f} GDD (base {gdd_base:.0f} degC)"]
    gdd_notes.append("GDD within Corn Belt range; scout V6-R3 for tar spot")
    ax_gdd.text(0.50, 0.45, "\n".join(gdd_notes),
                transform=ax_gdd.transAxes, fontsize=7,
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          alpha=0.85, edgecolor="#ccc"))

    # ---- Panel 5: SPI + P-PET ----
    if show_spi and spi_df is not None and ax_spi is not None:
        _plot_spi_panel(ax_spi, spi_df, ppet_df, year,
                        gs_doy_start, gs_doy_end, month_doys)

    # ---- Shared X-axis (plot panels only) ----
    ax_gdd.set_xlabel("Date (growing season)")
    ax_gdd.set_xticks(list(month_doys.values()))
    ax_gdd.set_xticklabels([month_map[m] for m in month_doys])

    plot_panels = [ax_ndvi, ax_precip, ax_temp, ax_gdd]
    if show_spi and spi_df is not None and ax_spi is not None:
        plot_panels.append(ax_spi)
    for ax in plot_panels:
        ax.set_xlim(gs_doy_start - 5, gs_doy_end + 5)
        for doy in month_doys.values():
            ax.axvline(x=doy, color="gray", linestyle=":", alpha=0.15)

    # ---- Dashboard title ----
    state_name = {"19": "Iowa", "17": "Illinois", "31": "Nebraska"}.get(
        str(state_fips), state_fips)
    title = (f"Field Dashboard  —  {field_id}  |  {year}  "
             f"|  {crop_name or '?'} ({cdl_pct:.0f}%)  "
             f"|  {county}, {state_name}  |  {area_acres:.0f} ac")
    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01,
                 ha="center")

    # ---- Bottom stats bar ----
    caption_lines = []
    if ndvi_events["peak"]:
        caption_lines.append(
            f"Peak NDVI {peak_ndvi:.2f} ({peak_date.strftime('%b %d')})")
    caption_lines.append(f"GDD {gdd_total:.0f} | Precip {gs_precip:.0f} mm | "
                         f"T2M {gs_temp_avg:.1f} degC")
    if n_hot > 0:
        caption_lines.append(f"{n_hot} hot days >{hot_day_thresh:.0f} degC")
    if n_heavy > 0:
        caption_lines.append(f"{n_heavy} heavy rain days")
    if spi_df is not None and show_spi:
        caption_lines.append("SPI-3 included")

    caption_text = "  |  ".join(caption_lines)
    fig.text(0.5, -0.01, caption_text, fontsize=7.5, ha="center", va="top",
             wrap=True,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="#f0f8ff",
                       edgecolor="gray", alpha=0.85))

    # ---- Save ----
    slug = field_id.replace("-", "_").replace(".", "_")
    out_path = out_dir / f"01_field_dashboard_{slug}_{year}.png"
    top_val = 0.96 if n_panels == 5 else 0.94
    bottom_val = 0.05 if n_panels == 5 else 0.06
    fig.subplots_adjust(top=top_val, bottom=bottom_val)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  Saved: {out_path}")

    # ---- Return summary ----
    spi_data = spi_df.to_dict("records") if spi_df is not None else None
    return {
        "field_id": field_id,
        "year": year,
        "crop": crop_name,
        "cdl_pct": cdl_pct,
        "county": county,
        "area_acres": area_acres,
        "scene_count": len(ndvi_df),
        "composite_mean_ndvi": comp_mean,
        "peak_ndvi": peak_ndvi,
        "peak_ndvi_date": peak_date,
        "gdd_total": gdd_total,
        "growing_temp_avg": gs_temp_avg,
        "growing_precip_total": gs_precip,
        "heavy_rain_days": weather_events["heavy_rain_days"],
        "hot_days": weather_events["hot_days"],
        "cool_periods": weather_events["cool_periods"],
        "ndvi_rapid_increases": ndvi_events["rapid_increases"],
        "ndvi_dips": ndvi_events["dips"],
        "coverage": coverage,
        "spi_3": spi_data,
    }
