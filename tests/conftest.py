import pytest
from pathlib import Path


@pytest.fixture
def data_root() -> Path:
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def backend_api_url() -> str:
    return "http://localhost:8000/api/v1"
