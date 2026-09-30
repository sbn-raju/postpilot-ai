"""The LLM behind the agents: Claude, driven through the Claude Agent SDK.

Agents never call the SDK directly. They hand an AgentRequest to an Llm, so tests can
swap in a scripted fake (see tests/fakes.py) and run the pipeline without network calls.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultError,
    ResultMessage,
    query,
)


class LlmError(RuntimeError):
    """Claude failed in a way that retrying won't fix (bad API key, unknown model, ...)."""


class TransientLlmError(LlmError):
    """Claude failed in a way that may succeed on retry (overload, rate limit, 5xx)."""


@dataclass(frozen=True)
class AgentRequest:
    """One agent turn: who is asking, the system prompt, and the task message.

    When output_schema (a JSON schema) is set, Claude must answer with matching JSON.
    """

    agent: str
    model: str
    system_prompt: str
    prompt: str
    output_schema: dict[str, Any] | None = None


class Llm(Protocol):
    async def run(self, request: AgentRequest) -> Any:
        """Return the reply: text, or the parsed JSON object when output_schema is set."""
        ...


def _is_retryable(status: int | None) -> bool:
    return status is not None and (status in (408, 429) or status >= 500)


def _error(status: int | None, detail: str) -> LlmError:
    detail = f"{status} {detail}" if status else detail
    return TransientLlmError(detail) if _is_retryable(status) else LlmError(detail)


class ClaudeLlm:
    """Runs each agent turn as a one-shot Claude Agent SDK query.

    Reads ANTHROPIC_API_KEY from the environment.
    """

    async def run(self, request: AgentRequest) -> Any:
        options = ClaudeAgentOptions(
            model=request.model,
            system_prompt=request.system_prompt,
            # The agents only write text: no file, shell, or web tools.
            tools=[],
            # Isolate from CLAUDE.md files and local Claude Code settings.
            setting_sources=[],
            output_format=(
                {"type": "json_schema", "schema": request.output_schema}
                if request.output_schema
                else None
            ),
        )

        result: ResultMessage | None = None
        try:
            async for message in query(prompt=request.prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message
        except ResultError as exc:
            raise _error(exc.api_error_status, exc.result or str(exc)) from exc
        except ClaudeSDKError as exc:
            raise LlmError(str(exc)) from exc

        if result is None:
            raise LlmError(f"{request.agent} got no result from Claude")
        if result.is_error:
            detail = result.result or "; ".join(result.errors or []) or result.subtype
            raise _error(result.api_error_status, detail)
        return result.structured_output if request.output_schema else result.result
