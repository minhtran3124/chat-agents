# apps/api/tests/unit/test_research_router.py
"""Unit tests for /research router — prompt version resolution and stream_end payload."""
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _make_mock_agent(
    stream_events: list[tuple[str, object]],
    state_values: dict | None = None,
):
    """Return a mock agent whose astream yields the given (mode, chunk) pairs.

    If *state_values* is provided, ``aget_state`` returns a snapshot whose
    ``.values`` is that dict (used to simulate a populated virtual FS for the
    final-report fallback path).
    """
    async def _astream(*args, **kwargs) -> AsyncGenerator:
        for item in stream_events:
            yield item

    agent = MagicMock()
    agent.astream = _astream
    if state_values is None:
        agent.aget_state = AsyncMock(return_value=None)
    else:
        state = MagicMock()
        state.values = state_values
        agent.aget_state = AsyncMock(return_value=state)
    return agent


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events = []
    current: dict = {}
    for line in text.splitlines():
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_end_contains_versions_used():
    """versions_used from registry.resolve_versions() must appear in stream_end."""
    mock_versions = {"main": "v1", "researcher": "v1", "critic": "v1"}
    mock_agent = _make_mock_agent([])  # empty stream → goes straight to stream_end

    with (
        patch("app.routers.research.registry") as mock_registry,
        patch("app.routers.research.build_research_agent", return_value=mock_agent),
    ):
        mock_registry.resolve_versions.return_value = mock_versions
        mock_registry.get.return_value = "mock prompt text"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/research",
                json={"question": "What is LangGraph?"},
            )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None, f"stream_end event not found in: {events}"
    assert stream_end_ev["data"]["versions_used"] == mock_versions


@pytest.mark.unit
@pytest.mark.asyncio
async def test_per_request_override_takes_precedence():
    """prompt_versions in the request must override active.yaml defaults."""
    # Active defaults: all v1. Request overrides main → v2.
    override_resolved = {"main": "v2", "researcher": "v1", "critic": "v1"}
    mock_agent = _make_mock_agent([])

    with (
        patch("app.routers.research.registry") as mock_registry,
        patch("app.routers.research.build_research_agent", return_value=mock_agent),
    ):
        mock_registry.resolve_versions.return_value = override_resolved
        mock_registry.get.return_value = "mock prompt text"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/research",
                json={"question": "test", "prompt_versions": {"main": "v2"}},
            )

    assert response.status_code == 200
    # resolve_versions was called with the raw override dict from the request
    mock_registry.resolve_versions.assert_called_once_with({"main": "v2"})
    # registry.get was called with the resolved v2 version for main
    mock_registry.get.assert_any_call("main", version="v2")
    # researcher and critic remain at their active default (v1)
    mock_registry.get.assert_any_call("researcher", version="v1")
    mock_registry.get.assert_any_call("critic", version="v1")
    # stream_end carries the merged versions
    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None, f"stream_end event not found in: {events}"
    assert stream_end_ev["data"]["versions_used"]["main"] == "v2"
    assert stream_end_ev["data"]["versions_used"]["researcher"] == "v1"
    assert stream_end_ev["data"]["versions_used"]["critic"] == "v1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_end_falls_back_to_draft_when_stream_is_thin():
    """When text_delta stream is below MIN_STREAM_REPORT_CHARS and draft.md exists,
    stream_end's final_report must be the draft content with source='file'."""
    mock_versions = {"main": "v2", "researcher": "v1", "critic": "v1"}
    draft = "# Report\n\n" + ("Long body content. " * 40)  # well over 200 chars
    assert len(draft) > 200

    # Empty stream → streamed_report is "" (0 chars) → fallback should trigger.
    mock_agent = _make_mock_agent(
        stream_events=[],
        state_values={"files": {"draft.md": draft}, "usage": {"input_tokens": 5}},
    )

    with (
        patch("app.routers.research.registry") as mock_registry,
        patch("app.routers.research.build_research_agent", return_value=mock_agent),
    ):
        mock_registry.resolve_versions.return_value = mock_versions
        mock_registry.get.return_value = "mock prompt text"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/research", json={"question": "Question?"})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None, f"stream_end event not found in: {events}"
    assert stream_end_ev["data"]["final_report"] == draft
    assert stream_end_ev["data"]["final_report_source"] == "file"
    assert stream_end_ev["data"]["usage"] == {"input_tokens": 5}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_end_prefers_stream_when_report_is_long_enough():
    """When text_delta stream clears MIN_STREAM_REPORT_CHARS, we must NOT
    fall back even if draft.md exists — source stays 'stream'."""
    from langchain_core.messages import AIMessageChunk

    long_text = "Streamed report content. " * 20  # > 200 chars
    assert len(long_text) > 200
    streamed_chunk = AIMessageChunk(content=long_text)
    stream_events: list[tuple[str, object]] = [("messages", (streamed_chunk, {}))]

    mock_agent = _make_mock_agent(
        stream_events=stream_events,
        state_values={"files": {"draft.md": "ignored draft " * 50}, "usage": {}},
    )

    with (
        patch("app.routers.research.registry") as mock_registry,
        patch("app.routers.research.build_research_agent", return_value=mock_agent),
    ):
        mock_registry.resolve_versions.return_value = {
            "main": "v2", "researcher": "v1", "critic": "v1",
        }
        mock_registry.get.return_value = "mock prompt text"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/research", json={"question": "Question?"})

    events = _parse_sse(response.text)
    stream_end_ev = next((e for e in events if e.get("event") == "stream_end"), None)
    assert stream_end_ev is not None
    assert stream_end_ev["data"]["final_report"] == long_text
    assert stream_end_ev["data"]["final_report_source"] == "stream"
