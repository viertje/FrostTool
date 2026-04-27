from datetime import datetime
from dash import html, Input, Output, State, callback, dash, clientside_callback, callback_context
import requests
import plotly.graph_objects as go

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
    Output("timeseries-graph", "figure"),
    Input("clicked-coordinate", "data"),
    State("raster-trigger", "data"),
    prevent_initial_call=True,
)
def update_timeseries_graph(clicked_coord: dict | None, raster_trigger: dict | None) -> go.Figure:
    """Update the timeseries graph when a coordinate is clicked."""
    if not clicked_coord:
        return go.Figure().update_layout(
            template="plotly_dark",
            paper_bgcolor="#0D4F44",
            plot_bgcolor="#0D4F44",
            font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
            margin=dict(l=40, r=20, t=30, b=40),
            showlegend=False,
        )
    
    if not raster_trigger:
        return go.Figure().update_layout(
            template="plotly_dark",
            paper_bgcolor="#0D4F44",
            plot_bgcolor="#0D4F44",
            font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
            margin=dict(l=40, r=20, t=30, b=40),
            showlegend=False,
        )
    
    lat = clicked_coord.get("lat")
    lon = clicked_coord.get("lon")
    
    # Extract date range from raster_trigger (which has the correct dateRange)
    raster_date_range = raster_trigger.get("dateRange")
    if isinstance(raster_date_range, dict):
        start_date = raster_date_range.get("start")
        end_date = raster_date_range.get("end")
    else:
        # Fallback: use single date from raster_trigger
        start_date = raster_trigger.get("date")
        end_date = raster_trigger.get("date")
    
    if not start_date or not end_date:
        return go.Figure().update_layout(
            template="plotly_dark",
            paper_bgcolor="#0D4F44",
            plot_bgcolor="#0D4F44",
            font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
            margin=dict(l=40, r=20, t=30, b=40),
            showlegend=False,
        )
    
    temp_type = raster_trigger.get("tempType", "mean")
    
    try:
        # Fetch timeseries data from backend
        ts_url = f"{API}/timeseries?start_date={start_date}&end_date={end_date}&lat={lat}&lon={lon}&temp_type={temp_type}"
        response = requests.get(ts_url, timeout=30)
        response.raise_for_status()
        ts_data = response.json()
        
        dates = [d["date"] for d in ts_data["data"]]
        values_k = [d["value"] for d in ts_data["data"]]
        values_c = [v - 273.15 for v in values_k]
        
        # Create figure
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=values_c,
            mode='lines+markers',
            name='Temperature',
            line=dict(color='#D6CDA4', width=2),
            marker=dict(size=4, color='#D6CDA4'),
            hovertemplate='<b>%{x}</b><br>%{y:.1f}°C<extra></extra>',
        ))
        
        fig.update_layout(
            title=f"Temperature at {lat:.2f}°, {lon:.2f}° ({start_date} to {end_date})",
            xaxis_title="Date",
            yaxis_title="Temperature (°C)",
            template="plotly_dark",
            paper_bgcolor="#0D4F44",
            plot_bgcolor="#0D4F44",
            font=dict(color="#EEF2E6", family="'Space Mono', monospace", size=11),
            margin=dict(l=40, r=20, t=40, b=40),
            showlegend=False,
            hovermode='x unified',
        )
        
        return fig
        
    except Exception as e:
        # Return error figure
        fig = go.Figure()
        fig.add_annotation(
            text=f"Error loading timeseries: {str(e)}",
            showarrow=False,
            font=dict(size=12, color="#e07050"),
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0D4F44",
            plot_bgcolor="#0D4F44",
            font=dict(color="#EEF2E6"),
            margin=dict(l=40, r=20, t=30, b=40),
        )
        return fig


@callback(
    Output("stats-box", "children"),
    Output("raster-trigger", "data"),
    Input("render-btn", "n_clicks"),
    State("date-range", "start_date"),
    State("date-range", "end_date"),
    State("selected-continent", "data"),
    State("selected-temp-type", "data"),
    prevent_initial_call=True,
)
def render_heatmap(
    n_clicks: int,
    start_date: str | None,
    end_date: str | None,
    selected_continent: str | None,
    selected_temp_type: str | None,
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

    temp_type = selected_temp_type or "mean"

    try:
        # Use aggregation (minimum temperature across range) for frost detection
        colorscale_url: str = f"{API}/colorscale?start_date={d_start_str}&end_date={d_end_str}&agg_type=min&temp_type={temp_type}"
        raster_url: str = f"{API}/raster?start_date={d_start_str}&end_date={d_end_str}&agg_type=min&temp_type={temp_type}"
        
        if selected_continent:
            raster_url += f"&continent={selected_continent}"
        
        cs: dict = requests.get(colorscale_url, timeout=60).json()
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

    temp_type_label = "Minimum (24h)" if temp_type == "min" else "Mean (24h)"

    stats: list = [
        html.Div(f"Date Range : {d_start_str} to {d_end_str}"),
        html.Div(f"Days       : {days}"),
        html.Div(f"Type       : {temp_type_label}"),
        html.Div(f"Aggregation: Minimum (frost detection)"),
        html.Div(f"Units      : °C"),
        html.Div(f"Min        : {cs['min_value'] - 273.15:.3f}"),
        html.Div(f"Max        : {cs['max_value'] - 273.15:.3f}"),
        html.Div(f"Mean       : {cs['mean_value'] - 273.15:.3f}"),
    ]

    trigger: dict = {
        "rasterUrl": raster_url,
        "colorscaleUrl": colorscale_url,
        "date": d_start_str,
        "dateRange": {"start": d_start_str, "end": d_end_str}
        if d_start != d_end
        else None,
        "continent": selected_continent,
        "tempType": temp_type,
    }
    return stats, trigger


@callback(
    Output("selected-continent", "data"),
    Input("continent-selector", "value"),
    prevent_initial_call=True,
)
def select_continent(value: str | None) -> str | None:
    return value if value else None


@callback(
    Output("selected-temp-type", "data"),
    Input("temp-type-selector", "value"),
    prevent_initial_call=True,
)
def select_temp_type(value: str | None) -> str | None:
    return value if value else "mean"
