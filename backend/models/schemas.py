from pydantic import BaseModel


class AvailableDatesResponse(BaseModel):
    dates: list[str]


class ColorscaleResponse(BaseModel):
    min_value: float
    max_value: float
    mean_value: float
    units: str


class CellValueResponse(BaseModel):
    value: float
    lat: float
    lon: float
    date: str


class TimeseriesDataPoint(BaseModel):
    date: str
    value: float


class TimeseriesResponse(BaseModel):
    lat: float
    lon: float
    start_date: str
    end_date: str
    data: list[TimeseriesDataPoint]
    units: str


class HealthResponse(BaseModel):
    status: str
