"""🧐 Critique Agent: scores the current version for accuracy, engagement, and audience fit."""

from backend.app.agents.base import ClaudeAgent, RetryConfig
from backend.app.agents.state import CRITIQUE_KEY
from backend.app.prompts.critique import critique_instruction
from backend.app.schemas import Critique


def build_critique_agent(model: str, retry_config: RetryConfig | None = None) -> ClaudeAgent:
    return ClaudeAgent(
        name="critique_agent",
        description="Reviews the post for technical accuracy and engagement potential.",
        model=model,
        retry_config=retry_config,
        instruction=critique_instruction,
        task="Critique the post.",
        output_schema=Critique,
        output_key=CRITIQUE_KEY,
    )
