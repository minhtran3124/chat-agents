from unittest.mock import MagicMock, patch


def test_internet_search_calls_tavily_with_kwargs(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    # Patch the source module so that `from tavily import TavilyClient` during reload
    # gets the mock, preventing real API calls during module-level initialization.
    with patch("tavily.TavilyClient", return_value=fake_client):
        from importlib import reload

        from app.services import search_tool

        reload(search_tool)

        result = search_tool.internet_search.invoke({"query": "agentic AI"})

    # Current internet_search hardcodes max_results=5 and topic="general";
    # if this tool gains a max_results param in the future, reinstate it here.
    fake_client.search.assert_called_once_with(
        query="agentic AI",
        max_results=5,
        topic="general",
    )
    assert result == {"results": []}
