"""FastAPI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.auth import router as auth_router
from backend.app.api.generations import router as generations_router
from backend.app.api.posts import router as posts_router
from backend.app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="PostPilot AI", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(posts_router)
app.include_router(generations_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
