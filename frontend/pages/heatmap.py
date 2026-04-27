from dash import html, dcc, Input, Output, callback, callback_context
import dash_bootstrap_components as dbc

from frontend.components.controls import create_controls, create_header, create_map_frame
from frontend.components.map_component import get_map_html, get_map_html_with_initial_raster


def create_layout() -> dbc.Container:
    return dbc.Container(
        fluid=True,
        style={"background": "#1B6758", "minHeight": "100vh", "padding": "0"},
        children=[
            create_header(),
            dbc.Row(
                style={"margin": "0", "height": "calc(100vh - 72px)"},
                children=[
                    create_controls(),
                    dbc.Col(
                        width=9,
                        style={"padding": "0", "position": "relative"},
                        children=[
                            create_map_frame(),
                            dcc.Store(id="raster-trigger"),
                        ],
                    ),
                ],
            ),
        ],
    )


# Single callback for both initial load and raster updates
# This avoids duplicate output errors and consolidates map rendering logic
@callback(
    Output("map-frame", "srcDoc"),
    Input("map-frame", "id"),
    Input("raster-trigger", "data"),
    prevent_initial_call=False,
)
def update_map(map_frame_id: str, trigger_data: dict | None) -> str:
    """Update map on initial load or when raster-trigger changes.
    
    - Initial load: Returns empty map
    - Raster update: Returns map with auto-loaded raster data
    """
    ctx = callback_context
    
    # Determine which input triggered this callback
    if ctx.triggered and ctx.triggered[0]["prop_id"].startswith("raster-trigger"):
        # Raster-trigger changed: regenerate iframe with data
        if not trigger_data:
            return get_map_html("http://localhost:8000/api/v1")
        
        return get_map_html_with_initial_raster(
            api_url="http://localhost:8000/api/v1",
            raster_url=trigger_data.get("rasterUrl"),
            colorscale_url=trigger_data.get("colorscaleUrl"),
            date=trigger_data.get("date"),
            continent=trigger_data.get("continent"),
            temp_type=trigger_data.get("tempType"),
        )
    
    # Initial load: return empty map
    return get_map_html("http://localhost:8000/api/v1")
