import pytest


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_checkpointer(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(db_path))

    from importlib import reload

    from app.config import settings as cfg

    reload(cfg)
    from app.stores import memory_store

    reload(memory_store)

    # Before lifespan: checkpointer not available
    with pytest.raises(RuntimeError, match="not initialized"):
        memory_store.get_checkpointer()

    # During lifespan
    async with memory_store.lifespan_stores():
        cp = memory_store.get_checkpointer()
        assert cp is not None
        assert db_path.exists() or db_path.parent.exists()

    # After lifespan: cleared
    with pytest.raises(RuntimeError, match="not initialized"):
        memory_store.get_checkpointer()


def test_get_store_returns_in_memory_store():
    from langgraph.store.memory import InMemoryStore

    from app.stores.memory_store import get_store

    assert isinstance(get_store(), InMemoryStore)
