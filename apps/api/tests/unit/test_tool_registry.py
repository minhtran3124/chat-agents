import pytest
from langchain_core.tools import tool

from app.tools.registry import ToolRegistry


@pytest.mark.unit
def test_register_and_get() -> None:
    reg = ToolRegistry()

    @reg.register("echo")
    @tool
    def echo(text: str) -> str:
        """Echo back the input."""
        return text

    retrieved = reg.get("echo")
    assert retrieved.name == "echo"


@pytest.mark.unit
def test_duplicate_registration_raises() -> None:
    reg = ToolRegistry()

    @reg.register("twice")
    @tool
    def first(text: str) -> str:
        """first"""
        return text

    with pytest.raises(RuntimeError, match="already registered"):
        @reg.register("twice")
        @tool
        def second(text: str) -> str:
            """second"""
            return text


@pytest.mark.unit
def test_unknown_tool_raises() -> None:
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="Unknown tool 'missing'"):
        reg.get("missing")


@pytest.mark.unit
def test_get_many_preserves_order() -> None:
    reg = ToolRegistry()

    @reg.register("a")
    @tool
    def a(x: str) -> str:
        """a"""
        return x

    @reg.register("b")
    @tool
    def b(x: str) -> str:
        """b"""
        return x

    names = [t.name for t in reg.get_many(["b", "a"])]
    assert names == ["b", "a"]


@pytest.mark.unit
def test_singleton_registers_all_initial_tools() -> None:
    import app.tools  # noqa: F401 — triggers registration
    from app.tools.registry import registry
    assert {"web_search", "fetch_url", "repo_search"}.issubset(set(registry.names()))
