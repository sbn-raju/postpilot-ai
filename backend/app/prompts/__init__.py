"""Prompt templates, one module per agent.

Each template is a function of the pipeline state that builds the agent's system prompt.
Using functions rather than "{key}" templates keeps generated text containing braces from
being treated as state placeholders.
"""

import json
from typing import Any

# Keep in sync with the length labels in streamlit_app.py.
LENGTH_WORDS = {"short": 100, "medium": 200, "long": 350}


def brief(state: Any) -> str:
    """The user's request, shared by every agent's prompt."""
    return (
        f"Topic: {state['topic']}\n"
        f"Audience: {state['audience']}\n"
        f"Tone: {state['tone']}\n"
        f"Length: about {LENGTH_WORDS[state['length']]} words"
    )


def as_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def current_version(state: Any) -> str:
    """The post under review: the latest revision, or the first draft before any revision."""
    return state.get("final_post") or state["draft"]
