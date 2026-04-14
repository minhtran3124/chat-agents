import json
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.integration
async def test_runner_emits_expected_event_sequence() -> None:
    # Fake graph: yields one AIMessageChunk via messages mode, then ends.
    from langchain_core.messages import AIMessageChunk

    from app.routers._runner import run_graph

    async def fake_astream(*args, **kwargs):
        # Values snapshot (empty) then one AI chunk then final values snapshot
        yield ("values", {"messages": [], "files": {}})
        yield ("messages", (AIMessageChunk(content="Hello"), {}))

    fake_graph = MagicMock()
    fake_graph.astream = fake_astream
    fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    events = []
    async for ev in run_graph(
        graph=fake_graph,
        question="hi",
        thread_id="t1",
        versions_used={"classifier": "v1"},
        force_intent="chat",  # short-circuit the classifier path
    ):
        events.append(ev)

    names = [e["event"] for e in events]
    assert names[0] == "stream_start"
    assert "intent_classified" in names
    assert names[-1] == "stream_end"

    ic = next(e for e in events if e["event"] == "intent_classified")
    data = json.loads(ic["data"])
    assert data["intent"] == "chat"
    assert data["fallback_used"] is False
