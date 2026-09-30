"""Application settings, read from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ANTHROPIC_API_KEY (read by the Claude Agent SDK) and the settings below can live in .env.
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_PATH = Path(os.getenv("POSTPILOT_DB_PATH", PROJECT_ROOT / "data" / "postpilot.db"))

# How long a login session stays valid.
SESSION_TTL_HOURS = int(os.getenv("POSTPILOT_SESSION_TTL_HOURS", "24"))

# ---------- Agent pipeline ----------

# Claude model used by every agent in the pipeline.
CLAUDE_MODEL = os.getenv("POSTPILOT_MODEL", "claude-opus-5")

# Upper bound on critique -> revision passes. At least one revision always runs.
MAX_REVISIONS = max(1, int(os.getenv("POSTPILOT_MAX_REVISIONS", "3")))

# A post is approved once every critique score (1-10) reaches this value.
APPROVAL_SCORE = int(os.getenv("POSTPILOT_APPROVAL_SCORE", "8"))

# Each agent retries transient Claude errors (429, 5xx, overload) and malformed structured
# output, with exponential backoff starting at LLM_RETRY_INITIAL_DELAY seconds.
LLM_MAX_ATTEMPTS = max(1, int(os.getenv("POSTPILOT_LLM_MAX_ATTEMPTS", "3")))
LLM_RETRY_INITIAL_DELAY = float(os.getenv("POSTPILOT_LLM_RETRY_INITIAL_DELAY", "2"))

# Wall-clock limit for one full pipeline run.
GENERATION_TIMEOUT_SECONDS = float(os.getenv("POSTPILOT_GENERATION_TIMEOUT_SECONDS", "300"))
