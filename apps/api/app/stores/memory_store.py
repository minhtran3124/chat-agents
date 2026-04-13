from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore

from app.config.settings import settings

_store = InMemoryStore()
_checkpointer: AsyncSqliteSaver | None = None


@asynccontextmanager
async def lifespan_stores() -> AsyncIterator[None]:
    global _checkpointer
    Path(settings.CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(settings.CHECKPOINT_DB_PATH) as cp:
        _checkpointer = cp
        try:
            yield
        finally:
            _checkpointer = None


def get_store() -> InMemoryStore:
    return _store


def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized — app lifespan not active")
    return _checkpointer
