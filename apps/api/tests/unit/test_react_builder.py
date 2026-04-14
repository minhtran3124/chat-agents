from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from app.agents.specs import AgentSpec


@pytest.fixture
def fake_registries(tmp_path: Path) -> tuple[MagicMock, MagicMock, MagicMock]:
    from app.models.registry import ModelRegistry
    from app.tools.registry import ToolRegistry

    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        fast:
          provider: openai
          model: gpt-4o-mini
          temperature: 0.3
          streaming: true
        main:
          provider: openai
          model: gpt-4o
          temperature: 0.7
          streaming: true
    """))
    model_reg = ModelRegistry(yaml_path=yaml_path, env={})
    # Mock build() so we do not initialize a real LLM client.
    model_reg.build = MagicMock(return_value=MagicMock(name="fake_llm"))  # type: ignore[method-assign]

    tool_reg = ToolRegistry()

    prompt_reg = MagicMock()
    prompt_reg.get.return_value = "You are a test agent."

    return model_reg, tool_reg, prompt_reg


@pytest.mark.unit
def test_build_react_agent_no_tools(fake_registries) -> None:
    model_reg, tool_reg, prompt_reg = fake_registries
    spec = AgentSpec(name="chat", model_role="fast", tools=[], prompt_name="chat")

    from app.agents.builders.react import build_react_agent

    with patch("app.agents.builders.react.create_react_agent") as mock_create:
        mock_create.return_value = "compiled-graph"
        result = build_react_agent(
            spec=spec,
            model_registry=model_reg,
            tool_registry=tool_reg,
            prompt_registry=prompt_reg,
        )

    assert result == "compiled-graph"
    _args, kwargs = mock_create.call_args
    assert kwargs["tools"] == []
    assert kwargs["prompt"] == "You are a test agent."


@pytest.mark.unit
def test_build_react_agent_with_tools(fake_registries) -> None:
    from langchain_core.tools import tool as tool_deco

    model_reg, tool_reg, prompt_reg = fake_registries

    @tool_reg.register("web_search")
    @tool_deco
    def web_search(q: str) -> str:
        """stub"""
        return q

    @tool_reg.register("fetch_url")
    @tool_deco
    def fetch_url(u: str) -> str:
        """stub"""
        return u

    spec = AgentSpec(
        name="research",
        model_role="main",
        tools=["web_search", "fetch_url"],
        prompt_name="research",
    )

    from app.agents.builders.react import build_react_agent

    with patch("app.agents.builders.react.create_react_agent") as mock_create:
        mock_create.return_value = "compiled-graph"
        build_react_agent(
            spec=spec,
            model_registry=model_reg,
            tool_registry=tool_reg,
            prompt_registry=prompt_reg,
        )

    _, kwargs = mock_create.call_args
    assert [t.name for t in kwargs["tools"]] == ["web_search", "fetch_url"]
