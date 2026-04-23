# Development Commands

Backend:

```bash
uvicorn backend.main:app --reload
```

Frontend:

```bash
python -m frontend.app
```

# NC Temperature Heatmap

A full-stack app that loads global NetCDF (`.nc`) temperature files and visualises them as an interactive Leaflet heatmap using **georaster-layer-for-leaflet**.

```
┌──────────────────────────┐        ┌─────────────────────────────────┐
│   Dash Frontend :8050    │  HTTP  │   FastAPI Backend :8000         │
│  ┌─────────────────────┐ │◄──────►│  POST /upload  → loads .nc      │
│  │  Sidebar controls   │ │        │  GET  /variables               │
│  │  - Upload .nc       │ │        │  GET  /times                   │
│  │  - Variable picker  │ │        │  GET  /colorscale              │
│  │  - Time slider      │ │        │  GET  /raster → GeoTIFF stream │
│  └─────────────────────┘ │        └─────────────────────────────────┘
│  ┌─────────────────────┐ │
│  │  Leaflet Iframe     │ │
│  │  georaster-layer    │ │
│  │  chroma.js colors   │ │
│  └─────────────────────┘ │
└──────────────────────────┘
```

## Architecture

| Layer | Tech | Role |
|---|---|---|
| Data I/O | `xarray` + `netcdf4` | Open/slice `.nc` files |
| Raster export | `rasterio` | Encode 2D array → GeoTIFF (WGS84) |
| API | `FastAPI` | REST endpoints, streams GeoTIFF bytes |
| UI framework | `Dash` + `dash-bootstrap-components` | Python-driven reactive UI |
| Map | `Leaflet` + `georaster-layer-for-leaflet` | Client-side raster rendering |
| Colour | `chroma.js` | Blue→cyan→green→yellow→red temperature palette |

---

## Quick Start

### 1 · Install & run the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at http://localhost:8000/docs

### 2 · Install & run the frontend

```bash
cd frontend
pip install -r requirements.txt
python app.py
```

Open http://localhost:8050 in your browser.

---

## Usage

1. **Upload** a `.nc` file via the sidebar drop zone.
2. **Select** the temperature variable from the dropdown (e.g. `t2m`, `air`, `TMP_2maboveground`).
3. **Scrub** the time slider to choose a time step.
4. Click **⚡ Render Heatmap** — the GeoTIFF is fetched from the backend and painted onto Leaflet by georaster.
5. The legend and stats panel update with min/max/mean and units.

---

## Supported NC file conventions

The backend auto-detects coordinate names for common conventions:

| Convention | Lat names | Lon names |
|---|---|---|
| CF | `lat`, `latitude` | `lon`, `longitude` |
| ROMS/MOM | `nlat`, `nav_lat` | `nlon`, `nav_lon` |
| Generic | `y` | `x` |

Time dimensions: `time`, `t`, `Times`, `TIME`

---

## Extending

- **Multiple variables at once**: add a second `dcc.Dropdown` and a layer toggle in the Leaflet iframe.
- **Animations**: add a `dcc.Interval` that auto-increments the time slider and re-renders.
- **Contour lines**: add a canvas overlay in the iframe using D3 or leaflet-contour.
- **Docker**: wrap each process in a Dockerfile and use `docker-compose` to launch both.
