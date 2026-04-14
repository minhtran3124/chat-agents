import pytest

from app.tools.repo_search import repo_search


@pytest.mark.unit
async def test_repo_search_finds_known_symbol() -> None:
    result = await repo_search.ainvoke({"pattern": "create_deep_agent"})
    assert "matches" in result
    assert any("agent_factory.py" in line for line in result["matches"])


@pytest.mark.unit
async def test_repo_search_empty_on_garbage() -> None:
    result = await repo_search.ainvoke({"pattern": "zzz_this_should_not_exist_12345"})
    assert result.get("matches") == [] or result.get("note") == "no matches"
