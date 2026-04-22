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


class HealthResponse(BaseModel):
    status: str
