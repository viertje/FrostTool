from dash import html, dcc, Input, Output, State, callback, callback_context, clientside_callback
import dash_bootstrap_components as dbc
import json

from frontend.components.controls import create_controls, create_header, create_map_frame
from frontend.components.map_component import get_map_html, get_map_html_with_initial_raster


def create_layout() -> dbc.Container:
    return dbc.Container(
        fluid=True,
        style={"background": "#1B6758", "minHeight": "100vh", "padding": "0"},
        children=[
            create_header(),
            dbc.Row(
                style={"margin": "0", "height": "calc(100vh - 72px)", "display": "flex", "flexDirection": "column"},
                children=[
                    dbc.Row(
                        style={"margin": "0", "flex": "1", "minHeight": "0"},
                        children=[
                            create_controls(),
                            dbc.Col(
                                width=9,
                                style={"padding": "0", "display": "flex", "flexDirection": "column"},
                                children=[
                                    html.Div(
                                        style={"flex": "1", "minHeight": "0", "position": "relative"},
                                        children=[
                                            create_map_frame(),
                                            dcc.Store(id="raster-trigger"),
                                            dcc.Store(id="clicked-coordinate"),
                                            dcc.Store(id="coordinate-intermediate"),
                                            html.Button(id="coordinate-trigger", style={"display": "none"}),
                                        ],
                                    ),
                                    html.Div(
                                        id="graph-container",
                                        style={
                                            "height": "0%",
                                            "borderTop": "1px solid #3C8361",
                                            "background": "#0D4F44",
                                            "padding": "12px",
                                            "overflow": "hidden",
                                            "transition": "height 0.3s ease",
                                            "position": "relative",
                                        },
                                        children=[
                                            html.Button(
                                                "✕",
                                                id="close-graph-btn",
                                                style={
                                                    "position": "absolute",
                                                    "top": "8px",
                                                    "right": "8px",
                                                    "background": "transparent",
                                                    "border": "none",
                                                    "color": "#D6CDA4",
                                                    "fontSize": "20px",
                                                    "cursor": "pointer",
                                                    "padding": "0",
                                                    "width": "24px",
                                                    "height": "24px",
                                                    "display": "flex",
                                                    "alignItems": "center",
                                                    "justifyContent": "center",
                                                    "zIndex": "10",
                                                },
                                            ),
                                            dcc.Graph(
                                                id="timeseries-graph",
                                                style={"height": "100%", "margin": "0"},
                                                config={"responsive": True, "displayModeBar": False},
                                            )
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# Clientside callback to update intermediate store from window._lastCoordinate
clientside_callback(
    """
    function(n_clicks) {
        console.log('[INTERMEDIATE] Button clicked, n_clicks=' + n_clicks);
        if (window._lastCoordinate) {
            console.log('[INTERMEDIATE] Updating store with:', window._lastCoordinate);
            return window._lastCoordinate;
        }
        console.log('[INTERMEDIATE] No coordinate in window');
        return undefined;
    }
    """,
    Output("coordinate-intermediate", "data"),
    Input("coordinate-trigger", "n_clicks"),
    prevent_initial_call=False,
)


# Server-side callback to copy from intermediate store to final store
# This ensures server-side callbacks are properly triggered
@callback(
    Output("clicked-coordinate", "data"),
    Input("coordinate-intermediate", "data"),
    prevent_initial_call=True,
)
def sync_coordinate_to_final_store(intermediate_data: dict | None) -> dict | None:
    """Sync coordinate from intermediate store to final store."""
    return intermediate_data


# Setup postMessage listener - runs once on page load
clientside_callback(
    """
    function() {
        console.log('[SETUP] Setting up postMessage listener');
        if (window._messageListenerSetup) {
            console.log('[SETUP] Listener already setup');
            return '';
        }
        window._messageListenerSetup = true;
        
        window.addEventListener('message', function(e) {
            console.log('[LISTENER] Received message:', e.data);
            if (e.data && e.data.type === 'coordinateClicked') {
                console.log('[LISTENER] Processing coordinateClicked');
                // Store the coordinate in window
                window._lastCoordinate = {
                    lat: e.data.lat,
                    lon: e.data.lon,
                    date: e.data.date,
                    dateRange: e.data.dateRange,
                };
                console.log('[LISTENER] Stored coordinate, clicking trigger');
                // Trigger the hidden button to signal coordinate change
                const btn = document.getElementById('coordinate-trigger');
                if (btn) {
                    btn.click();
                    console.log('[LISTENER] Clicked trigger button');
                }
            }
        });
        return '';
    }
    """,
    Output("map-frame", "title"),
    Input("map-frame", "id"),
    prevent_initial_call=False,
)


# Callback to toggle graph container height based on clicked coordinate or close button
@callback(
    Output("graph-container", "style"),
    Input("clicked-coordinate", "data"),
    Input("close-graph-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_graph_visibility(clicked_data: dict | None, close_clicks: int) -> dict:
    """Show graph container when coordinate is clicked, hide when close button is pressed."""
    base_style = {
        "borderTop": "1px solid #3C8361",
        "background": "#0D4F44",
        "padding": "12px",
        "overflow": "hidden",
        "transition": "height 0.3s ease",
        "position": "relative",
    }
    
    # Check which input triggered this callback
    trigger_id = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else None
    
    if trigger_id == "close-graph-btn":
        # Close button was clicked - hide the graph
        base_style["height"] = "0%"
    elif clicked_data:
        # Coordinate was clicked - show the graph
        base_style["height"] = "25%"
    else:
        # No data, hide graph
        base_style["height"] = "0%"
    
    return base_style





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
