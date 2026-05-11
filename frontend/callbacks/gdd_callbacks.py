import logging
from concurrent.futures import ThreadPoolExecutor, Future

import requests
from dash import Input, Output, State, callback

from frontend.components.gdd_map_component import get_gdd_map_html, get_gdd_map_html_with_raster
from frontend.config import API_BASE_URL

logger = logging.getLogger(__name__)

# Module-level cache: populated on first successful fetch per Dash server session.
# Subsequent navigations to /gdd return instantly without hitting the backend.
_cached_crop_options: list[dict] | None = None
_cached_year_options: list[dict] | None = None
_cached_default_year: int | None = None

_TIMEOUT = 5  # seconds per request


def _fetch_crops() -> list[dict]:
    r = requests.get(f"{API_BASE_URL}/gdd/crops", timeout=_TIMEOUT)
    r.raise_for_status()
    return [{"label": c["display_name"], "value": c["name"]} for c in r.json()["crops"]]


def _fetch_years() -> tuple[list[dict], int]:
    r = requests.get(f"{API_BASE_URL}/gdd/available-years", timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    options = [{"label": str(y), "value": y} for y in reversed(data["years"])]
    return options, data["max_year"]


@callback(
    Output("gdd-crop-selector", "options"),
    Output("gdd-crop-selector", "value"),
    Output("gdd-year-selector", "options"),
    Output("gdd-year-selector", "value"),
    Input("gdd-page-store", "data"),
    prevent_initial_call=False,
)
def populate_gdd_dropdowns(_: bool) -> tuple[list[dict], str | None, list[dict], int | None]:
    global _cached_crop_options, _cached_year_options, _cached_default_year

    if _cached_crop_options is not None and _cached_year_options is not None:
        default_crop = _cached_crop_options[0]["value"] if _cached_crop_options else None
        return _cached_crop_options, default_crop, _cached_year_options, _cached_default_year

    # Both requests run in parallel — worst-case block is _TIMEOUT, not 2 × _TIMEOUT.
    crop_options: list[dict] = []
    default_crop: str | None = None
    year_options: list[dict] = []
    default_year: int | None = None

    with ThreadPoolExecutor(max_workers=2) as pool:
        crops_future: Future[list[dict]] = pool.submit(_fetch_crops)
        years_future: Future[tuple[list[dict], int]] = pool.submit(_fetch_years)

        try:
            crop_options = crops_future.result()
            default_crop = crop_options[0]["value"] if crop_options else None
        except Exception as exc:
            logger.warning("Could not fetch crop list from backend: %s", exc)
            crop_options = [{"label": "Grapevine", "value": "grapevine"}]
            default_crop = "grapevine"

        try:
            year_options, default_year = years_future.result()
        except Exception as exc:
            logger.warning("Could not fetch available years from backend: %s", exc)
            year_options = [{"label": str(y), "value": y} for y in range(2007, 1978, -1)]
            default_year = 2007

    # Only cache if both fetches succeeded (i.e., we got real data, not fallbacks).
    if crops_future.exception() is None and years_future.exception() is None:
        _cached_crop_options = crop_options
        _cached_year_options = year_options
        _cached_default_year = default_year

    return crop_options, default_crop, year_options, default_year


@callback(
    Output("gdd-map-frame", "srcDoc"),
    Output("gdd-status", "children"),
    Input("gdd-render-btn", "n_clicks"),
    State("gdd-crop-selector", "value"),
    State("gdd-year-selector", "value"),
    prevent_initial_call=True,
)
def render_gdd_map(
    n_clicks: int | None,
    crop: str | None,
    year: int | None,
) -> tuple[str, str]:
    if not crop or not year:
        return get_gdd_map_html(), "Select a crop and year, then click Render."

    raster_url = f"{API_BASE_URL}/gdd/raster?year={year}&crop={crop}"
    src = get_gdd_map_html_with_raster(raster_url, year, crop)
    crop_label = crop.capitalize()
    return src, f"Rendering {year} · {crop_label} — this may take ~30 s on first load."
