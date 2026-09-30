"""Shared pipeline state that the agents read from and write to."""

from pydantic import BaseModel

from backend.app.schemas import Length, Tone

# State keys written by each agent (via ClaudeAgent.output_key).
RESEARCH_KEY = "research"
DRAFT_KEY = "draft"
CRITIQUE_KEY = "critique"
FINAL_POST_KEY = "final_post"


class PostGenerationState(BaseModel):
    """The shared state for one run of the pipeline.

    The four inputs come from the post request. The agents fill in the rest:
    research and critique hold the structured outputs as dicts, and final_post is
    the latest revision. iteration counts revision passes.
    """

    topic: str
    audience: str
    tone: Tone
    length: Length

    research: dict | None = None
    draft: str | None = None
    critique: dict | None = None
    final_post: str | None = None

    iteration: int = 0
    status: str = "generating"
