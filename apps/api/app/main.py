import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.routers import research as research_router
from app.services.prompt_registry import registry
from app.stores.memory_store import lifespan_stores

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(levelname)-8s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    registry.reload()   # fail fast: raises RuntimeError if prompts/ is missing
    async with lifespan_stores():
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
