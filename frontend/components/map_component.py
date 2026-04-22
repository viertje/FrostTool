API: str = "http://localhost:8000/api/v1"

MAP_HTML_TEMPLATE: str = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body,#map{{width:100%;height:100%;background:#1B6758;}}

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
  const API = '{api_url}';
  const map = L.map('map', {{ center:[20,0], zoom:2, zoomControl:true }});
  
  L.tileLayer(
    'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{ attribution:'© OpenStreetMap © CARTO', maxZoom:19 }}
  ).addTo(map);

  let currentLayer = null;
  let currentDate = null;
  let dateRange = null;
  let vmin = 0, vmax = 1;
  let continentBounds = {{}};

  const colorScale = chroma.scale([
    '#00007f','#0000ff','#007fff','#00ffff',
    '#7fff7f','#ffff00','#ff7f00','#ff0000','#7f0000'
  ]).mode('lab');

  // Load continent bounds
  fetch(API + '/continents')
    .then(r => r.json())
    .then(data => {{ continentBounds = data; }})
    .catch(e => console.error('Failed to load continent bounds:', e));

  window.loadRaster = function(rasterUrl, colorscaleUrl, date, dateRangeObj, continent) {{
    currentDate = date;
    dateRange = dateRangeObj || null;
    document.getElementById('loading').style.display = 'block';

    fetch(colorscaleUrl)
      .then(r => r.json())
      .then(meta => {{
        vmin = meta.min_value;
        vmax = meta.max_value;
        document.getElementById('leg-min').textContent = vmin.toFixed(1);
        document.getElementById('leg-max').textContent = vmax.toFixed(1);
        document.getElementById('leg-units').textContent = meta.units || '';
        document.getElementById('leg-title').textContent = 'Temperature';
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
        
        // Zoom to continent bounds if continent is selected, else fit layer bounds
        if (continent && continentBounds[continent]) {{
          const b = continentBounds[continent].bounds;
          map.fitBounds([[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]]);
        }} else {{
          map.fitBounds(currentLayer.getBounds());
        }}
        
        document.getElementById('loading').style.display = 'none';
      }})
      .catch(e => {{
        console.error('Raster load error:', e);
        document.getElementById('loading').style.display = 'none';
      }});
  }};

  const tooltip = document.getElementById('tooltip');

  map.on('click', function(e) {{
    if (!currentDate) {{
      console.warn('No date selected. Please render a heatmap first.');
      return;
    }}
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    
    console.log('Fetching value for:', currentDate, 'at', lat, lon);
    
    fetch(`${{API}}/value?date_str=${{currentDate}}&lat=${{lat}}&lon=${{lon}}`)
      .then(r => {{
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }})
      .then(d => {{
        console.log('Received:', d);
        const celsius = (d.value - 273.15).toFixed(2);
        const k = d.value != null ? celsius + ' °C' : '—';
        tooltip.innerHTML =
          `<span class="hi">${{currentDate}}</span><br>` +
          `<span class="lo">lat ${{d.lat}}  lon ${{d.lon}}</span><br>` +
          `<span class="hi">${{k}}</span>`;
        tooltip.style.display = 'block';
        tooltip.style.position = 'absolute';
        tooltip.style.top = '16px';
        tooltip.style.left = '50%';
        tooltip.style.transform = 'translateX(-50%)';
      }})
      .catch(err => {{
        console.error('Error fetching value:', err);
        tooltip.style.display = 'none';
      }});
  }});

  map.on('mouseout', () => {{ tooltip.style.display = 'none'; }});

  window.addEventListener('message', e => {{
    if (e.data && e.data.type === 'loadRaster') {{
      window.loadRaster(e.data.rasterUrl, e.data.colorscaleUrl, e.data.date, e.data.dateRange, e.data.continent);
    }}
    if (e.data && e.data.type === 'setView') {{
      map.setView(e.data.center, e.data.zoom);
    }}
  }});
}})();
</script>
</body>
</html>"""


def get_map_html(api_url: str) -> str:
    return MAP_HTML_TEMPLATE.format(api_url=api_url)
