"""A scripted stand-in for Claude, so the agent pipeline runs without network calls."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from backend.app.llm import AgentRequest

RESEARCH = {
    "summary": "Retrieval-augmented generation grounds answers in your own documents.",
    "key_facts": ["RAG retrieves documents at query time", "Fine-tuning changes model weights"],
    "angles": ["Cost of keeping knowledge fresh", "Debuggability of retrieved sources"],
    "audience_insights": ["Engineers want concrete trade-offs, not hype"],
    "pitfalls": ["Avoid claiming RAG eliminates hallucinations"],
}
DRAFT = "DRAFT: Stop fine-tuning for facts. Retrieve them instead."
REVISION = "REVISED: Your model doesn't need to memorize your docs. #RAG"


def critique(score: int = 9, issue: str = "Hook could be sharper") -> dict:
    return {
        "accuracy_score": score,
        "engagement_score": score,
        "audience_fit_score": score,
        "strengths": ["Clear contrast between RAG and fine-tuning"],
        "issues": [issue],
        "suggestions": ["Open with a concrete failure story"],
    }


PASSING = critique(9)
FAILING = critique(5, issue="Claims are vague")


@dataclass
class FakeLlm:
    """Replies per agent from a script.

    script maps an agent name (e.g. "critique_agent") to a list of responses consumed in
    order; the last one repeats. A response is text, a dict (the parsed JSON Claude would
    return), or an exception to raise. Every request is recorded in requests.
    """

    script: dict[str, list[Any]] = field(default_factory=dict)
    delay: float = 0.0
    requests: list[AgentRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.script = {
            "research_agent": [RESEARCH],
            "draft_agent": [DRAFT],
            "critique_agent": [PASSING],
            "revision_agent": [REVISION],
            **self.script,
        }

    @property
    def calls(self) -> list[tuple[str, str]]:
        """(agent_name, system_prompt) for every request, in order."""
        return [(r.agent, r.system_prompt) for r in self.requests]

    def prompts(self, agent: str) -> list[str]:
        return [prompt for name, prompt in self.calls if name == agent]

    def agent_sequence(self) -> list[str]:
        return [name for name, _ in self.calls]

    async def run(self, request: AgentRequest) -> Any:
        count = self.agent_sequence().count(request.agent)
        self.requests.append(request)

        if self.delay:
            await asyncio.sleep(self.delay)

        responses = self.script[request.agent]
        response = responses[min(count, len(responses) - 1)]
        if isinstance(response, BaseException):
            raise response
        return response
