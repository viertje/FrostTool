import io
import logging
from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

from backend.core.config import DATA_ROOT, VARIABLE, CONTINENTS
from backend.core.exceptions import (
    DatasetNotFoundError,
    VariableNotFoundError,
    InvalidTimeIndexError,
)

logger = logging.getLogger(__name__)


class NetCDFService:
    @staticmethod
    def resolve_nc_path(date_obj: date) -> Path:
        folder: Path = DATA_ROOT / f"{date_obj.year:04d}"
        pattern: str = date_obj.isoformat().replace("-", "")  # YYYYMMDD
        matches: list[Path] = list(folder.glob(f"*{pattern}*.nc"))
        
        if not matches:
            logger.error(
                "NetCDF file not found",
                extra={"date": str(date_obj), "folder": str(folder), "pattern": pattern}
            )
            raise DatasetNotFoundError(date_obj)
        
        if len(matches) > 1:
            logger.warning(
                f"Multiple NetCDF files found for {date_obj}; using first match",
                extra={"matches": [str(m) for m in matches]}
            )
        
        return matches[0]

    @staticmethod
    def get_temperature_slice(
        date_obj: date,
        time_index: int = 0,
        variable: str = VARIABLE,
    ) -> np.ndarray:
        path: Path = NetCDFService.resolve_nc_path(date_obj)
        
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
                return slice_data.astype(np.float32)
        
        except FileNotFoundError as exc:
            logger.error("NetCDF file not found", extra={"path": str(path)})
            raise DatasetNotFoundError(date_obj) from exc

    @staticmethod
    def get_colorscale_info(
        date_obj: date,
        time_index: int = 0,
        variable: str = VARIABLE,
    ) -> dict[str, float | str]:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, variable
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
        variable: str = VARIABLE,
        continent: str | None = None,
    ) -> bytes:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, variable
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
        variable: str = VARIABLE,
    ) -> float:
        data: np.ndarray = NetCDFService.get_temperature_slice(
            date_obj, time_index, variable
        )
        
        lat_idx: int = int((lat + 90) * (data.shape[0] - 1) / 180)
        lon_idx: int = int((lon + 180) * (data.shape[1] - 1) / 360)
        
        lat_idx = max(0, min(lat_idx, data.shape[0] - 1))
        lon_idx = max(0, min(lon_idx, data.shape[1] - 1))
        
        return float(data[lat_idx, lon_idx])

    @staticmethod
    def get_available_dates() -> list[str]:
        dates: list[str] = []
        
        for year_folder in DATA_ROOT.glob("????"):
            if not year_folder.is_dir():
                continue
            
            for month_folder in year_folder.glob("??"):
                if not month_folder.is_dir():
                    continue
                
                for nc_file in month_folder.glob("*.nc"):
                    filename: str = nc_file.name
                    
                    for part in filename.split("_"):
                        if len(part) == 10 and part[4] == "-" and part[7] == "-":
                            try:
                                date_obj = date.fromisoformat(part)
                                dates.append(part)
                                break
                            except ValueError:
                                continue
        
        return sorted(set(dates))
