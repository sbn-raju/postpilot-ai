"""The building block every PostPilot agent is made from."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.app.llm import AgentRequest, Llm, TransientLlmError

# Builds an agent's system prompt from the pipeline state.
Instruction = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True)
class RetryConfig:
    """Retry transient Claude errors and schema-invalid output with exponential backoff."""

    max_attempts: int = 1
    initial_delay: float = 0.0


@dataclass(frozen=True)
class ClaudeAgent:
    """One specialised agent: a system prompt built from state, and where its output goes.

    Agents with an output_schema return a validated dict; the others return text.
    """

    name: str
    description: str
    model: str
    instruction: Instruction
    output_key: str
    task: str
    output_schema: type[BaseModel] | None = None
    retry_config: RetryConfig | None = None

    def request(self, state: Mapping[str, Any]) -> AgentRequest:
        return AgentRequest(
            agent=self.name,
            model=self.model,
            system_prompt=self.instruction(state),
            prompt=self.task,
            output_schema=self.output_schema.model_json_schema() if self.output_schema else None,
        )

    def _parse(self, output: Any) -> Any:
        if self.output_schema is None:
            return output
        if isinstance(output, str):
            return self.output_schema.model_validate_json(output).model_dump()
        return self.output_schema.model_validate(output).model_dump()

    async def run(self, state: Mapping[str, Any], llm: Llm) -> Any:
        """Run the agent on the current state and return its validated output."""
        request = self.request(state)
        retry = self.retry_config or RetryConfig()
        delay = retry.initial_delay
        for attempt in range(1, retry.max_attempts + 1):
            try:
                return self._parse(await llm.run(request))
            except (TransientLlmError, ValidationError):
                if attempt >= retry.max_attempts:
                    raise
            await asyncio.sleep(delay)
            delay *= 2
