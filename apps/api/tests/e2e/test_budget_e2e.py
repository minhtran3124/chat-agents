import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_over_budget_request_yields_budget_exceeded_then_stream_end(monkeypatch):
    """Mocked agent crosses MAX_TOKENS_PER_RUN — expect budget_exceeded → stream_end(error)."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    import app.config.settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "MAX_TOKENS_PER_RUN", 1_000)

    async def fake_astream(*args, **kwargs):
        # Each messages chunk reports 600 tokens — two chunks cross 1000.
        msg1 = SimpleNamespace(usage_metadata={"input_tokens": 400, "output_tokens": 200})
        yield ("messages", (msg1, {}))
        msg2 = SimpleNamespace(usage_metadata={"input_tokens": 400, "output_tokens": 200})
        yield ("messages", (msg2, {}))
        # This chunk should never be processed — generator should have returned.
        yield ("values", {"messages": [], "files": {}})

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    events_seen: list[tuple[str, dict]] = []
    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app

        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream("POST", "/research", json={"question": "anything"}) as resp,
        ):
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events_seen.append((line[len("event: ") :].strip(), {}))
                elif line.startswith("data: ") and events_seen:
                    events_seen[-1] = (
                        events_seen[-1][0],
                        json.loads(line[len("data: ") :]),
                    )

    names = [name for name, _ in events_seen]
    assert names[0] == "stream_start"
    assert "budget_exceeded" in names
    assert names[-1] == "stream_end"

    budget_data = next(d for n, d in events_seen if n == "budget_exceeded")
    assert budget_data["limit"] == 1_000
    assert budget_data["tokens_used"] >= 1_000

    end_data = events_seen[-1][1]
    assert end_data["final_report_source"] == "error"
