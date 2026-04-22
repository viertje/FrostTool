import dash
import dash_bootstrap_components as dbc

from .pages.heatmap import create_layout
from . import callbacks as map_callbacks

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="AgERA5 Temperature Heatmap",
)

app.layout = create_layout()


if __name__ == "__main__":
    app.run(debug=True, port=8050)

