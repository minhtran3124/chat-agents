import pytest

from app.tools.repo_search import repo_search


@pytest.mark.unit
async def test_repo_search_finds_known_symbol() -> None:
    result = await repo_search.ainvoke({"pattern": "create_deep_agent"})
    assert "matches" in result
    assert any("agent_factory.py" in line for line in result["matches"])


@pytest.mark.unit
async def test_repo_search_empty_on_garbage() -> None:
    # Construct pattern at runtime so the literal never appears in source
    # (git grep would find the pattern inside this file if it were a literal).
    pattern = "ZZZNOMATCH_" + "xk9q2v8m"
    result = await repo_search.ainvoke({"pattern": pattern})
    assert result.get("matches") == [] or result.get("note") == "no matches"
