from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_registries(tmp_path: Path):
    from langchain_core.tools import tool as tool_deco

    from app.models.registry import ModelRegistry
    from app.tools.registry import ToolRegistry

    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(
        dedent("""
        fast:
          provider: openai
          model: gpt-4o-mini
        main:
          provider: openai
          model: gpt-4o
    """)
    )
    model_reg = ModelRegistry(yaml_path=yaml_path, env={})
    model_reg.build = MagicMock(return_value=MagicMock(name="fake_llm"))  # type: ignore[method-assign]

    tool_reg = ToolRegistry()

    @tool_reg.register("web_search")
    @tool_deco
    def web_search(q: str) -> str:
        """stub"""
        return q

    prompt_reg = MagicMock()
    prompt_reg.get.side_effect = lambda name, version=None: f"{name}-prompt"

    return model_reg, tool_reg, prompt_reg


@pytest.mark.unit
def test_build_deep_research_composes_subagents(fake_registries) -> None:
    model_reg, tool_reg, prompt_reg = fake_registries
    spec = next(
        s
        for s in __import__("app.agents.specs", fromlist=["REGISTERED_SPECS"]).REGISTERED_SPECS
        if s.name == "deep-research"
    )

    from app.agents.builders.deep_research import build_deep_research_agent

    with patch("app.agents.builders.deep_research.create_deep_agent") as mock_create:
        mock_create.return_value = MagicMock(name="deep_agent")
        build_deep_research_agent(
            spec=spec,
            model_registry=model_reg,
            tool_registry=tool_reg,
            prompt_registry=prompt_reg,
            checkpointer=None,
            store=None,
        )

    _args, kwargs = mock_create.call_args
    assert kwargs["system_prompt"] == "main-prompt"
    assert [t.name for t in kwargs["tools"]] == ["web_search"]
    # SubAgent from deepagents is a TypedDict (plain dict); access by key not attribute
    sub_names = {s["name"] for s in kwargs["subagents"]}
    assert sub_names == {"researcher", "critic"}
