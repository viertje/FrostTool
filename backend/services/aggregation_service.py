import logging
from datetime import date

import numpy as np

from backend.models.domain import AggregationResult

logger = logging.getLogger(__name__)

_VALID_AGGREGATIONS: frozenset[str] = frozenset({"min", "max", "mean"})


class AggregationService:
    @staticmethod
    def aggregate(
        slices: list[tuple[date, np.ndarray]],
        aggregation: str,
        variable: str,
    ) -> AggregationResult:
        if not slices:
            raise ValueError("No data slices to aggregate")
        if aggregation not in _VALID_AGGREGATIONS:
            raise ValueError(f"Unknown aggregation '{aggregation}'. Valid: {sorted(_VALID_AGGREGATIONS)}")

        grids = [data for _, data in slices]
        stacked = np.stack(grids, axis=0)

        with np.errstate(all="ignore"):
            if aggregation == "min":
                result = np.nanmin(stacked, axis=0)
            elif aggregation == "max":
                result = np.nanmax(stacked, axis=0)
            else:
                result = np.nanmean(stacked, axis=0)

        logger.debug(
            f"Aggregated {len(slices)} slices of '{variable}' using '{aggregation}'"
        )

        return AggregationResult(
            data=result.astype(np.float32),
            aggregation=aggregation,
            start_date=slices[0][0],
            end_date=slices[-1][0],
            units="K",
        )
