from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_build_research_agent_wires_subagents_and_store(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from importlib import reload

    from app.config import settings as cfg

    reload(cfg)

    # Reload agent_factory BEFORE patching so the module's imports run cleanly,
    # then patch the names in the freshly-loaded module's namespace.
    from app.services import agent_factory

    reload(agent_factory)

    fake_agent = MagicMock()
    with (
        patch("app.services.agent_factory.create_deep_agent", return_value=fake_agent) as mock_cda,
        patch("app.services.agent_factory.get_llm", return_value=MagicMock()),
        patch("app.services.agent_factory.get_fast_llm", return_value=MagicMock()),
    ):
        from app.stores.memory_store import lifespan_stores

        async with lifespan_stores():
            agent = agent_factory.build_research_agent(
                main_prompt="You are a test assistant.",
                researcher_prompt="Research this.",
                critic_prompt="Critique this.",
            )

    kwargs = mock_cda.call_args.kwargs
    assert agent is fake_agent
    assert "tools" in kwargs
    assert kwargs["system_prompt"]
    assert len(kwargs["subagents"]) == 2
    # SubAgent is a dict subclass — access fields via dict syntax
    names = {sa["name"] for sa in kwargs["subagents"]}
    assert names == {"researcher", "critic"}
    assert kwargs["store"] is not None
    assert kwargs["checkpointer"] is not None
