import logging
import threading
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS: int = 3600


class TemperatureCache:
    def __init__(self, ttl_seconds: int = _CACHE_TTL_SECONDS) -> None:
        self._cache: dict[str, tuple[float, np.ndarray]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> np.ndarray | None:
        current_time = datetime.now().timestamp()
        with self._lock:
            if key in self._cache:
                cached_time, data = self._cache[key]
                if current_time - cached_time < self._ttl:
                    logger.debug(f"Cache hit for {key}")
                    return data
                del self._cache[key]
        return None

    def set(self, key: str, data: np.ndarray) -> None:
        current_time = datetime.now().timestamp()
        with self._lock:
            self._cache[key] = (current_time, data)


temperature_cache = TemperatureCache()
