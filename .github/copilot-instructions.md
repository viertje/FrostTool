# Copilot Instructions

## Project Overview

Full-stack geospatial data application for visualising global climate data from NetCDF (`.nc`) files. The backend is a **FastAPI** REST API; the frontend is a **Dash** app rendering interactive **Leaflet** heatmaps via `georaster-layer-for-leaflet`. The architecture must remain fast and expandable — future features include multi-parameter support, regional crop-damage aggregation, and timeline graphs.

---

## Tech Stack

| Layer     | Technology                                              |
|-----------|---------------------------------------------------------|
| Backend   | Python 3.14.4, FastAPI, Uvicorn                          |
| Data I/O  | xarray, netCDF4, numpy, rasterio                        |
| Frontend  | Dash (Plotly), dash-leaflet, georaster-layer-for-leaflet|
| Caching   | functools.lru_cache / diskcache for heavy NetCDF reads  |
| Testing   | pytest, httpx (async FastAPI tests)                     |
| Linting   | ruff, black, mypy (strict)                              |

---

## Project Structure

```
project-root/
├── backend/
│   ├── main.py                  # FastAPI app factory
│   ├── api/
│   │   ├── routes/
│   │   │   ├── climate.py       # Climate data endpoints
│   │   │   └── regions.py       # Region aggregation endpoints
│   │   └── dependencies.py      # Shared FastAPI dependencies
│   ├── services/
│   │   ├── netcdf_service.py    # All NetCDF I/O and processing
│   │   ├── aggregation_service.py  # Region/crop aggregation logic
│   │   └── cache_service.py     # Caching wrappers
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── domain.py            # Internal domain dataclasses
│   └── core/
│       ├── config.py            # Settings via pydantic-settings
│       └── exceptions.py        # Custom exception types
├── frontend/
│   ├── app.py                   # Dash app factory
│   ├── pages/
│   │   └── heatmap.py           # Heatmap page layout
│   ├── components/
│   │   ├── map_component.py     # Leaflet map wrapper
│   │   ├── timeline_graph.py    # Timeline/graph component
│   │   └── controls.py          # Parameter/filter controls
│   └── callbacks/
│       ├── map_callbacks.py     # Map interactivity callbacks
│       └── graph_callbacks.py   # Graph update callbacks
├── data/
│   └── nc/                      # NetCDF source files (gitignored)
├── tests/
│   ├── backend/
│   └── frontend/
└── .github/
    └── copilot-instructions.md
```

---

## Coding Conventions

### Core Principles

| Principle | Rule |
|-----------|------|
| **DRY** | Never duplicate logic. Extract repeated patterns into shared utilities or base classes. |
| **SRP** | Every module, class, and function has exactly one reason to change. Services handle logic; routes handle HTTP; components handle rendering only. |
| **YAGNI** | Do not add abstractions, parameters, or features until they are actually needed. No speculative generality. |
| **KISS** | Prefer simple, readable solutions. Complexity must be justified by a concrete requirement. |
| **OCP** | Design for extension without modification. New climate parameters must be addable without touching existing route/service code. |

### Python Style

- Follow **PEP 8**; enforced by `ruff` and `black` (line length: 88).
- Use **type hints everywhere** — all function signatures, class attributes, and return types.
- Use `mypy --strict`; fix all errors before committing.
- Prefer **`dataclasses`** or **Pydantic models** over plain dicts for structured data.
- Avoid mutable default arguments. Never use `def f(x=[])`.
- All public functions and classes must have **docstrings** (Google style).

```python
# Good
def get_temperature_slice(
    path: Path,
    time_index: int,
    variable: str = "t2m",
) -> np.ndarray:
    """Extract a 2-D temperature slice from a NetCDF file.

    Args:
        path: Absolute path to the .nc file.
        time_index: Zero-based index along the time dimension.
        variable: NetCDF variable name to extract.

    Returns:
        2-D float32 numpy array of shape (lat, lon).

    Raises:
        FileNotFoundError: If the .nc file does not exist.
        KeyError: If the variable is absent in the file.
    """
    ...

# Bad — no types, no docstring, magic variable name
def get_data(p, t):
    ...
```

### FastAPI Conventions

- Use **APIRouter** per domain; never add routes directly to the `FastAPI()` instance.
- All endpoints must declare **response models** via `response_model=`.
- Use **dependency injection** (`Depends`) for shared resources (DB sessions, config, caches).
- Raise `HTTPException` only in route handlers. Services raise domain exceptions (see `core/exceptions.py`); routes convert them.
- Async endpoints (`async def`) for I/O-bound routes; sync (`def`) only for CPU-heavy operations offloaded to a thread pool.

```python
# Good
router = APIRouter(prefix="/climate", tags=["climate"])

@router.get("/temperature", response_model=TemperatureResponse)
async def get_temperature(
    time_index: int = Query(..., ge=0),
    service: NetCDFService = Depends(get_netcdf_service),
) -> TemperatureResponse:
    ...
```

### Dash / Frontend Conventions

- Each **page** owns its layout function; each **component** is a pure function returning a Dash element.
- Callbacks live in `callbacks/` and are registered via a `register_callbacks(app)` function — never inline in layout files.
- Callbacks must be **lean**: fetch data from the API, transform minimally, return to component. Heavy logic belongs in a service or utility module.
- Use `dcc.Store` for shared client-side state between callbacks.
- Avoid `global` variables in Dash; use `diskcache` or server-side sessions for cross-request state.

### NetCDF / Data Processing

- Always open NetCDF files with `xarray.open_dataset(..., engine="netcdf4", chunks={})` (lazy loading via Dask).
- Close datasets explicitly or use context managers; never leave file handles open.
- Clip, downsample, or slice data **server-side** before sending to the frontend — never ship a raw full-resolution grid to the browser.
- Tile or chunk large grids when streaming to georaster-layer-for-leaflet.
- Cache expensive computed slices (reprojection, aggregation) using `diskcache` with a TTL.

### Naming Conventions

| Context            | Convention           | Example                          |
|--------------------|----------------------|----------------------------------|
| Files/modules      | `snake_case`         | `netcdf_service.py`              |
| Classes            | `PascalCase`         | `NetCDFService`                  |
| Functions/methods  | `snake_case`         | `get_temperature_slice()`        |
| Constants          | `UPPER_SNAKE_CASE`   | `DEFAULT_VARIABLE = "t2m"`       |
| Pydantic schemas   | `PascalCase` + noun  | `TemperatureRequest`             |
| Dash component IDs | `kebab-case`         | `"heatmap-layer"`, `"time-slider"` |
| API routes         | Plural nouns         | `/climate/temperatures`          |

---

## Expandability Rules

These rules exist so that new parameters (wind, precipitation, soil moisture) and new features (crop damage, timeline graphs) can be added without architectural rewrites.

1. **Parameter-agnostic services**: `NetCDFService` must accept a `variable: str` argument. Never hard-code `"t2m"` (or any variable name) outside of configuration or constants.
2. **Config-driven file paths**: All `.nc` file paths and variable-to-file mappings live in `core/config.py` (loaded from environment variables or a `.env` file). No hardcoded paths elsewhere.
3. **Pluggable aggregation**: `AggregationService` must accept a region geometry (GeoJSON) and a variable name. New aggregation methods (mean, max, weighted crop-damage index) are added as strategy functions, not as branching conditionals.
4. **Component isolation**: Each Dash component accepts only the data it needs as props — no component reaches into another component's state.
5. **Versioned API**: All routes are prefixed `/api/v1/`. Breaking changes increment the version; old versions are deprecated, not deleted immediately.

---

## Performance Guidelines

- **Lazy-load** NetCDF files; never load an entire file into memory upfront.
- **Downsample** grids to match the current map zoom level (coarser grid at low zoom, finer at high zoom).
- **Cache** processed tiles and aggregation results; invalidate cache only when source files change (use file mtime as cache key).
- Use `numpy` vectorised operations — avoid Python-level loops over grid cells.
- Prefer `float32` over `float64` for grid arrays sent to the frontend.
- Profile with `py-spy` or `cProfile` before optimising; do not pre-optimise without evidence of a bottleneck.

---

## Error Handling

- Define all custom exceptions in `core/exceptions.py` (e.g., `DatasetNotFoundError`, `VariableNotFoundError`, `InvalidTimeIndexError`).
- Services raise domain exceptions; routes catch them and return the appropriate `HTTPException`.
- Never swallow exceptions silently with bare `except: pass`.
- All exceptions must be **logged** with context (file path, variable, index) before re-raising or converting.

```python
# Good
try:
    ds = xr.open_dataset(path)
except FileNotFoundError as exc:
    logger.error("NetCDF file not found", extra={"path": str(path)})
    raise DatasetNotFoundError(path) from exc
```

---

## Testing

- Minimum **80% coverage** on all service modules.
- Use `pytest` fixtures for shared test data (small synthetic `.nc` files, not production data).
- Test FastAPI routes with `httpx.AsyncClient` + `pytest-anyio`.
- Test Dash callbacks with `dash.testing` or by unit-testing callback functions directly (extract logic out of the callback decorator).
- All tests must pass before merging to `main`.

---

## Git & Commit Conventions

- Branch names: `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`.
- Commit messages follow **Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- No commits directly to `main`; all changes via pull requests.
- Each PR should change one thing — do not mix feature work with refactoring.

---

## What NOT to Do

- ❌ Do not mix data-processing logic into route handlers or Dash callbacks.
- ❌ Do not load entire NetCDF datasets eagerly at startup.
- ❌ Do not hardcode file paths, variable names, or CRS values anywhere except `config.py` / constants.
- ❌ Do not add configuration options or abstraction layers "just in case" (YAGNI).
- ❌ Do not use `Any` in type hints without a comment explaining why it is unavoidable.
- ❌ Do not create God-classes or God-modules; if a file exceeds ~300 lines, split it.
- ❌ Do not return raw numpy arrays from API endpoints — always serialise to a defined Pydantic schema or a tiled binary format.
