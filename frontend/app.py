"""
Dash frontend — AgERA5 Temperature Heatmap
==========================================
* Calendar date picker (only dates with data are enabled)
* Leaflet map powered by georaster-layer-for-leaflet
* Hover tooltip: temperature (K + °C) · lat/lon · date
* Colour scale: blue → cyan → green → yellow → red  (chroma.js)
* Backend: FastAPI on http://localhost:8000
"""

import requests
import dash
from dash import dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc

API = "http://localhost:8000"

# ── Fetch available dates once at startup ──────────────────────────────────────
def _fetch_available_dates() -> list[str]:
    try:
        r = requests.get(f"{API}/available-dates", timeout=10)
        return r.json().get("dates", [])
    except Exception:
        return []

AVAILABLE_DATES = _fetch_available_dates()
MIN_DATE = AVAILABLE_DATES[0]  if AVAILABLE_DATES else "2000-01-01"
MAX_DATE = AVAILABLE_DATES[-1] if AVAILABLE_DATES else "2030-12-31"

# ── Leaflet map (lives inside an iframe) ───────────────────────────────────────
# postMessage protocol from Dash → iframe:
#   { type: "loadRaster", rasterUrl, colorscaleUrl }
# Tooltip is driven by mousemove → fetch /value from the API.

MAP_HTML = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body,#map{{width:100%;height:100%;background:#1B6758;}}

  /* Legend */
  #legend{{
    position:absolute;bottom:28px;right:10px;z-index:9999;
    background:rgba(27,103,88,0.88);border:1px solid #3C8361;
    border-radius:10px;padding:13px 17px;min-width:170px;
    font-family:'Space Mono',monospace;color:#EEF2E6;font-size:11px;
    backdrop-filter:blur(6px);
  }}
  #legend .leg-title{{font-weight:700;font-size:12px;color:#D6CDA4;margin-bottom:8px;}}
  #legend .leg-bar{{
    height:13px;width:100%;border-radius:3px;margin-bottom:5px;
    background:linear-gradient(to right,
      #00007f,#0000ff,#007fff,#00ffff,#7fff7f,#ffff00,#ff7f00,#ff0000,#7f0000);
  }}
  #legend .leg-labels{{display:flex;justify-content:space-between;font-size:10px;color:#EEF2E6;}}
  #legend .leg-units{{margin-top:6px;color:#D6CDA4;font-size:10px;}}

  /* Hover tooltip */
  #tooltip{{
    position:absolute;top:16px;left:50%;transform:translateX(-50%);
    z-index:9999;pointer-events:none;
    background:rgba(27,103,88,0.90);border:1px solid #3C8361;
    border-radius:8px;padding:9px 14px;
    font-family:'Space Mono',monospace;font-size:11px;color:#EEF2E6;
    white-space:nowrap;backdrop-filter:blur(6px);
    display:none;
  }}
  #tooltip span.hi{{color:#D6CDA4;font-weight:700;}}
  #tooltip span.lo{{color:#D6CDA4;}}

  /* Loading spinner */
  #loading{{
    position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    z-index:9998;display:none;
    font-family:'Space Mono',monospace;font-size:13px;color:#D6CDA4;
  }}
</style>
</head>
<body>
<div id="map"></div>
<div id="legend">
  <div class="leg-title" id="leg-title">Temperature</div>
  <div class="leg-bar"></div>
  <div class="leg-labels"><span id="leg-min">—</span><span id="leg-max">—</span></div>
  <div class="leg-units" id="leg-units"></div>
</div>
<div id="tooltip">—</div>
<div id="loading">⏳ Loading raster…</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/georaster@1.6.0/dist/georaster.browser.bundle.min.js"></script>
<script src="https://unpkg.com/georaster-layer-for-leaflet/dist/georaster-layer-for-leaflet.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chroma-js@2.4.2/chroma.min.js"></script>

<script>
(function () {{
  const API = '{API}';

  // ── Map setup ──────────────────────────────────────────────────────────────
  const map = L.map('map', {{ center:[20,0], zoom:2, zoomControl:true }});

  L.tileLayer(
    'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{ attribution:'© OpenStreetMap © CARTO', maxZoom:19 }}
  ).addTo(map);

  // ── State ──────────────────────────────────────────────────────────────────
  let currentLayer = null;
  let currentDate  = null;
  let dateRange    = null;  // for range queries: {{ start, end }}
  let vmin = 0, vmax = 1;

  const colorScale = chroma.scale([
    '#00007f','#0000ff','#007fff','#00ffff',
    '#7fff7f','#ffff00','#ff7f00','#ff0000','#7f0000'
  ]).mode('lab');

  // ── Load raster ────────────────────────────────────────────────────────────
  window.loadRaster = function(rasterUrl, colorscaleUrl, date, dateRangeObj) {{
    currentDate = date;
    dateRange = dateRangeObj || null;
    document.getElementById('loading').style.display = 'block';

    fetch(colorscaleUrl)
      .then(r => r.json())
      .then(meta => {{
        vmin = meta.min;
        vmax = meta.max;
        document.getElementById('leg-min').textContent   = vmin.toFixed(1);
        document.getElementById('leg-max').textContent   = vmax.toFixed(1);
        document.getElementById('leg-units').textContent = meta.units || '';
        document.getElementById('leg-title').textContent = meta.long_name || 'Temperature';

        return fetch(rasterUrl);
      }})
      .then(r => r.arrayBuffer())
      .then(ab => parseGeoraster(ab))
      .then(georaster => {{
        if (currentLayer) map.removeLayer(currentLayer);
        currentLayer = new GeoRasterLayer({{
          georaster,
          opacity: 0.45,
          pixelValuesToColorFn: values => {{
            const v = values[0];
            if (v == null || isNaN(v)) return null;
            const norm = Math.min(1, Math.max(0, (v - vmin) / (vmax - vmin)));
            return colorScale(norm).hex();
          }},
          resolution: 256,
        }});
        currentLayer.addTo(map);
        map.fitBounds(currentLayer.getBounds());
        document.getElementById('loading').style.display = 'none';
      }})
      .catch(e => {{
        console.error('Raster load error:', e);
        document.getElementById('loading').style.display = 'none';
      }});
  }};

  // ── Click tooltip ──────────────────────────────────────────────────────────
  const tooltip = document.getElementById('tooltip');

  map.on('click', function(e) {{
    if (!currentDate && !dateRange) return;
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    
    let fetchUrl;
    if (dateRange) {{
      fetchUrl = `${{API}}/min-value?date_start=${{dateRange.start}}&date_end=${{dateRange.end}}&lat=${{lat}}&lon=${{lon}}`;
    }} else {{
      fetchUrl = `${{API}}/value?date=${{currentDate}}&lat=${{lat}}&lon=${{lon}}`;
    }}
    
    fetch(fetchUrl)
      .then(r => r.json())
      .then(d => {{
        const k   = d.value   != null ? d.value.toFixed(2)   + ' ' + d.units : '—';
        const c   = d.celsius != null ? d.celsius.toFixed(2) + ' °C'         : '';
        const sep = c ? ' · ' : '';
        
        let dateStr;
        if (dateRange) {{
          dateStr = `<span class="hi">${{dateRange.start}} to ${{dateRange.end}}</span>`;
        }} else {{
          dateStr = `<span class="hi">${{currentDate}}</span>`;
        }}
        
        tooltip.innerHTML =
          dateStr + `  ` +
          `<span class="lo">lat ${{d.lat}}  lon ${{d.lon}}</span><br>` +
          `<span class="hi">${{k}}${{sep}}${{c}}</span>`;
        tooltip.style.display = 'block';
      }})
      .catch(() => {{ tooltip.style.display = 'none'; }});
  }});

  map.on('mouseout', () => {{ tooltip.style.display = 'none'; }});

  // ── postMessage bridge from Dash ───────────────────────────────────────────
  window.addEventListener('message', e => {{
    if (e.data && e.data.type === 'loadRaster') {{
      window.loadRaster(e.data.rasterUrl, e.data.colorscaleUrl, e.data.date, e.data.dateRange);
    }}
    if (e.data && e.data.type === 'setView') {{
      map.setView(e.data.center, e.data.zoom);
    }}
  }});
}})();
</script>
</body>
</html>"""


# ── Dash app ───────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="AgERA5 Temperature Heatmap",
)

SIDEBAR_STYLE = {
    "background":   "#EEF2E6",
    "borderRight":  "1px solid #3C8361",
    "padding":      "26px 20px",
    "overflowY":    "auto",
    "height":       "100%",
}

LABEL_STYLE = {
    "fontFamily":    "'Space Mono',monospace",
    "fontSize":      "10px",
    "letterSpacing": "2px",
    "color":         "#3C8361",
    "marginBottom":  "10px",
}

app.layout = dbc.Container(
    fluid=True,
    style={"background": "#1B6758", "minHeight": "100vh", "padding": "0"},
    children=[
        # ── Header ─────────────────────────────────────────────────────────
        html.Div(
            style={
                "background":   "linear-gradient(135deg,#1B6758,#3C8361)",
                "borderBottom": "1px solid #3C8361",
                "padding":      "16px 30px",
                "display":      "flex",
                "alignItems":   "center",
                "gap":          "18px",
            },
            children=[
                html.Span("🌡", style={"fontSize": "30px"}),
                html.Div([
                    html.H1("AgERA5 Temperature Heatmap",
                            style={"fontFamily": "'Syne',sans-serif", "fontWeight": "800",
                                   "fontSize": "22px", "color": "#EEF2E6", "margin": "0"}),
                    html.P("Global daily 2 m air temperature · ERA5-based · georaster-layer-for-leaflet",
                           style={"fontFamily": "'Space Mono',monospace", "fontSize": "10px",
                                  "color": "#D6CDA4", "margin": "3px 0 0"}),
                ]),
            ],
        ),

        # ── Body ────────────────────────────────────────────────────────────
        dbc.Row(
            style={"margin": "0", "height": "calc(100vh - 72px)"},
            children=[

                # Sidebar
                dbc.Col(width=3, style=SIDEBAR_STYLE, children=[

                    html.H6("CONTINENT", style=LABEL_STYLE),
                    dcc.Dropdown(
                        id="continent-selector",
                        options=[
                            {"label": "🌍 Global", "value": ""},
                            {"label": "Africa", "value": "Africa"},
                            {"label": "North America", "value": "North America"},
                            {"label": "South America", "value": "South America"},
                            {"label": "Europe", "value": "Europe"},
                            {"label": "Asia", "value": "Asia"},
                            {"label": "Oceania", "value": "Oceania"},
                        ],
                        value="",
                        clearable=False,
                        style={
                            "width": "100%",
                            "marginBottom": "12px",
                        },
                    ),
                    
                    dcc.Store(id="selected-continent", data=None),

                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),

                    html.H6("DATE RANGE", style=LABEL_STYLE),
                    dcc.DatePickerRange(
                        id="date-range",
                        start_date="2020-12-30",
                        end_date="2020-12-31",
                        display_format="YYYY-MM-DD",
                        style={"width": "100%"},
                        className="dark-datepicker",
                    ),
                    html.Div(id="date-status",
                             style={"fontFamily": "'Space Mono',monospace", "fontSize": "11px",
                                    "marginTop": "8px", "color": "#3C8361"}),

                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),

                    dbc.Button(
                        "⚡  Render Heatmap",
                        id="render-btn",
                        style={
                            "width":       "100%",
                            "fontFamily":  "'Space Mono',monospace",
                            "fontWeight":  "700",
                            "letterSpacing": "1px",
                            "background":  "linear-gradient(135deg,#3C8361,#1B6758)",
                            "border":      "none",
                            "color":       "#EEF2E6",
                            "padding":     "12px",
                            "borderRadius": "8px",
                        },
                    ),

                    html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),

                    html.H6("STATS", style=LABEL_STYLE),
                    html.Div(id="stats-box",
                             style={"fontFamily": "'Space Mono',monospace", "fontSize": "11px",
                                    "color": "#3C8361", "lineHeight": "1.9"}),
                ]),

                # Map
                dbc.Col(width=9, style={"padding": "0", "position": "relative"}, children=[
                    html.Iframe(
                        id="map-frame",
                        srcDoc=MAP_HTML,
                        style={"width": "100%", "height": "100%", "border": "none"},
                    ),
                    dcc.Store(id="raster-trigger"),
                ]),
            ],
        ),
    ],
)


# ── Callbacks ──────────────────────────────────────────────────────────────────

@callback(
    Output("date-status", "children"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def show_date_status(start_date, end_date):
    if not start_date or not end_date:
        return ""
    from datetime import datetime
    d_start = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
    d_end = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
    days = (d_end - d_start).days + 1
    
    if days > 180:
        return f"⚠ Range is {days} days (>6 months). Max allowed: 180 days."
    return f"✓ {days} days selected"


@callback(
    Output("stats-box", "children"),
    Output("raster-trigger", "data"),
    Input("render-btn", "n_clicks"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("selected-continent", "data"),
    prevent_initial_call=True,
)
def render_heatmap(n_clicks, start_date, end_date, selected_continent):
    if not start_date or not end_date:
        return [html.Div("Please select a date range first.", style={"color": "#e07050"})], dash.no_update

    d_start_str = start_date[:10]
    d_end_str = end_date[:10]
    
    # Validate range
    from datetime import datetime
    d_start = datetime.strptime(d_start_str, "%Y-%m-%d").date()
    d_end = datetime.strptime(d_end_str, "%Y-%m-%d").date()
    days = (d_end - d_start).days + 1
    
    if days > 180:
        return [html.Div(f"⚠ Range is {days} days (>6 months). Max allowed: 180 days.", 
                        style={"color": "#e07050"})], dash.no_update
    
    # Build continent parameter for API
    continent_param = f"&continent={selected_continent}" if selected_continent else ""
    
    try:
        # For single day, use regular colorscale; for range, use min-colorscale
        if d_start == d_end:
            cs = requests.get(f"{API}/colorscale", params={"date": d_start_str, "continent": selected_continent}, timeout=20).json()
            raster_url = f"{API}/raster?date={d_start_str}{continent_param}"
            colorscale_url = f"{API}/colorscale?date={d_start_str}{continent_param}"
        else:
            cs = requests.get(f"{API}/min-colorscale", 
                            params={"date_start": d_start_str, "date_end": d_end_str, "continent": selected_continent}, 
                            timeout=20).json()
            raster_url = f"{API}/min-raster?date_start={d_start_str}&date_end={d_end_str}{continent_param}"
            colorscale_url = f"{API}/min-colorscale?date_start={d_start_str}&date_end={d_end_str}{continent_param}"
    except Exception as e:
        return [html.Div(f"Backend error: {e}", style={"color": "#e07050"})], dash.no_update

    if "detail" in cs:
        return [html.Div(f"⚠ {cs['detail']}", style={"color": "#e07050"})], dash.no_update

    if d_start == d_end:
        # Single date
        stats = [
            html.Div(f"Date    : {d_start_str}"),
            html.Div(f"Variable: {cs.get('long_name', '—')}"),
            html.Div(f"Units   : {cs.get('units', '—')}"),
            html.Div(f"Min     : {cs['min']:.3f}"),
            html.Div(f"Max     : {cs['max']:.3f}"),
            html.Div(f"Mean    : {cs['mean']:.3f}"),
        ]
    else:
        # Date range
        stats = [
            html.Div(f"Period  : {d_start_str} to {d_end_str}"),
            html.Div(f"Days    : {days}"),
            html.Div(f"Variable: {cs.get('long_name', '—')}"),
            html.Div(f"Units   : {cs.get('units', '—')}"),
            html.Div(f"Min     : {cs['min']:.3f}"),
            html.Div(f"Max     : {cs['max']:.3f}"),
            html.Div(f"Mean    : {cs['mean']:.3f}"),
        ]
    
    trigger = {
        "rasterUrl":     raster_url,
        "colorscaleUrl": colorscale_url,
        "date":          d_start_str,
        "dateRange":     {"start": d_start_str, "end": d_end_str} if d_start != d_end else None,
        "continent":     selected_continent,
    }
    return stats, trigger


# Continent selector callback
@callback(
    Output("selected-continent", "data"),
    Input("continent-selector", "value"),
    prevent_initial_call=True,
)
def select_continent(value):
    return value if value else None


# Clientside callback: update map zoom and center, then load raster via postMessage
app.clientside_callback(
    """
    function(trigger) {
        if (!trigger) return '';
        
        const continentZoom = {
            "Africa": 4,
            "North America": 4,
            "South America": 4,
            "Europe": 5,
            "Asia": 3,
            "Oceania": 4,
        };
        
        const continentCenter = {
            "Africa": [0, 20],
            "North America": [45, -100],
            "South America": [-15, -60],
            "Europe": [54, 15],
            "Asia": [34, 100],
            "Oceania": [-25, 145],
        };
        
        const iframe = document.getElementById('map-frame');
        if (iframe && iframe.contentWindow) {
            // Set view if continent is selected
            if (trigger.continent) {
                const zoom = continentZoom[trigger.continent] || 2;
                const center = continentCenter[trigger.continent] || [20, 0];
                iframe.contentWindow.postMessage(
                    { type: 'setView', center: center, zoom: zoom },
                    '*'
                );
            }
            
            // Load raster
            iframe.contentWindow.postMessage(
                { type: 'loadRaster',
                  rasterUrl:     trigger.rasterUrl,
                  colorscaleUrl: trigger.colorscaleUrl,
                  date:          trigger.date,
                  dateRange:     trigger.dateRange },
                '*'
            );
        }
        return '';
    }
    """,
    Output("map-frame", "title"),
    Input("raster-trigger", "data"),
)


if __name__ == "__main__":
    app.run(debug=True, port=8050, host="0.0.0.0")
