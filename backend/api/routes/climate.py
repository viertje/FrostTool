from datetime import date

from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_netcdf_service
from backend.services.netcdf_service import NetCDFService
from backend.models.schemas import (
    AvailableDatesResponse,
    ColorscaleResponse,
    CellValueResponse,
)
from backend.core.exceptions import (
    DatasetNotFoundError,
    VariableNotFoundError,
    InvalidTimeIndexError,
)
from backend.core.config import CONTINENTS

router = APIRouter(prefix="/api/v1", tags=["climate"])


@router.get("/available-dates", response_model=AvailableDatesResponse)
async def get_available_dates(
    service: NetCDFService = Depends(get_netcdf_service),
) -> AvailableDatesResponse:
    try:
        dates: list[str] = service.get_available_dates()
        return AvailableDatesResponse(dates=dates)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/raster")
async def get_raster(
    date_str: str = Query(..., description="Date in YYYY-MM-DD format"),
    continent: str | None = Query(None, description="Optional continent name"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> StreamingResponse:
    try:
        date_obj: date = date.fromisoformat(date_str)
        raster_bytes: bytes = service.get_raster_bytes(date_obj, continent=continent)
        
        return StreamingResponse(
            iter([raster_bytes]),
            media_type="image/tiff",
            headers={"Content-Disposition": f"attachment; filename={date_str}.tif"},
        )
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"No data for date {date_str}")
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/colorscale", response_model=ColorscaleResponse)
async def get_colorscale(
    date_str: str = Query(..., description="Date in YYYY-MM-DD format"),
    service: NetCDFService = Depends(get_netcdf_service),
) -> ColorscaleResponse:
    try:
        date_obj: date = date.fromisoformat(date_str)
        info: dict = service.get_colorscale_info(date_obj)
        return ColorscaleResponse(**info)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"No data for date {date_str}")
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/value", response_model=CellValueResponse)
async def get_cell_value(
    date_str: str = Query(..., description="Date in YYYY-MM-DD format"),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    service: NetCDFService = Depends(get_netcdf_service),
) -> CellValueResponse:
    try:
        date_obj: date = date.fromisoformat(date_str)
        value: float = service.get_cell_value(date_obj, lat, lon)
        return CellValueResponse(value=value, lat=lat, lon=lon, date=date_str)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail=f"No data for date {date_str}")
    except (ValueError, VariableNotFoundError, InvalidTimeIndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/continents")
async def get_continents() -> dict[str, dict]:
    return {
        name: {"bounds": {"min_lat": bounds[0], "max_lat": bounds[1], "min_lon": bounds[2], "max_lon": bounds[3]}}
        for name, bounds in CONTINENTS.items()
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
