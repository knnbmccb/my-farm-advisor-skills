// ---- Constants ----
const NDVI_BACKDROP_CS = /*NDVI_BACKDROP_CS*/;

const MONTH_NAMES = {
    '04': 'April', '05': 'May', '06': 'June', '07': 'July',
    '08': 'August', '09': 'September', '10': 'October'
};

// ---- Data ----
const DATA = /*EMBEDDED_DATA*/;

// ---- State ----
let currentMapView = 'ndvi';

// ---- Helpers ----
function round(value, decimals) {
    const factor = Math.pow(10, decimals);
    return Math.round(value * factor) / factor;
}

function getMonthlyPixelData(year, month, field) {
    const monthNum = parseInt(month, 10);
    if (monthNum < 4 || monthNum > 10) return null;

    let yrData = DATA.map_px_monthly && DATA.map_px_monthly[year];
    let moData = yrData && yrData[month];
    let fallback = false;

    // Fallback to previous months (backwards through the year)
    if (!moData) {
        const months = ['10', '09', '08', '07', '06', '05', '04'];
        const idx = months.indexOf(month);
        for (let i = idx + 1; i < months.length; i++) {
            if (yrData && yrData[months[i]]) {
                moData = yrData[months[i]];
                fallback = true;
                break;
            }
        }
    }

    if (!moData) return null;

    if (field !== 'all') {
        const entry = moData[field];
        if (!entry) return null;
        return {
            lon: entry.lon, lat: entry.lat, raw: entry.raw, norm: entry.norm,
            mean: entry.mean, min: entry.min, max: entry.max,
            scene_date: entry.scene_date, source: entry.source, fallback: fallback
        };
    }

    const allLons = [];
    const allLats = [];
    const allRaw = [];
    const allNorm = [];
    let globalMin = Infinity;
    let globalMax = -Infinity;

    for (const f of DATA.fields) {
        const entry = moData[f.id];
        if (entry) {
            allLons.push(...entry.lon);
            allLats.push(...entry.lat);
            allRaw.push(...entry.raw);
            allNorm.push(...entry.norm);
            globalMin = Math.min(globalMin, entry.min);
            globalMax = Math.max(globalMax, entry.max);
        }
    }

    if (allLons.length === 0) return null;
    return {
        lon: allLons, lat: allLats, raw: allRaw, norm: allNorm,
        mean: allRaw.reduce((a, b) => a + b, 0) / allRaw.length,
        min: globalMin, max: globalMax,
        scene_date: null, source: null, fallback: fallback
    };
}

// ---- Map functions ----
function setMapView(view) {
    currentMapView = view;
    const mapEl = document.getElementById('choropleth-map');
    if (!mapEl || typeof Plotly === 'undefined') return;

    const btnN = document.getElementById('btn-ndvi');
    const btnS = document.getElementById('btn-soil');
    if (btnN) btnN.classList.toggle('active', view === 'ndvi');
    if (btnS) btnS.classList.toggle('active', view === 'soil');

    if (view === 'ndvi') {
        const year = document.getElementById('year-filter').value;
        const month = document.getElementById('month-filter').value;
        const field = document.getElementById('field-filter').value;

        // Choropleth: use monthly scene means if available, else yearly composite
        let ndviVals;
        const monthlyMeta = DATA.monthly_ndvi && DATA.monthly_ndvi[year] && DATA.monthly_ndvi[year][month];
        if (monthlyMeta) {
            ndviVals = DATA.fields.map(f => monthlyMeta[f.id] ? monthlyMeta[f.id].mean : 0.0);
        } else {
            // Fallback to previous months for choropleth
            const months = ['10', '09', '08', '07', '06', '05', '04'];
            const idx = months.indexOf(month);
            let fallbackMeta = null;
            for (let i = idx + 1; i < months.length; i++) {
                fallbackMeta = DATA.monthly_ndvi && DATA.monthly_ndvi[year] && DATA.monthly_ndvi[year][months[i]];
                if (fallbackMeta) break;
            }
            if (fallbackMeta) {
                ndviVals = DATA.fields.map(f => fallbackMeta[f.id] ? fallbackMeta[f.id].mean : 0.0);
            } else {
                ndviVals = (DATA.map_ndvi[year] || []).map(v => v !== null && v !== undefined ? v : 0.0);
            }
        }

        // Autoscale choropleth range
        const validNdvi = ndviVals.filter(v => v > 0);
        let zmin = 0.2, zmax = 0.6;
        if (validNdvi.length > 0) {
            zmin = Math.min(...validNdvi);
            zmax = Math.max(...validNdvi);
            if (zmax - zmin < 0.1) { zmax = zmin + 0.1; }
        }

        Plotly.restyle('choropleth-map', {
            'z': [ndviVals],
            'colorscale': [NDVI_BACKDROP_CS],
            'zmin': [zmin],
            'zmax': [zmax],
            'showscale': [false],
        }, 0);
        updateMapPixels(year, month, field);
    } else {
        const soilScores = DATA.fields.map(f => f.soil_score || 0);
        Plotly.restyle('choropleth-map', {
            'z': [soilScores],
            'colorscale': ['YlGn'],
            'zmin': [5.0],
            'zmax': [10.0],
            'showscale': [true],
        }, 0);
        Plotly.restyle('choropleth-map', {'visible': [false]}, 1);
    }
}

function updateMapPixels(year, month, field) {
    const mapEl = document.getElementById('choropleth-map');
    if (!mapEl || typeof Plotly === 'undefined') return;
    if (currentMapView !== 'ndvi') return;

    const monthly = getMonthlyPixelData(year, month, field);
    if (monthly && monthly.lon.length > 0) {
        // Use actual scene pixels
        Plotly.restyle('choropleth-map', {
            'lon': [monthly.lon],
            'lat': [monthly.lat],
            'marker.color': [monthly.norm],
            'customdata': [monthly.raw],
            'visible': [true],
        }, 1);
        // Update colorbar with raw NDVI tick labels
        const rawMin = monthly.min;
        const rawMax = monthly.max;
        const tickVals = [0, 0.25, 0.5, 0.75, 1.0];
        const tickText = tickVals.map(t => (rawMin + t * (rawMax - rawMin)).toFixed(2));
        Plotly.restyle('choropleth-map', {
            'marker.colorbar.tickvals': [tickVals],
            'marker.colorbar.ticktext': [tickText],
            'marker.colorbar.title.text': 'NDVI (raw)',
        }, 1);
    } else {
        // Fallback to yearly composite pixels
        const yearNorm = (DATA.map_px && DATA.map_px.norm_vals && DATA.map_px.norm_vals[year]) || [];
        const yearRaw = (DATA.map_px && DATA.map_px.vals && DATA.map_px.vals[year]) || [];
        const lons = DATA.map_px.lon || [];
        const lats = DATA.map_px.lat || [];
        const validLons = [];
        const validLats = [];
        const validNorm = [];
        const validRaw = [];
        for (let i = 0; i < yearNorm.length; i++) {
            const n = yearNorm[i];
            const r = yearRaw[i];
            if (n !== null && n !== undefined && r !== null && r !== undefined) {
                validLons.push(lons[i]);
                validLats.push(lats[i]);
                validNorm.push(n);
                validRaw.push(r);
            }
        }
        if (validNorm.length > 0) {
            Plotly.restyle('choropleth-map', {
                'lon': [validLons],
                'lat': [validLats],
                'marker.color': [validNorm],
                'customdata': [validRaw],
                'visible': [true],
            }, 1);
            Plotly.restyle('choropleth-map', {
                'marker.colorbar.tickvals': [[0, 0.25, 0.5, 0.75, 1.0]],
                'marker.colorbar.ticktext': [['0.20', '0.30', '0.40', '0.50', '0.60']],
                'marker.colorbar.title.text': 'NDVI (yearly avg)',
            }, 1);
        } else {
            Plotly.restyle('choropleth-map', {'visible': [false]}, 1);
        }
    }
}

// ---- Utilities ----
function fmt(v, suffix) {
    if (v === null || v === undefined) return 'N/A';
    return v + (suffix || '');
}

function kpiVal(v, decimals) {
    if (v === null || v === undefined) return 'N/A';
    if (typeof v === 'number' && decimals !== undefined) return v.toFixed(decimals);
    return v;
}

function topCropText(cropBreakdown) {
    if (!cropBreakdown || typeof cropBreakdown !== 'object') return 'N/A';
    const entries = Object.entries(cropBreakdown);
    if (entries.length === 0) return 'N/A';
    entries.sort((a, b) => b[1] - a[1]);
    const [crop, pct] = entries[0];
    return crop + ' (' + pct + '%)';
}

function prettifyFieldId(fid) {
    return fid.replace('osm-', '').replace('ia-new-', '').replace(/_/g, '-');
}

function buildNarrative1(data, year, field) {
    if (!data || !data.total) return 'No NDVI data available for the selected filters.';
    const yrLabel = year === 'all' ? 'across all years' : 'in ' + year;
    let txt = 'Mean NDVI across ' + data.total + ' field(s) ' + yrLabel + ' is ' + data.avg_ndvi.toFixed(3) + '. ';
    if (data.best && data.worst && data.best !== data.worst) {
        txt += 'Field ' + prettifyFieldId(data.best) + ' leads at ' + data.best_ndvi.toFixed(3) + ', ';
        txt += 'while ' + prettifyFieldId(data.worst) + ' trails at ' + data.worst_ndvi.toFixed(3) + '.';
    } else if (data.best) {
        txt += 'Field ' + prettifyFieldId(data.best) + ' has NDVI of ' + data.best_ndvi.toFixed(3) + '.';
    }
    return txt;
}

function buildNarrative2(data, year, field) {
    if (!data || !data.best) return 'No NDVI ranking data available.';
    let txt = '';
    if (data.best && data.worst && data.best !== data.worst) {
        txt += 'Field ' + prettifyFieldId(data.best) + ' leads with mean NDVI of ' + data.best_ndvi.toFixed(3) + ', ';
        txt += 'while ' + prettifyFieldId(data.worst) + ' trails at ' + data.worst_ndvi.toFixed(3) + '. ';
    } else if (data.best) {
        txt += 'Field ' + prettifyFieldId(data.best) + ' has mean NDVI of ' + data.best_ndvi.toFixed(3) + '. ';
    }
    txt += 'Crop type explains part of this gap — soybeans average higher NDVI than corn — ';
    txt += 'but the key finding is the correlation between NDVI and soil organic matter, ';
    txt += 'which ties crop health directly to soil variability.';
    return txt;
}

function buildNarrative3(data, year, field) {
    if (!data) return 'No soil data available.';
    let txt = '';
    if (data.avg_shs !== null && data.avg_shs !== undefined) {
        txt += 'Mean Soil Health Score is ' + data.avg_shs + '/10. ';
    }
    if (data.low_shs && data.low_shs.length > 0) {
        const lowStr = data.low_shs.map(([fid, score]) => prettifyFieldId(fid) + ' (' + score + ')').join(', ');
        txt += lowStr + ' score below 7.0, indicating opportunities for improvement through cover cropping or organic amendment. ';
    }
    if (data.cont_fields && data.cont_fields.length > 0) {
        const contStr = data.cont_fields.slice(0, 3).map(fid => prettifyFieldId(fid)).join(', ');
        txt += 'Continuous monoculture fields (' + contStr + ') show the highest soil risk, reinforcing that crop health and soil health are tightly linked.';
    } else {
        txt += 'All fields show crop rotation diversity, which supports long-term soil health.';
    }
    return txt;
}

function buildRecs(data, year, field) {
    if (!data) return '';
    const recs = [];
    if (data.low_shs && data.low_shs.length > 0) {
        const lowIds = data.low_shs.map(fid => prettifyFieldId(fid));
        recs.push('Introduce cover crops on fields ' + lowIds.join(', ') + ' to rebuild organic matter and improve water storage.');
    }
    if (data.cont_fields && data.cont_fields.length > 0) {
        const contShort = data.cont_fields.map(fid => prettifyFieldId(fid));
        recs.push('Break continuous cropping on fields ' + contShort.join(', ') + ' with a rotational year to restore soil biology and reduce pest pressure.');
    }
    if (data.avg_aws !== null && data.avg_aws !== undefined && data.avg_aws < 4.0) {
        recs.push('Prioritize drought-tolerant hybrid selection on fields with below-average Available Water Storage (<4 inches).');
    }
    recs.push('Continue monitoring NDVI trends annually to detect field-level stress before visible symptoms appear.');
    return recs.slice(0, 4).map((r, i) => '<li>' + (i + 1) + '. ' + r + '</li>').join('');
}

function statusFor(metric, value) {
    if (value === null || value === undefined) return { text: 'N/A', cls: 'na' };
    let h, m_low;
    switch (metric) {
        case 'ndvi':    h = 0.45; m_low = 0.30; break;
        case 'rain':    h = [400, 650]; m_low = 350; break;
        case 'gdd':     h = 2700; m_low = 2400; break;
        case 'season':  h = 200; m_low = 185; break;
        case 'shs':     h = 7.5; m_low = 6.0; break;
        case 'sust':    h = 7.5; m_low = 6.0; break;
        default: return { text: '—', cls: 'na' };
    }
    if (metric === 'rain') {
        if (value >= h[0] && value <= h[1]) return { text: 'Healthy', cls: 'healthy' };
        if (value >= m_low && value < h[0]) return { text: 'Moderate', cls: 'moderate' };
        return { text: 'At Risk', cls: 'atrisk' };
    }
    if (value >= h) return { text: 'Healthy', cls: 'healthy' };
    if (value >= m_low) return { text: 'Moderate', cls: 'moderate' };
    return { text: 'At Risk', cls: 'atrisk' };
}

function getDelta(cur, prev, decimals, unit, prevYear) {
    if (cur === null || cur === undefined || prev === null || prev === undefined) return { txt: 'No prior year', cls: 'flat' };
    const d = cur - prev;
    if (Math.abs(d) < 1e-9) return { txt: 'No change vs ' + prevYear, cls: 'flat' };
    const arrow = d > 0 ? '▲' : '▼';
    return { txt: arrow + ' ' + Math.abs(d).toFixed(decimals) + (unit || '') + ' vs ' + prevYear, cls: d > 0 ? 'up' : 'down' };
}

function setDelta(id, delta) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = delta.txt;
    el.className = 'kpi-delta ' + delta.cls;
}

function setStatus(id, status) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = status.text;
    el.className = 'kpi-status ' + status.cls;
}

function prevMonth(mo) {
    const order = ['04', '05', '06', '07', '08', '09', '10'];
    const idx = order.indexOf(mo);
    return idx > 0 ? order[idx - 1] : null;
}

function monthlyKpi(field, year, month) {
    if (!DATA.monthly || !DATA.monthly[field]) return null;
    const yr = DATA.monthly[field][year];
    if (!yr) return null;
    return yr[month] || null;
}

// ---- Main Dashboard Update ----
function updateDashboard() {
    const year = document.getElementById('year-filter').value;
    const month = document.getElementById('month-filter').value;
    const field = document.getElementById('field-filter').value;
    const key = year + '_' + field;
    const monthName = MONTH_NAMES[month] || month;
    const prevMo = prevMonth(month);

    let kpi = DATA.kpis[key];
    if (!kpi) {
        kpi = {
            fields: null, acres: null, ndvi: null, rainfall: null,
            gdd: null, temp: null, shs: null, sust: null,
            crop_breakdown: null, season_span: null,
        };
    }

    // Monthly weather KPIs (computed from DATA.monthly)
    let mKpi = null, prevMKpi = null;
    if (field === 'all') {
        const fields = DATA.fields;
        let rainSum = 0, gddSum = 0, tempSum = 0, seasonSum = 0, count = 0;
        let prevRainSum = 0, prevGddSum = 0, prevTempSum = 0, prevSeasonSum = 0, prevCount = 0;
        for (const f of fields) {
            const mk = monthlyKpi(f.id, year, month);
            if (mk) {
                rainSum += mk.rain; gddSum += mk.gdd; tempSum += mk.temp;
                seasonSum += mk.season_days; count++;
            }
            if (prevMo) {
                const pmk = monthlyKpi(f.id, year, prevMo);
                if (pmk) {
                    prevRainSum += pmk.rain; prevGddSum += pmk.gdd; prevTempSum += pmk.temp;
                    prevSeasonSum += pmk.season_days; prevCount++;
                }
            }
        }
        if (count > 0) {
            mKpi = {
                rainfall: round(rainSum / count, 1),
                gdd: round(gddSum / count, 0),
                temp: round(tempSum / count, 1),
                season_span: round(seasonSum / count, 0),
            };
        }
        if (prevCount > 0) {
            prevMKpi = {
                rainfall: round(prevRainSum / prevCount, 1),
                gdd: round(prevGddSum / prevCount, 0),
                temp: round(prevTempSum / prevCount, 1),
                season_span: round(prevSeasonSum / prevCount, 0),
            };
        }
    } else {
        mKpi = monthlyKpi(field, year, month);
        if (prevMo) prevMKpi = monthlyKpi(field, year, prevMo);
    }

    // Use monthly weather if available, else fallback to yearly
    const weather = mKpi || kpi;
    const prevWeather = prevMKpi || null;

    // Monthly NDVI override from actual satellite scene
    let displayNdvi = kpi.ndvi;
    let ndviSource = 'yearly composite';
    const monthNum = parseInt(month, 10);
    if (monthNum >= 4 && monthNum <= 10) {
        const monthly = getMonthlyPixelData(year, month, field);
        if (monthly) {
            displayNdvi = monthly.mean;
            ndviSource = monthly.source ? (monthly.source === 'sentinel' ? 'Sentinel-2' : 'Landsat-9') + ' ' + monthly.scene_date : 'multi-source';
            if (monthly.fallback) ndviSource += ' (previous month)';
        }
    }

    // Update KPI values
    document.getElementById('kpi-fields').textContent = kpiVal(kpi.fields, 0);
    document.getElementById('kpi-acres').textContent = kpiVal(kpi.acres, 1);
    document.getElementById('kpi-ndvi').textContent = kpiVal(displayNdvi, 3);
    document.getElementById('kpi-rainfall').textContent = fmt(weather.rainfall, ' mm');
    document.getElementById('kpi-gdd').textContent = kpiVal(weather.gdd, 0);
    document.getElementById('kpi-season').textContent = fmt(weather.season_span, '');
    document.getElementById('kpi-crop').textContent = topCropText(kpi.crop_breakdown);
    document.getElementById('kpi-shs').textContent = fmt(kpi.shs, '/10');
    document.getElementById('kpi-sust').textContent = fmt(kpi.sust, '/10');

    // Deltas vs previous month for weather KPIs
    const prevMonthName = prevMo ? MONTH_NAMES[prevMo] : null;
    setDelta('delta-fields', { txt: '—', cls: 'flat' });
    setDelta('delta-acres', { txt: '—', cls: 'flat' });
    setDelta('delta-ndvi', { txt: '—', cls: 'flat' });
    if (prevWeather && prevMonthName) {
        setDelta('delta-rainfall', getDelta(weather.rainfall, prevWeather.rainfall, 1, ' mm', prevMonthName));
        setDelta('delta-gdd', getDelta(weather.gdd, prevWeather.gdd, 0, '', prevMonthName));
        setDelta('delta-season', getDelta(weather.season_span, prevWeather.season_span, 0, ' days', prevMonthName));
    } else {
        setDelta('delta-rainfall', { txt: 'No prior month', cls: 'flat' });
        setDelta('delta-gdd', { txt: 'No prior month', cls: 'flat' });
        setDelta('delta-season', { txt: 'No prior month', cls: 'flat' });
    }
    setDelta('delta-crop', { txt: '—', cls: 'flat' });
    setDelta('delta-shs', { txt: '—', cls: 'flat' });
    setDelta('delta-sust', { txt: '—', cls: 'flat' });

    // Status markers
    setStatus('status-fields', { text: '—', cls: 'na' });
    setStatus('status-acres', { text: '—', cls: 'na' });
    setStatus('status-ndvi', statusFor('ndvi', displayNdvi));
    setStatus('status-rainfall', statusFor('rain', weather.rainfall));
    setStatus('status-gdd', statusFor('gdd', weather.gdd));
    setStatus('status-season', statusFor('season', weather.season_span));
    setStatus('status-crop', { text: '—', cls: 'na' });
    setStatus('status-shs', statusFor('shs', kpi.shs));
    setStatus('status-sust', statusFor('sust', kpi.sust));

    // Update narratives with month context
    const narr = DATA.narratives[key] || {};
    const monthPrefix = monthName + ' ' + year + ': ';
    const n1 = document.getElementById('narrative-1');
    const n2 = document.getElementById('narrative-2');
    const n3 = document.getElementById('narrative-3');
    const n4 = document.getElementById('narrative-4');
    const recList = document.getElementById('rec-list');
    if (n1) n1.textContent = monthPrefix + buildNarrative1(narr.s1, year, field);
    if (n2) n2.textContent = monthPrefix + buildNarrative2(narr.s2, year, field);
    if (n3) n3.textContent = monthPrefix + buildNarrative3(narr.s3, year, field);
    if (n4) n4.innerHTML = '<strong>Priority actions for ' + monthName + ' ' + year + ':</strong>';
    if (recList) recList.innerHTML = buildRecs(narr.recs, year, field);

    // Update map scene info text
    const sceneInfoEl = document.getElementById('map-scene-info');
    if (sceneInfoEl) {
        const monthly = getMonthlyPixelData(year, month, field);
        if (monthly && monthly.scene_date) {
            const srcText = monthly.source === 'sentinel' ? 'Sentinel-2' : 'Landsat-9';
            const fallbackText = monthly.fallback ? ' (previous month)' : '';
            sceneInfoEl.textContent = 'NDVI from ' + srcText + ' scene ' + monthly.scene_date + fallbackText + '. Raw range: ' + monthly.min.toFixed(3) + ' – ' + monthly.max.toFixed(3);
        } else if (monthly && monthly.fallback) {
            sceneInfoEl.textContent = 'Showing previous month scene. Raw range: ' + monthly.min.toFixed(3) + ' – ' + monthly.max.toFixed(3);
        } else if (monthly) {
            sceneInfoEl.textContent = 'Multi-source monthly composite. Raw range: ' + monthly.min.toFixed(3) + ' – ' + monthly.max.toFixed(3);
        } else {
            sceneInfoEl.textContent = 'Yearly composite NDVI (no monthly satellite scene available)';
        }
    }

    // Update map: backdrop, pixel colors, zoom
    const mapEl = document.getElementById('choropleth-map');
    if (mapEl && typeof Plotly !== 'undefined') {
        if (currentMapView === 'ndvi') {
            setMapView('ndvi');
        }
        if (field === 'all') {
            Plotly.relayout('choropleth-map', {
                'mapbox.center': {lat: DATA.map_center.lat, lon: DATA.map_center.lon},
                'mapbox.zoom': 11
            });
        } else {
            const fld = DATA.fields.find(f => f.id === field);
            if (fld) {
                const b = fld.bbox;
                Plotly.relayout('choropleth-map', {
                    'mapbox.center': {lat: (b[1] + b[3]) / 2, lon: (b[0] + b[2]) / 2},
                    'mapbox.zoom': 14
                });
            }
        }
    }
}

// ---- Initialization ----
window.addEventListener('load', updateDashboard);
