"""🔎 Research Agent: turns the request into a structured research brief."""

from backend.app.agents.base import ClaudeAgent, RetryConfig
from backend.app.agents.state import RESEARCH_KEY
from backend.app.prompts.research import research_instruction
from backend.app.schemas import ResearchBrief


def build_research_agent(model: str, retry_config: RetryConfig | None = None) -> ClaudeAgent:
    return ClaudeAgent(
        name="research_agent",
        description="Gathers key facts, angles, and audience insights for the post.",
        model=model,
        retry_config=retry_config,
        instruction=research_instruction,
        task="Prepare the research brief.",
        output_schema=ResearchBrief,
        output_key=RESEARCH_KEY,
    )
