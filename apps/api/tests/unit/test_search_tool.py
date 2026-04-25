from importlib import reload
from unittest.mock import MagicMock, patch


def _reload_with_mocks(fake_tavily: MagicMock, fake_backend: MagicMock | None = None):
    """Reload search_tool with TavilyClient and (optionally) StateBackend patched.

    StateBackend is patched at its source module so the `from deepagents.backends.state
    import StateBackend` line picks up the mock during reload.
    """
    sb_target = "deepagents.backends.state.StateBackend"
    sb_patch = (
        patch(sb_target, return_value=fake_backend)
        if fake_backend is not None
        else patch(sb_target)
    )
    return patch("tavily.TavilyClient", return_value=fake_tavily), sb_patch


def test_internet_search_calls_tavily_with_kwargs(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    tavily_patch, sb_patch = _reload_with_mocks(fake_client)
    with tavily_patch, sb_patch:
        from app.services import search_tool

        reload(search_tool)
        result = search_tool.internet_search.invoke({"query": "agentic AI"})

    fake_client.search.assert_called_once_with(
        query="agentic AI",
        max_results=5,
        topic="general",
    )
    assert result == {"results": []}
    assert "offloaded" not in result


def test_internet_search_returns_inline_when_under_threshold(monkeypatch):
    """Small Tavily payload → response unchanged, no VFS write."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    payload = {
        "query": "agentic AI",
        "answer": "It's a thing.",
        "results": [
            {
                "title": "Intro",
                "url": "https://example.com/a",
                "content": "short body",
                "score": 0.9,
            }
        ],
    }
    fake_client = MagicMock()
    fake_client.search.return_value = payload
    fake_backend = MagicMock()

    tavily_patch, sb_patch = _reload_with_mocks(fake_client, fake_backend)
    with tavily_patch, sb_patch:
        from app.services import search_tool

        reload(search_tool)
        result = search_tool.internet_search.invoke({"query": "agentic AI"})

    assert result == payload
    fake_backend.write.assert_not_called()


def test_internet_search_offloads_when_over_threshold(monkeypatch):
    """Large Tavily payload → results carry snippet+path, full content goes to VFS."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import settings as live_settings

    monkeypatch.setattr(live_settings, "VFS_OFFLOAD_THRESHOLD_TOKENS", 100)

    big_content = "lorem ipsum dolor sit amet " * 100
    fake_client = MagicMock()
    fake_client.search.return_value = {
        "query": "deep research",
        "answer": "summary",
        "results": [
            {
                "title": "A",
                "url": "https://example.com/a",
                "content": big_content,
                "score": 0.9,
            },
            {
                "title": "B",
                "url": "https://other.org/b",
                "content": big_content,
                "score": 0.8,
            },
        ],
    }
    fake_backend = MagicMock()
    fake_backend.write.return_value = MagicMock(error=None, path="/written")

    tavily_patch, sb_patch = _reload_with_mocks(fake_client, fake_backend)
    with tavily_patch, sb_patch:
        from app.services import search_tool

        reload(search_tool)
        result = search_tool.internet_search.invoke({"query": "deep research"})

    assert result["offloaded"] is True
    assert result["query"] == "deep research"
    assert result["answer"] == "summary"
    assert len(result["results"]) == 2
    for r in result["results"]:
        assert "snippet" in r
        assert len(r["snippet"]) <= 600
        assert r["snippet"] != big_content
        assert "content" not in r
        assert r["full_content_path"].startswith("/research/searches/deep-research/")
        assert r["full_content_path"].endswith(".md")
    assert fake_backend.write.call_count == 2
    written_paths = [call.args[0] for call in fake_backend.write.call_args_list]
    assert written_paths[0].endswith("01-example-com.md")
    assert written_paths[1].endswith("02-other-org.md")


def test_internet_search_handles_write_collision(monkeypatch):
    """If StateBackend.write returns error, tool retries with a uuid-suffixed path."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import settings as live_settings

    monkeypatch.setattr(live_settings, "VFS_OFFLOAD_THRESHOLD_TOKENS", 10)

    fake_client = MagicMock()
    fake_client.search.return_value = {
        "query": "q",
        "results": [
            {
                "title": "T",
                "url": "https://x.com/p",
                "content": "long content " * 50,
                "score": 0.5,
            }
        ],
    }
    fake_backend = MagicMock()
    fake_backend.write.side_effect = [
        MagicMock(error="exists", path=None),
        MagicMock(error=None, path="/written"),
    ]

    tavily_patch, sb_patch = _reload_with_mocks(fake_client, fake_backend)
    with tavily_patch, sb_patch:
        from app.services import search_tool

        reload(search_tool)
        result = search_tool.internet_search.invoke({"query": "q"})

    assert fake_backend.write.call_count == 2
    final_path = result["results"][0]["full_content_path"]
    assert final_path != "/research/searches/q/01-x-com.md"
    assert final_path.startswith("/research/searches/q/01-x-com-")
    assert final_path.endswith(".md")
