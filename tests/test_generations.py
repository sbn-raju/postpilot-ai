import json
import sqlite3

import pytest

from backend.app import config
from backend.app.api.generations import get_llm
from backend.app.db import init_db
from backend.app.llm import ClaudeLlm, TransientLlmError
from tests.fakes import DRAFT, FAILING, PASSING, RESEARCH, REVISION
from tests.test_posts import POST, auth_headers


@pytest.fixture
def headers(client):
    return auth_headers(client)


@pytest.fixture
def post_id(client, headers):
    return client.post("/api/posts", json=POST, headers=headers).json()["id"]


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def post_status(client, post_id, headers) -> str:
    return client.get(f"/api/posts/{post_id}", headers=headers).json()["status"]


def generate(client, post_id, headers):
    return client.post(f"/api/posts/{post_id}/generate", headers=headers)


# ---------- Table ----------

def test_generations_table_matches_schema(client):
    with db() as conn:
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(generations)")}
        fks = conn.execute("PRAGMA foreign_key_list(generations)").fetchall()

    assert list(columns) == [
        "id", "post_id", "research_output", "draft", "critique", "final_post", "created_at",
    ]
    assert columns["id"]["pk"] == 1
    assert all(columns[c]["notnull"] for c in columns if c != "id")
    assert [(fk["table"], fk["from"], fk["to"], fk["on_delete"]) for fk in fks] == [
        ("posts", "post_id", "id", "CASCADE")
    ]


def test_init_db_is_idempotent(client):
    init_db()
    init_db()


def test_startup_marks_interrupted_generations_failed(client, headers, post_id):
    with db() as conn:
        conn.execute("UPDATE posts SET status = 'generating' WHERE id = ?", (post_id,))
    init_db()
    assert post_status(client, post_id, headers) == "failed"


# ---------- Generate ----------

def test_generate_runs_pipeline_and_returns_generation(client, headers, post_id, fake_llm):
    resp = generate(client, post_id, headers)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {
        "id", "post_id", "research_output", "draft", "critique", "final_post", "created_at",
    }
    assert body["post_id"] == post_id
    assert body["research_output"] == RESEARCH
    assert body["draft"] == DRAFT
    assert body["critique"] == PASSING
    assert body["final_post"] == REVISION
    assert post_status(client, post_id, headers) == "completed"


def test_generate_persists_row_with_json_columns(client, headers, post_id, fake_llm):
    gen_id = generate(client, post_id, headers).json()["id"]
    with db() as conn:
        row = conn.execute("SELECT * FROM generations WHERE id = ?", (gen_id,)).fetchone()
    assert row["post_id"] == post_id
    assert json.loads(row["research_output"]) == RESEARCH
    assert json.loads(row["critique"]) == PASSING
    assert (row["draft"], row["final_post"]) == (DRAFT, REVISION)


def test_generate_passes_post_fields_to_agents(client, headers, fake_llm):
    post = {**POST, "tone": "storytelling", "length": "long"}
    post_id = client.post("/api/posts", json=post, headers=headers).json()["id"]
    generate(client, post_id, headers)
    (prompt,) = fake_llm.prompts("research_agent")
    for value in (post["topic"], post["audience"], "storytelling", "about 350 words"):
        assert value in prompt


def test_generate_stores_last_critique_after_revision_loop(client, headers, post_id, fake_llm):
    fake_llm.script["critique_agent"] = [FAILING, FAILING, PASSING]
    fake_llm.script["revision_agent"] = ["revision one", "revision two"]
    body = generate(client, post_id, headers).json()
    assert body["final_post"] == "revision two"
    assert body["critique"] == PASSING


def test_regenerate_keeps_history(client, headers, post_id, fake_llm):
    first = generate(client, post_id, headers).json()
    fake_llm.script["revision_agent"] = ["a fresh take"]
    second = generate(client, post_id, headers)
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]
    assert second.json()["final_post"] == "a fresh take"


def test_generate_failure_marks_post_failed(client, headers, post_id, fake_llm):
    fake_llm.script["draft_agent"] = [RuntimeError("quota exceeded")]
    resp = generate(client, post_id, headers)
    assert resp.status_code == 502
    assert "quota exceeded" in resp.json()["detail"]
    assert post_status(client, post_id, headers) == "failed"
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0] == 0


def test_generate_invalid_model_output_marks_post_failed(client, headers, post_id, fake_llm):
    fake_llm.script["critique_agent"] = ["not json at all"]
    assert generate(client, post_id, headers).status_code == 502
    assert post_status(client, post_id, headers) == "failed"


def test_generate_timeout_marks_post_failed(client, headers, post_id, fake_llm, monkeypatch):
    monkeypatch.setattr(config, "GENERATION_TIMEOUT_SECONDS", 0.1)
    fake_llm.delay = 0.5
    resp = generate(client, post_id, headers)
    assert resp.status_code == 502
    assert "timed out" in resp.json()["detail"]
    assert post_status(client, post_id, headers) == "failed"


def test_generate_recovers_from_transient_claude_error(client, headers, post_id, fake_llm):
    fake_llm.script["research_agent"] = [TransientLlmError("529 overloaded"), RESEARCH]
    assert generate(client, post_id, headers).status_code == 201
    assert post_status(client, post_id, headers) == "completed"


def test_failed_post_can_be_retried(client, headers, post_id, fake_llm):
    fake_llm.script["research_agent"] = [RuntimeError("temporary outage"), RESEARCH]
    assert generate(client, post_id, headers).status_code == 502
    assert generate(client, post_id, headers).status_code == 201
    assert post_status(client, post_id, headers) == "completed"


def test_failed_regeneration_keeps_earlier_generations(client, headers, post_id, fake_llm):
    generate(client, post_id, headers)
    fake_llm.script["research_agent"] = [RuntimeError("outage")]
    assert generate(client, post_id, headers).status_code == 502
    listing = client.get(f"/api/posts/{post_id}/generations", headers=headers).json()
    assert listing["total"] == 1


def test_generate_rejects_post_already_generating(client, headers, post_id, fake_llm):
    with db() as conn:
        conn.execute("UPDATE posts SET status = 'generating' WHERE id = ?", (post_id,))
    resp = generate(client, post_id, headers)
    assert resp.status_code == 409
    assert fake_llm.calls == []
    assert post_status(client, post_id, headers) == "generating"


def test_completed_post_can_no_longer_be_edited(client, headers, post_id, fake_llm):
    generate(client, post_id, headers)
    resp = client.patch(f"/api/posts/{post_id}", json={"tone": "casual"}, headers=headers)
    assert resp.status_code == 409


def test_generate_requires_auth(client, post_id, fake_llm):
    assert client.post(f"/api/posts/{post_id}/generate").status_code == 401
    assert fake_llm.calls == []


def test_generate_unknown_post_is_404(client, headers, fake_llm):
    assert generate(client, 9999, headers).status_code == 404


def test_cannot_generate_other_users_post(client, headers, post_id, fake_llm):
    other = auth_headers(client, email="grace@example.com")
    assert generate(client, post_id, other).status_code == 404
    assert fake_llm.calls == []
    assert post_status(client, post_id, headers) == "pending"


def test_default_llm_is_claude():
    assert isinstance(get_llm(), ClaudeLlm)


# ---------- List ----------

def test_list_generations_newest_first_with_pagination(client, headers, post_id, fake_llm):
    for text in ("take one", "take two", "take three"):
        fake_llm.script["revision_agent"] = [text]
        generate(client, post_id, headers)

    body = client.get(f"/api/posts/{post_id}/generations", headers=headers).json()
    assert body["total"] == 3
    assert [g["final_post"] for g in body["items"]] == ["take three", "take two", "take one"]

    page = client.get(
        f"/api/posts/{post_id}/generations?limit=1&offset=1", headers=headers
    ).json()
    assert page["total"] == 3
    assert [g["final_post"] for g in page["items"]] == ["take two"]


def test_list_generations_empty(client, headers, post_id):
    body = client.get(f"/api/posts/{post_id}/generations", headers=headers).json()
    assert body == {"items": [], "total": 0}


def test_list_generations_only_for_that_post(client, headers, post_id, fake_llm):
    other_post = client.post("/api/posts", json=POST, headers=headers).json()["id"]
    generate(client, post_id, headers)
    assert client.get(f"/api/posts/{other_post}/generations", headers=headers).json()["total"] == 0


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_list_generations_validates_pagination(client, headers, post_id, query):
    resp = client.get(f"/api/posts/{post_id}/generations?{query}", headers=headers)
    assert resp.status_code == 422


def test_list_generations_requires_auth(client, post_id):
    assert client.get(f"/api/posts/{post_id}/generations").status_code == 401


def test_cannot_list_other_users_generations(client, headers, post_id, fake_llm):
    generate(client, post_id, headers)
    other = auth_headers(client, email="grace@example.com")
    assert client.get(f"/api/posts/{post_id}/generations", headers=other).status_code == 404


# ---------- Cascade ----------

def test_deleting_post_deletes_its_generations(client, headers, post_id, fake_llm):
    generate(client, post_id, headers)
    generate(client, post_id, headers)
    assert client.delete(f"/api/posts/{post_id}", headers=headers).status_code == 204
    with db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM generations WHERE post_id = ?", (post_id,)
        ).fetchone()[0]
    assert count == 0
