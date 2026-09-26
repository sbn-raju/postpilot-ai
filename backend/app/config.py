"""Application settings, read from environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_PATH = Path(os.getenv("POSTPILOT_DB_PATH", PROJECT_ROOT / "data" / "postpilot.db"))

# How long a login session stays valid.
SESSION_TTL_HOURS = int(os.getenv("POSTPILOT_SESSION_TTL_HOURS", "24"))
