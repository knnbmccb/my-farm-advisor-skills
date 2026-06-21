#!/usr/bin/env python3
"""Generate a lightweight interactive grower-level web map.

Usage:
    python scripts/reporting/generate_grower_web_map.py \
        --grower-slug il-grower

Outputs a single self-contained HTML file at:
    growers/<grower-slug>/derived/reports/grower_web_map.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

from runtime_paths import resolve_runtime_paths  # noqa: E402

_RUNTIME_PATHS = resolve_runtime_paths()
_DATA_ROOT = _RUNTIME_PATHS.runtime_base
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from paths import (  # noqa: E402
    farm_boundary_path,
    grower_dir,
)


# ---------------------------------------------------------------------------
# Colour palette -- one colour per farm
# ---------------------------------------------------------------------------
_FARM_COLORS = [
    "#2E7D32",  # green
    "#1565C0",  # blue
    "#C62828",  # red
    "#F9A825",  # yellow
    "#6A1B9A",  # purple
    "#00838F",  # teal
    "#D84315",  # orange
    "#37474F",  # grey
]


def _discover_farms(grower_slug: str) -> list[dict[str, Any]]:
    """Return every farm under *grower_slug* that has a boundary file."""
    farms_dir = grower_dir(grower_slug) / "farms"
    farms: list[dict[str, Any]] = []
    if not farms_dir.is_dir():
        return farms
    for farm_slug_dir in sorted(farms_dir.glob("*")):
        if not farm_slug_dir.is_dir():
            continue
        farm_slug = farm_slug_dir.name
        boundary = farm_boundary_path(grower_slug, farm_slug)
        if boundary.exists():
            farms.append({"farm_slug": farm_slug, "boundary_path": boundary})
    return farms


def _load_weather_for_fields(grower_slug: str, farms: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Load and aggregate daily weather to monthly growing-season summaries.
    
    Returns: {field_id: {"2021-04": {"tavg": 12.3, "tmax": 18.5, "tmin": 6.1, "precip": 45.2, "solar": 15.3}, ...}}
    """
    weather_by_field: dict[str, dict[str, dict[str, Any]]] = {}
    
    for farm in farms:
        farm_slug = farm["farm_slug"]
        farm_dir = grower_dir(grower_slug) / "farms" / farm_slug
        fields_dir = farm_dir / "fields"
        
        if not fields_dir.is_dir():
            continue
            
        for field_dir in fields_dir.glob("*"):
            if not field_dir.is_dir():
                continue
            field_id = field_dir.name
            weather_csv = field_dir / "weather" / "daily_weather.csv"
            
            if not weather_csv.exists():
                continue
                
            try:
                df = pd.read_csv(weather_csv, parse_dates=["date"])
                df["year"] = df["date"].dt.year
                df["month"] = df["date"].dt.month
                df["year_month"] = df["date"].dt.strftime("%Y-%m")
                
                # Filter growing season: Apr-Oct
                gs = df[(df["month"] >= 4) & (df["month"] <= 10)]
                
                if gs.empty:
                    continue
                    
                monthly = gs.groupby("year_month").agg({
                    "T2M": "mean",
                    "T2M_MAX": "max",
                    "T2M_MIN": "min",
                    "PRECTOTCORR": "sum",
                    "ALLSKY_SFC_SW_DWN": "mean",
                }).reset_index()
                
                field_weather: dict[str, dict[str, Any]] = {}
                for _, row in monthly.iterrows():
                    ym = row["year_month"]
                    field_weather[ym] = {
                        "tavg": round(float(row["T2M"]), 1),
                        "tmax": round(float(row["T2M_MAX"]), 1),
                        "tmin": round(float(row["T2M_MIN"]), 1),
                        "precip": round(float(row["PRECTOTCORR"]), 1),
                        "solar": round(float(row["ALLSKY_SFC_SW_DWN"]), 1),
                    }
                
                if field_weather:
                    weather_by_field[field_id] = field_weather
                    
            except Exception as e:
                print(f"  warn  Could not load weather for {field_id}: {e}")
                continue
    
    return weather_by_field


def _generate_grower_html(
    grower_slug: str,
    farms: list[dict[str, Any]],
    output_path: Path,
    weather_data: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> Path:
    """Build a single self-contained Leaflet HTML map for the grower."""

    # --- Load all GeoJSON features, tagged with farm info -------------------
    all_features: list[dict[str, Any]] = []
    farm_info: list[dict[str, str]] = []
    bounds_lonlat: list[list[float]] = []  # [[min_lon, min_lat], [max_lon, max_lat]]

    for idx, farm in enumerate(farms):
        gdf = gpd.read_file(farm["boundary_path"]).to_crs("EPSG:4326")
        if gdf.empty:
            continue
        farm_name = farm.get("farm_name", farm["farm_slug"].replace("-", " ").title())
        color = _FARM_COLORS[idx % len(_FARM_COLORS)]
        farm_info.append(
            {
                "slug": farm["farm_slug"],
                "name": farm_name,
                "color": color,
                "field_count": str(len(gdf)),
            }
        )

        b = gdf.total_bounds  # [minx, miny, maxx, maxy]
        bounds_lonlat.append([b[0], b[1]])
        bounds_lonlat.append([b[2], b[3]])

        geojson = json.loads(gdf.to_json())
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            props["_farm_slug"] = farm["farm_slug"]
            props["_farm_name"] = farm_name
            props["_farm_color"] = color
            # Ensure friendly labels exist
            if "field_id" not in props:
                props["field_id"] = "unknown"
            if "area_acres" not in props:
                # compute area if missing
                try:
                    area = (
                        gpd.GeoSeries([feature["geometry"]], crs="EPSG:4326")
                        .to_crs("EPSG:5070")
                        .area.iloc[0]
                    )
                    props["area_acres"] = area * 0.000247105
                except Exception:
                    props["area_acres"] = 0.0
            all_features.append(feature)

    if not all_features:
        raise RuntimeError(f"No field boundaries found for grower {grower_slug}")

    # Overall bounds
    min_lon = min(p[0] for p in bounds_lonlat)
    min_lat = min(p[1] for p in bounds_lonlat)
    max_lon = max(p[0] for p in bounds_lonlat)
    max_lat = max(p[1] for p in bounds_lonlat)
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2

    # Distance heuristic for zoom
    max_span = max(max_lon - min_lon, max_lat - min_lat)
    zoom = max(5, min(14, int(14 - max_span * 2)))

    feature_collection = {"type": "FeatureCollection", "features": all_features}
    geojson_js = json.dumps(feature_collection)
    farms_js = json.dumps(farm_info)
    weather_js = json.dumps(weather_data or {})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{grower_slug} -- Grower Web Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; height: 100vh; display: flex; overflow: hidden; }}
  #sidebar {{ width: 280px; background: #fff; border-right: 1px solid #ddd; display: flex; flex-direction: column; }}
  #sidebar header {{ padding: 1rem; background: #1e3a5f; color: #fff; }}
  #sidebar header h1 {{ font-size: 1.1rem; margin-bottom: 0.25rem; }}
  #sidebar header p {{ font-size: 0.8rem; opacity: 0.85; }}
  #field-list {{ flex: 1; overflow-y: auto; padding: 0.5rem 0; }}
  .farm-group {{ margin-bottom: 0.75rem; }}
  .farm-group h3 {{ font-size: 0.8rem; text-transform: uppercase; color: #666; padding: 0.5rem 1rem; letter-spacing: 0.5px; }}
  .field-item {{ display: flex; align-items: center; padding: 0.5rem 1rem; cursor: pointer; transition: background 0.15s; border-left: 4px solid transparent; }}
  .field-item:hover {{ background: #f0f4f8; }}
  .field-item .swatch {{ width: 14px; height: 14px; border-radius: 3px; margin-right: 0.6rem; flex-shrink: 0; border: 1px solid rgba(0,0,0,0.15); }}
  .field-item .label {{ font-size: 0.88rem; color: #1e293b; line-height: 1.3; }}
  .field-item .sub {{ font-size: 0.75rem; color: #64748b; }}
  #map {{ flex: 1; }}
  .leaflet-popup-content-wrapper {{ border-radius: 8px; }}
  .leaflet-popup-content {{ font-size: 0.9rem; line-height: 1.5; margin: 10px 14px; }}
  .popup-row {{ display: flex; justify-content: space-between; gap: 1rem; }}
  .popup-row:not(:last-child) {{ margin-bottom: 4px; }}
  .popup-label {{ color: #64748b; font-size: 0.8rem; }}
  .popup-value {{ font-weight: 600; color: #1e293b; }}
  .weather-section {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0; }}
  .weather-title {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
  .weather-row {{ display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.82rem; }}
  .weather-row span:first-child {{ color: #64748b; }}
  .weather-row span:last-child {{ font-weight: 600; color: #1e293b; }}
  #weather-slider-container {{ padding: 0.75rem 1rem; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
  #weather-slider-container label {{ font-size: 0.75rem; color: #64748b; display: block; margin-bottom: 0.3rem; }}
  #month-slider {{ width: 100%; }}
  #month-display {{ font-size: 0.85rem; font-weight: 600; color: #1e293b; margin-top: 0.3rem; }}
  @media (max-width: 640px) {{
    body {{ flex-direction: column; }}
    #sidebar {{ width: 100%; height: 180px; border-right: none; border-bottom: 1px solid #ddd; }}
  }}
</style>
</head>
<body>
<div id="sidebar">
  <header>
    <h1>{grower_slug.replace("-", " ").title()}</h1>
    <p>{len(farm_info)} farm(s) &middot; {len(all_features)} field(s)</p>
  </header>
  <div id="weather-slider-container">
    <label>Growing Season Weather</label>
    <input type="range" id="month-slider" min="0" max="0" value="0" step="1">
    <div id="month-display">Select a month</div>
  </div>
  <div id="field-list"></div>
</div>
<div id="map"></div>

<script>
  const map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});

  const osmLayer = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
  }});

  const satelliteLayer = L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
    {{ attribution: 'Esri', maxZoom: 18 }}
  ).addTo(map);

  L.control.layers(
    {{ 'OpenStreetMap': osmLayer, 'Satellite': satelliteLayer }},
    null,
    {{ position: 'topright', collapsed: true }}
  ).addTo(map);

  const geojsonData = {geojson_js};
  const farms = {farms_js};
  const weatherData = {weather_js};

  const layers = {{}};
  const fieldList = document.getElementById('field-list');
  
  // --- Month slider setup ---
  const monthSlider = document.getElementById('month-slider');
  const monthDisplay = document.getElementById('month-display');
  const monthNames = ['Apr','May','Jun','Jul','Aug','Sep','Oct'];
  
  // Collect all unique year-months across all fields
  const allMonths = new Set();
  for (const fieldWeather of Object.values(weatherData)) {{
    for (const ym of Object.keys(fieldWeather)) {{
      allMonths.add(ym);
    }}
  }}
  const sortedMonths = Array.from(allMonths).sort();
  
  if (sortedMonths.length > 0) {{
    monthSlider.min = 0;
    monthSlider.max = sortedMonths.length - 1;
    monthSlider.value = sortedMonths.length - 1; // default to latest
    updateMonthDisplay();
  }}
  
  function updateMonthDisplay() {{
    const idx = parseInt(monthSlider.value);
    const ym = sortedMonths[idx];
    if (ym) {{
      const parts = ym.split('-');
      const y = parts[0];
      const m = parts[1];
      monthDisplay.textContent = monthNames[parseInt(m)-4] + ' ' + y;
    }}
  }}
  
  monthSlider.addEventListener('input', function() {{
    updateMonthDisplay();
    // Update all open popups
    for (const layerGroup of Object.values(layers)) {{
      layerGroup.eachLayer(function(layer) {{
        if (layer.isPopupOpen()) {{
          layer.setPopupContent(buildPopupContent(layer.feature.properties));
        }}
      }});
    }}
  }});
  
  function getCurrentMonth() {{
    return sortedMonths[parseInt(monthSlider.value)] || null;
  }}
  
  function buildPopupContent(p) {{
    const area = (parseFloat(p.area_acres) || 0).toFixed(1);
    const fieldId = p.field_id;
    const currentMonth = getCurrentMonth();
    const w = currentMonth && weatherData[fieldId] ? weatherData[fieldId][currentMonth] : null;
    
    let html = `
      <div class="popup-row"><span class="popup-label">Grower</span><span class="popup-value">{grower_slug}</span></div>
      <div class="popup-row"><span class="popup-label">Farm</span><span class="popup-value">${{p._farm_name}}</span></div>
      <div class="popup-row"><span class="popup-label">Field</span><span class="popup-value">${{p.field_id}}</span></div>
      <div class="popup-row"><span class="popup-label">Area</span><span class="popup-value">${{area}} ac</span></div>
      <div class="popup-row"><span class="popup-label">County</span><span class="popup-value">${{p.county_name || '--'}}</span></div>
    `;
    
    if (w) {{
      html += `
        <div class="weather-section">
          <div class="weather-title">Weather — ${{monthDisplay.textContent}}</div>
          <div class="weather-row"><span>Avg Temp</span><span>${{w.tavg}}°C</span></div>
          <div class="weather-row"><span>Max / Min</span><span>${{w.tmax}}° / ${{w.tmin}}°C</span></div>
          <div class="weather-row"><span>Precipitation</span><span>${{w.precip}} mm</span></div>
          <div class="weather-row"><span>Solar Radiation</span><span>${{w.solar}} MJ/m²</span></div>
        </div>
      `;
    }}
    
    return html;
  }}

  // Group features by farm
  const featuresByFarm = {{}};
  geojsonData.features.forEach(f => {{
    const slug = f.properties._farm_slug;
    if (!featuresByFarm[slug]) featuresByFarm[slug] = [];
    featuresByFarm[slug].push(f);
  }});

  farms.forEach(farm => {{
    const group = document.createElement('div');
    group.className = 'farm-group';
    const heading = document.createElement('h3');
    heading.textContent = farm.name;
    group.appendChild(heading);

    const farmFeatures = featuresByFarm[farm.slug] || [];
    const geoLayer = L.geoJSON(farmFeatures, {{
      style: {{
        color: '#FFFFFF',
        weight: 3,
        opacity: 1,
        fillOpacity: 0.15,
        fillColor: farm.color
      }},
      onEachFeature: function(feature, layer) {{
        const p = feature.properties;
        const area = (parseFloat(p.area_acres) || 0).toFixed(1);
        layer.bindPopup(buildPopupContent(p));

        // Build sidebar item
        const item = document.createElement('div');
        item.className = 'field-item';
        item.innerHTML = `
          <div class="swatch" style="background:${{farm.color}}"></div>
          <div>
            <div class="label">${{p.field_id}}</div>
            <div class="sub">${{area}} ac &middot; ${{p.county_name || ''}}</div>
          </div>
        `;
        item.addEventListener('click', () => {{
          map.fitBounds(layer.getBounds(), {{ padding: [40, 40], maxZoom: 16 }});
          layer.openPopup();
        }});
        group.appendChild(item);
      }}
    }}).addTo(map);

    layers[farm.slug] = geoLayer;
    fieldList.appendChild(group);
  }});

  // Fit to all fields
  const allLayers = Object.values(layers);
  if (allLayers.length) {{
    const group = L.featureGroup(allLayers);
    map.fitBounds(group.getBounds(), {{ padding: [50, 50] }});
  }}
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate grower-level interactive web map")
    parser.add_argument("--grower-slug", required=True, help="Grower slug")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path (defaults to growers/<slug>/derived/reports/grower_web_map.html)",
    )
    args = parser.parse_args()

    farms = _discover_farms(args.grower_slug)
    if not farms:
        print(f"ERROR: No farms with boundaries found for grower '{args.grower_slug}'")
        sys.exit(1)

    print(f"Found {len(farms)} farm(s) for grower '{args.grower_slug}'")

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = (
            grower_dir(args.grower_slug)
            / "derived"
            / "reports"
            / "grower_web_map.html"
        )

    weather = _load_weather_for_fields(args.grower_slug, farms)
    print(f"  Loaded weather for {len(weather)} field(s)")
    
    result = _generate_grower_html(args.grower_slug, farms, output_path, weather)
    size_kb = result.stat().st_size / 1024
    print(f"  ok  Grower web map ({size_kb:.1f} KB)")
    print(f"      {result}")


if __name__ == "__main__":
    main()
