"""Frontend configuration and constants."""
import os

# API Configuration
API_BASE_URL = os.environ.get("REACT_APP_API_URL", "http://localhost:8000/api/v1")
API_TIMEOUT = int(os.environ.get("API_TIMEOUT", "60"))

# UI Configuration
MAP_CENTER = [20, 0]
MAP_INITIAL_ZOOM = 2
MAP_MAX_ZOOM = 19

# Feature flags
DEBUG_LOGGING = os.environ.get("DEBUG_LOGGING", "false").lower() == "true"
