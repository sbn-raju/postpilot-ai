"""Runs the Claude agent pipeline.

    research -> draft -> critique -> quality_gate --"done"---> finalize
                            ^              |
                            |          "revise"
                            +-- revision <-+

The quality gate always sends the first draft through one revision, so the Revision
Agent can tailor it to the audience and tone. After that, it loops until every critique
score reaches config.APPROVAL_SCORE or config.MAX_REVISIONS passes have run.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.app import config
from backend.app.agents import (
    ClaudeAgent,
    RetryConfig,
    build_critique_agent,
    build_draft_agent,
    build_research_agent,
    build_revision_agent,
)
from backend.app.agents.state import CRITIQUE_KEY, PostGenerationState
from backend.app.llm import ClaudeLlm, Llm
from backend.app.schemas import Critique

REVISE = "revise"
DONE = "done"


class GenerationError(RuntimeError):
    """The pipeline failed or produced incomplete output."""


def is_approved(critique: Critique, threshold: int | None = None) -> bool:
    threshold = config.APPROVAL_SCORE if threshold is None else threshold
    return min(
        critique.accuracy_score, critique.engagement_score, critique.audience_fit_score
    ) >= threshold


def quality_gate(state: dict[str, Any]) -> str:
    """Decide whether the latest critique ends the run or triggers another revision."""
    # iteration counts revision passes. Deciding on it rather than on final_post keeps the
    # loop bounded even if the Revision Agent returns nothing.
    iteration = state.get("iteration", 0)
    approved = is_approved(Critique.model_validate(state[CRITIQUE_KEY]))

    if iteration >= 1 and (approved or iteration >= config.MAX_REVISIONS):
        return DONE
    state["iteration"] = iteration + 1
    return REVISE


def llm_retry_config() -> RetryConfig:
    """Retry transient Claude errors and schema-invalid output; fail fast on anything else
    (bad API key, unknown model, and other client errors won't fix themselves)."""
    return RetryConfig(
        max_attempts=config.LLM_MAX_ATTEMPTS,
        initial_delay=config.LLM_RETRY_INITIAL_DELAY,
    )


@dataclass(frozen=True)
class Pipeline:
    research: ClaudeAgent
    draft: ClaudeAgent
    critique: ClaudeAgent
    revision: ClaudeAgent

    @property
    def agents(self) -> list[ClaudeAgent]:
        return [self.research, self.draft, self.critique, self.revision]

    async def run(self, initial: PostGenerationState, llm: Llm) -> PostGenerationState:
        state = initial.model_dump()

        async def step(agent: ClaudeAgent) -> None:
            state[agent.output_key] = await agent.run(state, llm)

        await step(self.research)
        await step(self.draft)
        await step(self.critique)
        while quality_gate(state) == REVISE:
            await step(self.revision)
            await step(self.critique)

        state["status"] = "completed"
        return PostGenerationState.model_validate(state)


def build_pipeline(model: str | None = None) -> Pipeline:
    model = model or config.CLAUDE_MODEL
    retry = llm_retry_config()
    return Pipeline(
        research=build_research_agent(model, retry),
        draft=build_draft_agent(model, retry),
        critique=build_critique_agent(model, retry),
        revision=build_revision_agent(model, retry),
    )


async def run_generation(
    *,
    topic: str,
    audience: str,
    tone: str,
    length: str,
    llm: Llm | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> PostGenerationState:
    """Run the full pipeline and return the completed state.

    Raises GenerationError if an agent fails, the run times out, or any output is missing.
    """
    initial = PostGenerationState(topic=topic, audience=audience, tone=tone, length=length)
    pipeline = build_pipeline(model)
    llm = llm or ClaudeLlm()
    timeout = config.GENERATION_TIMEOUT_SECONDS if timeout is None else timeout

    try:
        state = await asyncio.wait_for(pipeline.run(initial, llm), timeout=timeout)
    except TimeoutError as exc:
        raise GenerationError(f"Generation timed out after {timeout:g}s") from exc
    except Exception as exc:
        raise GenerationError(f"Generation failed: {exc}") from exc

    missing = [
        key for key in ("research", "draft", "critique", "final_post") if not getattr(state, key)
    ]
    if state.status != "completed" or missing:
        raise GenerationError(f"Generation incomplete; missing: {', '.join(missing) or 'status'}")
    return state
