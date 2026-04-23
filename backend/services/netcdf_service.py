import io
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

from backend.core.config import TEMPERATURE_SOURCES, CONTINENTS
from backend.core.exceptions import (
    DatasetNotFoundError,
    VariableNotFoundError,
    InvalidTimeIndexError,
)

logger = logging.getLogger(__name__)

# Cache for temperature slices: {cache_key: (timestamp, ndarray)}
_temperature_cache: dict[str, tuple[float, np.ndarray]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_data_root(temp_type: str = "mean") -> Path:
    """Get DATA_ROOT for a given temperature type."""
    if temp_type not in TEMPERATURE_SOURCES:
        raise ValueError(f"Unknown temperature type: {temp_type}")
    return TEMPERATURE_SOURCES[temp_type]["path"]


def _get_variable(temp_type: str = "mean") -> str:
    """Get VARIABLE name for a given temperature type."""
    if temp_type not in TEMPERATURE_SOURCES:
        raise ValueError(f"Unknown temperature type: {temp_type}")
    return TEMPERATURE_SOURCES[temp_type]["variable"]


class NetCDFService:
    @staticmethod
    def resolve_nc_path(date_obj: date, temp_type: str = "mean") -> Path:
        data_root = _get_data_root(temp_type)
        folder: Path = data_root / f"{date_obj.year:04d}"
        pattern: str = date_obj.isoformat().replace("-", "")  # YYYYMMDD
        
        logger.debug(f"Searching for {pattern} in {folder}")
        matches: list[Path] = list(folder.glob(f"*{pattern}*.nc"))
        
        if not matches:
            logger.error(
                "NetCDF file not found",
                extra={"date": str(date_obj), "folder": str(folder), "pattern": pattern, "glob": f"*{pattern}*.nc"}
            )
            raise DatasetNotFoundError(date_obj)
        
        if len(matches) > 1:
            logger.warning(
                f"Multiple NetCDF files found for {date_obj}; using first match",
                extra={"matches": [str(m) for m in matches]}
            )
        
        logger.debug(f"Found file: {matches[0]}")
        return matches[0]

    @staticmethod
    def get_temperature_slice(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> np.ndarray:
        variable = _get_variable(temp_type)
        
        # Check cache first
        cache_key = f"{date_obj.isoformat()}_{time_index}_{temp_type}"
        current_time = datetime.now().timestamp()
        
        with _cache_lock:
            if cache_key in _temperature_cache:
                cached_time, cached_data = _temperature_cache[cache_key]
                if current_time - cached_time < _CACHE_TTL_SECONDS:
                    logger.debug(f"Cache hit for {cache_key}")
                    return cached_data
                else:
                    # Cache expired
                    del _temperature_cache[cache_key]
        
        # Load from disk
        path: Path = NetCDFService.resolve_nc_path(date_obj, temp_type)
        
        try:
            with xr.open_dataset(path, engine="netcdf4", chunks={}) as ds:
                if variable not in ds.data_vars:
                    logger.error(
                        "Variable not found",
                        extra={"variable": variable, "path": str(path)}
                    )
                    raise VariableNotFoundError(variable, str(path))
                
                data_array = ds[variable]
                
                if time_index >= data_array.sizes.get("time", 1):
                    logger.error(
                        "Time index out of range",
                        extra={
                            "index": time_index,
                            "max": data_array.sizes.get("time", 1) - 1
                        }
                    )
                    raise InvalidTimeIndexError(
                        time_index, data_array.sizes.get("time", 1) - 1
                    )
                
                slice_data: np.ndarray = data_array.isel(time=time_index).values
                slice_data = slice_data.astype(np.float32)
                
                # Store in cache
                with _cache_lock:
                    _temperature_cache[cache_key] = (current_time, slice_data)
                
                return slice_data
        
        except FileNotFoundError as exc:
            logger.error("NetCDF file not found", extra={"path": str(path)})
            raise DatasetNotFoundError(date_obj) from exc

    @staticmethod
    def get_colorscale_info(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> dict[str, float | str]:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )
        
        valid_data: np.ndarray = data[~np.isnan(data)]
        
        return {
            "min_value": float(np.min(valid_data)),
            "max_value": float(np.max(valid_data)),
            "mean_value": float(np.mean(valid_data)),
            "units": "K",
        }

    @staticmethod
    def get_raster_bytes(
        date_obj: date,
        time_index: int = 0,
        temp_type: str = "mean",
        continent: str | None = None,
    ) -> bytes:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )
        
        lat_size, lon_size = data.shape
        
        # Determine bounds (either full globe or continent)
        if continent and continent in CONTINENTS:
            min_lat, max_lat, min_lon, max_lon = CONTINENTS[continent]
        else:
            # Global view: exclude Antarctica (south of -60)
            min_lat, max_lat, min_lon, max_lon = -60, 90, -180, 180
        
        # Clip data to bounds
        # In GeoTIFF: row 0 = lat 90 (north), row lat_size-1 = lat -90 (south)
        lat_indices = np.linspace(90, -90, lat_size)
        lon_indices = np.linspace(-180, 180, lon_size)
        
        lat_mask = (lat_indices >= min_lat) & (lat_indices <= max_lat)
        lon_mask = (lon_indices >= min_lon) & (lon_indices <= max_lon)
        
        # Get bounding indices
        lat_rows = np.where(lat_mask)[0]
        lon_cols = np.where(lon_mask)[0]
        
        if len(lat_rows) == 0 or len(lon_cols) == 0:
            # No data in bounds, return empty raster
            clipped_data = np.full((1, 1), np.nan, dtype=np.float32)
            new_min_lat, new_max_lat = min_lat, max_lat
            new_min_lon, new_max_lon = min_lon, max_lon
        else:
            # Extract the bounding rectangle
            row_start, row_end = lat_rows[0], lat_rows[-1] + 1
            col_start, col_end = lon_cols[0], lon_cols[-1] + 1
            
            clipped_data = data[row_start:row_end, col_start:col_end].astype(np.float32)
            
            # Calculate new bounds based on extracted rows/cols
            new_max_lat = lat_indices[row_start]
            new_min_lat = lat_indices[row_end - 1]
            new_min_lon = lon_indices[col_start]
            new_max_lon = lon_indices[col_end - 1]
        
        clipped_lat_size, clipped_lon_size = clipped_data.shape
        transform = from_bounds(new_min_lon, new_min_lat, new_max_lon, new_max_lat, clipped_lon_size, clipped_lat_size)
        
        output = io.BytesIO()
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            height=clipped_lat_size,
            width=clipped_lon_size,
            count=1,
            dtype=clipped_data.dtype,
            crs=CRS.from_epsg(4326),
            transform=transform,
        ) as dst:
            dst.write(clipped_data, 1)
        
        output.seek(0)
        return output.getvalue()

    @staticmethod
    def get_cell_value(
        date_obj: date,
        lat: float,
        lon: float,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> float:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, temp_type
        )
        
        # In GeoTIFF: row 0 = lat 90 (north), row lat_size-1 = lat -90 (south)
        lat_idx: int = int((90 - lat) * (data.shape[0] - 1) / 180)
        lon_idx: int = int((lon + 180) * (data.shape[1] - 1) / 360)
        
        lat_idx = max(0, min(lat_idx, data.shape[0] - 1))
        lon_idx = max(0, min(lon_idx, data.shape[1] - 1))
        
        value = data[lat_idx, lon_idx]
        
        if np.isnan(value):
            raise ValueError(f"No data available at lat={lat}, lon={lon}")
        
        return float(value)

    @staticmethod
    def get_available_dates(temp_type: str = "mean") -> list[str]:
        data_root = _get_data_root(temp_type)
        dates: list[str] = []
        
        for year_folder in data_root.glob("????"):
            if not year_folder.is_dir():
                continue
            
            for nc_file in year_folder.glob("*.nc"):
                filename: str = nc_file.name
                
                for part in filename.split("_"):
                    if len(part) == 8 and part.isdigit():
                        # Try YYYYMMDD format
                        try:
                            year = int(part[:4])
                            month = int(part[4:6])
                            day = int(part[6:8])
                            date_obj = date(year, month, day)
                            dates.append(date_obj.isoformat())
                            break
                        except (ValueError, IndexError):
                            continue
        
        return sorted(set(dates))

    @staticmethod
    def get_temperature_slice_range(
        start_date: date,
        end_date: date,
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> list[tuple[date, np.ndarray]]:
        """Load multiple dates in parallel. Returns list of (date, ndarray) tuples."""
        dates: list[date] = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)
        
        results: list[tuple[date, np.ndarray]] = []
        failed_dates: list[tuple[date, str]] = []
        
        # Parallel loading with max 5 workers to avoid overwhelming disk I/O
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    NetCDFService.get_temperature_slice, d, time_index, temp_type
                ): d
                for d in dates
            }
            
            for future in futures:
                date_obj = futures[future]
                try:
                    data = future.result()
                    results.append((date_obj, data))
                except Exception as e:
                    failed_dates.append((date_obj, str(e)))
                    logger.warning(f"Failed to load date {date_obj}: {e}")
        
        if not results:
            # All dates failed
            failed_summary = "; ".join([f"{d.isoformat()}: {err}" for d, err in failed_dates[:3]])
            logger.error(f"No data available for any date in range {start_date} to {end_date}. Failures: {failed_summary}")
            raise DatasetNotFoundError(start_date)
        
        if failed_dates:
            logger.info(f"Loaded {len(results)}/{len(dates)} dates; skipped {len(failed_dates)} missing dates")
        
        return sorted(results, key=lambda x: x[0])

    @staticmethod
    def get_raster_bytes_aggregated(
        start_date: date,
        end_date: date,
        aggregation: str = "min",
        time_index: int = 0,
        temp_type: str = "mean",
        continent: str | None = None,
    ) -> bytes:
        """Get aggregated raster across a date range (min, max, or mean)."""
        # Load all dates in parallel
        date_data_pairs = NetCDFService.get_temperature_slice_range(
            start_date, end_date, time_index, temp_type
        )
        
        if not date_data_pairs:
            raise DatasetNotFoundError(start_date)
        
        # Stack all data arrays
        grids = [data for _, data in date_data_pairs]
        stacked = np.stack(grids, axis=0)  # (time, lat, lon)
        
        # Aggregate along time axis
        if aggregation == "min":
            result = np.nanmin(stacked, axis=0)
        elif aggregation == "max":
            result = np.nanmax(stacked, axis=0)
        elif aggregation == "mean":
            result = np.nanmean(stacked, axis=0)
        else:
            raise ValueError(f"Unknown aggregation: {aggregation}")
        
        result = result.astype(np.float32)
        
        # Clip to bounds (same as get_raster_bytes)
        lat_size, lon_size = result.shape
        
        if continent and continent in CONTINENTS:
            min_lat, max_lat, min_lon, max_lon = CONTINENTS[continent]
        else:
            min_lat, max_lat, min_lon, max_lon = -60, 90, -180, 180
        
        lat_indices = np.linspace(90, -90, lat_size)
        lon_indices = np.linspace(-180, 180, lon_size)
        
        lat_mask = (lat_indices >= min_lat) & (lat_indices <= max_lat)
        lon_mask = (lon_indices >= min_lon) & (lon_indices <= max_lon)
        
        lat_rows = np.where(lat_mask)[0]
        lon_cols = np.where(lon_mask)[0]
        
        if len(lat_rows) == 0 or len(lon_cols) == 0:
            clipped_data = np.full((1, 1), np.nan, dtype=np.float32)
            new_min_lat, new_max_lat = min_lat, max_lat
            new_min_lon, new_max_lon = min_lon, max_lon
        else:
            row_start, row_end = lat_rows[0], lat_rows[-1] + 1
            col_start, col_end = lon_cols[0], lon_cols[-1] + 1
            
            clipped_data = result[row_start:row_end, col_start:col_end]
            
            new_max_lat = lat_indices[row_start]
            new_min_lat = lat_indices[row_end - 1]
            new_min_lon = lon_indices[col_start]
            new_max_lon = lon_indices[col_end - 1]
        
        clipped_lat_size, clipped_lon_size = clipped_data.shape
        transform = from_bounds(new_min_lon, new_min_lat, new_max_lon, new_max_lat, clipped_lon_size, clipped_lat_size)
        
        output = io.BytesIO()
        with rasterio.open(
            output,
            "w",
            driver="GTiff",
            height=clipped_lat_size,
            width=clipped_lon_size,
            count=1,
            dtype=clipped_data.dtype,
            crs=CRS.from_epsg(4326),
            transform=transform,
        ) as dst:
            dst.write(clipped_data, 1)
        
        output.seek(0)
        return output.getvalue()

    @staticmethod
    def get_colorscale_info_aggregated(
        start_date: date,
        end_date: date,
        aggregation: str = "min",
        time_index: int = 0,
        temp_type: str = "mean",
    ) -> dict[str, float | str]:
        """Get colorscale info for aggregated data across range."""
        date_data_pairs = NetCDFService.get_temperature_slice_range(
            start_date, end_date, time_index, temp_type
        )
        
        if not date_data_pairs:
            raise DatasetNotFoundError(start_date)
        
        grids = [data for _, data in date_data_pairs]
        stacked = np.stack(grids, axis=0)
        
        if aggregation == "min":
            result = np.nanmin(stacked, axis=0)
        elif aggregation == "max":
            result = np.nanmax(stacked, axis=0)
        elif aggregation == "mean":
            result = np.nanmean(stacked, axis=0)
        else:
            raise ValueError(f"Unknown aggregation: {aggregation}")
        
        valid_data = result[~np.isnan(result)]
        
        return {
            "min_value": float(np.min(valid_data)),
            "max_value": float(np.max(valid_data)),
            "mean_value": float(np.mean(valid_data)),
            "units": "K",
        }

