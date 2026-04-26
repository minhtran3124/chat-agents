from importlib import reload
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


def _set_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


def _load(fake_tavily: MagicMock):
    """Reload search_tool with TavilyClient patched and return the module."""
    with patch("tavily.TavilyClient", return_value=fake_tavily):
        from app.services import search_tool

        reload(search_tool)
    return search_tool


def _search_call(idx: int) -> AIMessage:
    """Build an AIMessage whose tool_calls record one prior internet_search."""
    return AIMessage(
        content="",
        tool_calls=[{"name": "internet_search", "id": f"call_{idx}", "args": {"query": "x"}}],
    )


def test_internet_search_calls_tavily_with_kwargs(monkeypatch):
    _set_env(monkeypatch)
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    search_tool = _load(fake_client)

    state = {"messages": [_search_call(1)]}  # this call is the in-flight one
    result = search_tool.internet_search.invoke({"query": "agentic AI", "state": state})

    fake_client.search.assert_called_once_with(
        query="agentic AI",
        max_results=5,
        topic="general",
    )
    assert result == {"results": []}


def test_internet_search_allows_up_to_four_searches(monkeypatch):
    """A state showing 4 prior internet_search tool_calls (this one being the 4th)
    should still call Tavily — count == max is allowed."""
    _set_env(monkeypatch)
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    search_tool = _load(fake_client)

    state = {"messages": [_search_call(i) for i in range(1, 5)]}  # 4 calls including current
    result = search_tool.internet_search.invoke({"query": "x", "state": state})

    assert "error" not in result
    fake_client.search.assert_called_once()


def test_internet_search_refuses_fifth_call(monkeypatch):
    """A state showing 5 prior internet_search tool_calls means the agent already
    used its 4-search quota; the tool must refuse and not hit Tavily."""
    _set_env(monkeypatch)
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    search_tool = _load(fake_client)

    state = {"messages": [_search_call(i) for i in range(1, 6)]}  # 5 internet_search tool_calls
    result = search_tool.internet_search.invoke({"query": "x", "state": state})

    assert result["error"] == "search_budget_exhausted"
    assert "already made 4" in result["message"]
    fake_client.search.assert_not_called()


def test_internet_search_ignores_other_tool_calls_in_count(monkeypatch):
    """Tool calls of other names (think_tool, write_todos, …) must NOT count
    toward the search quota — only internet_search calls do."""
    _set_env(monkeypatch)
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    search_tool = _load(fake_client)

    other_calls = [
        AIMessage(
            content="",
            tool_calls=[{"name": "think_tool", "id": f"t{i}", "args": {"reflection": "z"}}],
        )
        for i in range(10)
    ]
    state = {"messages": [*other_calls, _search_call(1)]}
    result = search_tool.internet_search.invoke({"query": "x", "state": state})

    assert "error" not in result
    fake_client.search.assert_called_once()


def test_internet_search_handles_missing_messages_state(monkeypatch):
    """An empty/absent state must not crash the tool — fall through to Tavily."""
    _set_env(monkeypatch)
    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    search_tool = _load(fake_client)

    result = search_tool.internet_search.invoke({"query": "x", "state": {}})

    assert "error" not in result
    fake_client.search.assert_called_once()
