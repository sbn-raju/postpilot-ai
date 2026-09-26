import pytest
from fastapi.testclient import TestClient

from backend.app import config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test.db")
    from backend.app.main import app

    with TestClient(app) as c:
        yield c
