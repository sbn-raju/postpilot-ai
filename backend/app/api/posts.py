"""Post routes: create, list, read, update, and delete the current user's post requests."""

import sqlite3
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.app.api.auth import CurrentUser, Db
from backend.app.schemas import PostCreate, PostListResponse, PostResponse, PostStatus, PostUpdate

router = APIRouter(prefix="/api/posts", tags=["posts"])

POST_COLUMNS = "id, user_id, topic, audience, tone, length, status, created_at"


def _to_post(row: sqlite3.Row) -> PostResponse:
    return PostResponse(**dict(row))


def _get_owned_post(db: sqlite3.Connection, post_id: int, user_id: int) -> sqlite3.Row:
    """Fetch a post, returning 404 (not 403) for other users' posts so IDs don't leak."""
    row = db.execute(
        f"SELECT {POST_COLUMNS} FROM posts WHERE id = ? AND user_id = ?", (post_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return row


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(body: PostCreate, db: Db, user: CurrentUser) -> PostResponse:
    cur = db.execute(
        """
        INSERT INTO posts (user_id, topic, audience, tone, length, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (user.id, body.topic, body.audience, body.tone, body.length,
         datetime.now(timezone.utc).isoformat()),
    )
    return _to_post(_get_owned_post(db, cur.lastrowid, user.id))


@router.get("", response_model=PostListResponse)
def list_posts(
    db: Db,
    user: CurrentUser,
    status_filter: Annotated[PostStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PostListResponse:
    where, params = "user_id = ?", [user.id]
    if status_filter:
        where += " AND status = ?"
        params.append(status_filter)
    total = db.execute(f"SELECT COUNT(*) FROM posts WHERE {where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT {POST_COLUMNS} FROM posts WHERE {where} "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return PostListResponse(items=[_to_post(r) for r in rows], total=total)


@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Db, user: CurrentUser) -> PostResponse:
    return _to_post(_get_owned_post(db, post_id, user.id))


@router.patch("/{post_id}", response_model=PostResponse)
def update_post(post_id: int, body: PostUpdate, db: Db, user: CurrentUser) -> PostResponse:
    row = _get_owned_post(db, post_id, user.id)
    if row["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only pending posts can be edited")
    # Column names come from the PostUpdate model, never from user input.
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if changes:
        assignments = ", ".join(f"{col} = ?" for col in changes)
        db.execute(
            f"UPDATE posts SET {assignments} WHERE id = ?", (*changes.values(), post_id)
        )
    return _to_post(_get_owned_post(db, post_id, user.id))


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Db, user: CurrentUser) -> Response:
    _get_owned_post(db, post_id, user.id)
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
