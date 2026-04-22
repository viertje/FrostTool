"""
FastAPI backend for the AgERA5 NC Temperature Heatmap app.

File layout expected on disk:
    DATA_ROOT/
        YYYY/
            MM/
                <any_filename_containing_YYYY-MM-DD>.nc

Set the DATA_ROOT environment variable to point at your local data root,
e.g.:  export DATA_ROOT=/mnt/data/agera5

Endpoints:
    GET  /available-dates                       → list all dates that have a file on disk
    GET  /raster?date=YYYY-MM-DD               → stream GeoTIFF for georaster-layer-for-leaflet
    GET  /colorscale?date=YYYY-MM-DD           → min/max/mean/units for the legend
    GET  /value?date=YYYY-MM-DD&lat=..&lon=..  → single cell value for hover tooltip
    GET  /health
"""

import os
import io
import glob
from pathlib import Path
from datetime import date, datetime

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Config ─────────────────────────────────────────────────────────────────────
# Adjust DATA_ROOT to match the actual data location
DATA_ROOT = Path(os.environ.get("DATA_ROOT", r"C:\Olivier\Terra local\data\AgERA5\tmean_v2"))
VARIABLE   = "Temperature_Air_2m_Mean_24h"   # fixed AgERA5 variable name

# Continent bounding boxes (lat_min, lat_max, lon_min, lon_max)
CONTINENTS = {
    "Africa":        (-35, 37, -18, 52),
    "North America": (15, 83, -170, -50),
    "South America": (-56, 13, -82, -35),
    "Europe":        (30, 76, -15, 45),
    "Asia":          (-10, 77, 26, 180),
    "Oceania":       (-47, -10, 113, 180),
}

# Map zoom levels for each continent
CONTINENT_ZOOM = {
    "Africa":        4,
    "North America": 4,
    "South America": 4,
    "Europe":        5,
    "Asia":          3,
    "Oceania":       4,
}

# Map centers for each continent (lat, lon)
CONTINENT_CENTER = {
    "Africa":        (0, 20),
    "North America": (45, -100),
    "South America": (-15, -60),
    "Europe":        (54, 15),
    "Asia":          (34, 100),
    "Oceania":       (-25, 145),
}

app = FastAPI(title="AgERA5 Temperature Heatmap API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple single-slot cache so repeated requests for the same date don't re-open the file
_cache: dict = {"date": None, "ds": None}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_file(d: date) -> Path:
    """Return the .nc file path for a given date using YYYY folder structure."""
    folder  = DATA_ROOT / f"{d.year:04d}"
    pattern = str(folder / f"*{d.strftime('%Y%m%d')}*.nc")
    matches = glob.glob(pattern)
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"No .nc file found for {d.isoformat()} — looked in {folder}",
        )
    return Path(sorted(matches)[0])


def _load_ds(d: date) -> xr.Dataset:
    """Load (and cache) the xarray Dataset for a given date."""
    if _cache["date"] == d and _cache["ds"] is not None:
        return _cache["ds"]
    path = _find_file(d)
    if _cache["ds"] is not None:
        _cache["ds"].close()
    ds = xr.open_dataset(path, engine="netcdf4")
    _cache["date"] = d
    _cache["ds"]   = ds
    return ds


def _parse_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD.",
        )


def _extract_2d(ds: xr.Dataset, continent: str = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Slice the target variable to a 2-D float32 array.
    Optionally filters by continent bounding box.
    Filters out Antarctica (lat < -60).
    Returns (data[lat, lon], lat_vals descending, lon_vals ascending).
    """
    da      = ds[VARIABLE].isel(time=0).squeeze()
    lat_arr = ds["lat"].values.astype(float)
    lon_arr = ds["lon"].values.astype(float)
    
    # Filter out Antarctica (lat < -60)
    lat_mask = lat_arr >= -60
    lat_arr = lat_arr[lat_mask]
    
    # Apply Antarctica filter to data
    data = da.values.astype(np.float32)
    data = data[lat_mask, :]
    
    # Apply continent bounding box filter if specified
    if continent and continent in CONTINENTS:
        lat_min, lat_max, lon_min, lon_max = CONTINENTS[continent]
        lat_cont_mask = (lat_arr >= lat_min) & (lat_arr <= lat_max)
        lon_cont_mask = (lon_arr >= lon_min) & (lon_arr <= lon_max)
        
        # Apply latitude filter
        lat_arr = lat_arr[lat_cont_mask]
        data = data[lat_cont_mask, :]
        
        # Apply longitude filter
        lon_arr = lon_arr[lon_cont_mask]
        data = data[:, lon_cont_mask]

    # rasterio expects lat descending (north → south)
    if lat_arr[0] < lat_arr[-1]:
        lat_arr = lat_arr[::-1]
        data    = data[::-1, :]

    return data, lat_arr, lon_arr


def _date_range_days(d1: date, d2: date) -> int:
    """Return the number of days between two dates (inclusive)."""
    return (d2 - d1).days + 1


def _validate_date_range(d1: date, d2: date):
    """Validate that date range is <= 6 months (~180 days)."""
    days = _date_range_days(d1, d2)
    if days > 180:
        raise HTTPException(
            status_code=400,
            detail=f"Date range is {days} days (>6 months). Max allowed: 180 days.",
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/available-dates")
def available_dates():
    """
    Walk DATA_ROOT/YYYY/MM/ and return every date that has a .nc file.
    The calendar picker uses this list to disable dates with no data.
    """
    dates = set()
    for nc_path in DATA_ROOT.rglob("*.nc"):
        for part in nc_path.stem.split("_"):
            try:
                dates.add(datetime.strptime(part, "%Y-%m-%d").date().isoformat())
                break
            except ValueError:
                continue
    return {"dates": sorted(dates)}


@app.get("/continents")
def get_continents():
    """Return list of available continents with their zoom levels and centers."""
    return {
        "continents": [
            {
                "name": name,
                "zoom": CONTINENT_ZOOM.get(name, 3),
                "center": CONTINENT_CENTER.get(name, (0, 0))
            }
            for name in sorted(CONTINENTS.keys())
        ]
    }


@app.get("/colorscale")
def colorscale(date: str = Query(..., description="YYYY-MM-DD"), continent: str = Query(None, description="Continent name")):
    """Return statistics used to build the colour legend on the frontend."""
    d       = _parse_date(date)
    ds      = _load_ds(d)
    data, *_ = _extract_2d(ds, continent)
    finite  = data[np.isfinite(data)]
    units   = ds[VARIABLE].attrs.get("units", "K")
    return {
        "min":       float(finite.min()),
        "max":       float(finite.max()),
        "mean":      float(finite.mean()),
        "units":     units,
        "long_name": ds[VARIABLE].attrs.get("long_name", VARIABLE),
        "date":      date,
        "continent": continent,
    }


@app.get("/raster")
def raster(date: str = Query(..., description="YYYY-MM-DD"), continent: str = Query(None, description="Continent name")):
    """
    Stream a WGS84 Float32 single-band GeoTIFF.
    georaster-layer-for-leaflet on the client fetches this URL directly.
    """
    d                    = _parse_date(date)
    ds                   = _load_ds(d)
    data, lat_arr, lon_arr = _extract_2d(ds, continent)

    lon_min, lon_max = float(lon_arr.min()), float(lon_arr.max())
    lat_min, lat_max = float(lat_arr.min()), float(lat_arr.max())
    height, width    = data.shape

    transform = from_bounds(lon_min, lat_min, lon_max, lat_max, width, height)

    buf = io.BytesIO()
    with rasterio.open(
        buf, "w",
        driver    = "GTiff",
        height    = height,
        width     = width,
        count     = 1,
        dtype     = rasterio.float32,
        crs       = CRS.from_epsg(4326),
        transform = transform,
        nodata    = np.nan,
    ) as dst:
        dst.write(data, 1)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type = "image/tiff",
        headers    = {"Content-Disposition": f'inline; filename="temp_{date}.tif"'},
    )


@app.get("/value")
def cell_value(
    date: str   = Query(..., description="YYYY-MM-DD"),
    lat:  float = Query(..., description="Cursor latitude"),
    lon:  float = Query(..., description="Cursor longitude"),
    continent: str = Query(None, description="Continent name"),
):
    """
    Return the temperature at the nearest grid cell to the cursor position.
    Called on every Leaflet mousemove event to power the hover tooltip.
    """
    d       = _parse_date(date)
    ds      = _load_ds(d)

    lat_arr = ds["lat"].values.astype(float)
    lon_arr = ds["lon"].values.astype(float)

    # Clamp to grid extent then find nearest index
    lat     = float(np.clip(lat, lat_arr.min(), lat_arr.max()))
    lon     = float(np.clip(lon, lon_arr.min(), lon_arr.max()))
    lat_idx = int(np.argmin(np.abs(lat_arr - lat)))
    lon_idx = int(np.argmin(np.abs(lon_arr - lon)))

    raw   = float(ds[VARIABLE].isel(time=0).values[lat_idx, lon_idx])
    units = ds[VARIABLE].attrs.get("units", "K")

    celsius = round(raw - 273.15, 2) if units.upper() in ("K", "KELVIN") else None

    return {
        "value":   round(raw, 4),
        "celsius": celsius,
        "units":   units,
        "lat":     round(lat_arr[lat_idx], 4),
        "lon":     round(lon_arr[lon_idx], 4),
        "date":    date,
    }


@app.get("/min-value")
def min_cell_value(
    date_start: str = Query(..., description="YYYY-MM-DD"),
    date_end: str   = Query(..., description="YYYY-MM-DD"),
    lat:  float     = Query(..., description="Cursor latitude"),
    lon:  float     = Query(..., description="Cursor longitude"),
    continent: str = Query(None, description="Continent name"),
):
    """
    Return the minimum temperature at the nearest grid cell across a date range.
    """
    d_start = _parse_date(date_start)
    d_end   = _parse_date(date_end)
    _validate_date_range(d_start, d_end)

    # Load all files in range and compute minimum
    min_value = None
    lat_arr, lon_arr = None, None
    current_d = d_start
    from datetime import timedelta
    
    while current_d <= d_end:
        try:
            ds = _load_ds(current_d)
            data, lat_arr, lon_arr = _extract_2d(ds, continent)
            
            # Find nearest cell
            lat_clipped = float(np.clip(lat, lat_arr.min(), lat_arr.max()))
            lon_clipped = float(np.clip(lon, lon_arr.min(), lon_arr.max()))
            lat_idx = int(np.argmin(np.abs(lat_arr - lat_clipped)))
            lon_idx = int(np.argmin(np.abs(lon_arr - lon_clipped)))
            
            cell_value = data[lat_idx, lon_idx]
            if np.isfinite(cell_value):
                if min_value is None:
                    min_value = float(cell_value)
                else:
                    min_value = float(np.minimum(min_value, cell_value))
        except HTTPException:
            pass  # File not found, skip
        current_d += timedelta(days=1)

    if min_value is None or lat_arr is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data found at lat={lat}, lon={lon} in range {date_start} to {date_end}",
        )

    lat_clipped = float(np.clip(lat, lat_arr.min(), lat_arr.max()))
    lon_clipped = float(np.clip(lon, lon_arr.min(), lon_arr.max()))
    lat_idx = int(np.argmin(np.abs(lat_arr - lat_clipped)))
    lon_idx = int(np.argmin(np.abs(lon_arr - lon_clipped)))
    
    units = "K"
    celsius = round(min_value - 273.15, 2) if units.upper() in ("K", "KELVIN") else None

    return {
        "value":     round(float(min_value), 4),
        "celsius":   celsius,
        "units":     units,
        "lat":       float(round(lat_arr[lat_idx], 4)),
        "lon":       float(round(lon_arr[lon_idx], 4)),
        "date_start": date_start,
        "date_end":   date_end,
    }


@app.get("/health")
def health():
    return {
        "status":            "ok",
        "data_root":         str(DATA_ROOT),
        "data_root_exists":  DATA_ROOT.exists(),
        "cached_date":       _cache["date"].isoformat() if _cache["date"] else None,
    }


@app.get("/min-colorscale")
def min_colorscale(
    date_start: str = Query(..., description="YYYY-MM-DD"),
    date_end: str = Query(..., description="YYYY-MM-DD"),
    continent: str = Query(None, description="Continent name"),
):
    """Return statistics for minimum temperature across a date range."""
    d_start = _parse_date(date_start)
    d_end   = _parse_date(date_end)
    _validate_date_range(d_start, d_end)

    # Load all files in range and compute minimum across time axis
    min_data = None
    current_d = d_start
    from datetime import timedelta
    
    while current_d <= d_end:
        try:
            ds = _load_ds(current_d)
            data, *_ = _extract_2d(ds, continent)
            if min_data is None:
                min_data = data.copy()
            else:
                min_data = np.minimum(min_data, data)
        except HTTPException:
            pass  # File not found, skip this date
        current_d += timedelta(days=1)

    if min_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data found in range {date_start} to {date_end}",
        )

    finite = min_data[np.isfinite(min_data)]
    units  = "K"
    
    return {
        "min":       float(np.min(finite)),
        "max":       float(np.max(finite)),
        "mean":      float(np.mean(finite)),
        "units":     units,
        "long_name": "Minimum Temperature (Coldest Day)",
        "date_start": date_start,
        "date_end":   date_end,
        "continent": continent,
    }


@app.get("/min-raster")
def min_raster(
    date_start: str = Query(..., description="YYYY-MM-DD"),
    date_end: str = Query(..., description="YYYY-MM-DD"),
    continent: str = Query(None, description="Continent name"),
):
    """
    Stream a GeoTIFF containing the minimum temperature across a date range.
    """
    d_start = _parse_date(date_start)
    d_end   = _parse_date(date_end)
    _validate_date_range(d_start, d_end)

    # Load all files in range and compute minimum across time axis
    min_data = None
    lat_arr, lon_arr = None, None
    current_d = d_start
    from datetime import timedelta
    
    while current_d <= d_end:
        try:
            ds = _load_ds(current_d)
            data, lat_arr, lon_arr = _extract_2d(ds, continent)
            if min_data is None:
                min_data = data.copy()
            else:
                min_data = np.minimum(min_data, data)
        except HTTPException:
            pass  # File not found, skip this date
        current_d += timedelta(days=1)

    if min_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"No data found in range {date_start} to {date_end}",
        )

    lon_min, lon_max = float(lon_arr.min()), float(lon_arr.max())
    lat_min, lat_max = float(lat_arr.min()), float(lat_arr.max())
    height, width    = min_data.shape

    transform = from_bounds(lon_min, lat_min, lon_max, lat_max, width, height)

    buf = io.BytesIO()
    with rasterio.open(
        buf, "w",
        driver    = "GTiff",
        height    = height,
        width     = width,
        count     = 1,
        dtype     = rasterio.float32,
        crs       = CRS.from_epsg(4326),
        transform = transform,
        nodata    = np.nan,
    ) as dst:
        dst.write(min_data, 1)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type = "image/tiff",
        headers    = {"Content-Disposition": f'inline; filename="min_temp_{date_start}_{date_end}.tif"'},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
