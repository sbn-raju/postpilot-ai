import asyncio
import json

import pytest
from pydantic import ValidationError

from backend.app.agents import (
    ClaudeAgent,
    RetryConfig,
    build_critique_agent,
    build_draft_agent,
    build_research_agent,
    build_revision_agent,
)
from backend.app.agents.state import PostGenerationState
from backend.app.llm import AgentRequest, LlmError, TransientLlmError
from backend.app.prompts import LENGTH_WORDS, brief, current_version
from backend.app.prompts.critique import critique_instruction
from backend.app.prompts.draft import draft_instruction
from backend.app.prompts.research import research_instruction
from backend.app.prompts.revision import revision_instruction
from backend.app.schemas import Critique, ResearchBrief
from tests.fakes import DRAFT, FAILING, RESEARCH, FakeLlm, critique

STATE = {
    "topic": "Why RAG beats fine-tuning",
    "audience": "software engineers",
    "tone": "technical",
    "length": "medium",
    "research": RESEARCH,
    "draft": "the first draft",
    "critique": FAILING,
    "final_post": None,
    "iteration": 0,
    "status": "generating",
}


def ctx(**overrides):
    """The pipeline state the prompts are built from."""
    return {**STATE, **overrides}


BUILDERS = (build_research_agent, build_draft_agent, build_critique_agent, build_revision_agent)


# ---------- Agent definitions ----------

@pytest.mark.parametrize(
    "build, name, output_key, output_schema",
    [
        (build_research_agent, "research_agent", "research", ResearchBrief),
        (build_draft_agent, "draft_agent", "draft", None),
        (build_critique_agent, "critique_agent", "critique", Critique),
        (build_revision_agent, "revision_agent", "final_post", None),
    ],
)
def test_agent_definition(build, name, output_key, output_schema):
    agent = build("claude-x")
    assert isinstance(agent, ClaudeAgent)
    assert agent.name == name
    assert agent.output_key == output_key
    assert agent.output_schema is output_schema
    assert agent.model == "claude-x"
    assert agent.description
    assert agent.task
    assert callable(agent.instruction)


def test_agent_output_keys_are_state_fields():
    fields = PostGenerationState.model_fields
    for build in BUILDERS:
        assert build("claude-x").output_key in fields


def test_agents_accept_retry_config():
    retry = RetryConfig(max_attempts=2)
    for build in BUILDERS:
        assert build("claude-x").retry_config is None
        assert build("claude-x", retry).retry_config is retry


# ---------- Agent requests ----------

def test_request_carries_system_prompt_task_and_model():
    agent = build_draft_agent("claude-x")
    request = agent.request(ctx())
    assert request == AgentRequest(
        agent="draft_agent",
        model="claude-x",
        system_prompt=draft_instruction(ctx()),
        prompt=agent.task,
        output_schema=None,
    )


@pytest.mark.parametrize(
    "build, schema", [(build_research_agent, ResearchBrief), (build_critique_agent, Critique)]
)
def test_structured_agents_request_json_schema(build, schema):
    assert build("claude-x").request(ctx()).output_schema == schema.model_json_schema()


def run(agent, llm):
    return asyncio.run(agent.run(ctx(), llm))


def test_structured_output_is_validated_from_dict_or_json_text():
    agent = build_critique_agent("claude-x")
    assert run(agent, FakeLlm(script={"critique_agent": [critique(7)]})) == critique(7)
    as_text = json.dumps(critique(7))
    assert run(agent, FakeLlm(script={"critique_agent": [as_text]})) == critique(7)


def test_text_agent_returns_reply_unchanged():
    assert run(build_draft_agent("claude-x"), FakeLlm()) == DRAFT


def test_run_retries_transient_errors_and_invalid_output():
    agent = build_research_agent("claude-x", RetryConfig(max_attempts=3))
    llm = FakeLlm(script={"research_agent": [TransientLlmError("529"), "not json", RESEARCH]})
    assert run(agent, llm) == RESEARCH
    assert llm.agent_sequence() == ["research_agent"] * 3


def test_run_does_not_retry_permanent_errors():
    agent = build_research_agent("claude-x", RetryConfig(max_attempts=3))
    llm = FakeLlm(script={"research_agent": [LlmError("401 invalid x-api-key")]})
    with pytest.raises(LlmError, match="invalid x-api-key"):
        run(agent, llm)
    assert llm.agent_sequence() == ["research_agent"]


# ---------- State ----------

def test_state_defaults():
    state = PostGenerationState(topic="t", audience="a", tone="casual", length="short")
    assert state.research is state.draft is state.critique is state.final_post is None
    assert state.iteration == 0
    assert state.status == "generating"


def test_state_rejects_unknown_tone_and_length():
    with pytest.raises(ValidationError):
        PostGenerationState(topic="t", audience="a", tone="angry", length="short")
    with pytest.raises(ValidationError):
        PostGenerationState(topic="t", audience="a", tone="casual", length="huge")


# ---------- Output schemas ----------

def test_research_brief_requires_every_field():
    assert ResearchBrief.model_validate(RESEARCH).key_facts == RESEARCH["key_facts"]
    with pytest.raises(ValidationError):
        ResearchBrief.model_validate({k: v for k, v in RESEARCH.items() if k != "angles"})


@pytest.mark.parametrize("score", [1, 10])
def test_critique_accepts_score_bounds(score):
    assert Critique.model_validate(critique(score)).accuracy_score == score


@pytest.mark.parametrize("score", [0, 11, -3])
def test_critique_rejects_out_of_range_scores(score):
    with pytest.raises(ValidationError):
        Critique.model_validate(critique(score))


# ---------- Prompts ----------

@pytest.mark.parametrize("length, words", LENGTH_WORDS.items())
def test_brief_includes_request_and_word_target(length, words):
    text = brief({**STATE, "length": length})
    for value in (STATE["topic"], STATE["audience"], STATE["tone"], f"about {words} words"):
        assert value in text


def test_length_words_cover_every_length():
    assert set(LENGTH_WORDS) == {"short", "medium", "long"}


def test_current_version_prefers_latest_revision():
    assert current_version({"draft": "d", "final_post": None}) == "d"
    assert current_version({"draft": "d"}) == "d"
    assert current_version({"draft": "d", "final_post": "r"}) == "r"


def test_research_instruction_includes_request():
    text = research_instruction(ctx())
    assert STATE["topic"] in text and STATE["audience"] in text
    assert "JSON" in text


def test_draft_instruction_includes_research_brief():
    text = draft_instruction(ctx())
    for fact in RESEARCH["key_facts"] + RESEARCH["pitfalls"]:
        assert fact in text


def test_critique_instruction_reviews_current_version():
    assert "the first draft" in critique_instruction(ctx())
    text = critique_instruction(ctx(final_post="the revision"))
    assert "the revision" in text and "the first draft" not in text
    for score in ("accuracy_score", "engagement_score", "audience_fit_score"):
        assert score in text


def test_revision_instruction_includes_critique_and_current_version():
    text = revision_instruction(ctx(final_post="the revision"))
    assert "the revision" in text
    for item in FAILING["issues"] + FAILING["suggestions"]:
        assert item in text


def test_prompts_keep_unicode_readable():
    text = draft_instruction(ctx(research={**RESEARCH, "summary": "Café ☕ naïve"}))
    assert "Café ☕ naïve" in text
