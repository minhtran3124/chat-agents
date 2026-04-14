import pytest

from app.agents.specs import REGISTERED_SPECS, AgentSpec


@pytest.mark.unit
def test_six_specialists_declared() -> None:
    names = {s.name for s in REGISTERED_SPECS}
    assert names == {"chat", "research", "deep-research", "summarize", "code", "planner"}


@pytest.mark.unit
def test_deep_research_has_subagents() -> None:
    deep = next(s for s in REGISTERED_SPECS if s.name == "deep-research")
    sub_names = {s.name for s in deep.subagents}
    assert sub_names == {"researcher", "critic"}


@pytest.mark.unit
def test_simple_specialists_have_no_subagents() -> None:
    for s in REGISTERED_SPECS:
        if s.name == "deep-research":
            continue
        assert s.subagents == [], f"{s.name} must not have subagents"


@pytest.mark.unit
def test_spec_name_is_unique() -> None:
    names = [s.name for s in REGISTERED_SPECS]
    assert len(names) == len(set(names))


@pytest.mark.unit
def test_agent_spec_rejects_unknown_intent_name() -> None:
    with pytest.raises(ValueError):
        AgentSpec(name="unknown", model_role="fast", prompt_name="chat")  # type: ignore[arg-type]
