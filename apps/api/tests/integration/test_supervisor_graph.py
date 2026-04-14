from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def registries(tmp_path: Path):
    from langchain_core.tools import tool as tool_deco

    from app.models.registry import ModelRegistry
    from app.tools.registry import ToolRegistry

    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(
        dedent("""
        classifier:
          provider: openai
          model: gpt-4o-mini
          streaming: false
        fast:
          provider: openai
          model: gpt-4o-mini
        main:
          provider: openai
          model: gpt-4o
    """)
    )
    model_reg = ModelRegistry(yaml_path=yaml_path, env={})
    model_reg.build = MagicMock(return_value=MagicMock(name="llm"))  # type: ignore[method-assign]

    tool_reg = ToolRegistry()
    for name in ("web_search", "fetch_url", "repo_search"):

        @tool_reg.register(name)
        @tool_deco
        def _stub(q: str, _n=name) -> str:
            """stub"""
            return f"{_n}:{q}"

    prompt_reg = MagicMock()
    prompt_reg.get.side_effect = lambda name, version=None: f"{name}-prompt"

    return model_reg, tool_reg, prompt_reg


@pytest.mark.integration
def test_supervisor_graph_compiles_with_all_six_specialists(registries) -> None:
    model_reg, tool_reg, prompt_reg = registries
    from app.agents.supervisor_graph import build_supervisor_graph

    with patch("app.agents.builders.deep_research.create_deep_agent") as mock_deep:
        mock_deep.return_value = MagicMock(name="deep_agent_subgraph")
        with patch("app.agents.builders.react.create_react_agent") as mock_react:
            mock_react.return_value = MagicMock(name="react_agent")
            graph = build_supervisor_graph(
                model_registry=model_reg,
                tool_registry=tool_reg,
                prompt_registry=prompt_reg,
                checkpointer=None,
                store=None,
            )

    # All six specialist node names must be registered on the graph.
    node_names = set(graph.nodes.keys())
    assert {
        "classifier",
        "chat",
        "research",
        "deep-research",
        "summarize",
        "code",
        "planner",
    }.issubset(node_names)
