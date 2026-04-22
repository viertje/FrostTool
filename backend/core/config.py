from pathlib import Path
import os

DATA_ROOT: Path = Path(
    os.environ.get(
        "DATA_ROOT", r"C:\Olivier\Terra local\data\AgERA5\tmean_v2"
    )
)
VARIABLE: str = "Temperature_Air_2m_Mean_24h"

CONTINENTS: dict[str, tuple[float, float, float, float]] = {
    "Africa": (-35, 37, -18, 52),
    "North America": (15, 83, -170, -50),
    "South America": (-56, 13, -82, -35),
    "Europe": (30, 76, -15, 45),
    "Asia": (-10, 77, 26, 180),
    "Oceania": (-47, -10, 113, 180),
}
