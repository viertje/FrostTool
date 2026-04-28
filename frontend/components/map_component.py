from frontend.config import API_BASE_URL

API: str = API_BASE_URL

MAP_HTML_TEMPLATE: str = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
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
    text-align:center;
  }}
  
  /* Spinner styles */
  .spinner{{
    width:50px;height:50px;
    border:4px solid rgba(214,205,164,0.2);
    border-top:4px solid #D6CDA4;
    border-radius:50%;
    animation:spin 0.8s linear infinite;
    margin:0 auto 12px;
  }}
  
  @keyframes spin{{
    0%{{transform:rotate(0deg);}}
    100%{{transform:rotate(360deg);}}
  }}
  
  .loading-text{{
    color:#D6CDA4;
    font-size:12px;
    letter-spacing:1px;
    opacity:0.9;
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
<div id="loading">
  <div class="spinner"></div>
  <div class="loading-text">LOADING RASTER</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster@1.6.0"></script>
<script src="https://cdn.jsdelivr.net/npm/georaster-layer-for-leaflet"></script>
<script src="https://cdn.jsdelivr.net/npm/chroma-js@2.4.2"></script>

<script>
(function () {{
  const API = '{api_url}';
  const DEBUG = false; // Set to true for verbose logging
  const log = (msg, ...args) => {{ if (DEBUG) console.log(msg, ...args); }};
  
  const map = L.map('map', {{ center:[20,0], zoom:2, zoomControl:true }});
  
  L.tileLayer(
    'https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png',
    {{ attribution:'© OpenStreetMap © CARTO', maxZoom:19 }}
  ).addTo(map);

  let currentLayer = null;
  let currentDate = null;
  let dateRange = null;
  let currentTempType = "mean";
  let vmin = 0, vmax = 1;
  let continentBounds = {{}};
  let isLoading = false;
  let lastFetchedZoomLevel = null;  // Track zoom level used for last fetch
  let rasterUrls = {{}};  // Store current URLs for re-fetching on zoom
  let currentContinent = null;
  // Absolute temperature color scale (Celsius to color mapping)
  // -40°C to 50°C range
  const absoluteColorScale = chroma.scale([
    '#00007f', '#0000ff', '#007fff', '#00ffff',  // -40 to 0°C (frost/ice - blue)
    '#7fff7f',                                    // 0 to 10°C (cold - light green)
    '#ffff00',                                    // 10 to 20°C (cool - yellow)
    '#ff7f00',                                    // 20 to 30°C (warm - orange)
    '#ff0000', '#7f0000'                          // 30 to 50°C (hot - red)
  ]).domain([-40, 50]).mode('lab');

  // Function to map Kelvin to absolute color
  const getAbsoluteColor = (kelvin) => {{
    const celsius = kelvin - 273.15;
    return absoluteColorScale(celsius).hex();
  }};

  // Load continent bounds
  fetch(API + '/continents')
    .then(r => {{
      if (!r.ok) {{
        console.error('Continent bounds fetch failed with status:', r.status);
        return {{}};
      }}
      return r.json();
    }})
    .then(data => {{
      continentBounds = data || {{}};
    }})
    .catch(e => {{
      console.error('Failed to load continent bounds:', e);
      continentBounds = {{}};
    }});

  window.loadRaster = function(rasterUrl, colorscaleUrl, date, dateRangeObj, continent, tempType) {{
    // Prevent multiple simultaneous loads
    if (isLoading) {{
      console.warn('Raster already loading, ignoring new request');
      return;
    }}
    
    isLoading = true;
    currentDate = date;
    currentTempType = tempType || "mean";
    dateRange = dateRangeObj || null;
    document.getElementById('loading').style.display = 'block';

    // Keep reference to old layer to ensure cleanup
    const previousLayer = currentLayer;
    currentLayer = null;

    // Get current zoom level and add to URL for adaptive resolution
    const currentZoom = map.getZoom();
    const zoomParam = '&zoom_level=' + currentZoom;

    // Add cache-busting parameter to prevent tile caching at different zoom levels
    const cacheBuster = '&_cache=' + Date.now();
    const bustColorscaleUrl = colorscaleUrl + cacheBuster;
    const bustRasterUrl = rasterUrl + zoomParam + cacheBuster;

    fetch(bustColorscaleUrl)
      .then(r => {{
        if (!r.ok) {{
          throw new Error(`HTTP ${{r.status}}: Failed to fetch colorscale`);
        }}
        return r.json();
      }})
      .then(meta => {{
        if (!meta || !meta.min_value || !meta.max_value) {{
          throw new Error('Invalid colorscale response format');
        }}
        vmin = meta.min_value;
        vmax = meta.max_value;
        document.getElementById('leg-min').textContent = (vmin - 273.15).toFixed(1) + '°C';
        document.getElementById('leg-max').textContent = (vmax - 273.15).toFixed(1) + '°C';
        document.getElementById('leg-units').textContent = 'Absolute Scale';
        document.getElementById('leg-title').textContent = 'Temperature';
        return fetch(bustRasterUrl);
      }})
      .then(r => {{
        if (!r.ok) {{
          throw new Error(`HTTP ${{r.status}}: Failed to fetch raster`);
        }}
        return r.arrayBuffer();
      }})
      .then(ab => {{
        if (!ab || ab.byteLength === 0) {{
          throw new Error('Received empty raster data');
        }}
        return parseGeoraster(ab);
      }})
      .then(georaster => {{
        // Remove previous layer
        if (previousLayer) {{
          try {{
            map.removeLayer(previousLayer);
          }} catch(e) {{
            console.error('Error removing previous layer:', e);
          }}
        }}
        
        // Create and add new layer
        currentLayer = new GeoRasterLayer({{
          georaster,
          opacity: 0.45,
          pixelValuesToColorFn: values => {{
            const v = values[0];
            if (v == null || isNaN(v)) return null;
            return getAbsoluteColor(v);
          }},
          resolution: 256,
        }});
        
        currentLayer.addTo(map);
        
        // Only zoom to bounds on initial load, not on zoom-triggered re-fetches
        const isInitialLoad = lastFetchedZoomLevel === null;
        if (isInitialLoad) {{
          if (continent && continentBounds[continent]) {{
            const b = continentBounds[continent].bounds;
            map.fitBounds([[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]]);
          }} else {{
            map.fitBounds(currentLayer.getBounds());
          }}
        }}
        
        // Track URLs and zoom level for zoom-based re-fetching
        rasterUrls.rasterUrl = rasterUrl;
        rasterUrls.colorscaleUrl = colorscaleUrl;
        currentContinent = continent;
        lastFetchedZoomLevel = currentZoom;
        
        document.getElementById('loading').style.display = 'none';
        isLoading = false;
      }})
      .catch(e => {{
        console.error('Raster load error:', e);
        document.getElementById('loading').style.display = 'none';
        isLoading = false;
        
        // If new layer failed to load, restore previous state for visibility
        if (previousLayer && !currentLayer) {{
          try {{
            currentLayer = previousLayer;
            map.addLayer(previousLayer);
          }} catch(restoreErr) {{
            console.error('Could not restore previous layer:', restoreErr);
          }}
        }}
      }});
  }};

  const tooltip = document.getElementById('tooltip');

  map.on('click', function(e) {{
    if (!currentDate) {{
      console.warn('No date selected. Please render a heatmap first.');
      return;
    }}
    let lat = e.latlng.lat;
    let lon = e.latlng.lng;
    
    // Normalize longitude to [-180, 180] range (handle wrapped map)
    lon = ((lon + 180) % 360 - 180);
    
    lat = lat.toFixed(4);
    lon = lon.toFixed(4);
    
    // Store clicked coordinate and send to parent
    window.lastClickedCoordinate = {{
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      date: currentDate,
      dateRange: dateRange,
    }};
    
    // Send to parent Dash app via postMessage
    window.parent.postMessage({{
      type: 'coordinateClicked',
      lat: parseFloat(lat),
      lon: parseFloat(lon),
      date: currentDate,
      dateRange: dateRange,
    }}, '*');
    
    fetch(`${{API}}/value?date_str=${{currentDate}}&lat=${{lat}}&lon=${{lon}}&temp_type=${{currentTempType}}`)
      .then(r => {{
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      }})
      .then(d => {{
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

  // Zoom event listener: re-fetch at appropriate resolution when zoom level crosses thresholds
  map.on('zoomend', function() {{
    if (!currentDate || !rasterUrls.rasterUrl) return;
    
    const newZoom = map.getZoom();
    
    // Determine if we need to fetch at different resolution
    // Thresholds: zoom < 4 (4x down), zoom 4-7 (2x down), zoom >= 8 (full)
    let shouldRefetch = false;
    
    if (lastFetchedZoomLevel === null) {{
      shouldRefetch = true;
    }} else if (lastFetchedZoomLevel < 4 && newZoom >= 4) {{
      // Zooming in: was downsampled 4x, now need 2x or full
      shouldRefetch = true;
    }} else if (lastFetchedZoomLevel < 8 && newZoom >= 8) {{
      // Zooming in: was downsampled, now need full resolution
      shouldRefetch = true;
    }} else if (lastFetchedZoomLevel >= 8 && newZoom < 8) {{
      // Zooming out: was full resolution, now need downsampled - MUST refetch for proper bounds
      shouldRefetch = true;
    }} else if (lastFetchedZoomLevel >= 4 && newZoom < 4) {{
      // Zooming out: was 2x downsampled, now need 4x downsampled
      shouldRefetch = true;
    }}
    
    if (shouldRefetch && !isLoading) {{
      log('Zoom threshold crossed (' + lastFetchedZoomLevel + ' -> ' + newZoom + '): re-fetching with new resolution');
      window.loadRaster(
        rasterUrls.rasterUrl,
        rasterUrls.colorscaleUrl,
        currentDate,
        dateRange,
        currentContinent,
        currentTempType
      );
    }}
  }});

  window.addEventListener('message', e => {{
    if (e.data && e.data.type === 'loadRaster') {{
      window.loadRaster(e.data.rasterUrl, e.data.colorscaleUrl, e.data.date, e.data.dateRange, e.data.continent, e.data.tempType);
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


def get_map_html_with_initial_raster(
    api_url: str,
    raster_url: str,
    colorscale_url: str,
    date: str,
    continent: str | None,
    temp_type: str,
) -> str:
    """Generate map HTML that auto-loads a raster on iframe creation.
    
    This replaces the entire iframe content, forcing a complete reset of:
    - All JavaScript variables and state
    - Leaflet's internal cache
    - Browser HTTP cache
    - DOM cache
    
    This is equivalent to a hard refresh (Ctrl+Shift+R).
    """
    import json
    
    base_html = MAP_HTML_TEMPLATE.format(api_url=api_url)
    
    # Properly escape and JSON-encode parameters
    raster_url_safe = json.dumps(raster_url)
    colorscale_url_safe = json.dumps(colorscale_url)
    date_safe = json.dumps(date)
    continent_safe = json.dumps(continent) if continent else "null"
    temp_type_safe = json.dumps(temp_type)
    
    # Inject auto-load script at the end, just before closing body tag
    auto_load_script = f"""
<script>
// Auto-load raster immediately after page loads (fresh iframe)
window.addEventListener('load', function() {{
    setTimeout(function() {{
        window.loadRaster(
            {raster_url_safe},
            {colorscale_url_safe},
            {date_safe},
            null,
            {continent_safe},
            {temp_type_safe}
        );
    }}, 100);
}});
</script>
"""
    
    return base_html.replace("</body>", auto_load_script + "</body>")
