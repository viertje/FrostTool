import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Handle imports for both direct execution and module invocation
try:
    from .api.routes.climate import router as climate_router
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from backend.api.routes.climate import router as climate_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FrostTool Backend",
        description="AgERA5 NetCDF Temperature Heatmap API",
        version="1.0.0",
    )
    
    # Add CORS middleware BEFORE routes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8050", "http://127.0.0.1:8050", "*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    app.include_router(climate_router)
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

