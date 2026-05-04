from dataclasses import dataclass
from datetime import date

import numpy as np


@dataclass
class ColorscaleInfo:
    min_value: float
    max_value: float
    mean_value: float
    units: str


@dataclass
class AggregationResult:
    data: np.ndarray
    aggregation: str
    start_date: date
    end_date: date
    units: str
