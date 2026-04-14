import pytest

from app.tools.repo_search import repo_search


@pytest.mark.unit
async def test_repo_search_finds_known_symbol() -> None:
    result = await repo_search.ainvoke({"pattern": "create_deep_agent"})
    assert "matches" in result
    assert any("deep_research.py" in line for line in result["matches"])


@pytest.mark.unit
async def test_repo_search_empty_on_garbage() -> None:
    # Split literal so git grep cannot match the full pattern in this source file.
    pattern = "zzz_this_should_not" + "_exist_67890"
    result = await repo_search.ainvoke({"pattern": pattern})
    assert result.get("matches") == [] or result.get("note") == "no matches"
