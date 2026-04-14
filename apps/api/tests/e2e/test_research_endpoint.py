import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def research_app(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from langchain_core.messages import AIMessageChunk

    async def fake_deep_astream(*args, **kwargs):
        yield ("messages", (AIMessageChunk(content="Report text."), {}))

    fake_deep = MagicMock()
    fake_deep.astream = fake_deep_astream
    fake_deep.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    fake_supervisor = MagicMock()
    fake_supervisor.astream = AsyncMock(return_value=iter([]))
    fake_supervisor.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    with (
        patch("app.main.build_supervisor_graph", return_value=fake_supervisor),
        patch("app.main.build_deep_research_only_graph", return_value=fake_deep),
    ):
        from app.main import app
        with TestClient(app) as client:
            yield client


def test_research_endpoint_streams_expected_event_sequence(research_app) -> None:
    with research_app.stream("POST", "/research", json={"question": "compare frameworks"}) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    seen_events = [
        line.split(":", 1)[1].strip()
        for line in body.splitlines()
        if line.startswith("event:")
    ]

    assert "stream_start" in seen_events
    assert "intent_classified" in seen_events
    assert "text_delta" in seen_events
    assert seen_events[-1] == "stream_end"

    # Normalize line endings and parse the intent_classified event payload
    normalized = body.replace("\r\n", "\n")
    for chunk in normalized.split("\n\n"):
        if "event: intent_classified" in chunk:
            data_line = next(line for line in chunk.splitlines() if line.startswith("data: "))
            data = json.loads(data_line[len("data: "):])
            assert data["intent"] == "deep-research"
            assert data["confidence"] == 1.0
            assert data["fallback_used"] is False
            break
    else:
        pytest.fail("no intent_classified event found")


def test_synthetic_compression_emitted_when_no_real_compression(monkeypatch) -> None:
    """When peak_tokens > 30k and no real compression seen, runner emits
    a synthetic compression_triggered event before stream_end."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    async def fake_astream(*args, **kwargs):
        # Single huge values snapshot so peak_tokens > 30k
        # tiktoken encodes 8 consecutive 'x' as ~1 token, so 250_000 chars ≈ 31_250 tokens > 30k
        yield ("values", {"messages": ["x" * 250_000], "files": {}})

    fake_deep = MagicMock()
    fake_deep.astream = fake_astream
    fake_deep.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))
    fake_supervisor = MagicMock()

    from app.main import app
    with (
        patch("app.main.build_supervisor_graph", return_value=fake_supervisor),
        patch("app.main.build_deep_research_only_graph", return_value=fake_deep),
        TestClient(app) as client,
        client.stream("POST", "/research", json={"question": "compare X"}) as resp,
    ):
        seen_events = [
            line.split(":", 1)[1].strip()
            for line in resp.iter_lines()
            if line.startswith("event:")
        ]

    assert "compression_triggered" in seen_events
