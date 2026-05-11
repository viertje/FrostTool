from pathlib import Path
import os

# Temperature data sources configuration
TEMPERATURE_SOURCES: dict[str, dict[str, Path | str]] = {
    "mean": {
        "path": Path(os.environ.get("DATA_ROOT_MEAN", r"C:\Olivier\Terra local\data\AgERA5\tmean_v2")),
        "variable": "Temperature_Air_2m_Mean_24h",
        "label": "Mean (24h)",
        "units": "K",
    },
    "min": {
        "path": Path(os.environ.get("DATA_ROOT_MIN", r"C:\Olivier\Terra local\data\AgERA5\tmin_v2")),
        "variable": "Temperature_Air_2m_Min_24h",
        "label": "Minimum (24h)",
        "units": "K",
    },
}

# Default to mean, but can be overridden
DEFAULT_TEMP_TYPE: str = "mean"

# Legacy support
DATA_ROOT: Path = TEMPERATURE_SOURCES[DEFAULT_TEMP_TYPE]["path"]
VARIABLE: str = TEMPERATURE_SOURCES[DEFAULT_TEMP_TYPE]["variable"]

CACHE_DIR: Path = Path(
    os.environ.get("CACHE_DIR", str(Path(__file__).parent.parent.parent / ".cache"))
)

CROPS_CONFIG_PATH: Path = Path(
    os.environ.get("CROPS_CONFIG", str(Path(__file__).parent.parent.parent / "crops.txt"))
)

# Earliest year included in the background GDD warm-up at startup.
# Pre-2000 years are rarely needed; raise this value to reduce cold-start time.
GDD_WARMUP_MIN_YEAR: int = int(os.environ.get("GDD_WARMUP_MIN_YEAR", "2000"))

CONTINENTS: dict[str, tuple[float, float, float, float]] = {
    "Africa": (-35, 37, -18, 52),
    "North America": (15, 83, -170, -50),
    "South America": (-56, 13, -82, -35),
    "Europe": (30, 76, -15, 45),
    "Asia": (-10, 77, 26, 180),
    "Oceania": (-47, -10, 113, 180),
}
