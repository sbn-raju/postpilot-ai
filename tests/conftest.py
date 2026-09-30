import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.llm import ClaudeLlm
from tests.fakes import FakeLlm


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Make sure no test can reach Claude, even if .env holds a real key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "CLAUDE_MODEL", "no-real-llm-in-tests")

    async def refuse(self, request):
        raise AssertionError(f"{request.agent} tried to call the real Claude API")

    monkeypatch.setattr(ClaudeLlm, "run", refuse)
    # Keep retries (on by default) but skip the backoff sleeps.
    monkeypatch.setattr(config, "LLM_RETRY_INITIAL_DELAY", 0.0)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test.db")
    from backend.app.main import app

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def fake_llm(client):
    """A FakeLlm wired into the API. Adjust .script or .delay before calling the endpoint."""
    from backend.app.api.generations import get_llm
    from backend.app.main import app

    llm = FakeLlm()
    app.dependency_overrides[get_llm] = lambda: llm
    return llm
