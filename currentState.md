# FrostTool — Current State

Last updated: 2026-05-11

---

## What the app is

A geospatial climate visualisation tool built on **AgERA5** daily 2 m air temperature data (NetCDF files). Two pages:

1. **Heatmap** (`/`) — renders a daily or date-range temperature raster on a Leaflet map. Click a cell to get a temperature time-series chart below the map.
2. **Frost Risk** (`/gdd`) — computes per-cell frost event counts (GDD-based) for a selected crop and year, renders the result on a Europe-only Leaflet map.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn, port 8000 |
| Frontend | Dash (Plotly) + Dash Bootstrap Components, port 8050 |
| Map rendering | Leaflet 1.9.4 inside `html.Iframe` (srcDoc), `georaster-layer-for-leaflet` for GeoTIFF tiles |
| Data | AgERA5 NetCDF, read with xarray/netcdf4 |
| Raster encoding | rasterio (GeoTIFF via `from_bounds`) |
| Caching | Two-level: in-memory LRU + diskcache (`.cache/`) |

---

## Project structure

```
FrostTool/
├── backend/
│   ├── main.py                     FastAPI app factory + lifespan warm-up
│   ├── core/
│   │   ├── config.py               TEMPERATURE_SOURCES, CONTINENTS, CROPS_CONFIG_PATH, GDD_WARMUP_MIN_YEAR
│   │   └── exceptions.py           DatasetNotFoundError, VariableNotFoundError, etc.
│   ├── models/
│   │   ├── domain.py               ColorscaleInfo dataclass
│   │   └── schemas.py              Pydantic response models (incl. GDD models)
│   ├── services/
│   │   ├── netcdf_service.py       NetCDFService: read slices, build GeoTIFF bytes
│   │   ├── gdd_service.py          GDDService + YearStack two-level cache
│   │   ├── cache_service.py        diskcache + LRU wrapper
│   │   └── aggregation_service.py  min/max/mean aggregation over date ranges
│   └── api/routes/
│       ├── climate.py              /api/v1/* (raster, colorscale, value, timeseries, continents)
│       └── gdd.py                  /api/v1/gdd/* (raster, colorscale, crops, available-years)
├── frontend/
│   ├── app.py                      Dash app (use_pages=True), shared layout
│   ├── config.py                   API_BASE_URL = http://localhost:8000/api/v1
│   ├── pages/
│   │   ├── heatmap.py              Registered at /
│   │   └── gdd.py                  Registered at /gdd — layout() makes zero API calls
│   ├── components/
│   │   ├── controls.py             create_shared_header(), create_controls(), create_map_frame()
│   │   ├── map_component.py        HTML template + get_map_html() for heatmap iframe
│   │   ├── map.js                  Leaflet + GeoRasterLayer logic for heatmap
│   │   ├── gdd_map_component.py    HTML template + get_gdd_map_html() for GDD iframe
│   │   ├── gdd_map.js              Leaflet + GeoRasterLayer logic for GDD map
│   │   └── timeline_graph.py       Plotly graph container component
│   └── callbacks/
│       ├── map_callbacks.py        Heatmap render, coordinate bridge iframe→Dash
│       ├── graph_callbacks.py      Timeseries chart, date status display
│       └── gdd_callbacks.py        Dropdown init, GDD render button
├── crops.txt                       INI-format crop parameters (editable without code changes)
└── currentState.md                 This file
```

---

## Data layout (local machine)

```
C:\Olivier\Terra local\data\AgERA5\
├── tmean_v2\
│   └── {YYYY}\   ← years 1979–2022
│       └── *.nc  (one file per day, Temperature_Air_2m_Mean_24h variable)
└── tmin_v2\
    └── {YYYY}\   ← years 1979–2007 only (test dataset)
        └── *.nc  (one file per day, Temperature_Air_2m_Min_24h variable)
```

**Important:** `tmin` only goes to 2007 in the current test dataset. When deployed with a full S3 dataset both variables will cover up to the current year. The GDD year dropdown is limited to years available in **both** `tmean` and `tmin` folders, determined at startup by `get_available_gdd_years()` (result cached in memory — see GDD caching section).

---

## Backend API endpoints

### Climate router (`/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/raster` | GeoTIFF for a date or date range (min/max/mean aggregation). `zoom_level` param drives downsampling. |
| GET | `/colorscale` | Min/max/mean values for legend scaling |
| GET | `/value` | Single cell temperature at lat/lon/date |
| GET | `/timeseries` | Temperature array across a date range for one cell |
| GET | `/continents` | Bounding boxes for continent zoom |
| GET | `/available-dates` | Sorted list of all available dates |
| GET | `/health` | `{"status": "ok"}` |

### GDD router (`/api/v1/gdd`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/raster` | GeoTIFF frost event count raster for `year` + `crop`. Values: NaN=ocean, -1=never budbreak, 0=no frost, ≥1=count. |
| GET | `/colorscale` | Max frost count for the year (min always 0) |
| GET | `/crops` | List of crop names from `crops.txt` (reloaded per request — editable live) |
| GET | `/available-years` | Years where both tmean and tmin data exist (served from memory cache) |

---

## GDD algorithm and caching (`gdd_service.py`)

Season: **1 Jan – 31 May** per year.

### Two-level cache

The computation is split so expensive file I/O is separated from cheap numpy math:

**Level 1 — `YearStack` (crop-agnostic, key `gdd_stack_{year}`):**
- Loads all daily `tmean` and `tmin` NetCDF slices for the Jan–May season (~302 files)
- Clips both stacks to Europe (reduces ~3.7 GB → ~166 MB combined)
- Stores `tmean_stack`, `tmin_stack`, and `EuropeBounds` in diskcache
- Cold load: ~60 s (302 sequential file reads through `_HDF5_LOCK`); warm: <100 ms

**Level 2 — `GDDResult` (per crop, key `gdd_frost_{year}_{crop}`):**
- Runs fast numpy math over the cached `YearStack` (~1–2 s)
- Caches the full `GDDResult` (frost_count array + bounds) so bounds are always accurate
- Cold (stack warm): ~2 s; warm: <100 ms

### Algorithm

```
gdd_daily  = max(Tavg_celsius - base_temperature, 0)
gdd_accum  = cumsum(gdd_daily, axis=time)
sensitive  = gdd_accum >= gdd_threshold          # budbreak reached
frost      = sensitive & (Tmin_celsius < frost_threshold)
frost_count = frost.sum(axis=time)               # per cell
```

Cells where `sensitive` was never True → set to sentinel `-1.0` (never reached budbreak).
Ocean/no-data cells stay `NaN`.

### Crop parameters (`crops.txt`)

INI format, editable without restarting the server (reloaded per request via `configparser`):

```ini
[grapevine]
display_name = Grapevine
base_temperature = 5
gdd_threshold = 250
frost_threshold = -2

[apple]
display_name = Apple
base_temperature = 4
gdd_threshold = 150
frost_threshold = -2

[pear]
display_name = Pear
base_temperature = 4
gdd_threshold = 170
frost_threshold = -2

[cherry]
display_name = Cherry
base_temperature = 4
gdd_threshold = 120
frost_threshold = -2
```

---

## Startup warm-up (`main.py`)

On backend startup the `lifespan` context manager:

1. **Synchronously** calls `get_available_gdd_years()` to populate its in-memory cache before the warm-up thread starts. This prevents the warm-up's disk I/O from blocking the Uvicorn async event loop on the first `/gdd/available-years` request.
2. Starts a **background daemon thread** (`gdd-warmup`) that pre-warms all `YearStack` + `GDDResult` combinations for years ≥ `GDD_WARMUP_MIN_YEAR` (default 2000, overridable via env var). Years are warmed most-recent-first. After the warm-up completes, every user render request is a diskcache hit.

**Expected cold warm-up time (local test data, 2000–2007 = 8 years):**
- ~60 s per year for the first stack (302 file reads)
- ~2 s per additional crop on the same year (cached stack)
- Total: ~8–10 min background, app is fully usable the entire time

The app serves requests immediately; the warm-up only reduces first-render latency for uncached year×crop combos.

---

## Frontend — Heatmap page (`/`)

- **Sidebar:** continent selector, temperature type (mean/min), date range picker (max 180 days), Render button, stats box.
- **Map iframe:** Leaflet + `georaster-layer-for-leaflet`. Absolute temperature colour scale −40°C (blue) → 50°C (dark red). `opacity: 0.45` at layer level. Click sends `postMessage` to parent Dash frame.
- **Coordinate bridge:** `clientside_callback` listens for `coordinateClicked` postMessage, clicks a hidden button, stores lat/lon/date in `dcc.Store`.
- **Graph panel:** Plotly timeseries chart slides up (25% height) on cell click, shows temperature for the selected date range at the clicked coordinate. Closeable.
- **Zoom refetch:** re-fetches raster at crossing zoom thresholds (4, 8) for adaptive resolution.

---

## Frontend — Frost Risk page (`/gdd`)

- **Sidebar:** crop dropdown, year dropdown, Render button, status text, legend, methodology note.
- **Dropdown population:** `layout()` renders empty dropdowns immediately (no blocking calls). A `dcc.Store(id="gdd-page-store", data=True)` in the layout triggers `populate_gdd_dropdowns` once on mount. That callback fetches `/gdd/crops` and `/gdd/available-years` **in parallel** (2 threads, 5 s timeout). Results are cached at module level so re-navigation is instant.
- **Map iframe:** Leaflet + `georaster-layer-for-leaflet`, centered on Europe `[52, 15]` zoom 4.
- **Colour scale** (solid hex colours, transparency via `opacity: 0.75` on the layer — matches the heatmap approach, prevents tile-seam grid artefacts):
  - `#bebebe` — never reached budbreak
  - `#2d8a4e` — budbreak reached, 0 frost events
  - `#3b82f6` — 1 frost event
  - `#f97316` → `#7f1d1d` (chroma LAB mix) — 2+ frost events
- **Render flow:** button click → `gdd_callbacks.py` builds URL `/gdd/raster?year=…&crop=…` → replaces iframe `srcDoc` with HTML that auto-calls `window.loadGDDRaster(url, year, crop)` after 100 ms.
- Click sends `gddCoordinateClicked` postMessage (lat/lon only, no further handling yet).

---

## Shared header

72 px tall gradient bar with title, subtitle, and nav links:
- **HEATMAP** → `/`
- **FROST RISK** → `/gdd`

Page layouts use `height: calc(100vh - 72px)` to fill below the header.

---

## Known open issues / next priorities

**Backend loading times are still slow on first render (cache cold).**
The first GDD render for an uncached year×crop combination takes ~30–60 s due to sequential NetCDF file reads serialised through `_HDF5_LOCK`. The warm-up mitigates this for years ≥ 2000 after the background thread completes, but the thread itself takes ~8–10 min. Potential optimisations to investigate:
- Reduce per-file read overhead (e.g. lazy-loading only the required spatial slice rather than full global arrays)
- Parallelise across years rather than across daily files within a year (disk-head locality)
- For S3 deployment: pre-generate and store all `YearStack` and `GDDResult` objects as static artefacts, eliminating runtime computation entirely

---

## How to run

```
# Backend (from project root, with PYTHONPATH=.)
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend (from project root)
python -m frontend.app
```

CORS is configured to allow `http://localhost:8050` and `http://127.0.0.1:8050`.

JS files (`map.js`, `gdd_map.js`) are read from disk at **Dash server startup** — restart required after JS changes.
