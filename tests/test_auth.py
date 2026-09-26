from backend.app import config


def register(client, email="ada@example.com", name="Ada", password="s3cret-pass"):
    return client.post(
        "/api/auth/register", json={"email": email, "name": name, "password": password}
    )


def login(client, email="ada@example.com", password="s3cret-pass"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_register_returns_user_without_password(client):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {"id", "email", "name", "created_at"}
    assert body["email"] == "ada@example.com"


def test_register_duplicate_email_is_rejected_case_insensitively(client):
    register(client)
    resp = register(client, email="ADA@example.com")
    assert resp.status_code == 409


def test_register_validates_input(client):
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, password="short").status_code == 422


def test_login_and_me(client):
    register(client)
    resp = login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ada@example.com"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == body["user"]


def test_login_wrong_password(client):
    register(client)
    assert login(client, password="wrong-pass").status_code == 401
    assert login(client, email="nobody@example.com").status_code == 401


def test_logout_revokes_token(client):
    register(client)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/logout", headers=headers).status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_expired_session_is_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "SESSION_TTL_HOURS", 0)
    register(client)
    token = login(client).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
