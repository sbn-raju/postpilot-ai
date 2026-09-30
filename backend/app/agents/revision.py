"""✨ Revision Agent: applies the critique and tailors the post to the audience and tone."""

from backend.app.agents.base import ClaudeAgent, RetryConfig
from backend.app.agents.state import FINAL_POST_KEY
from backend.app.prompts.revision import revision_instruction


def build_revision_agent(model: str, retry_config: RetryConfig | None = None) -> ClaudeAgent:
    return ClaudeAgent(
        name="revision_agent",
        description="Applies the critique and produces the final, ready-to-post version.",
        model=model,
        retry_config=retry_config,
        instruction=revision_instruction,
        task="Revise the post.",
        output_key=FINAL_POST_KEY,
    )
