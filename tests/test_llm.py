"""ClaudeLlm, with the Claude Agent SDK's query() replaced by a stub."""

import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, CLINotFoundError, ResultError, ResultMessage, TextBlock

from backend.app import llm as llm_module
from backend.app.llm import AgentRequest, ClaudeLlm, LlmError, TransientLlmError

# conftest.py blocks ClaudeLlm.run for every test; keep the real one for these.
REAL_RUN = ClaudeLlm.run

TEXT_REQUEST = AgentRequest(
    agent="draft_agent", model="claude-x", system_prompt="You write posts.", prompt="Write."
)
SCHEMA = {"type": "object", "properties": {"score": {"type": "integer"}}, "required": ["score"]}
JSON_REQUEST = AgentRequest(
    agent="critique_agent", model="claude-x", system_prompt="You review.", prompt="Review.",
    output_schema=SCHEMA,
)


def result(**overrides) -> ResultMessage:
    fields = dict(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
        session_id="s", result="the post",
    )
    return ResultMessage(**{**fields, **overrides})


@pytest.fixture
def sdk(monkeypatch):
    """Stub query(): yields .messages (or raises .error) and records each call."""
    stub = type("Stub", (), {"messages": [result()], "error": None, "calls": []})()

    async def fake_query(*, prompt, options):
        stub.calls.append((prompt, options))
        for message in stub.messages:
            yield message
        if stub.error:
            raise stub.error

    monkeypatch.setattr(llm_module, "query", fake_query)
    return stub


def run(request: AgentRequest = TEXT_REQUEST):
    return asyncio.run(REAL_RUN(ClaudeLlm(), request))


def test_text_request_returns_result_text(sdk):
    sdk.messages = [AssistantMessage(content=[TextBlock("thinking out loud")], model="m"), result()]
    assert run() == "the post"


def test_options_isolate_the_agent(sdk):
    run()
    ((prompt, options),) = sdk.calls
    assert prompt == "Write."
    assert options.model == "claude-x"
    assert options.system_prompt == "You write posts."
    assert options.tools == []
    assert options.setting_sources == []
    assert options.output_format is None


def test_structured_request_sends_schema_and_returns_structured_output(sdk):
    sdk.messages = [result(result="", structured_output={"score": 7})]
    assert run(JSON_REQUEST) == {"score": 7}
    ((_, options),) = sdk.calls
    assert options.output_format == {"type": "json_schema", "schema": SCHEMA}


@pytest.mark.parametrize("status", [408, 429, 500, 529])
def test_retryable_api_errors_are_transient(sdk, status):
    sdk.messages = [result(is_error=True, api_error_status=status, result="API Error: busy")]
    with pytest.raises(TransientLlmError, match=f"{status} API Error: busy"):
        run()


@pytest.mark.parametrize("status", [400, 401, 404, None])
def test_other_errors_are_permanent(sdk, status):
    sdk.messages = [result(is_error=True, api_error_status=status, result="API Error: nope")]
    with pytest.raises(LlmError, match="nope") as exc:
        run()
    assert not isinstance(exc.value, TransientLlmError)


def test_result_error_raised_by_sdk_is_mapped(sdk):
    sdk.messages = []
    sdk.error = ResultError(
        "failed", data={"subtype": "success", "api_error_status": 529, "result": "Overloaded"}
    )
    with pytest.raises(TransientLlmError, match="529 Overloaded"):
        run()


def test_missing_cli_is_a_permanent_error(sdk):
    sdk.messages = []
    sdk.error = CLINotFoundError("Claude Code not found")
    with pytest.raises(LlmError, match="Claude Code not found"):
        run()


def test_no_result_is_an_error(sdk):
    sdk.messages = []
    with pytest.raises(LlmError, match="draft_agent got no result"):
        run()
