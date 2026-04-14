from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from app.agents.classifier import classify
from app.schemas.routing import ClassifierResult


@pytest.mark.unit
async def test_classifier_returns_intent_and_confidence() -> None:
    fake_llm = AsyncMock()
    fake_llm.with_structured_output = MagicMock(return_value=fake_llm)
    fake_llm.ainvoke.return_value = ClassifierResult(
        intent="chat", confidence=0.9, fallback_used=False
    )

    result = await classify(
        messages=[HumanMessage("hi")],
        current_intent=None,
        llm=fake_llm,
        prompt="stub",
    )
    assert result.intent == "chat"
    assert result.confidence == 0.9
    assert result.fallback_used is False


@pytest.mark.unit
async def test_classifier_exception_returns_fallback() -> None:
    fake_llm = AsyncMock()
    fake_llm.with_structured_output = MagicMock(return_value=fake_llm)
    fake_llm.ainvoke.side_effect = RuntimeError("429")

    result = await classify(
        messages=[HumanMessage("hi")],
        current_intent=None,
        llm=fake_llm,
        prompt="stub",
    )
    assert result.intent == "chat"
    assert result.confidence == 0.0
    assert result.fallback_used is True


@pytest.mark.unit
async def test_low_confidence_falls_back_to_chat() -> None:
    fake_llm = AsyncMock()
    fake_llm.with_structured_output = MagicMock(return_value=fake_llm)
    fake_llm.ainvoke.return_value = ClassifierResult(
        intent="research",
        confidence=0.30,
        fallback_used=False,
    )
    result = await classify(
        messages=[HumanMessage("asdf qwerty")],
        current_intent=None,
        llm=fake_llm,
        prompt="stub",
    )
    assert result.intent == "chat"
    assert result.fallback_used is True


@pytest.mark.unit
async def test_stickiness_preserves_current_intent() -> None:
    fake_llm = AsyncMock()
    fake_llm.with_structured_output = MagicMock(return_value=fake_llm)
    fake_llm.ainvoke.return_value = ClassifierResult(
        intent="research",
        confidence=0.45,
        fallback_used=False,
    )
    result = await classify(
        messages=[HumanMessage("tell me more")],
        current_intent="research",
        llm=fake_llm,
        prompt="stub",
    )
    assert result.intent == "research"
    assert result.fallback_used is False
