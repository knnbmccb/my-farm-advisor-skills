#!/usr/bin/env python3
"""Field-level EDA comparison module for agricultural data.

Compares field boundaries, CDL/cropland data, and weather across growers.
Produces static matplotlib/seaborn visualizations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import pearsonr

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
# Orchestrator
# ---------------------------------------------------------------------------

def run_all_analyses(growers: list[str], data_root: Path, out_dir: Path) -> None:
    """Run all 9 visualizations + summary CSV."""
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

    print("\n=== Summary ===")
    generate_summary_csv(growers, data_root, out_dir)

    print(f"\n✓ All outputs written to: {out_dir}")
