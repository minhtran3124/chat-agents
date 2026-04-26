import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_research_endpoint_streams_expected_event_sequence(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from langchain_core.messages import AIMessage, ToolMessage

    async def fake_astream(*args, **kwargs):
        # Router uses subgraphs=True → (namespace, mode, chunk) triples.
        # Empty namespace == parent graph; non-empty would be a subagent.
        yield ((), "updates", {"main": {"todos": [{"text": "step1", "status": "pending"}]}})
        # Main agent spawns researcher subagent via the `task` tool
        yield (
            (),
            "updates",
            {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "task",
                                    "id": "call_research_1",
                                    "args": {
                                        "subagent_type": "researcher",
                                        "description": "research X",
                                    },
                                }
                            ],
                        )
                    ]
                }
            },
        )
        # Researcher returns via matching ToolMessage
        yield (
            (),
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="researcher done",
                            tool_call_id="call_research_1",
                            name="task",
                        )
                    ]
                }
            },
        )

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    # build_research_agent is imported INTO app.routers.research, so patch
    # the symbol in that namespace, not in app.services.agent_factory.
    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app

        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream(
                "POST",
                "/research",
                json={"question": "compare frameworks"},
            ) as resp,
        ):
            seen_events = []
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    seen_events.append(line.split(":", 1)[1].strip())

    assert "stream_start" in seen_events
    assert "todo_updated" in seen_events
    assert "subagent_started" in seen_events
    assert "subagent_completed" in seen_events
    assert seen_events[-1] == "stream_end"


@pytest.mark.asyncio
async def test_synthetic_compression_emitted_when_no_real_compression(monkeypatch):
    """When peak_tokens > 30k and no real compression seen, router emits
    a synthetic compression_triggered event before stream_end."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    async def fake_astream(*args, **kwargs):
        # Single huge values snapshot so peak_tokens > 30k, but no token drop
        # tiktoken encodes 8 consecutive 'x' as 1 token, so 250_000 chars ≈ 31_250 tokens > 30k
        yield ((), "values", {"messages": ["x" * 250_000], "files": {}})

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app

        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream("POST", "/research", json={"question": "compare X"}) as resp,
        ):
            seen_events = [
                line.split(":", 1)[1].strip()
                async for line in resp.aiter_lines()
                if line.startswith("event:")
            ]

    assert "compression_triggered" in seen_events


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_research_timeout_produces_error_and_stream_end(
    slow_agent_factory,
    monkeypatch,
):
    """DESIGN: Full HTTP path — a slow agent should trigger timeout,
    producing error{reason:timeout} followed by stream_end{source:error}."""
    import app.config.settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "RESEARCH_TIMEOUT_S", 0.05)

    agent = slow_agent_factory(sleep_s=10)
    with patch("app.routers.research.build_research_agent", return_value=agent):
        from app.main import app

        events_seen: list[tuple[str, dict]] = []
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream(
                "POST",
                "/research",
                json={"question": "anything"},
            ) as resp,
        ):
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_name = line[len("event: ") :].strip()
                    events_seen.append((event_name, {}))
                elif line.startswith("data: ") and events_seen:
                    events_seen[-1] = (
                        events_seen[-1][0],
                        json.loads(line[len("data: ") :]),
                    )

    names = [name for name, _ in events_seen]
    assert names[0] == "stream_start"
    assert "error" in names
    assert names[-1] == "stream_end"

    error_data = next(data for name, data in events_seen if name == "error")
    assert error_data["reason"] == "timeout"
    assert error_data["recoverable"] is True

    end_data = events_seen[-1][1]
    assert end_data["final_report_source"] == "error"
