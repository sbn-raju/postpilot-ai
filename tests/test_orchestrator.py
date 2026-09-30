import asyncio

import pytest

from backend.app import config
from backend.app.agents.state import PostGenerationState
from backend.app.llm import LlmError, TransientLlmError
from backend.app.orchestrator import GenerationError, build_pipeline, is_approved, run_generation
from backend.app.schemas import Critique
from tests.fakes import DRAFT, FAILING, PASSING, RESEARCH, REVISION, FakeLlm, critique

REQUEST = {
    "topic": "Why RAG beats fine-tuning",
    "audience": "software engineers",
    "tone": "technical",
    "length": "short",
}


def generate(llm: FakeLlm, **overrides) -> PostGenerationState:
    return asyncio.run(run_generation(**{**REQUEST, **overrides}, llm=llm))


# ---------- Approval rule ----------

@pytest.mark.parametrize(
    "scores, expected",
    [
        ((8, 8, 8), True),
        ((10, 9, 8), True),
        ((7, 10, 10), False),
        ((10, 7, 10), False),
        ((10, 10, 7), False),
        ((1, 1, 1), False),
    ],
)
def test_is_approved_requires_every_score_at_threshold(scores, expected):
    result = Critique(
        accuracy_score=scores[0], engagement_score=scores[1], audience_fit_score=scores[2],
        strengths=[], issues=[], suggestions=[],
    )
    assert is_approved(result, threshold=8) is expected


def test_is_approved_defaults_to_configured_threshold(monkeypatch):
    result = Critique.model_validate(critique(6))
    monkeypatch.setattr(config, "APPROVAL_SCORE", 6)
    assert is_approved(result)
    monkeypatch.setattr(config, "APPROVAL_SCORE", 7)
    assert not is_approved(result)


# ---------- Pipeline shape ----------

def test_pipeline_contains_every_agent_in_order():
    names = [agent.name for agent in build_pipeline().agents]
    assert names == ["research_agent", "draft_agent", "critique_agent", "revision_agent"]


def test_pipeline_defaults_to_configured_claude_model(monkeypatch):
    monkeypatch.setattr(config, "CLAUDE_MODEL", "claude-test-model")
    assert {agent.model for agent in build_pipeline().agents} == {"claude-test-model"}


def test_pipeline_model_can_be_overridden():
    assert {agent.model for agent in build_pipeline("claude-other").agents} == {"claude-other"}


def test_run_generation_passes_model_to_every_agent():
    llm = FakeLlm()
    asyncio.run(run_generation(**REQUEST, llm=llm, model="claude-other"))
    assert {request.model for request in llm.requests} == {"claude-other"}


# ---------- Happy paths ----------

def test_approved_after_one_revision():
    llm = FakeLlm()
    state = generate(llm)

    assert llm.agent_sequence() == [
        "research_agent", "draft_agent", "critique_agent", "revision_agent", "critique_agent",
    ]
    assert state.status == "completed"
    assert state.iteration == 1
    assert state.research == RESEARCH
    assert state.draft == DRAFT
    assert state.final_post == REVISION
    assert state.critique == PASSING


def test_inputs_are_preserved_in_final_state():
    state = generate(FakeLlm(), tone="storytelling", length="long")
    assert (state.topic, state.audience, state.tone, state.length) == (
        REQUEST["topic"], REQUEST["audience"], "storytelling", "long",
    )


def test_perfect_draft_is_still_revised_once():
    llm = FakeLlm(script={"critique_agent": [critique(10)]})
    state = generate(llm)
    assert llm.agent_sequence().count("revision_agent") == 1
    assert state.final_post == REVISION


def test_loops_until_critique_approves():
    llm = FakeLlm(script={
        "critique_agent": [FAILING, FAILING, PASSING],
        "revision_agent": ["revision one", "revision two", "revision three"],
    })
    state = generate(llm)

    assert llm.agent_sequence().count("revision_agent") == 2
    assert llm.agent_sequence().count("critique_agent") == 3
    assert state.iteration == 2
    assert state.final_post == "revision two"
    assert state.critique == PASSING


def test_stops_after_max_revisions_when_never_approved(monkeypatch):
    monkeypatch.setattr(config, "MAX_REVISIONS", 2)
    llm = FakeLlm(script={
        "critique_agent": [FAILING],
        "revision_agent": ["revision one", "revision two", "revision three"],
    })
    state = generate(llm)

    assert llm.agent_sequence().count("revision_agent") == 2
    assert state.iteration == 2
    assert state.status == "completed"
    assert state.final_post == "revision two"
    assert state.critique == FAILING  # the last critique is kept even though it failed


def test_approval_threshold_is_configurable(monkeypatch):
    monkeypatch.setattr(config, "APPROVAL_SCORE", 5)
    llm = FakeLlm(script={"critique_agent": [FAILING]})  # scores of 5
    generate(llm)
    assert llm.agent_sequence().count("revision_agent") == 1


# ---------- What each agent sees ----------

def test_research_prompt_contains_the_request():
    llm = FakeLlm()
    generate(llm)
    (prompt,) = llm.prompts("research_agent")
    for value in (REQUEST["topic"], REQUEST["audience"], REQUEST["tone"], "about 100 words"):
        assert value in prompt


def test_draft_prompt_contains_research_brief():
    llm = FakeLlm()
    generate(llm)
    (prompt,) = llm.prompts("draft_agent")
    for fact in RESEARCH["key_facts"]:
        assert fact in prompt


def test_critique_reviews_draft_first_then_latest_revision():
    llm = FakeLlm(script={
        "critique_agent": [FAILING, FAILING, PASSING],
        "revision_agent": ["revision one", "revision two"],
    })
    generate(llm)
    first, second, third = llm.prompts("critique_agent")
    assert DRAFT in first
    assert "revision one" in second and DRAFT not in second
    assert "revision two" in third


def test_revision_prompt_contains_critique_and_current_version():
    llm = FakeLlm(script={
        "critique_agent": [critique(5, issue="Vague claim about latency"), PASSING],
    })
    generate(llm)
    (prompt,) = llm.prompts("revision_agent")
    assert "Vague claim about latency" in prompt
    assert DRAFT in prompt
    assert REQUEST["tone"] in prompt


def test_generated_text_with_braces_does_not_break_prompts():
    llm = FakeLlm(script={
        "draft_agent": ["Use {context} and {{state}} wisely"],
        "revision_agent": ["Final {post} text"],
    })
    state = generate(llm)
    assert "Use {context} and {{state}} wisely" in llm.prompts("critique_agent")[0]
    assert state.final_post == "Final {post} text"


def test_each_run_is_isolated():
    first, second = FakeLlm(), FakeLlm(script={"draft_agent": ["another draft"]})
    generate(first)
    state = generate(second)
    assert state.draft == "another draft"
    assert len(second.prompts("research_agent")) == 1


# ---------- Failures ----------

def test_llm_error_raises_generation_error():
    llm = FakeLlm(script={"draft_agent": [RuntimeError("quota exceeded")]})
    with pytest.raises(GenerationError, match="quota exceeded"):
        generate(llm)


def test_llm_error_mid_loop_raises_generation_error():
    llm = FakeLlm(script={"critique_agent": [FAILING, RuntimeError("503 unavailable")]})
    with pytest.raises(GenerationError, match="503"):
        generate(llm)


def test_invalid_research_json_raises_generation_error(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_ATTEMPTS", 2)
    llm = FakeLlm(script={"research_agent": ["this is not json"]})
    with pytest.raises(GenerationError):
        generate(llm)
    assert llm.agent_sequence() == ["research_agent", "research_agent"]


def test_research_missing_fields_raises_generation_error():
    llm = FakeLlm(script={"research_agent": [{"summary": "only a summary"}]})
    with pytest.raises(GenerationError):
        generate(llm)


@pytest.mark.parametrize("score", [0, 11])
def test_out_of_range_critique_score_raises_generation_error(score):
    llm = FakeLlm(script={"critique_agent": [critique(score)]})
    with pytest.raises(GenerationError):
        generate(llm)


def test_empty_revision_raises_generation_error(monkeypatch):
    monkeypatch.setattr(config, "MAX_REVISIONS", 2)
    llm = FakeLlm(script={"critique_agent": [FAILING], "revision_agent": [""]})
    with pytest.raises(GenerationError, match="final_post"):
        generate(llm)
    # The loop is still bounded by MAX_REVISIONS.
    assert llm.agent_sequence().count("revision_agent") == 2


def test_empty_draft_raises_generation_error():
    llm = FakeLlm(script={"draft_agent": [""]})
    with pytest.raises(GenerationError, match="draft"):
        generate(llm)


def test_timeout_raises_generation_error():
    llm = FakeLlm(delay=0.5)
    with pytest.raises(GenerationError, match="timed out"):
        asyncio.run(run_generation(**REQUEST, llm=llm, timeout=0.1))


def test_timeout_defaults_to_config(monkeypatch):
    monkeypatch.setattr(config, "GENERATION_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(GenerationError, match="timed out"):
        generate(FakeLlm(delay=0.5))


def test_invalid_request_is_rejected_before_calling_the_llm():
    llm = FakeLlm()
    with pytest.raises(ValueError):
        generate(llm, tone="angry")
    assert llm.calls == []



# ---------- Retries ----------

def overloaded() -> TransientLlmError:
    return TransientLlmError("503 overloaded")


def test_pipeline_agents_share_retry_config(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_ATTEMPTS", 4)
    monkeypatch.setattr(config, "LLM_RETRY_INITIAL_DELAY", 1.5)
    for agent in build_pipeline().agents:
        assert agent.retry_config.max_attempts == 4
        assert agent.retry_config.initial_delay == 1.5


def test_transient_server_error_is_retried():
    llm = FakeLlm(script={"draft_agent": [overloaded(), DRAFT]})
    state = generate(llm)
    assert state.draft == DRAFT
    assert llm.agent_sequence().count("draft_agent") == 2


def test_invalid_structured_output_is_retried():
    llm = FakeLlm(script={"critique_agent": ["not json", PASSING]})
    state = generate(llm)
    assert state.critique == PASSING
    assert state.status == "completed"


def test_retries_give_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_ATTEMPTS", 3)
    llm = FakeLlm(script={"research_agent": [overloaded()]})
    with pytest.raises(GenerationError, match="503"):
        generate(llm)
    assert llm.agent_sequence() == ["research_agent"] * 3


def test_client_errors_are_not_retried():
    bad_key = LlmError("401 API key not valid")
    llm = FakeLlm(script={"research_agent": [bad_key]})
    with pytest.raises(GenerationError, match="API key not valid"):
        generate(llm)
    assert llm.agent_sequence() == ["research_agent"]


def test_retries_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_ATTEMPTS", 1)
    llm = FakeLlm(script={"draft_agent": [overloaded(), DRAFT]})
    with pytest.raises(GenerationError):
        generate(llm)
    assert llm.agent_sequence().count("draft_agent") == 1
