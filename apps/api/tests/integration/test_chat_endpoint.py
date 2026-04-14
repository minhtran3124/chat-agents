import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_fakes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from langchain_core.messages import AIMessageChunk

    async def fake_supervisor_astream(*args, **kwargs):
        yield ("updates", {
            "classifier": {
                "current_intent": "chat",
                "confidence": 0.92,
                "fallback_used": False,
                "routing_history": [],
            }
        })
        yield ("messages", (AIMessageChunk(content="Hello!"), {}))

    fake_supervisor = MagicMock()
    fake_supervisor.astream = fake_supervisor_astream
    fake_supervisor.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    fake_deep = MagicMock()
    fake_deep.astream = AsyncMock(return_value=iter([]))
    fake_deep.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    with (
        patch("app.main.build_supervisor_graph", return_value=fake_supervisor),
        patch("app.main.build_deep_research_only_graph", return_value=fake_deep),
    ):
        from app.main import app
        with TestClient(app) as client:
            yield client


@pytest.mark.integration
def test_chat_endpoint_emits_intent_classified(app_with_fakes) -> None:
    with app_with_fakes.stream("POST", "/chat", json={"question": "hi there"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "event: stream_start" in body
    assert "event: intent_classified" in body
    assert "event: text_delta" in body
    assert "event: stream_end" in body

    # Normalize line endings and parse the intent_classified event payload
    normalized = body.replace("\r\n", "\n")
    for chunk in normalized.split("\n\n"):
        if "event: intent_classified" in chunk:
            data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
            data = json.loads(data_line[len("data: "):])
            assert data["intent"] == "chat"
            assert data["confidence"] == 0.92
            assert data["fallback_used"] is False
            break
    else:
        pytest.fail("no intent_classified event found")
