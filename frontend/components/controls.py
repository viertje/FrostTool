from dash import html, dcc
import dash_bootstrap_components as dbc

from .map_component import get_map_html, API


def create_map_frame() -> html.Iframe:
    map_html: str = get_map_html(API)
    return html.Iframe(
        id="map-frame",
        srcDoc=map_html,
        style={"width": "100%", "height": "100%", "border": "none"},
    )


def create_controls() -> dbc.Col:
    label_style: dict = {
        "fontFamily": "'Space Mono',monospace",
        "fontSize": "10px",
        "letterSpacing": "2px",
        "color": "#3C8361",
        "marginBottom": "10px",
    }

    sidebar_style: dict = {
        "background": "#EEF2E6",
        "borderRight": "1px solid #3C8361",
        "padding": "26px 20px",
        "overflowY": "auto",
        "height": "100%",
    }

    return dbc.Col(
        width=3,
        style=sidebar_style,
        children=[
            html.H6("CONTINENT", style=label_style),
            dcc.Dropdown(
                id="continent-selector",
                options=[
                    {"label": "🌍 Global", "value": ""},
                    {"label": "Africa", "value": "Africa"},
                    {"label": "North America", "value": "North America"},
                    {"label": "South America", "value": "South America"},
                    {"label": "Europe", "value": "Europe"},
                    {"label": "Asia", "value": "Asia"},
                    {"label": "Oceania", "value": "Oceania"},
                ],
                value="",
                clearable=False,
                style={"width": "100%", "marginBottom": "12px"},
            ),
            dcc.Store(id="selected-continent", data=None),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            html.H6("DATE RANGE", style=label_style),
            dcc.DatePickerRange(
                id="date-range",
                start_date="2020-12-30",
                end_date="2020-12-31",
                display_format="YYYY-MM-DD",
                style={"width": "100%"},
            ),
            html.Div(
                id="date-status",
                style={
                    "fontFamily": "'Space Mono',monospace",
                    "fontSize": "11px",
                    "marginTop": "8px",
                    "color": "#3C8361",
                },
            ),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            dbc.Button(
                "Render Heatmap",
                id="render-btn",
                style={
                    "width": "100%",
                    "fontFamily": "'Space Mono',monospace",
                    "fontWeight": "700",
                    "letterSpacing": "1px",
                    "background": "linear-gradient(135deg,#3C8361,#1B6758)",
                    "border": "none",
                    "color": "#EEF2E6",
                    "padding": "12px",
                    "borderRadius": "8px",
                },
            ),
            html.Hr(style={"borderColor": "#3C8361", "margin": "22px 0"}),
            html.H6("STATS", style=label_style),
            html.Div(
                id="stats-box",
                style={
                    "fontFamily": "'Space Mono',monospace",
                    "fontSize": "11px",
                    "color": "#3C8361",
                    "lineHeight": "1.9",
                },
            ),
        ],
    )


def create_header() -> html.Div:
    return html.Div(
        style={
            "background": "linear-gradient(135deg,#1B6758,#3C8361)",
            "borderBottom": "1px solid #3C8361",
            "padding": "16px 30px",
            "display": "flex",
            "alignItems": "center",
            "gap": "18px",
        },
        children=[
            html.Span("🌡", style={"fontSize": "30px"}),
            html.Div(
                [
                    html.H1(
                        "AgERA5 Temperature Heatmap",
                        style={
                            "fontFamily": "'Syne',sans-serif",
                            "fontWeight": "800",
                            "fontSize": "22px",
                            "color": "#EEF2E6",
                            "margin": "0",
                        },
                    ),
                    html.P(
                        "Global daily 2 m air temperature · ERA5-based · georaster-layer-for-leaflet",
                        style={
                            "fontFamily": "'Space Mono',monospace",
                            "fontSize": "10px",
                            "color": "#D6CDA4",
                            "margin": "3px 0 0",
                        },
                    ),
                ]
            ),
        ],
    )
