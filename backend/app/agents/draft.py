"""✍️ Draft Agent: writes the first draft from the research brief."""

from backend.app.agents.base import ClaudeAgent, RetryConfig
from backend.app.agents.state import DRAFT_KEY
from backend.app.prompts.draft import draft_instruction


def build_draft_agent(model: str, retry_config: RetryConfig | None = None) -> ClaudeAgent:
    return ClaudeAgent(
        name="draft_agent",
        description="Writes the first draft: hook, body, and call to action.",
        model=model,
        retry_config=retry_config,
        instruction=draft_instruction,
        task="Write the first draft of the post.",
        output_key=DRAFT_KEY,
    )
