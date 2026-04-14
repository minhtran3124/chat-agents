# apps/api/tests/unit/test_research_router.py
"""Unit tests for /research router — prompt version resolution and stream_end payload.

Updated for T10: router now delegates to _runner.run_graph with force_intent="deep-research".
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in text.replace("\r\n", "\n").splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def _make_fake_deep_graph():
    """Minimal fake graph that yields an empty stream."""
    fake = MagicMock()
    fake.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    async def _empty_astream(*args, **kwargs):
        return
        yield  # make it an async generator

    fake.astream = _empty_astream
    return fake


@pytest.fixture
def research_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    fake_deep = _make_fake_deep_graph()
    fake_supervisor = MagicMock()
    with (
        patch("app.main.build_supervisor_graph", return_value=fake_supervisor),
        patch("app.main.build_deep_research_only_graph", return_value=fake_deep),
        TestClient(app) as client,
    ):
        yield client


@pytest.mark.unit
def test_stream_end_contains_versions_used(research_client) -> None:
    """versions_used from registry.resolve_versions() must appear in stream_end."""
    mock_versions = {"main": "v1", "researcher": "v1", "critic": "v1"}

    with patch("app.routers.research.prompt_registry") as mock_registry:
        mock_registry.resolve_versions.return_value = mock_versions
        response = research_client.post(
            "/research",
            json={"question": "What is LangGraph?"},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None, f"stream_end event not found in: {events}"
    assert stream_end_ev["data"]["versions_used"] == mock_versions


@pytest.mark.unit
def test_per_request_override_takes_precedence(research_client) -> None:
    """prompt_versions in the request must be forwarded to resolve_versions."""
    override_resolved = {"main": "v2", "researcher": "v1", "critic": "v1"}

    with patch("app.routers.research.prompt_registry") as mock_registry:
        mock_registry.resolve_versions.return_value = override_resolved
        response = research_client.post(
            "/research",
            json={"question": "test", "prompt_versions": {"main": "v2"}},
        )

    assert response.status_code == 200
    mock_registry.resolve_versions.assert_called_once_with({"main": "v2"})
    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None, f"stream_end event not found in: {events}"
    assert stream_end_ev["data"]["versions_used"]["main"] == "v2"
