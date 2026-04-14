import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.tools as _tools  # noqa: F401  — triggers @register_tool decorators at startup
from app.agents.supervisor_graph import (
    build_deep_research_only_graph,
    build_supervisor_graph,
)
from app.config.settings import settings
from app.models.registry import ModelRegistry
from app.routers import chat as chat_router
from app.routers import research as research_router
from app.services.prompt_registry import registry as prompt_registry
from app.stores.memory_store import (
    get_checkpointer,
    get_store,
    lifespan_stores,
)
from app.tools.registry import registry as tool_registry

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(levelname)-8s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    prompt_registry.reload()

    model_registry = ModelRegistry(
        yaml_path=Path(__file__).parents[1] / "models.yaml",
        env=os.environ,
    )
    app.state.model_registry = model_registry
    app.state.tool_registry = tool_registry

    async with lifespan_stores():
        checkpointer = get_checkpointer()
        store = get_store()

        app.state.supervisor_graph = build_supervisor_graph(
            model_registry=model_registry,
            tool_registry=tool_registry,
            prompt_registry=prompt_registry,
            checkpointer=checkpointer,
            store=store,
        )
        app.state.deep_research_only_graph = build_deep_research_only_graph(
            model_registry=model_registry,
            tool_registry=tool_registry,
            prompt_registry=prompt_registry,
            checkpointer=checkpointer,
            store=store,
        )
        yield


app = FastAPI(title="Deep Agents Research API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(research_router.router)
app.include_router(chat_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
