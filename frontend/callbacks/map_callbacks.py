from datetime import datetime
from dash import html, Input, Output, State, callback, dash
import requests

from ..components.map_component import API


@callback(
    Output("date-status", "children"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def show_date_status(start_date: str | None, end_date: str | None) -> str:
    if not start_date or not end_date:
        return ""
    d_start: datetime = datetime.strptime(start_date[:10], "%Y-%m-%d")
    d_end: datetime = datetime.strptime(end_date[:10], "%Y-%m-%d")
    days: int = (d_end - d_start).days + 1

    if days > 180:
        return f"⚠ Range is {days} days (>6 months). Max allowed: 180 days."
    return f"✓ {days} days selected"


@callback(
    Output("stats-box", "children"),
    Output("raster-trigger", "data"),
    Input("render-btn", "n_clicks"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("selected-continent", "data"),
    prevent_initial_call=True,
)
def render_heatmap(
    n_clicks: int,
    start_date: str | None,
    end_date: str | None,
    selected_continent: str | None,
) -> tuple:
    if not start_date or not end_date:
        return (
            [
                html.Div(
                    "Please select a date range first.",
                    style={"color": "#e07050"},
                )
            ],
            dash.no_update,
        )

    d_start_str: str = start_date[:10]
    d_end_str: str = end_date[:10]

    d_start: datetime = datetime.strptime(d_start_str, "%Y-%m-%d")
    d_end: datetime = datetime.strptime(d_end_str, "%Y-%m-%d")
    days: int = (d_end - d_start).days + 1

    if days > 180:
        return (
            [
                html.Div(
                    f"⚠ Range is {days} days (>6 months). Max allowed: 180 days.",
                    style={"color": "#e07050"},
                )
            ],
            dash.no_update,
        )

    try:
        colorscale_url: str = f"{API}/colorscale?date_str={d_start_str}"
        raster_url: str = f"{API}/raster?date_str={d_start_str}"
        
        if selected_continent:
            raster_url += f"&continent={selected_continent}"
        
        cs: dict = requests.get(colorscale_url, timeout=20).json()
    except Exception as e:
        return (
            [html.Div(f"Backend error: {e}", style={"color": "#e07050"})],
            dash.no_update,
        )

    if "detail" in cs:
        return (
            [html.Div(f"⚠ {cs['detail']}", style={"color": "#e07050"})],
            dash.no_update,
        )

    stats: list = [
        html.Div(f"Date    : {d_start_str}"),
        html.Div(f"Variable: Temperature_Air_2m_Mean_24h"),
        html.Div(f"Units   : °C"),
        html.Div(f"Min     : {cs['min_value'] - 273.15:.3f}"),
        html.Div(f"Max     : {cs['max_value'] - 273.15:.3f}"),
        html.Div(f"Mean    : {cs['mean_value'] - 273.15:.3f}"),
    ]

    trigger: dict = {
        "rasterUrl": raster_url,
        "colorscaleUrl": colorscale_url,
        "date": d_start_str,
        "dateRange": {"start": d_start_str, "end": d_end_str}
        if d_start != d_end
        else None,
        "continent": selected_continent,
    }
    return stats, trigger


@callback(
    Output("selected-continent", "data"),
    Input("continent-selector", "value"),
    prevent_initial_call=True,
)
def select_continent(value: str | None) -> str | None:
    return value if value else None
