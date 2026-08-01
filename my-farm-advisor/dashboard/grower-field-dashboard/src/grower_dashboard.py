"""Grower Field Dashboard — reusable decision-support skill for My Farm Advisor.

Generates a self-contained HTML dashboard with KPI cards, interactive
choropleth map, and multi-panel static visualizations for any grower
in the data pipeline.

Usage:
    from grower_dashboard import generate_grower_dashboard
    path = generate_grower_dashboard("ia-grower")
"""

from __future__ import annotations

import datetime
import json
import os
import textwrap
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import rasterio

try:
    from shapely.geometry import Point, shape
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# Suppress numpy deprecation warnings from rasterio internals
warnings.filterwarnings("ignore", category=DeprecationWarning, message="Setting the shape on a NumPy array")
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CROP_COLORS: dict[str, str] = {
    "Corn": "#DAA520",
    "Soybeans": "#2E8B57",
    "Grass/Pasture": "#8FBC8F",
    "Alfalfa": "#CD853F",
    "Forest": "#228B22",
    "Other": "#AAAAAA",
}

DRAIN_COLORS: dict[str, str] = {
    "Poorly drained": "#4A90D9",
    "Moderately well drained": "#E8833A",
}

ROTATION_PALETTE: dict[str, str] = {
    "rotating": "#2E8B57",
    "continuous": "#DAA520",
    "grass_pasture": "#8FBC8F",
}

GROWER_NAMES: dict[str, str] = {
    "ia-grower": "Iowa",
    "il-grower": "Illinois",
    "ne-grower": "Nebraska",
}

# Satellite basemap style (ArcGIS World Imagery via custom Mapbox style)
SATELLITE_STYLE: dict[str, Any] = {
    "version": 8,
    "sources": {
        "satellite": {
            "type": "raster",
            "tiles": [
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ],
            "tileSize": 256,
        }
    },
    "layers": [
        {"id": "satellite-layer", "type": "raster", "source": "satellite"}
    ],
}

FALLBACK_MAPBOX_STYLE = "open-street-map"
DEFAULT_YEAR = "2025"

# Medium-opacity RdYlGn colorscale for choropleth NDVI backdrop
NDVI_BACKDROP_CS: list[list[Any]] = [
    [0.0, "rgba(165,0,38,0.50)"],
    [0.1, "rgba(215,48,39,0.50)"],
    [0.2, "rgba(244,109,67,0.50)"],
    [0.3, "rgba(253,174,97,0.50)"],
    [0.4, "rgba(254,224,139,0.50)"],
    [0.5, "rgba(255,255,191,0.50)"],
    [0.6, "rgba(217,239,139,0.50)"],
    [0.7, "rgba(166,217,106,0.50)"],
    [0.8, "rgba(102,189,99,0.50)"],
    [0.9, "rgba(26,152,80,0.50)"],
    [1.0, "rgba(0,104,55,0.50)"],
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_centroid(coords: list) -> tuple[float, float]:
    """Compute centroid of a polygon coordinate list."""
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _bbox_of_polygon(coords: list) -> tuple[float, float, float, float]:
    """Return (min_lon, min_lat, max_lon, max_lat)."""
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return min(xs), min(ys), max(xs), max(ys)


def _prettify_field_id(fid: str) -> str:
    """Shorten field IDs for display."""
    return fid.replace("osm-", "").replace("ia-new-", "").replace("_", "-")


# ---------------------------------------------------------------------------
# Generator class
# ---------------------------------------------------------------------------

class GrowerDashboardGenerator:
    """Loads grower data, computes KPIs, and generates an HTML dashboard."""

    def __init__(
        self,
        grower_slug: str = "ia-grower",
        data_root: str = "/home/coder/my-farm-advisor-runtime/data-pipeline",
    ):
        self.grower_slug = grower_slug
        self.data_root = Path(data_root)
        self.grower_path = self.data_root / "growers" / grower_slug
        self.display_name = GROWER_NAMES.get(grower_slug, grower_slug)

        # Populated by _discover_and_load()
        self.farms: list[dict] = []
        self.fields: list[dict] = []
        self.weather_df: Optional[pd.DataFrame] = None
        self.soil_df: Optional[pd.DataFrame] = None
        self.ndvi_data: list[dict] = []
        self.rotation_df: Optional[pd.DataFrame] = None
        self.combined_geojson: Optional[dict] = None

        # KPIs
        self.kpis: dict[str, Any] = {}

    # ---- Discovery -------------------------------------------------------

    def _discover_and_load(self) -> None:
        """Discover all farms and fields, load all datasets."""
        farms_dir = self.grower_path / "farms"
        if not farms_dir.is_dir():
            raise FileNotFoundError(
                f"No farms directory for grower '{self.grower_slug}' at {farms_dir}"
            )

        farm_slugs = sorted(
            d.name for d in farms_dir.iterdir() if d.is_dir()
        )
        if not farm_slugs:
            raise FileNotFoundError(f"No farms found under {farms_dir}")

        all_fields = []
        all_weather = []
        all_soil = []
        all_ndvi = []
        combined_features = []
        farm_name = farm_slugs[0]

        for fs in farm_slugs:
            fields_dir = farms_dir / fs / "fields"
            if not fields_dir.is_dir():
                continue
            for fd in sorted(fields_dir.iterdir()):
                if not fd.is_dir():
                    continue
                info = self._load_single_field(fd, fs)
                if info is not None:
                    all_fields.append(info)
                    combined_features.extend(info["geojson_features"])
                    if info["weather_df"] is not None:
                        all_weather.append(info["weather_df"])
                    if info["soil_row"] is not None:
                        all_soil.append(info["soil_row"])
                    all_ndvi.extend(info["ndvi_records"])

        self.farms = [{"slug": fs, "display": fs.replace("-", " ").title()}
                      for fs in farm_slugs]
        self.fields = all_fields

        # Combined GeoJSON for the map
        self.combined_geojson = {
            "type": "FeatureCollection",
            "features": combined_features,
        }

        # Weather
        if all_weather:
            self.weather_df = pd.concat(all_weather, ignore_index=True)

        # Soil
        if all_soil:
            self.soil_df = pd.DataFrame(all_soil)

        # NDVI
        self.ndvi_data = all_ndvi

        # Rotation
        self.rotation_df = self._load_rotation(farms_dir / farm_slugs[0])

        # Farm-level CDL composition
        self.cdl_df = self._load_cdl(farms_dir / farm_slugs[0])

    def _load_single_field(self, field_dir: Path, farm_slug: str
                           ) -> Optional[dict]:
        """Load boundary, weather, soil, NDVI for one field."""
        field_slug = field_dir.name

        # Boundary
        gj_path = field_dir / "boundary" / "field_boundary.geojson"
        if not gj_path.exists():
            return None
        with open(gj_path) as f:
            gj = json.load(f)
        if not gj.get("features"):
            return None
        feature = gj["features"][0]
        props = feature.get("properties", {})
        field_id = props.get("field_id", field_slug)
        area_acres = props.get("area_acres", 0)
        county = props.get("county_name", "")

        coords = feature["geometry"]["coordinates"][0]
        centroid = _compute_centroid(coords)
        bbox = _bbox_of_polygon(coords)

        # Weather
        weather_path = field_dir / "weather" / "daily_weather.csv"
        weather_df = None
        if weather_path.exists():
            try:
                weather_df = pd.read_csv(weather_path)
            except Exception:
                pass

        # Soil summary
        soil_path = field_dir / "soil" / "ssurgo_summary.csv"
        soil_row = None
        if soil_path.exists():
            try:
                sdf = pd.read_csv(soil_path)
                if len(sdf) > 0:
                    soil_row = sdf.iloc[0].to_dict()
                    soil_row["field_id"] = field_id
            except Exception:
                pass

        # NDVI from yearly composite TIFFs
        ndvi_records = []
        features_dir = field_dir / "derived" / "features"
        if features_dir.is_dir():
            for yr in range(2021, 2026):
                tif = features_dir / f"ndvi_year_{yr}_composite.tif"
                if tif.exists():
                    try:
                        with rasterio.open(tif) as src:
                            data = src.read(1).copy()
                            mask = ~np.isnan(data)
                            if mask.any():
                                mean_val = float(np.mean(data[mask]))
                                ndvi_records.append({
                                    "field_id": field_id,
                                    "field_slug": field_slug,
                                    "year": yr,
                                    "mean_ndvi": mean_val,
                                })
                    except Exception:
                        pass

        # Crop rotation from field.json or ndvi_yearly_summary
        field_json_path = field_dir / "field.json"
        crop_history = []
        if field_json_path.exists():
            try:
                with open(field_json_path) as f:
                    fj = json.load(f)
            except Exception:
                fj = {}

        # Also try ndvi_yearly_summary for crop info
        nys_path = field_dir / "derived" / "summaries" / "ndvi_yearly_summary.json"
        if nys_path.exists():
            try:
                with open(nys_path) as f:
                    nys = json.load(f)
                for ye in nys.get("years", []):
                    crop_history.append({
                        "year": ye["year"],
                        "crop": ye["crop_name"],
                        "scene_count": ye.get("scene_count", 0),
                    })
            except Exception:
                pass

        return {
            "field_id": field_id,
            "field_slug": field_slug,
            "farm_slug": farm_slug,
            "area_acres": area_acres,
            "county": county,
            "centroid": centroid,
            "bbox": bbox,
            "crop_history": crop_history,
            "geojson_features": gj["features"],
            "weather_df": weather_df,
            "soil_row": soil_row,
            "ndvi_records": ndvi_records,
        }

    def _load_rotation(self, farm_path: Path) -> Optional[pd.DataFrame]:
        """Load the crop rotation CSV."""
        path = farm_path / "derived" / "tables" / "ia_grower_iowa_crop_rotation.csv"
        # Try dynamic naming
        farm_slug = farm_path.name
        alt_path = farm_path / "derived" / "tables" / f"{farm_slug}_crop_rotation.csv"
        for p in [path, alt_path]:
            if p.exists():
                try:
                    return pd.read_csv(p)
                except Exception:
                    pass
        return None

    def _load_cdl(self, farm_path: Path) -> Optional[pd.DataFrame]:
        """Load combined CDL composition."""
        path = farm_path / "derived" / "tables"
        if not path.is_dir():
            return None
        for f in path.iterdir():
            if "cdl" in f.name and "full_composition" in f.name and f.suffix == ".csv":
                try:
                    return pd.read_csv(f)
                except Exception:
                    pass
        return None

    # ---- KPI Computation -----------------------------------------------

    def _compute_kpis(self) -> None:
        fields = self.fields
        ndvi = self.ndvi_data
        weather = self.weather_df
        soil = self.soil_df
        rotation = self.rotation_df

        total_fields = len(fields)
        total_acres = sum(f.get("area_acres", 0) for f in fields)

        # NDVI
        ndvi_vals = [r["mean_ndvi"] for r in ndvi if r.get("mean_ndvi") is not None]
        avg_ndvi = float(np.mean(ndvi_vals)) if ndvi_vals else None

        # Weather
        avg_rainfall = None
        avg_gdd = None
        avg_temp = None
        if weather is not None and not weather.empty:
            try:
                weather["date"] = pd.to_datetime(weather["date"])
                weather["year"] = weather["date"].dt.year
                weather["month"] = weather["date"].dt.month
                gs = weather[(weather["month"] >= 4) & (weather["month"] <= 10)]
                avg_rainfall = (
                    weather.groupby(["field_id", "year"])["PRECTOTCORR"]
                    .sum().mean()
                )
                gs_local = gs.copy()
                gs_local["gdd"] = np.maximum(0, gs_local["T2M"] - 10)
                avg_gdd = gs_local.groupby(["field_id", "year"])["gdd"].sum().mean()
                avg_temp = gs["T2M"].mean()
            except Exception:
                pass

        # Soil
        avg_om = None
        avg_cec = None
        avg_aws = None
        avg_ph = None
        if soil is not None and not soil.empty:
            cols = soil.columns
            if "avg_om_pct" in cols:
                avg_om = float(soil["avg_om_pct"].mean())
            if "avg_cec" in cols:
                avg_cec = float(soil["avg_cec"].mean())
            if "total_aws_inches" in cols:
                avg_aws = float(soil["total_aws_inches"].mean())
            if "avg_ph" in cols:
                avg_ph = float(soil["avg_ph"].mean())

        # Crop rotation
        rotating = 0
        continuous = 0
        if rotation is not None and not rotation.empty:
            if "crop_diversity" in rotation.columns:
                rotating = int((rotation["crop_diversity"] > 1).sum())
                continuous = int((rotation["crop_diversity"] == 1).sum())

        # Soil Health Score (0-10)
        shs_list = []
        if soil is not None and not soil.empty:
            for _, r in soil.iterrows():
                om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                drain = r.get("drainage_class", "")
                dr_s = 1.5 if "Moderately well" in str(drain) else 0.5
                ph = r.get("avg_ph", 7.0)
                ph_s = 1.0 if 6.0 <= ph <= 7.5 else 0.5
                shs_list.append(om_s + cec_s + aws_s + dr_s + ph_s)
        avg_shs = float(np.mean(shs_list)) if shs_list else None

        # Sustainability Index (0-10)
        sust_list = []
        if soil is not None and rotation is not None and not soil.empty:
            merged = soil.merge(
                rotation, on="field_id", how="left"
            )
            for _, r in merged.iterrows():
                rot_s = 3.0 if r.get("crop_diversity", 1) > 1 else 0.0
                # Compute SHS for this row
                om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                dr = r.get("drainage_class", "")
                dr_s = 1.5 if "Moderately well" in str(dr) else 0.5
                ph = r.get("avg_ph", 7.0)
                ph_s = 1.0 if 6.0 <= ph <= 7.5 else 0.5
                row_shs = om_s + cec_s + aws_s + dr_s + ph_s
                shs_norm = row_shs / 10.0 * 3.0
                er_s = 1.0  # all fields moderate
                dr_sust = 2.0 if "Moderately well" in str(dr) else 1.0
                sust_list.append(rot_s + shs_norm + er_s + dr_sust)
        avg_sust = float(np.mean(sust_list)) if sust_list else None

        # Rotation rate
        total_rot = rotating + continuous
        rotation_rate = (rotating / total_rot * 100) if total_rot > 0 else 0

        # Crop breakdown by acreage
        crop_acres: dict[str, float] = {}
        if rotation is not None and not rotation.empty:
            for _, r in rotation.iterrows():
                fid = r["field_id"]
                acres = next((f.get("area_acres", 0) for f in fields if f["field_id"] == fid), 0)
                # Use most recent crop from crop_history
                recent_crop = "Unknown"
                for f in fields:
                    if f["field_id"] == fid:
                        hist = f.get("crop_history", [])
                        if hist:
                            recent_crop = hist[-1].get("crop", "Unknown")
                        break
                crop_acres[recent_crop] = crop_acres.get(recent_crop, 0) + acres
        total_crop_acres = sum(crop_acres.values())
        crop_breakdown = {
            c: round(a / total_crop_acres * 100, 1) if total_crop_acres else 0
            for c, a in crop_acres.items()
        }

        # Season span: average days with T2M >= 10°C per field-year
        avg_season_span = None
        if weather is not None and not weather.empty:
            try:
                w = weather.copy()
                w["date"] = pd.to_datetime(w["date"])
                w["year"] = w["date"].dt.year
                w["warm"] = w["T2M"] >= 10
                season_days = w.groupby(["field_id", "year"])["warm"].sum()
                avg_season_span = round(float(season_days.mean()), 0) if not season_days.empty else None
            except Exception:
                pass

        # Most important variables
        top_vars = [
            ("Crop Rotation", "Determines NDVI trajectory, sustains soil OM, breaks pest cycles"),
            ("Available Water Storage", "Strongest predictor of drought resilience"),
            ("Organic Matter", "Nutrient cycling, soil structure, water retention"),
            ("Growing Season Precipitation", "Primary yield driver in rainfed systems"),
            ("Drainage Class", "Planting window timing, field trafficability"),
        ]

        self.kpis = {
            "total_fields": total_fields,
            "total_acres": round(total_acres, 1),
            "avg_ndvi": round(avg_ndvi, 3) if avg_ndvi else None,
            "avg_rainfall_mm": round(avg_rainfall, 0) if avg_rainfall else None,
            "avg_gdd": round(avg_gdd, 0) if avg_gdd else None,
            "avg_temp_c": round(avg_temp, 1) if avg_temp else None,
            "avg_om": round(avg_om, 2) if avg_om else None,
            "avg_cec": round(avg_cec, 1) if avg_cec else None,
            "avg_aws": round(avg_aws, 1) if avg_aws else None,
            "avg_ph": round(avg_ph, 2) if avg_ph else None,
            "avg_shs": round(avg_shs, 1) if avg_shs else None,
            "avg_sust": round(avg_sust, 1) if avg_sust else None,
            "rotating": rotating,
            "continuous": continuous,
            "rotation_rate": round(rotation_rate, 0),
            "crop_breakdown": crop_breakdown,
            "avg_season_span": int(avg_season_span) if avg_season_span else None,
            "top_vars": top_vars,
        }

    # ---- Narrative generation -----------------------------------------

    def _generate_narrative(self) -> dict[str, str]:
        k = self.kpis
        fields = self.fields
        ndvi = self.ndvi_data

        areas = [f.get("area_acres", 0) for f in fields]
        min_ac = min(areas) if areas else 0
        max_ac = max(areas) if areas else 0

        # Find field with highest/lowest NDVI
        field_ndvi_mean = {}
        for r in ndvi:
            fid = r["field_id"]
            v = r.get("mean_ndvi")
            if v is not None:
                field_ndvi_mean.setdefault(fid, []).append(v)
        field_ndvi_avg = {
            fid: np.mean(vals) for fid, vals in field_ndvi_mean.items()
        }
        best_field = max(field_ndvi_avg, key=field_ndvi_avg.get) if field_ndvi_avg else ""
        worst_field = min(field_ndvi_avg, key=field_ndvi_avg.get) if field_ndvi_avg else ""

        # Find driest/wettest year from weather
        dry_year = ""
        wet_year = ""
        if self.weather_df is not None:
            w = self.weather_df.copy()
            w["year"] = pd.to_datetime(w["date"]).dt.year
            yr_precip = w.groupby("year")["PRECTOTCORR"].sum()
            if not yr_precip.empty:
                dry_year = str(int(yr_precip.idxmin()))
                wet_year = str(int(yr_precip.idxmax()))

        # Continuous corn fields
        cont_fields = []
        if self.rotation_df is not None:
            for _, r in self.rotation_df.iterrows():
                if r.get("crop_diversity", 1) == 1:
                    cont_fields.append(r["field_id"])

        # Low SHS fields
        low_shs_fields = []
        if self.soil_df is not None:
            for _, r in self.soil_df.iterrows():
                om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                dr = r.get("drainage_class", "")
                dr_s = 1.5 if "Moderately well" in str(dr) else 0.5
                ph = r.get("avg_ph", 7.0)
                ph_s = 1.0 if 6.0 <= ph <= 7.5 else 0.5
                shs = om_s + cec_s + aws_s + dr_s + ph_s
                if shs < 7.0:
                    low_shs_fields.append(
                        (r["field_id"], round(shs, 1))
                    )

        field_ndvi_items = sorted(
            field_ndvi_avg.items(), key=lambda x: x[1], reverse=True
        )
        best_field = field_ndvi_items[0][0] if field_ndvi_items else ""
        worst_field = field_ndvi_items[-1][0] if field_ndvi_items else ""
        best_ndvi = field_ndvi_avg.get(best_field, 0)
        worst_ndvi = field_ndvi_avg.get(worst_field, 0)

        section1 = (
            f"Mean NDVI across all fields is {k['avg_ndvi']}. "
            f"Field {_prettify_field_id(best_field)} leads at {best_ndvi:.3f}, "
            f"while {_prettify_field_id(worst_field)} trails at {worst_ndvi:.3f}."
        )

        section2 = (
            f"Field {_prettify_field_id(best_field)} leads with mean NDVI of "
            f"{best_ndvi:.3f}, while {_prettify_field_id(worst_field)} "
            f"trails at {worst_ndvi:.3f}. "
            f"Crop type explains part of this gap — soybeans average "
            f"higher NDVI than corn — but the key finding is the "
            f"correlation between NDVI and soil organic matter (r = "
            f"see chart), which ties crop health directly to soil "
            f"variability."
        )

        cont_str = ", ".join(
            _prettify_field_id(f) for f in cont_fields[:3]
        ) if cont_fields else "none"
        low_shs_str = ", ".join(
            f"{_prettify_field_id(f)} ({s})" for f, s in low_shs_fields[:3]
        ) if low_shs_fields else "none"
        section3 = (
            f"Mean Soil Health Score is {k['avg_shs']}/10. "
            f"{low_shs_str} score below 7.0, "
            f"indicating opportunities for improvement through cover "
            f"cropping or organic amendment. Continuous monoculture "
            f"fields ({cont_str}) show the highest soil risk, "
            f"reinforcing that crop health and soil health are tightly linked."
        )

        recs = []
        if low_shs_fields:
            low_ids = [_prettify_field_id(f) for f, _ in low_shs_fields[:2]]
            recs.append(
                f"Introduce cover crops on fields {', '.join(low_ids)} "
                f"to rebuild organic matter and improve water storage."
            )
        if cont_fields:
            cont_short = [_prettify_field_id(f) for f in cont_fields[:2]]
            recs.append(
                f"Break continuous cropping on fields "
                f"{', '.join(cont_short)} with a rotational year to "
                f"restore soil biology and reduce pest pressure."
            )
        if k['avg_aws'] and k['avg_aws'] < 4.0:
            recs.append(
                "Prioritize drought-tolerant hybrid selection on fields "
                "with below-average Available Water Storage (<4 inches)."
            )
        recs.append(
            "Continue monitoring NDVI trends annually to detect field-level "
            "stress before visible symptoms appear."
        )
        section4 = "\n".join(
            f"{i+1}. {r}" for i, r in enumerate(recs[:4])
        )

        return {
            "section1": section1,
            "section2": section2,
            "section3": section3,
            "section4": section4,
        }

    # ---- Scene-based monthly NDVI (raw satellite pixels) -------------

    def _discover_scenes(self, field_id: str, farm_slug: str, year: int) -> list[dict]:
        """Find all satellite NDVI scenes for a field in a given year with QA paths."""
        scenes: list[dict] = []
        base = self.grower_path / "farms" / farm_slug / "fields" / field_id / "satellite"
        for source in ("landsat", "sentinel"):
            src_dir = base / source / str(year)
            if not src_dir.exists():
                continue
            for scene_dir in sorted(src_dir.iterdir()):
                if not scene_dir.is_dir():
                    continue
                parts = scene_dir.name.split("_")
                if len(parts) < 2:
                    continue
                date_str = parts[-1]
                if len(date_str) != 8 or not date_str.isdigit():
                    continue
                try:
                    scene_date = datetime.datetime.strptime(date_str, "%Y%m%d").date()
                except ValueError:
                    continue
                ndvi_files = list(scene_dir.glob("*_ndvi.tif"))
                if not ndvi_files:
                    continue
                qa_path: Optional[str] = None
                if source == "landsat":
                    qa_files = list(scene_dir.glob("*_qa_pixel.tif"))
                    qa_epsg = [f for f in qa_files if "epsg4326" in f.name]
                    qa_path = str(qa_epsg[0]) if qa_epsg else (str(qa_files[0]) if qa_files else None)
                else:
                    qa_files = list(scene_dir.glob("*_scl.tif"))
                    qa_epsg = [f for f in qa_files if "epsg4326" in f.name]
                    qa_path = str(qa_epsg[0]) if qa_epsg else (str(qa_files[0]) if qa_files else None)
                scenes.append({
                    "date": scene_date,
                    "source": source,
                    "ndvi_path": str(ndvi_files[0]),
                    "qa_path": qa_path,
                })
        return sorted(scenes, key=lambda s: s["date"])

    def _select_best_scene(self, scenes: list[dict], target_date: datetime.date) -> Optional[dict]:
        """Select best scene within ±15 days, preferring Sentinel."""
        if not scenes:
            return None
        sentinel_window = [s for s in scenes if s["source"] == "sentinel" and abs((s["date"] - target_date).days) <= 15]
        if sentinel_window:
            return min(sentinel_window, key=lambda s: abs((s["date"] - target_date).days))
        landsat_window = [s for s in scenes if s["source"] == "landsat" and abs((s["date"] - target_date).days) <= 15]
        if landsat_window:
            return min(landsat_window, key=lambda s: abs((s["date"] - target_date).days))
        return min(scenes, key=lambda s: abs((s["date"] - target_date).days))

    def _qa_filter_pixels(self, ndvi_path: str, qa_path: Optional[str], source: str,
                          boundary_geojson: Optional[dict]) -> list[tuple[float, float, float]]:
        """Extract QA-filtered NDVI pixels, return [(lon, lat, raw_ndvi), ...]."""
        try:
            with rasterio.open(ndvi_path) as src:
                ndvi_arr = src.read(1)
                transform = src.transform
        except Exception:
            return []
        qa_mask: Optional[np.ndarray] = None
        if qa_path and os.path.exists(qa_path):
            try:
                with rasterio.open(qa_path) as qa_src:
                    qa_arr = qa_src.read(1)
                    if qa_arr.shape == ndvi_arr.shape:
                        if source == "landsat":
                            qa_mask = ((qa_arr & 0x38) == 0)
                        else:
                            qa_mask = (qa_arr == 4)
            except Exception:
                pass
        h, w = ndvi_arr.shape
        pts: list[tuple[float, float, float]] = []
        for i in range(h):
            for j in range(w):
                if not np.isfinite(ndvi_arr[i, j]):
                    continue
                if qa_mask is not None and not qa_mask[i, j]:
                    continue
                lon, lat = rasterio.transform.xy(transform, i, j)
                pts.append((round(lon, 6), round(lat, 6), round(float(ndvi_arr[i, j]), 3)))
        if HAS_SHAPELY and boundary_geojson is not None:
            try:
                poly = shape(boundary_geojson["features"][0]["geometry"])
                pts = [(lo, la, v) for lo, la, v in pts if poly.contains(Point(lo, la))]
            except Exception:
                pass
        return pts

    def _build_monthly_pixel_ndvi(self) -> dict[str, Any]:
        """Build monthly pixel NDVI data from actual satellite scenes."""
        result: dict[str, Any] = {}
        for yr in range(2021, 2026):
            result[str(yr)] = {}
            for mo in range(4, 11):
                target = datetime.date(yr, mo, 15)
                month_data: dict[str, dict] = {}
                for f in self.fields:
                    fid = f["field_id"]
                    scenes = self._discover_scenes(fid, f["farm_slug"], yr)
                    if not scenes:
                        continue
                    best = self._select_best_scene(scenes, target)
                    if best is None:
                        continue
                    boundary_path = (
                        self.grower_path / "farms" / f["farm_slug"] / "fields" / fid / "boundary" / "field_boundary.geojson"
                    )
                    boundary_gj = None
                    if boundary_path.exists():
                        with open(boundary_path) as bf:
                            boundary_gj = json.load(bf)
                    pts = self._qa_filter_pixels(best["ndvi_path"], best["qa_path"], best["source"], boundary_gj)
                    if not pts:
                        continue
                    # Cap pixel count to keep HTML size reasonable (~300 max per field)
                    MAX_PIXELS = 300
                    if len(pts) > MAX_PIXELS:
                        step = max(1, len(pts) // MAX_PIXELS)
                        pts = pts[::step][:MAX_PIXELS]
                    lons, lats, raw_vals = zip(*pts)
                    raw_list = list(raw_vals)
                    fmin = min(raw_list)
                    fmax = max(raw_list)
                    frange = fmax - fmin if fmax > fmin else 1.0
                    norm_vals = [round((v - fmin) / frange, 4) for v in raw_list]
                    month_data[fid] = {
                        "lon": list(lons),
                        "lat": list(lats),
                        "raw": raw_list,
                        "norm": norm_vals,
                        "mean": round(float(np.mean(raw_list)), 4),
                        "min": round(fmin, 4),
                        "max": round(fmax, 4),
                        "scene_date": best["date"].isoformat(),
                        "source": best["source"],
                    }
                if month_data:
                    result[str(yr)][str(mo)] = month_data
        return result

    # ---- Embedded data for JS filters ----------------------------------

    def _build_embedded_data(self) -> dict:
        """Build a JSON-serializable dict of all data for JS-side filtering."""
        data: dict[str, Any] = {
            "fields": [],
            "years": [2021, 2022, 2023, 2024, 2025],
            "ndvi": {},
            "weather": {},
            "soil": {},
            "rotation": {},
            "kpis": {},
        }

        # Per-field info
        for f in self.fields:
            fid = f["field_id"]
            soil_score = None
            if self.soil_df is not None:
                sr = self.soil_df[self.soil_df["field_id"] == fid]
                if not sr.empty:
                    r = sr.iloc[0]
                    om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                    cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                    aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                    dr_s = 1.5 if "Moderately well" in str(r.get("drainage_class", "")) else 0.5
                    ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7.0) <= 7.5 else 0.5
                    soil_score = round(om_s + cec_s + aws_s + dr_s + ph_s, 1)
            data["fields"].append({
                "id": fid,
                "slug": f["field_slug"],
                "acres": f.get("area_acres", 0),
                "label": _prettify_field_id(fid),
                "centroid": list(f["centroid"]),
                "bbox": list(f["bbox"]),
                "soil_score": soil_score,
            })

        # NDVI per field per year
        for r in self.ndvi_data:
            fid = r["field_id"]
            yr = r["year"]
            v = r.get("mean_ndvi")
            if v is not None:
                data["ndvi"].setdefault(fid, {})[str(yr)] = round(v, 4)

        # Weather: per-field per-year growing-season aggregate + monthly breakdown
        if self.weather_df is not None:
            w = self.weather_df.copy()
            w["date"] = pd.to_datetime(w["date"])
            w["year"] = w["date"].dt.year
            w["month"] = w["date"].dt.month
            gs = w[(w["month"] >= 4) & (w["month"] <= 10)].copy()
            gs["gdd"] = np.maximum(0, gs["T2M"] - 10)
            for (fid, yr), grp in gs.groupby(["field_id", "year"]):
                data["weather"].setdefault(fid, {})[str(yr)] = {
                    "rain": round(grp["PRECTOTCORR"].sum(), 1),
                    "gdd": round(grp["gdd"].sum(), 0),
                    "temp": round(grp["T2M"].mean(), 1),
                }
            # Monthly aggregates (Apr–Oct) per field per year
            data["monthly"] = {}
            for (fid, yr, mo), grp in gs.groupby(["field_id", "year", "month"]):
                data["monthly"].setdefault(fid, {}).setdefault(str(yr), {})[str(mo)] = {
                    "rain": round(grp["PRECTOTCORR"].sum(), 1),
                    "gdd": round(grp["gdd"].sum(), 0),
                    "temp": round(grp["T2M"].mean(), 1),
                    "season_days": int((grp["T2M"] >= 10).sum()),
                }

        # Soil per field
        if self.soil_df is not None:
            for _, r in self.soil_df.iterrows():
                fid = r["field_id"]
                om = r.get("avg_om_pct", 0)
                cec = r.get("avg_cec", 0)
                aws = r.get("total_aws_inches", 0)
                ph = r.get("avg_ph", 7.0)
                drain = r.get("drainage_class", "")
                dom_soil = r.get("dominant_soil", "")
                om_s = min(om / 5.0, 1.0) * 2.5
                cec_s = min(cec / 25.0, 1.0) * 2.5
                aws_s = min(aws / 6.0, 1.0) * 2.5
                dr_s = 1.5 if "Moderately well" in str(drain) else 0.5
                ph_s = 1.0 if 6.0 <= ph <= 7.5 else 0.5
                shs = round(om_s + cec_s + aws_s + dr_s + ph_s, 2)
                data["soil"][fid] = {
                    "om": om, "cec": cec, "aws": aws, "ph": ph,
                    "shs": shs, "drainage": drain, "dominant_soil": dom_soil,
                }

        # Rotation per field
        if self.rotation_df is not None:
            for _, r in self.rotation_df.iterrows():
                fid = r["field_id"]
                data["rotation"][fid] = {
                    "diversity": int(r.get("crop_diversity", 1)),
                    "pattern": r.get("rotation_patterns", ""),
                    "sequence": r.get("rotation_sequence", ""),
                }

        # Pre-compute KPIs for year-by-year combinations (no "all" year)
        data["kpis"] = {}
        for yr in [2021, 2022, 2023, 2024, 2025]:
            data["kpis"][f"{yr}_all"] = self._kpi_for_filter(str(yr), "all")
            for f in self.fields:
                data["kpis"][f"{yr}_{f['field_id']}"] = self._kpi_for_filter(
                    str(yr), f["field_id"]
                )

        # Pre-compute narrative data points for year-by-year combinations
        data["narratives"] = {}
        for yr in [2021, 2022, 2023, 2024, 2025]:
            data["narratives"][f"{yr}_all"] = self._narrative_for_filter(str(yr), "all")
            for f in self.fields:
                data["narratives"][f"{yr}_{f['field_id']}"] = self._narrative_for_filter(
                    str(yr), f["field_id"]
                )

        # Map: per-year NDVI values in field iteration order
        data["map_ndvi"] = {}
        for yr in range(2021, 2026):
            yr_vals = []
            for f in self.fields:
                vals = [r["mean_ndvi"] for r in self.ndvi_data
                        if r["field_id"] == f["field_id"] and r["year"] == yr
                        and r.get("mean_ndvi") is not None]
                yr_vals.append(round(float(np.mean(vals)), 3) if vals else None)
            data["map_ndvi"][str(yr)] = yr_vals

        # Map center and field bounding boxes for zoom
        data["map_center"] = {
            "lat": float(np.mean([f["centroid"][1] for f in self.fields])) if self.fields else 43.27,
            "lon": float(np.mean([f["centroid"][0] for f in self.fields])) if self.fields else -94.24,
        }
        data["map_fields"] = [
            {"id": f["field_id"], "bbox": list(f["bbox"])}
            for f in self.fields
        ]

        # Pixel-level NDVI for all years (canonical grid from DEFAULT_YEAR, mean-pooled 2x2)
        data["map_px"] = self._build_pixel_ndvi()

        # Monthly pixel-level NDVI from actual satellite scenes (QA-filtered)
        data["map_px_monthly"] = self._build_monthly_pixel_ndvi()

        # Monthly NDVI metadata for KPIs (lightweight: mean + source per field)
        data["monthly_ndvi"] = {}
        for yr_str, yr_data in data["map_px_monthly"].items():
            data["monthly_ndvi"][yr_str] = {}
            for mo_str, mo_data in yr_data.items():
                meta: dict[str, dict] = {}
                for fid, entry in mo_data.items():
                    meta[fid] = {
                        "mean": entry["mean"],
                        "scene_date": entry["scene_date"],
                        "source": entry["source"],
                        "min": entry["min"],
                        "max": entry["max"],
                    }
                data["monthly_ndvi"][yr_str][mo_str] = meta

        return data

    def _build_pixel_ndvi(self) -> dict[str, Any]:
        """Build downsampled pixel NDVI grid for all years, shared lon/lat."""
        result: dict[str, Any] = {"lon": [], "lat": [], "field": [], "vals": {}}
        for yr in [2021, 2022, 2023, 2024, 2025]:
            result["vals"][str(yr)] = []

        for f in self.fields:
            fid = f["field_id"]
            base_path = self.grower_path / "farms" / f["farm_slug"] / "fields" / fid / "derived" / "features"
            canonical_tif = base_path / f"ndvi_year_{DEFAULT_YEAR}_composite.tif"
            if not canonical_tif.exists():
                continue
            with rasterio.open(canonical_tif) as src:
                arr = src.read(1).copy()
                transform = src.transform
                h, w = arr.shape
                h2, w2 = h // 2, w // 2
                if h2 == 0 or w2 == 0:
                    continue
                block = arr[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2)
                with np.errstate(invalid='ignore', divide='ignore'):
                    block_mean = np.nanmean(block, axis=(1, 3))
                mask = ~np.isnan(block_mean)
                pts: list[tuple[float, float, float]] = []
                for i in range(h2):
                    for j in range(w2):
                        if mask[i, j]:
                            lon, lat = rasterio.transform.xy(transform, 2 * i + 0.5, 2 * j + 0.5)
                            pts.append((round(lon, 6), round(lat, 6), round(float(block_mean[i, j]), 3)))
                # Clip to field boundary polygon so pixels stay inside the field
                if HAS_SHAPELY:
                    boundary_path = (
                        self.grower_path / "farms" / f["farm_slug"] / "fields" / fid / "boundary" / "field_boundary.geojson"
                    )
                    if boundary_path.exists():
                        with open(boundary_path) as bf:
                            boundary_gj = json.load(bf)
                        poly = shape(boundary_gj["features"][0]["geometry"])
                        pts = [(lo, la, v) for lo, la, v in pts if poly.contains(Point(lo, la))]

                if not pts:
                    continue
                lons, lats, vals_2025 = zip(*pts)
                n_pts = len(pts)
                result["lon"].extend(lons)
                result["lat"].extend(lats)
                result["field"].extend([fid] * n_pts)
                result["vals"][DEFAULT_YEAR].extend(vals_2025)
                coords = list(zip(lons, lats))
                for yr in [2021, 2022, 2023, 2024]:
                    yr_tif = base_path / f"ndvi_year_{yr}_composite.tif"
                    yr_vals = [None] * n_pts
                    if yr_tif.exists():
                        try:
                            with rasterio.open(yr_tif) as src2:
                                sampled = list(src2.sample(coords))
                                yr_vals = [
                                    round(float(np.array(v)[0]), 3)
                                    if not np.isnan(np.array(v)[0]) else None
                                    for v in sampled
                                ]
                        except Exception:
                            pass
                    result["vals"][str(yr)].extend(yr_vals)

        # Compute per-field per-year normalized values (0-1) for color mapping
        result["norm_vals"] = {}
        for yr_str, vals in result["vals"].items():
            norm = [None] * len(vals)
            field_ids = result["field"]
            for fid in set(field_ids):
                indices = [i for i, f in enumerate(field_ids) if f == fid]
                raw_field = [vals[i] for i in indices if vals[i] is not None]
                if raw_field:
                    fmin = min(raw_field)
                    fmax = max(raw_field)
                    frange = fmax - fmin
                else:
                    fmin, fmax, frange = 0, 1, 1
                for i in indices:
                    v = vals[i]
                    if v is not None and frange > 0:
                        norm[i] = round((v - fmin) / frange, 4)
                    elif v is not None:
                        norm[i] = 0.5
            result["norm_vals"][yr_str] = norm
        return result

    def _kpi_for_filter(self, year: str, field_id: str) -> dict:
        """Compute KPI dict filtered by year and/or field."""
        # Fields to include
        fields = self.fields
        if field_id != "all":
            fields = [f for f in fields if f["field_id"] == field_id]

        ndvi_vals = []
        total_acres = sum(f.get("area_acres", 0) for f in fields)
        total_fields = len(fields)

        for r in self.ndvi_data:
            if r["field_id"] not in {f["field_id"] for f in fields}:
                continue
            if year != "all" and str(r["year"]) != year:
                continue
            v = r.get("mean_ndvi")
            if v is not None:
                ndvi_vals.append(v)

        avg_ndvi = round(float(np.mean(ndvi_vals)), 3) if ndvi_vals else None

        # Weather
        avg_rainfall = None
        avg_gdd = None
        avg_temp = None
        if self.weather_df is not None:
            w = self.weather_df.copy()
            w["date"] = pd.to_datetime(w["date"])
            w["year"] = w["date"].dt.year
            w["month"] = w["date"].dt.month
            if field_id != "all":
                w = w[w["field_id"] == field_id]
            if year != "all":
                w = w[w["year"] == int(year)]
            gs = w[(w["month"] >= 4) & (w["month"] <= 10)].copy()
            if not gs.empty:
                gs["gdd"] = np.maximum(0, gs["T2M"] - 10)
                avg_rainfall = round(
                    gs.groupby(["field_id", "year"])["PRECTOTCORR"]
                    .sum().mean(), 0
                )
                avg_gdd = round(gs.groupby(["field_id", "year"])["gdd"].sum().mean(), 0)
                avg_temp = round(gs["T2M"].mean(), 1)

        # Soil (static, ignore year filter)
        soil_rows = [f for f in fields if f["soil_row"] is not None]
        soil = self.soil_df
        avg_shs = None
        if soil is not None and not soil.empty:
            sf = soil[soil["field_id"].isin(
                [f["field_id"] for f in fields]
            )] if field_id != "all" else soil
            if not sf.empty:
                shs_list = []
                for _, r in sf.iterrows():
                    om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                    cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                    aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                    dr_s = 1.5 if "Moderately well" in str(r.get("drainage_class", "")) else 0.5
                    ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7.0) <= 7.5 else 0.5
                    shs_list.append(om_s + cec_s + aws_s + dr_s + ph_s)
                avg_shs = round(float(np.mean(shs_list)), 1) if shs_list else None

        # Sustainability index
        avg_sust = None
        if soil is not None and not soil.empty and self.rotation_df is not None:
            sf = soil[soil["field_id"].isin(
                [f["field_id"] for f in fields]
            )] if field_id != "all" else soil
            if not sf.empty:
                merged = sf.merge(self.rotation_df, on="field_id", how="left")
                sust_vals = []
                for _, r in merged.iterrows():
                    rot_s = 3.0 if r.get("crop_diversity", 1) > 1 else 0.0
                    om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                    cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                    aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                    dr = r.get("drainage_class", "")
                    dr_s = 1.5 if "Moderately well" in str(dr) else 0.5
                    ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7.0) <= 7.5 else 0.5
                    row_shs = om_s + cec_s + aws_s + dr_s + ph_s
                    shs_norm = row_shs / 10.0 * 3.0
                    er_s = 1.0
                    dr_sust = 2.0 if "Moderately well" in str(dr) else 1.0
                    sust_vals.append(rot_s + shs_norm + er_s + dr_sust)
                avg_sust = round(float(np.mean(sust_vals)), 1) if sust_vals else None

        # Crop breakdown for filtered fields
        crop_acres_f: dict[str, float] = {}
        if self.rotation_df is not None and not self.rotation_df.empty:
            for _, r in self.rotation_df.iterrows():
                fid = r["field_id"]
                if field_id != "all" and fid != field_id:
                    continue
                acres = next((f.get("area_acres", 0) for f in self.fields if f["field_id"] == fid), 0)
                recent_crop = "Unknown"
                for f in self.fields:
                    if f["field_id"] == fid:
                        hist = f.get("crop_history", [])
                        if hist:
                            recent_crop = hist[-1].get("crop", "Unknown")
                        break
                crop_acres_f[recent_crop] = crop_acres_f.get(recent_crop, 0) + acres
        total_ca = sum(crop_acres_f.values())
        crop_breakdown_f = {
            c: round(a / total_ca * 100, 1) if total_ca else 0
            for c, a in crop_acres_f.items()
        }

        # Season span for filtered weather
        season_span_f = None
        if self.weather_df is not None:
            try:
                w = self.weather_df.copy()
                w["date"] = pd.to_datetime(w["date"])
                w["year"] = w["date"].dt.year
                if field_id != "all":
                    w = w[w["field_id"] == field_id]
                if year != "all":
                    w = w[w["year"] == int(year)]
                w["warm"] = w["T2M"] >= 10
                season_days = w.groupby(["field_id", "year"])["warm"].sum()
                season_span_f = round(float(season_days.mean()), 0) if not season_days.empty else None
            except Exception:
                pass

        return {
            "fields": total_fields,
            "acres": round(total_acres, 1),
            "ndvi": avg_ndvi,
            "rainfall": avg_rainfall,
            "gdd": avg_gdd,
            "temp": avg_temp,
            "shs": avg_shs,
            "sust": avg_sust,
            "crop_breakdown": crop_breakdown_f,
            "season_span": int(season_span_f) if season_span_f else None,
        }

    def _narrative_for_filter(self, year: str, field_id: str) -> dict:
        """Generate compact narrative data points for a year/field combo."""
        fields = self.fields
        if field_id != "all":
            fields = [f for f in fields if f["field_id"] == field_id]

        # NDVI
        ndvi_by_f: dict[str, list[float]] = {}
        for r in self.ndvi_data:
            if r["field_id"] not in {f["field_id"] for f in fields}:
                continue
            if year != "all" and str(r["year"]) != year:
                continue
            v = r.get("mean_ndvi")
            if v is not None:
                ndvi_by_f.setdefault(r["field_id"], []).append(v)

        field_ndvi_avg = {
            fid: float(np.mean(vals)) for fid, vals in ndvi_by_f.items() if vals
        }
        best_field = max(field_ndvi_avg, key=field_ndvi_avg.get) if field_ndvi_avg else ""
        worst_field = min(field_ndvi_avg, key=field_ndvi_avg.get) if field_ndvi_avg else ""
        avg_ndvi = round(float(np.mean(list(field_ndvi_avg.values()))), 3) if field_ndvi_avg else None

        # Soil
        low_shs: list[list] = []
        avg_shs = None
        if self.soil_df is not None:
            sf = self.soil_df[self.soil_df["field_id"].isin(
                [f["field_id"] for f in fields]
            )]
            if not sf.empty:
                shs_list = []
                for _, r in sf.iterrows():
                    om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                    cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                    aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                    dr_s = 1.5 if "Moderately well" in str(r.get("drainage_class", "")) else 0.5
                    ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7.0) <= 7.5 else 0.5
                    shs = om_s + cec_s + aws_s + dr_s + ph_s
                    shs_list.append(shs)
                    if shs < 7.0:
                        low_shs.append([r["field_id"], round(shs, 1)])
                avg_shs = round(float(np.mean(shs_list)), 1) if shs_list else None

        # Rotation
        cont_fields = []
        if self.rotation_df is not None:
            for _, r in self.rotation_df.iterrows():
                if r["field_id"] not in {f["field_id"] for f in fields}:
                    continue
                if r.get("crop_diversity", 1) == 1:
                    cont_fields.append(r["field_id"])

        # AWS
        avg_aws = None
        if self.soil_df is not None:
            sf = self.soil_df[self.soil_df["field_id"].isin(
                [f["field_id"] for f in fields]
            )]
            if not sf.empty:
                avg_aws = round(float(sf["total_aws_inches"].mean()), 1)

        return {
            "s1": {
                "total": len(fields),
                "avg_ndvi": avg_ndvi,
                "best": best_field,
                "best_ndvi": round(field_ndvi_avg.get(best_field, 0), 3),
                "worst": worst_field,
                "worst_ndvi": round(field_ndvi_avg.get(worst_field, 0), 3),
            },
            "s2": {
                "best": best_field,
                "best_ndvi": round(field_ndvi_avg.get(best_field, 0), 3),
                "worst": worst_field,
                "worst_ndvi": round(field_ndvi_avg.get(worst_field, 0), 3),
                "total": len(fields),
            },
            "s3": {
                "avg_shs": avg_shs,
                "low_shs": low_shs,
                "cont_fields": cont_fields,
            },
            "recs": {
                "low_shs": [f for f, _ in low_shs[:2]],
                "cont_fields": cont_fields[:2],
                "avg_aws": avg_aws,
            },
        }

    def _format_narrative_text(self, narr_data: dict, year: str, field_id: str) -> dict[str, str]:
        """Format narrative data points into human-readable text (mirrors JS builders)."""
        # Section 1
        s1d = narr_data.get("s1", {})
        total = s1d.get("total", 0)
        avg_ndvi = s1d.get("avg_ndvi")
        best = s1d.get("best", "")
        best_ndvi = s1d.get("best_ndvi", 0)
        worst = s1d.get("worst", "")
        worst_ndvi = s1d.get("worst_ndvi", 0)
        yr_label = "across all years" if year == "all" else f"in {year}"
        s1 = f"Mean NDVI across {total} field(s) {yr_label} is {avg_ndvi:.3f}. "
        if best and worst and best != worst:
            s1 += f"Field {_prettify_field_id(best)} leads at {best_ndvi:.3f}, while {_prettify_field_id(worst)} trails at {worst_ndvi:.3f}."
        elif best:
            s1 += f"Field {_prettify_field_id(best)} has NDVI of {best_ndvi:.3f}."

        # Section 2
        s2d = narr_data.get("s2", {})
        best = s2d.get("best", "")
        best_ndvi = s2d.get("best_ndvi", 0)
        worst = s2d.get("worst", "")
        worst_ndvi = s2d.get("worst_ndvi", 0)
        s2 = ""
        if best and worst and best != worst:
            s2 += f"Field {_prettify_field_id(best)} leads with mean NDVI of {best_ndvi:.3f}, while {_prettify_field_id(worst)} trails at {worst_ndvi:.3f}. "
        elif best:
            s2 += f"Field {_prettify_field_id(best)} has mean NDVI of {best_ndvi:.3f}. "
        s2 += "Crop type explains part of this gap — soybeans average higher NDVI than corn — but the key finding is the correlation between NDVI and soil organic matter, which ties crop health directly to soil variability."

        # Section 3
        s3d = narr_data.get("s3", {})
        avg_shs = s3d.get("avg_shs")
        low_shs = s3d.get("low_shs", [])
        cont_fields = s3d.get("cont_fields", [])
        s3 = ""
        if avg_shs is not None:
            s3 += f"Mean Soil Health Score is {avg_shs}/10. "
        if low_shs:
            low_str = ", ".join(f"{_prettify_field_id(fid)} ({score})" for fid, score in low_shs[:3])
            s3 += f"{low_str} score below 7.0, indicating opportunities for improvement through cover cropping or organic amendment. "
        if cont_fields:
            cont_str = ", ".join(_prettify_field_id(fid) for fid in cont_fields[:3])
            s3 += f"Continuous monoculture fields ({cont_str}) show the highest soil risk, reinforcing that crop health and soil health are tightly linked."
        else:
            s3 += "All fields show crop rotation diversity, which supports long-term soil health."

        # Recommendations
        recd = narr_data.get("recs", {})
        low_shs_recs = recd.get("low_shs", [])
        cont_recs = recd.get("cont_fields", [])
        avg_aws = recd.get("avg_aws")
        recs = []
        if low_shs_recs:
            low_ids = [_prettify_field_id(fid) for fid in low_shs_recs[:2]]
            recs.append(f"Introduce cover crops on fields {', '.join(low_ids)} to rebuild organic matter and improve water storage.")
        if cont_recs:
            cont_short = [_prettify_field_id(fid) for fid in cont_recs[:2]]
            recs.append(f"Break continuous cropping on fields {', '.join(cont_short)} with a rotational year to restore soil biology and reduce pest pressure.")
        if avg_aws is not None and avg_aws < 4.0:
            recs.append("Prioritize drought-tolerant hybrid selection on fields with below-average Available Water Storage (<4 inches).")
        recs.append("Continue monitoring NDVI trends annually to detect field-level stress before visible symptoms appear.")
        section4 = "\n".join(f"{i+1}. {r}" for i, r in enumerate(recs[:4]))

        return {"section1": s1, "section2": s2, "section3": s3, "section4": section4}

    # ---- Chart generators (Plotly) -------------------------------------

    def _create_ndvi_variability_map(self) -> str:
        """2-panel scattergeo map: mean NDVI + NDVI CV% per field."""
        from plotly.subplots import make_subplots
        ndvi = self.ndvi_data
        fields = self.fields

        field_means = {}
        for r in ndvi:
            fid = r["field_id"]
            v = r.get("mean_ndvi")
            if v is not None:
                field_means.setdefault(fid, []).append(v)
        stats = []
        for f in fields:
            fid = f["field_id"]
            vals = field_means.get(fid, [])
            if vals:
                mn = float(np.mean(vals))
                cv = float(np.std(vals) / mn * 100) if mn > 0 else 0
            else:
                mn = 0
                cv = 0
            stats.append({
                "field_id": fid,
                "lon": f["centroid"][0],
                "lat": f["centroid"][1],
                "mean_ndvi": round(mn, 3),
                "cv_pct": round(cv, 1),
                "label": _prettify_field_id(fid),
            })

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Mean NDVI per Field", "NDVI Variability (CV%)"),
            specs=[[{"type": "scattergeo"}, {"type": "scattergeo"}]],
        )

        for col, key, cmap, c_title in [
            (1, "mean_ndvi", "YlGn", "Mean NDVI"),
            (2, "cv_pct", "YlOrRd_r", "CV (%)"),
        ]:
            vals = [s[key] for s in stats]
            fig.add_trace(
                go.Scattergeo(
                    lon=[s["lon"] for s in stats],
                    lat=[s["lat"] for s in stats],
                    mode="markers+text",
                    marker=dict(
                        size=18,
                        color=vals,
                        colorscale=cmap,
                        colorbar=dict(title=c_title, x=0.45 if col == 1 else 1.0),
                        line=dict(width=0.5, color="black"),
                    ),
                    text=[s["label"] for s in stats],
                    textposition="top center",
                    textfont=dict(size=9),
                    hovertext=[f"{s['label']}: {s[key]}" for s in stats],
                    hoverinfo="text",
                    name="",
                ),
                row=1, col=col,
            )

        center_lat = sum(s["lat"] for s in stats) / len(stats)
        center_lon = sum(s["lon"] for s in stats) / len(stats)
        geo_kw = dict(
            projection_type="mercator",
            lonaxis_range=[center_lon - 0.08, center_lon + 0.08],
            lataxis_range=[center_lat - 0.04, center_lat + 0.04],
            showland=True,
            landcolor="rgba(240,240,240,1)",
            showocean=True,
            oceancolor="rgba(220,220,220,0.3)",
            showcoastlines=False,
            showframe=False,
        )
        fig.update_geos(**geo_kw)
        fig.update_layout(
            height=420, margin=dict(l=10, r=10, t=30, b=10),
            geo=geo_kw, geo2=geo_kw,
        )
        return fig.to_html(full_html=False, div_id="chart-ndvi-variability",
                           include_plotlyjs=False)

    def _create_field_ranking_chart(self) -> str:
        """2-panel Plotly: ranked NDVI bars + NDVI by crop boxplot."""
        from plotly.subplots import make_subplots
        ndvi = self.ndvi_data
        fields = self.fields
        rotation = self.rotation_df

        field_means = {}
        for r in ndvi:
            fid = r["field_id"]
            v = r.get("mean_ndvi")
            if v is not None:
                field_means.setdefault(fid, []).append(v)

        rot_cat = {}
        if rotation is not None:
            for _, row in rotation.iterrows():
                fid = row["field_id"]
                if row.get("crop_diversity", 1) > 1:
                    rot_cat[fid] = "rotating"
                elif "Grass" in str(row.get("rotation_sequence", "")):
                    rot_cat[fid] = "grass_pasture"
                else:
                    rot_cat[fid] = "continuous"

        ranking = []
        for f in fields:
            fid = f["field_id"]
            vals = field_means.get(fid, [])
            mn = float(np.mean(vals)) if vals else 0
            cat = rot_cat.get(fid, "rotating")
            crops = set()
            for ch in f.get("crop_history", []):
                if ch.get("crop") and ch["crop"] != "Grass/Pasture":
                    crops.add(ch["crop"])
            ranking.append({
                "field_id": fid,
                "label": _prettify_field_id(fid),
                "mean_ndvi": round(mn, 3),
                "category": cat,
                "dominant_crop": ", ".join(sorted(crops)) if crops else "Mixed",
            })
        ranking.sort(key=lambda x: x["mean_ndvi"], reverse=True)

        # NDVI by crop
        corn_vals, soy_vals = [], []
        for r in ndvi:
            fid = r["field_id"]
            yr = r["year"]
            v = r.get("mean_ndvi")
            if v is None:
                continue
            crop = None
            for f in fields:
                if f["field_id"] == fid:
                    for ch in f.get("crop_history", []):
                        if ch["year"] == yr:
                            crop = ch.get("crop")
                            break
            if crop == "Corn":
                corn_vals.append(v)
            elif crop == "Soybeans":
                soy_vals.append(v)

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=("Field Ranking by Mean NDVI",
                            "NDVI Distribution by Crop Type"),
            specs=[[{"type": "bar"}, {"type": "box"}]],
        )

        # Panel A: horizontal bars
        labels_rev = [r["label"] for r in ranking]
        vals_rev = [r["mean_ndvi"] for r in ranking]
        colors_rev = [ROTATION_PALETTE.get(r["category"], "#999") for r in ranking]
        fig.add_trace(
            go.Bar(
                x=vals_rev,
                y=labels_rev,
                orientation="h",
                marker_color=colors_rev,
                text=[f"{v:.3f}" for v in vals_rev],
                textposition="outside",
                hovertemplate="%{y}: %{x:.3f}<extra></extra>",
                showlegend=False,
            ),
            row=1, col=1,
        )
        # Legend for rotation categories
        for cat, color in [("Rotating", "#2E8B57"), ("Continuous", "#DAA520"),
                           ("Grass/Pasture", "#8FBC8F")]:
            fig.add_trace(
                go.Bar(x=[None], y=[None], marker_color=color,
                       name=cat, showlegend=True),
                row=1, col=1,
            )

        # Panel B: boxplot
        if corn_vals:
            fig.add_trace(
                go.Box(y=corn_vals, name="Corn",
                       marker_color="#DAA520", boxmean=True),
                row=1, col=2,
            )
        if soy_vals:
            fig.add_trace(
                go.Box(y=soy_vals, name="Soybeans",
                       marker_color="#2E8B57", boxmean=True),
                row=1, col=2,
            )
        all_vals = corn_vals + soy_vals
        farm_mean = float(np.mean(all_vals)) if all_vals else None
        if farm_mean:
            fig.add_hline(
                y=farm_mean, line_dash="dash",
                line_color="red", line_width=1,
                annotation_text=f"Farm mean = {farm_mean:.3f}",
                row=1, col=2,
            )

        fig.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", y=1.1, x=0.3, font=dict(size=10)),
        )
        fig.update_xaxes(title_text="Mean NDVI", row=1, col=1)
        fig.update_yaxes(title_text="NDVI", row=1, col=2)
        return fig.to_html(full_html=False, div_id="chart-field-ranking",
                           include_plotlyjs=False)

    def _create_environmental_correlations(self) -> str:
        """3-panel Plotly scatter: NDVI drivers — rainfall, GDD, soil OM."""
        from plotly.subplots import make_subplots
        from scipy import stats as scipy_stats

        ndvi = self.ndvi_data
        weather = self.weather_df
        soil = self.soil_df

        ndvi_by_fy: dict[tuple[str, int], float] = {}
        for r in ndvi:
            fid = r["field_id"]
            yr = r["year"]
            v = r.get("mean_ndvi")
            if v is not None:
                ndvi_by_fy[(fid, yr)] = v

        fy_data: list[dict] = []
        if weather is not None:
            w = weather.copy()
            w["date"] = pd.to_datetime(w["date"])
            w["year"] = w["date"].dt.year
            w["month"] = w["date"].dt.month
            gs = w[(w["month"] >= 4) & (w["month"] <= 10)].copy()
            gs["gdd"] = np.maximum(0, gs["T2M"] - 10)
            for (fid, yr), grp in gs.groupby(["field_id", "year"]):
                key = (fid, yr)
                ndvi_val = ndvi_by_fy.get(key)
                if ndvi_val is not None:
                    fy_data.append({
                        "field_id": fid,
                        "year": yr,
                        "mean_ndvi": ndvi_val,
                        "rain_mm": round(grp["PRECTOTCORR"].sum(), 1),
                        "gdd": round(grp["gdd"].sum(), 0),
                    })

        field_om: dict[str, float] = {}
        if soil is not None:
            for _, r in soil.iterrows():
                field_om[r["field_id"]] = r.get("avg_om_pct", 0)

        fig = make_subplots(rows=1, cols=3,
                            subplot_titles=(
                                "NDVI vs Growing Season Rain",
                                "NDVI vs GDD",
                                "NDVI vs Soil Organic Matter"))

        panels = [
            (1, 1, "rain_mm", "mean_ndvi", "Rainfall (mm)", "Mean NDVI"),
            (1, 2, "gdd", "mean_ndvi", "GDD (base 10°C)", "Mean NDVI"),
            (1, 3, "om", "mean_ndvi", "Organic Matter (%)", "Mean NDVI"),
        ]

        for row, col, x_key, y_key, x_label, y_label in panels:
            if x_key == "om":
                f_ndvi: dict[str, list] = {}
                for d in fy_data:
                    f_ndvi.setdefault(d["field_id"], []).append(d["mean_ndvi"])
                pts = []
                for fid, vlist in f_ndvi.items():
                    om = field_om.get(fid)
                    if om is not None:
                        pts.append({"x": om, "y": float(np.mean(vlist))})
                xv = [p["x"] for p in pts]
                yv = [p["y"] for p in pts]
            else:
                xv = [d[x_key] for d in fy_data]
                yv = [d[y_key] for d in fy_data]

            fig.add_trace(
                go.Scatter(
                    x=xv, y=yv, mode="markers",
                    marker=dict(size=8, opacity=0.6, color="#2E8B57",
                                line=dict(width=0.5, color="black")),
                    showlegend=False,
                    hovertemplate=f"{x_label}: %{{x}}<br>{y_label}: %{{y}}<extra></extra>",
                ),
                row=row, col=col,
            )

            if len(xv) > 2:
                xa = np.array(xv)
                ya = np.array(yv)
                mask = ~(np.isnan(xa) | np.isnan(ya))
                xa, ya = xa[mask], ya[mask]
                if len(xa) > 2:
                    slope, intercept, r_val, p_val, _ = scipy_stats.linregress(xa, ya)
                    x_line = np.linspace(xa.min(), xa.max(), 50)
                    fig.add_trace(
                        go.Scatter(x=x_line, y=slope * x_line + intercept,
                                   mode="lines", line=dict(dash="dash", color="red"),
                                   showlegend=False,
                                   hovertemplate=f"r = {r_val:.3f}<extra></extra>"),
                        row=row, col=col,
                    )
                    sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
                    ax_suffix = "" if col == 1 else str(col)
                    fig.add_annotation(
                        x=0.98, y=0.05,
                        xref=f"x{ax_suffix} domain",
                        yref=f"y{ax_suffix} domain",
                        text=f"r = {r_val:.3f}{sig}",
                        showarrow=False, font=dict(size=10),
                        bgcolor="white", bordercolor="#ccc", borderwidth=1,
                    )

            fig.update_xaxes(title_text=x_label, row=row, col=col)
            fig.update_yaxes(title_text=y_label, row=row, col=col)

        fig.update_layout(height=400, margin=dict(l=10, r=10, t=40, b=10))
        return fig.to_html(full_html=False, div_id="chart-correlations",
                           include_plotlyjs=False)

    def _create_soil_health_chart(self) -> str:
        """4-panel Plotly: SHS bars, OM+CEC, AWS, SustIndex breakdown."""
        from plotly.subplots import make_subplots
        soil = self.soil_df
        rotation = self.rotation_df

        if soil is None or soil.empty:
            fig = go.Figure()
            fig.add_annotation(text="No soil data available",
                               x=0.5, y=0.5, showarrow=False)
            return fig.to_html(full_html=False, div_id="chart-soil",
                               include_plotlyjs=False)

        shs_data = []
        for _, r in soil.iterrows():
            fid = r["field_id"]
            om = r.get("avg_om_pct", 0)
            cec = r.get("avg_cec", 0)
            aws = r.get("total_aws_inches", 0)
            dr = r.get("drainage_class", "")
            ph = r.get("avg_ph", 7.0)
            om_s = min(om / 5.0, 1.0) * 2.5
            cec_s = min(cec / 25.0, 1.0) * 2.5
            aws_s = min(aws / 6.0, 1.0) * 2.5
            dr_s = 1.5 if "Moderately well" in str(dr) else 0.5
            ph_s = 1.0 if 6.0 <= ph <= 7.5 else 0.5
            shs = round(om_s + cec_s + aws_s + dr_s + ph_s, 2)
            shs_data.append({
                "field_id": fid,
                "label": _prettify_field_id(fid),
                "shs": shs, "om": om, "cec": cec, "aws": aws,
                "drainage": dr,
            })

        shs_data.sort(key=lambda x: x["shs"], reverse=True)
        labels = [s["label"] for s in shs_data]

        # Sustainability breakdown
        sust_data = []
        if rotation is not None:
            merged = soil.merge(rotation, on="field_id", how="left")
            for _, r in merged.iterrows():
                fid = r["field_id"]
                rot_s = 3.0 if r.get("crop_diversity", 1) > 1 else 0.0
                om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                dr = r.get("drainage_class", "")
                dr_s = 1.5 if "Moderately well" in str(dr) else 0.5
                ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7) <= 7.5 else 0.5
                row_shs = om_s + cec_s + aws_s + dr_s + ph_s
                sust_data.append({
                    "field_id": fid,
                    "label": _prettify_field_id(fid),
                    "rotation": rot_s,
                    "soil_health": round(row_shs / 10.0 * 3.0, 2),
                    "erosion": 1.0,
                    "drainage": 2.0 if "Moderately well" in str(dr) else 1.0,
                })
        sust_data.sort(
            key=lambda x: x["rotation"] + x["soil_health"] + x["erosion"] + x["drainage"],
            reverse=True,
        )
        sust_labels = [s["label"] for s in sust_data]

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=("Soil Health Score", "OM% & CEC",
                            "Available Water Storage",
                            "Sustainability Index Breakdown"),
            specs=[[{"type": "bar"}, {"type": "bar"}],
                   [{"type": "bar"}, {"type": "bar"}]],
        )

        # Panel 1: SHS horizontal bars
        dr_colors = [DRAIN_COLORS.get(s["drainage"], "#999") for s in shs_data]
        fig.add_trace(
            go.Bar(x=[s["shs"] for s in shs_data], y=labels,
                   orientation="h", marker_color=dr_colors,
                   text=[f"{s['shs']:.1f}" for s in shs_data],
                   textposition="outside", showlegend=False),
            row=1, col=1,
        )
        fig.add_vline(x=7.0, line_dash="dash", line_color="red",
                      line_width=1, row=1, col=1)
        for d_c, d_hex in DRAIN_COLORS.items():
            fig.add_trace(go.Bar(x=[None], y=[None], marker_color=d_hex,
                                 name=d_c, showlegend=True), row=1, col=1)
        fig.update_xaxes(title_text="SHS (0–10)", range=[0, 10.5], row=1, col=1)

        # Panel 2: OM% and CEC side-by-side
        om_vals = [s["om"] for s in shs_data]
        cec_vals = [s["cec"] for s in shs_data]
        fig.add_trace(
            go.Bar(x=labels, y=om_vals, name="OM%",
                   marker_color="#2E8B57", opacity=0.8),
            row=1, col=2,
        )
        fig.add_trace(
            go.Bar(x=labels, y=cec_vals, name="CEC",
                   marker_color="#4A90D9", opacity=0.8),
            row=1, col=2,
        )
        fig.update_xaxes(tickangle=45, row=1, col=2)
        fig.update_yaxes(title_text="Value", row=1, col=2)

        # Panel 3: AWS horizontal bars
        aws_vals = [s["aws"] for s in shs_data]
        aws_colors = ["#4A90D9" if v >= 4.0 else "#E8833A" for v in aws_vals]
        fig.add_trace(
            go.Bar(x=aws_vals, y=labels, orientation="h",
                   marker_color=aws_colors,
                   text=[f"{v:.1f}" for v in aws_vals],
                   textposition="outside", showlegend=False),
            row=2, col=1,
        )
        fig.add_vline(x=4.0, line_dash="dash", line_color="green",
                      line_width=1, row=2, col=1)
        fig.update_xaxes(title_text="AWS (inches)", row=2, col=1)

        # Panel 4: Sustainability Index stacked bars
        categories = ["Rotation", "Soil Health", "Erosion", "Drainage"]
        cat_colors = ["#2E8B57", "#4A90D9", "#DAA520", "#8FBC8F"]
        for ci, cat in enumerate(categories):
            key = cat.lower().replace(" ", "_")
            fig.add_trace(
                go.Bar(x=[s[key] for s in sust_data], y=sust_labels,
                       orientation="h", name=cat,
                       marker_color=cat_colors[ci],
                       legendgroup=cat),
                row=2, col=2,
            )
        # Total text
        total_vals = [sum(s[k.lower().replace(" ", "_")] for k in categories)
                      for s in sust_data]
        fig.add_trace(
            go.Scatter(x=total_vals, y=sust_labels, mode="text",
                       text=[f"{v:.1f}" for v in total_vals],
                       textposition="middle right",
                       showlegend=False),
            row=2, col=2,
        )
        fig.update_xaxes(title_text="Sustainability Index (0–10)", row=2, col=2)
        fig.update_layout(
            height=620,
            margin=dict(l=10, r=10, t=40, b=10),
            barmode="stack",
            legend=dict(orientation="h", y=1.04, x=0.5, xanchor="center"),
        )
        return fig.to_html(full_html=False, div_id="chart-soil",
                           include_plotlyjs=False)

    def _create_ndvi_timeseries(self) -> str:
        """Line chart: mean NDVI per field over 2021–2025, colored by crop."""
        ndvi = self.ndvi_data
        fields = self.fields

        # Build per-field per-year NDVI
        field_year_ndvi: dict[str, dict[int, float]] = {}
        for r in ndvi:
            fid = r["field_id"]
            yr = r["year"]
            v = r.get("mean_ndvi")
            if v is not None:
                field_year_ndvi.setdefault(fid, {})[yr] = v

        # Determine dominant crop per field for coloring
        field_crop: dict[str, str] = {}
        for f in fields:
            fid = f["field_id"]
            crops = []
            for ch in f.get("crop_history", []):
                c = ch.get("crop")
                if c and c != "Grass/Pasture":
                    crops.append(c)
            # Fallback to rotation_df
            if not crops and self.rotation_df is not None:
                row = self.rotation_df[self.rotation_df["field_id"] == fid]
                if not row.empty:
                    seq = str(row.iloc[0].get("rotation_sequence", ""))
                    if "Corn" in seq and "Soy" in seq:
                        crops = ["Soybeans"]  # arbitrary fallback
                    elif "Corn" in seq:
                        crops = ["Corn"]
                    elif "Soy" in seq:
                        crops = ["Soybeans"]
            dominant = max(set(crops), key=crops.count) if crops else "Mixed"
            field_crop[fid] = dominant

        fig = go.Figure()
        years = [2021, 2022, 2023, 2024, 2025]

        for f in fields:
            fid = f["field_id"]
            label = _prettify_field_id(fid)
            crop = field_crop.get(fid, "Mixed")
            color = CROP_COLORS.get(crop, "#AAAAAA")
            yvals = []
            hover_texts = []
            for yr in years:
                v = field_year_ndvi.get(fid, {}).get(yr)
                if v is not None:
                    yvals.append(v)
                    hover_texts.append(f"{label} ({yr})<br>Crop: {crop}<br>NDVI: {v:.3f}")
                else:
                    yvals.append(None)
                    hover_texts.append(f"{label} ({yr})<br>Crop: {crop}<br>NDVI: N/A")

            fig.add_trace(go.Scatter(
                x=years, y=yvals,
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=7, color=color),
                hovertext=hover_texts,
                hoverinfo="text",
                connectgaps=False,
            ))

        # Farm mean line
        farm_means = []
        for yr in years:
            vals = [
                field_year_ndvi.get(f["field_id"], {}).get(yr)
                for f in fields
            ]
            vals = [v for v in vals if v is not None]
            farm_means.append(float(np.mean(vals)) if vals else None)

        if any(v is not None for v in farm_means):
            fig.add_trace(go.Scatter(
                x=years, y=farm_means,
                mode="lines+markers",
                name="Farm Mean",
                line=dict(color="#333333", width=2, dash="dash"),
                marker=dict(size=8, color="#333333"),
                hovertemplate="Farm Mean (%{x}): %{y:.3f}<extra></extra>",
            ))

        fig.update_layout(
            title="NDVI Trend by Field (2021–2025)",
            xaxis_title="Year",
            yaxis_title="Mean NDVI",
            yaxis=dict(range=[0.2, 0.65]),
            height=420,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center",
                        font=dict(size=10)),
            hovermode="x unified",
        )
        return fig.to_html(full_html=False, div_id="chart-ndvi-timeseries",
                           include_plotlyjs=False)

    def _create_interactive_map(self, year: str = "all", pixel_data: Optional[dict] = None) -> str:
        """Plotly map: raw pixel NDVI + field boundaries + soil health toggle."""
        gj = self.combined_geojson
        if not gj or not gj.get("features"):
            return "<p>No field boundaries available for map.</p>"

        fields = self.fields
        fids = []
        counties = []
        centroids = []
        ndvi_means = []
        soil_scores = []
        field_crops = {}
        for f in fields:
            fid = f["field_id"]
            fids.append(fid)
            counties.append(f.get("county", ""))
            centroids.append(f["centroid"])
            vals = [r["mean_ndvi"] for r in self.ndvi_data
                    if r["field_id"] == fid and str(r["year"]) == year
                    and r.get("mean_ndvi") is not None]
            ndvi_means.append(round(float(np.mean(vals)), 3) if vals else None)
            if self.soil_df is not None:
                sr = self.soil_df[self.soil_df["field_id"] == fid]
                if not sr.empty:
                    r = sr.iloc[0]
                    om_s = min(r.get("avg_om_pct", 0) / 5.0, 1.0) * 2.5
                    cec_s = min(r.get("avg_cec", 0) / 25.0, 1.0) * 2.5
                    aws_s = min(r.get("total_aws_inches", 0) / 6.0, 1.0) * 2.5
                    dr_s = 1.5 if "Moderately well" in str(r.get("drainage_class", "")) else 0.5
                    ph_s = 1.0 if 6.0 <= r.get("avg_ph", 7.0) <= 7.5 else 0.5
                    soil_scores.append(round(om_s + cec_s + aws_s + dr_s + ph_s, 1))
                else:
                    soil_scores.append(None)
            else:
                soil_scores.append(None)
            crops = list(dict.fromkeys(
                ch.get("crop", "") for ch in f.get("crop_history", [])
                if ch.get("crop")
            ))
            field_crops[fid] = ", ".join(crops) if crops else "N/A"

        lats = [c[1] for c in centroids]
        lons = [c[0] for c in centroids]
        center_lat = sum(lats) / len(lats) if lats else 43.27
        center_lon = sum(lons) / len(lons) if lons else -94.24

        field_rot = {}
        for f in fields:
            fid = f["field_id"]
            seq = list(dict.fromkeys(
                ch.get("crop", "") for ch in f.get("crop_history", [])
            ))
            field_rot[fid] = " → ".join(seq) if seq else "N/A"

        field_soil = {}
        if self.soil_df is not None:
            for _, r in self.soil_df.iterrows():
                field_soil[r["field_id"]] = r.get("dominant_soil", "")

        # Pixel NDVI data for the default year (normalized colors + raw hover values)
        px = pixel_data or {}
        px_year = str(year) if year != "all" else DEFAULT_YEAR
        px_norm = px.get("norm_vals", {}).get(px_year, [])
        px_raw = px.get("vals", {}).get(px_year, [])
        px_lons = px.get("lon", [])
        px_lats = px.get("lat", [])
        # Filter out None values
        px_valid = [(lo, la, n, r) for lo, la, n, r in zip(px_lons, px_lats, px_norm, px_raw) if n is not None]
        if px_valid:
            vlons, vlats, vnorm, vraw = zip(*px_valid)
        else:
            vlons, vlats, vnorm, vraw = [], [], [], []

        try:
            fig = go.Figure()

            # Trace 0: choropleth backdrop — field-mean NDVI at medium opacity
            fig.add_trace(go.Choroplethmapbox(
                geojson=gj,
                locations=fids,
                z=[v if v is not None else 0.0 for v in ndvi_means],
                featureidkey="properties.field_id",
                colorscale=NDVI_BACKDROP_CS,
                zmin=0.2, zmax=0.6,
                marker=dict(line=dict(width=1.5, color="white")),
                showscale=False,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "NDVI: %{customdata[1]}<br>"
                    "Crop: %{customdata[5]}<br>"
                    "Soil Health: %{customdata[6]}<br>"
                    "Acres: %{customdata[2]:.0f}<br>"
                    "Rotation: %{customdata[3]}<br>"
                    "Soil: %{customdata[4]}<br>"
                    "<extra></extra>"
                ),
                customdata=list(zip(
                    [_prettify_field_id(f) for f in fids],
                    [f"{n:.3f}" if n is not None else "N/A" for n in ndvi_means],
                    [f.get("area_acres", 0) for f in fields],
                    [field_rot.get(f, "") for f in fids],
                    [field_soil.get(f, "") for f in fids],
                    [field_crops.get(f, "N/A") for f in fids],
                    [f"{s}/10" if s else "N/A" for s in soil_scores],
                )),
            ))

            # Trace 1: pixel NDVI layer (field-normalized colors, raw hover values)
            fig.add_trace(go.Scattermapbox(
                lon=list(vlons),
                lat=list(vlats),
                mode="markers",
                marker=dict(
                    color=list(vnorm),
                    colorscale="RdYlGn",
                    cmin=0.0, cmax=1.0,
                    size=5,
                    opacity=0.9,
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="NDVI (field-normalized)"),
                        thickness=12,
                        len=0.5,
                        y=0.5,
                        tickvals=[0, 0.5, 1],
                        ticktext=["Low", "Mid", "High"],
                    ),
                ),
                customdata=list(vraw),
                hovertemplate="NDVI: %{customdata:.3f}<extra></extra>",
                visible=True,
            ))

            fig.update_layout(
                mapbox=dict(
                    style="white-bg",
                    center={"lat": center_lat, "lon": center_lon},
                    zoom=11,
                    layers=[{
                        "below": "traces",
                        "sourcetype": "raster",
                        "source": [
                            "https://server.arcgisonline.com/ArcGIS/rest/services/"
                            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
                        ],
                    }],
                ),
                margin={"r": 0, "t": 0, "l": 0, "b": 0},
                height=500,
                dragmode="zoom",
            )

            html_str = fig.to_html(
                include_plotlyjs=False,
                full_html=False,
                div_id="choropleth-map",
            )
            return html_str

        except Exception as exc:
            return f"<p>Map generation failed: {exc}</p>"

    # ---- Data normalization & validation -----------------------------

    def _normalize_month_keys(self, data: dict) -> dict:
        """Ensure all month keys are zero-padded strings ('04'-'10')."""
        # monthly structure: {field_id: {year: {month: data}}}
        if "monthly" in data:
            normalized: dict[str, dict] = {}
            for fid, fid_data in data["monthly"].items():
                normalized[fid] = {}
                for yr, yr_data in fid_data.items():
                    normalized[fid][yr] = {}
                    for mo, mo_data in yr_data.items():
                        normalized[fid][yr][f"{int(mo):02d}"] = mo_data
            data["monthly"] = normalized
        # monthly_ndvi and map_px_monthly structure: {year: {month: {field_id: data}}}
        for key in ["monthly_ndvi", "map_px_monthly"]:
            if key not in data:
                continue
            normalized = {}
            for yr, yr_data in data[key].items():
                normalized[yr] = {}
                for mo, mo_data in yr_data.items():
                    normalized[yr][f"{int(mo):02d}"] = mo_data
            data[key] = normalized
        return data

    def _validate_embedded_data(self, data: dict) -> None:
        """Validate data structure before embedding."""
        required = [
            "fields", "years", "ndvi", "weather", "monthly",
            "map_ndvi", "map_center", "map_px", "map_px_monthly",
        ]
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"Missing DATA keys: {missing}")

        # Verify month keys are zero-padded
        # monthly structure: {field_id: {year: {month: data}}}
        if "monthly" in data:
            for fid, fid_data in data["monthly"].items():
                for yr, yr_data in fid_data.items():
                    for mo in yr_data:
                        if mo not in ["04", "05", "06", "07", "08", "09", "10"]:
                            raise ValueError(
                                f"Invalid month key '{mo}' in monthly[{fid}][{yr}]; expected '04'-'10'"
                            )
        # monthly_ndvi and map_px_monthly structure: {year: {month: {field_id: data}}}
        for key in ["monthly_ndvi", "map_px_monthly"]:
            if key not in data:
                continue
            for yr, yr_data in data[key].items():
                for mo in yr_data:
                    if mo not in ["04", "05", "06", "07", "08", "09", "10"]:
                        raise ValueError(
                            f"Invalid month key '{mo}' in {key}[{yr}]; expected '04'-'10'"
                        )

        # Verify geojson feature IDs match field IDs
        if self.combined_geojson and data.get("fields"):
            gj_ids = {
                f["properties"]["field_id"]
                for f in self.combined_geojson.get("features", [])
            }
            data_ids = {f["id"] for f in data["fields"]}
            if gj_ids != data_ids:
                raise ValueError(
                    f"GeoJSON feature IDs {gj_ids} don't match field IDs {data_ids}"
                )

    # ---- Template-based HTML rendering --------------------------------

    def _render_html(
        self,
        narrative: dict[str, str],
        map_html: str,
        chart_html: dict[str, str],
        embedded_data: dict,
    ) -> str:
        """Assemble dashboard HTML from external templates."""
        # Normalize and validate data
        embedded_data = self._normalize_month_keys(embedded_data)
        self._validate_embedded_data(embedded_data)

        # Load templates
        tpl_dir = Path(__file__).parent.parent / "templates"
        html_tpl = (tpl_dir / "dashboard.html").read_text(encoding="utf-8")
        css = (tpl_dir / "dashboard.css").read_text(encoding="utf-8")
        js_tpl = (tpl_dir / "dashboard.js").read_text(encoding="utf-8")

        # Interpolate JS template
        embedded_json = json.dumps(embedded_data)
        js_code = (
            js_tpl.replace("/*EMBEDDED_DATA*/", embedded_json)
            .replace("/*NDVI_BACKDROP_CS*/", json.dumps(NDVI_BACKDROP_CS))
        )

        # Build year/month/field dropdown options
        year_opts = ""
        for yr in [2021, 2022, 2023, 2024, 2025]:
            selected = ' selected' if str(yr) == DEFAULT_YEAR else ''
            year_opts += f'<option value="{yr}"{selected}>{yr}</option>\n'

        month_opts = ""
        for mo, name in [
            ("04", "April"), ("05", "May"), ("06", "June"),
            ("07", "July"), ("08", "August"), ("09", "September"), ("10", "October"),
        ]:
            selected = ' selected' if mo == "10" else ''
            month_opts += f'<option value="{mo}"{selected}>{name}</option>\n'

        field_opts = '<option value="all">All Fields</option>\n'
        for f in self.fields:
            label = _prettify_field_id(f["field_id"])
            field_opts += f'<option value="{f["field_id"]}">{label}</option>\n'

        # KPI initial values for first paint
        initial = embedded_data.get("kpis", {}).get(f"{DEFAULT_YEAR}_all", {})
        initial_narr_data = embedded_data.get("narratives", {}).get(f"{DEFAULT_YEAR}_all", {})
        initial_narr = self._format_narrative_text(initial_narr_data, DEFAULT_YEAR, "all")

        # Methodology HTML
        methodology_html = textwrap.dedent("""\
        <div class="methodology">
        <h3>Soil Health Score (SHS) — 0 to 10</h3>
        <table>
        <tr><th>Component</th><th>Target</th><th>Max Pts</th><th>Scoring</th></tr>
        <tr><td>Organic Matter</td><td>5.0%</td><td>2.5</td><td>min(OM%/5, 1) × 2.5</td></tr>
        <tr><td>CEC</td><td>25 meq/100g</td><td>2.5</td><td>min(CEC/25, 1) × 2.5</td></tr>
        <tr><td>Available Water Storage</td><td>6.0 in</td><td>2.5</td><td>min(AWS/6, 1) × 2.5</td></tr>
        <tr><td>Drainage Class</td><td>Well drained</td><td>1.5</td><td>Mod well=1.5, Poorly=0.5</td></tr>
        <tr><td>pH Suitability</td><td>6.0–7.5</td><td>1.0</td><td>In range=1.0, else=0.5</td></tr>
        <tr><td><strong>Total</strong></td><td></td><td><strong>10</strong></td><td></td></tr>
        </table>
        <h3>Sustainability Index — 0 to 10</h3>
        <table>
        <tr><th>Component</th><th>Max Pts</th><th>Scoring</th></tr>
        <tr><td>Crop Rotation Diversity</td><td>3.0</td><td>&gt;1 crop types in 5yr = 3, monoculture = 0</td></tr>
        <tr><td>Soil Health (normalized)</td><td>3.0</td><td>SHS/10 × 3</td></tr>
        <tr><td>Erosion Risk</td><td>2.0</td><td>low=2, moderate=1, high=0</td></tr>
        <tr><td>Drainage Quality</td><td>2.0</td><td>mod well=2, poorly=1, very poorly=0</td></tr>
        <tr><td><strong>Total</strong></td><td><strong>10</strong></td><td></td></tr>
        </table>
        <h3>Data Sources</h3>
        <ul>
        <li><strong>Field Boundaries:</strong> OpenStreetMap / Overpass API</li>
        <li><strong>Weather:</strong> NASA POWER (daily, 2021–2025)</li>
        <li><strong>Soil:</strong> USDA NRCS SSURGO database</li>
        <li><strong>NDVI:</strong> Sentinel-2 + Landsat yearly composites</li>
        <li><strong>Crop Rotation:</strong> USDA NASS CDL (2021–2025)</li>
        </ul>
        <h3>Limitations</h3>
        <ul>
        <li>No actual yield data — NDVI serves as a vegetation health proxy</li>
        <li>Soil data from SSURGO may not reflect within-field variability</li>
        <li>5-year window limits long-term trend detection</li>
        <li>Weather data from NASA POWER is grid-interpolated (not on-site station)</li>
        </ul>
        </div>
        """)

        # Top variables
        top_vars_html = "<ol>\n"
        for name, desc in self.kpis.get("top_vars", []):
            top_vars_html += f"<li><strong>{name}</strong> — {desc}</li>\n"
        top_vars_html += "</ol>\n"

        # KPI cards
        kpi_cards = f"""
<div class="kpi-card"><div class="kpi-icon">📋</div><div class="value" id="kpi-fields">{initial.get('fields', 'N/A')}</div><div class="kpi-delta" id="delta-fields">—</div><div class="label">Fields</div><div class="kpi-status na" id="status-fields">—</div></div>
<div class="kpi-card"><div class="kpi-icon">📐</div><div class="value" id="kpi-acres">{initial.get('acres', 'N/A')}</div><div class="kpi-delta" id="delta-acres">—</div><div class="label">Acres</div><div class="kpi-status na" id="status-acres">—</div></div>
<div class="kpi-card"><div class="kpi-icon">🌿</div><div class="value" id="kpi-ndvi">{initial.get('ndvi', 'N/A')}</div><div class="kpi-delta" id="delta-ndvi"></div><div class="label">Avg NDVI</div><div class="kpi-status" id="status-ndvi"></div></div>
<div class="kpi-card"><div class="kpi-icon">🌧️</div><div class="value" id="kpi-rainfall">{initial.get('rainfall', 'N/A')} mm</div><div class="kpi-delta" id="delta-rainfall"></div><div class="label">Rainfall</div><div class="kpi-status" id="status-rainfall"></div></div>
<div class="kpi-card"><div class="kpi-icon">🌡️</div><div class="value" id="kpi-gdd">{initial.get('gdd', 'N/A')}</div><div class="kpi-delta" id="delta-gdd"></div><div class="label">GDD</div><div class="kpi-status" id="status-gdd"></div></div>
<div class="kpi-card"><div class="kpi-icon">📆</div><div class="value" id="kpi-season">{initial.get('season_span', 'N/A')}</div><div class="kpi-delta" id="delta-season"></div><div class="label">Season Days</div><div class="kpi-status" id="status-season"></div></div>
<div class="kpi-card"><div class="kpi-icon">🌾</div><div class="value" id="kpi-crop">{next(iter(initial.get('crop_breakdown', {})), 'N/A')}</div><div class="kpi-delta" id="delta-crop"></div><div class="label">Top Crop</div><div class="kpi-status na" id="status-crop">—</div></div>
<div class="kpi-card"><div class="kpi-icon">🧪</div><div class="value" id="kpi-shs">{initial.get('shs', 'N/A')}/10</div><div class="kpi-delta" id="delta-shs">—</div><div class="label">Soil Health</div><div class="kpi-status" id="status-shs"></div></div>
<div class="kpi-card"><div class="kpi-icon">♻️</div><div class="value" id="kpi-sust">{initial.get('sust', 'N/A')}/10</div><div class="kpi-delta" id="delta-sust">—</div><div class="label">Sustainability</div><div class="kpi-status" id="status-sust"></div></div>
"""

        # Replace placeholders in HTML template
        html = (
            html_tpl.replace("/*CSS_PLACEHOLDER*/", css)
            .replace("/*JS_PLACEHOLDER*/", js_code)
            .replace("{{display_name}}", self.display_name)
            .replace("{{county_info}}", f"Kossuth County, Iowa — Decision-support tool for {len(self.fields)} fields")
            .replace("{{year_options}}", year_opts)
            .replace("{{month_options}}", month_opts)
            .replace("{{field_options}}", field_opts)
            .replace("{{kpi_cards}}", kpi_cards)
            .replace("{{narrative1}}", initial_narr.get("section1", ""))
            .replace("{{narrative2}}", initial_narr.get("section2", ""))
            .replace("{{narrative3}}", initial_narr.get("section3", ""))
            .replace("{{narrative4}}", initial_narr.get("section4", ""))
            .replace("{{map_html}}", map_html)
            .replace("{{chart_correlations}}", chart_html.get("correlations", ""))
            .replace("{{chart_ndvi_variability}}", chart_html.get("ndvi_variability", ""))
            .replace("{{methodology_html}}", methodology_html)
            .replace("{{rec_list_initial}}", initial_narr.get("section4", ""))
            .replace("{{top_vars_html}}", top_vars_html)
            .replace("{{footer_text}}", "Generated by the my-farm-advisor grower-field-dashboard • Data: OSM, NASA POWER, NRCS SSURGO, USDA CDL, Sentinel-2 & Landsat")
        )
        return html

    # ---- Main entry point ---------------------------------------------

    def generate(self, output_path: Optional[str] = None) -> str:
        """Run the full pipeline and write dashboard.html."""
        print(f"Loading data for grower: {self.grower_slug}...")
        self._discover_and_load()
        print(f"  Discovered {len(self.fields)} fields across "
              f"{len(self.farms)} farm(s)")

        print("Computing KPIs...")
        self._compute_kpis()

        print("Generating narrative...")
        narrative = self._generate_narrative()

        print("Building embedded data for filters...")
        embedded_data = self._build_embedded_data()

        print("Creating visualizations...")
        chart_html = {
            "ndvi_variability": self._create_ndvi_variability_map(),
            "correlations": self._create_environmental_correlations(),
        }

        print("Building interactive map...")
        map_html = self._create_interactive_map(year=DEFAULT_YEAR, pixel_data=embedded_data.get("map_px", {}))

        print("Assembling dashboard HTML...")
        html = self._render_html(narrative, map_html, chart_html, embedded_data)

        out = Path(output_path or (
            self.grower_path / "derived" / "reports"
            / "grower_field_dashboard.html"
        ))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"\nDashboard written to: {out.resolve()}")
        return str(out.resolve())


def generate_grower_dashboard(
    grower_slug: str = "ia-grower",
    data_root: str = "/home/coder/my-farm-advisor-runtime/data-pipeline",
    output_path: Optional[str] = None,
) -> str:
    """Convenience function to generate a grower dashboard.

    Args:
        grower_slug: Grower identifier (e.g. "ia-grower").
        data_root: Path to the data-pipeline runtime root.
        output_path: Where to write dashboard.html.
            Defaults to growers/{slug}/derived/reports/grower_field_dashboard.html.

    Returns:
        Absolute path to the generated dashboard HTML.
    """
    gen = GrowerDashboardGenerator(grower_slug=grower_slug, data_root=data_root)
    return gen.generate(output_path=output_path)


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "ia-grower"
    generate_grower_dashboard(grower_slug=slug)
