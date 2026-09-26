import pytest

from tests.test_auth import login, register

POST = {"topic": "Why RAG beats fine-tuning", "audience": "software engineers", "tone": "technical"}


def auth_headers(client, email="ada@example.com"):
    register(client, email=email)
    token = login(client, email=email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def headers(client):
    return auth_headers(client)


def test_create_post_saves_as_pending(client, headers):
    resp = client.post("/api/posts", json=POST, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {
        "id", "user_id", "topic", "audience", "tone", "length", "status", "created_at"
    }
    assert body["status"] == "pending"
    assert body["length"] == "medium"  # default
    assert client.get(f"/api/posts/{body['id']}", headers=headers).json() == body


def test_create_post_validates_input(client, headers):
    assert client.post("/api/posts", json={**POST, "tone": "angry"}, headers=headers).status_code == 422
    assert client.post("/api/posts", json={**POST, "length": "huge"}, headers=headers).status_code == 422
    assert client.post("/api/posts", json={**POST, "topic": "   "}, headers=headers).status_code == 422
    # Clients can't choose the status.
    resp = client.post("/api/posts", json={**POST, "status": "completed"}, headers=headers)
    assert resp.json()["status"] == "pending"


def test_posts_require_auth(client):
    assert client.post("/api/posts", json=POST).status_code == 401
    assert client.get("/api/posts").status_code == 401


def test_list_posts_newest_first_with_pagination(client, headers):
    for i in range(3):
        client.post("/api/posts", json={**POST, "topic": f"Topic number {i}"}, headers=headers)

    body = client.get("/api/posts", headers=headers).json()
    assert body["total"] == 3
    assert [p["topic"] for p in body["items"]] == [f"Topic number {i}" for i in (2, 1, 0)]

    page = client.get("/api/posts?limit=1&offset=1", headers=headers).json()
    assert page["total"] == 3
    assert [p["topic"] for p in page["items"]] == ["Topic number 1"]

    assert client.get("/api/posts?status=completed", headers=headers).json()["total"] == 0


def test_users_only_see_their_own_posts(client, headers):
    post_id = client.post("/api/posts", json=POST, headers=headers).json()["id"]
    other = auth_headers(client, email="grace@example.com")

    assert client.get("/api/posts", headers=other).json() == {"items": [], "total": 0}
    assert client.get(f"/api/posts/{post_id}", headers=other).status_code == 404
    assert client.patch(f"/api/posts/{post_id}", json={"tone": "casual"}, headers=other).status_code == 404
    assert client.delete(f"/api/posts/{post_id}", headers=other).status_code == 404
    assert client.get(f"/api/posts/{post_id}", headers=headers).status_code == 200


def test_update_post(client, headers):
    post_id = client.post("/api/posts", json=POST, headers=headers).json()["id"]
    resp = client.patch(f"/api/posts/{post_id}", json={"tone": "casual", "length": "short"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["tone"], body["length"], body["topic"]) == ("casual", "short", POST["topic"])


def test_delete_post(client, headers):
    post_id = client.post("/api/posts", json=POST, headers=headers).json()["id"]
    assert client.delete(f"/api/posts/{post_id}", headers=headers).status_code == 204
    assert client.get(f"/api/posts/{post_id}", headers=headers).status_code == 404
