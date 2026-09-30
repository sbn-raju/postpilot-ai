"""SQLite connection handling and table setup."""

import sqlite3
from collections.abc import Iterator

from backend.app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    password_hash TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic      TEXT    NOT NULL,
    audience   TEXT    NOT NULL,
    tone       TEXT    NOT NULL,
    length     TEXT    NOT NULL,
    status     TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_user_id_created_at ON posts(user_id, created_at);

-- One row per successful agent pipeline run. research_output and critique hold JSON.
CREATE TABLE IF NOT EXISTS generations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    research_output TEXT    NOT NULL,
    draft           TEXT    NOT NULL,
    critique        TEXT    NOT NULL,
    final_post      TEXT    NOT NULL,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_generations_post_id_created_at ON generations(post_id, created_at);
"""


def connect() -> sqlite3.Connection:
    # Each connection serves one request, but FastAPI may create it in a worker thread
    # and use it from the event loop (async routes), so the same-thread check is off.
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Generation runs in-process, so any post still "generating" at startup was
        # interrupted by a restart and would otherwise stay locked forever.
        conn.execute("UPDATE posts SET status = 'failed' WHERE status = 'generating'")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, committed on success."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
