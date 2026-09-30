"""Generation routes: run the agent pipeline for a post, and list its past generations."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app import orchestrator
from backend.app.api.auth import CurrentUser, Db
from backend.app.api.posts import _get_owned_post
from backend.app.llm import ClaudeLlm, Llm
from backend.app.schemas import GenerationListResponse, GenerationResponse

router = APIRouter(prefix="/api/posts", tags=["generations"])

GENERATION_COLUMNS = "id, post_id, research_output, draft, critique, final_post, created_at"


def get_llm() -> Llm:
    """The LLM the agents use: Claude. Tests override this dependency with a fake."""
    return ClaudeLlm()


LlmDep = Annotated[Llm, Depends(get_llm)]


def _to_generation(row: sqlite3.Row) -> GenerationResponse:
    data = dict(row)
    data["research_output"] = json.loads(data["research_output"])
    data["critique"] = json.loads(data["critique"])
    return GenerationResponse(**data)


def _set_status(db: sqlite3.Connection, post_id: int, new_status: str) -> None:
    db.execute("UPDATE posts SET status = ? WHERE id = ?", (new_status, post_id))
    db.commit()


@router.post(
    "/{post_id}/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate(post_id: int, db: Db, user: CurrentUser, llm: LlmDep) -> GenerationResponse:
    post = _get_owned_post(db, post_id, user.id)

    # Claim the post atomically so two concurrent requests can't both start a run.
    claimed = db.execute(
        "UPDATE posts SET status = 'generating' WHERE id = ? AND status != 'generating'",
        (post_id,),
    ).rowcount
    if not claimed:
        raise HTTPException(status.HTTP_409_CONFLICT, "This post is already being generated")
    # Commit now so other requests see "generating" while the agents run.
    db.commit()

    try:
        state = await orchestrator.run_generation(
            topic=post["topic"],
            audience=post["audience"],
            tone=post["tone"],
            length=post["length"],
            llm=llm,
        )
    except orchestrator.GenerationError as exc:
        _set_status(db, post_id, "failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    except BaseException:
        # e.g. the request was cancelled: don't leave the post stuck in "generating".
        _set_status(db, post_id, "failed")
        raise

    cur = db.execute(
        """
        INSERT INTO generations (post_id, research_output, draft, critique, final_post, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            json.dumps(state.research),
            state.draft,
            json.dumps(state.critique),
            state.final_post,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.execute("UPDATE posts SET status = 'completed' WHERE id = ?", (post_id,))
    row = db.execute(
        f"SELECT {GENERATION_COLUMNS} FROM generations WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _to_generation(row)


@router.get("/{post_id}/generations", response_model=GenerationListResponse)
def list_generations(
    post_id: int,
    db: Db,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenerationListResponse:
    _get_owned_post(db, post_id, user.id)
    total = db.execute(
        "SELECT COUNT(*) FROM generations WHERE post_id = ?", (post_id,)
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT {GENERATION_COLUMNS} FROM generations WHERE post_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (post_id, limit, offset),
    ).fetchall()
    return GenerationListResponse(items=[_to_generation(r) for r in rows], total=total)
