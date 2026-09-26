"""Auth routes: register, login, logout, and current user."""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app import config
from backend.app.db import get_db
from backend.app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserResponse
from backend.app.security import hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)

Db = Annotated[sqlite3.Connection, Depends(get_db)]

USER_COLUMNS = "id, email, name, created_at"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_user(row: sqlite3.Row) -> UserResponse:
    return UserResponse(
        id=row["id"], email=row["email"], name=row["name"], created_at=row["created_at"]
    )


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_session_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None:
        raise _unauthorized()
    return credentials.credentials


def get_current_user(db: Db, token: Annotated[str, Depends(get_session_token)]) -> UserResponse:
    row = db.execute(
        """
        SELECT u.id, u.email, u.name, u.created_at, s.expires_at
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        (hash_token(token),),
    ).fetchone()
    if row is None:
        raise _unauthorized("Invalid or expired session")
    if datetime.fromisoformat(row["expires_at"]) <= _now():
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
        db.commit()
        raise _unauthorized("Invalid or expired session")
    return _to_user(row)


CurrentUser = Annotated[UserResponse, Depends(get_current_user)]


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Db) -> UserResponse:
    try:
        cur = db.execute(
            "INSERT INTO users (email, name, created_at, password_hash) VALUES (?, ?, ?, ?)",
            (body.email.lower(), body.name.strip(), _now().isoformat(), hash_password(body.password)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    row = db.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _to_user(row)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Db) -> LoginResponse:
    row = db.execute(
        f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE email = ?", (body.email.lower(),)
    ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise _unauthorized("Incorrect email or password")

    token = new_session_token()
    now = _now()
    expires_at = now + timedelta(hours=config.SESSION_TTL_HOURS)
    # Housekeeping: drop this user's expired sessions.
    db.execute(
        "DELETE FROM sessions WHERE user_id = ? AND expires_at <= ?", (row["id"], now.isoformat())
    )
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), row["id"], now.isoformat(), expires_at.isoformat()),
    )
    return LoginResponse(access_token=token, expires_at=expires_at, user=_to_user(row))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(db: Db, user: CurrentUser, token: Annotated[str, Depends(get_session_token)]) -> Response:
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return user
