from dash import html, dcc, Input, Output, callback, clientside_callback
import dash_bootstrap_components as dbc

from frontend.components.controls import create_controls, create_header, create_map_frame
from frontend.components.map_component import get_map_html


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
                            dcc.Store(id="_map-update-trigger"),
                        ],
                    ),
                ],
            ),
        ],
    )


# Initialize map on load
@callback(
    Output("map-frame", "srcDoc"),
    Input("map-frame", "id"),
    prevent_initial_call=False,
)
def load_initial_map(_: str) -> str:
    return get_map_html("http://localhost:8000/api/v1")


# Post message to iframe when raster-trigger data changes (clientside for speed)
clientside_callback(
    """
    function(trigger_data) {
        if (!trigger_data) return;
        const iframe = document.querySelector('#map-frame');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({
                type: 'loadRaster',
                rasterUrl: trigger_data.rasterUrl,
                colorscaleUrl: trigger_data.colorscaleUrl,
                date: trigger_data.date,
                dateRange: trigger_data.dateRange,
                continent: trigger_data.continent
            }, '*');
        }
        return undefined;
    }
    """,
    Output("_map-update-trigger", "data"),
    Input("raster-trigger", "data"),
)
