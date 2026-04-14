from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_web_search_returns_tavily_results() -> None:
    fake = {"results": [{"title": "a", "url": "http://a"}], "query": "q"}
    with patch("app.tools.web_search._tavily") as mock_client:
        mock_client.search.return_value = fake
        from app.tools import web_search as mod
        result = mod.web_search.invoke({"query": "q"})
    assert result == fake


@pytest.mark.unit
def test_web_search_wraps_exceptions() -> None:
    with patch("app.tools.web_search._tavily") as mock_client:
        mock_client.search.side_effect = RuntimeError("boom")
        from app.tools import web_search as mod
        result = mod.web_search.invoke({"query": "q"})
    assert "error" in result
    assert "boom" in result["error"]
