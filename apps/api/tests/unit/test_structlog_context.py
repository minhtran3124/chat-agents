import asyncio

import pytest
import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.observability.middleware import RequestContextMiddleware


@pytest.mark.unit
def test_request_id_bound_in_middleware():
    captured: dict[str, str] = {}

    async def endpoint(request: Request) -> JSONResponse:
        ctx = structlog.contextvars.get_contextvars()
        captured["request_id"] = ctx.get("request_id", "")
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/test", endpoint)])
    app.add_middleware(RequestContextMiddleware)

    client = TestClient(app)
    res1 = client.get("/test")
    assert res1.status_code == 200
    rid1 = captured["request_id"]
    assert len(rid1) == 36  # uuid4 str length

    res2 = client.get("/test")
    assert res2.status_code == 200
    rid2 = captured["request_id"]
    assert len(rid2) == 36
    assert rid1 != rid2  # fresh per request


@pytest.mark.unit
async def test_context_survives_create_task():
    """Values bound before create_task are visible inside the task."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="parent-req")

    captured: dict[str, str] = {}

    async def child() -> None:
        ctx = structlog.contextvars.get_contextvars()
        captured["request_id"] = ctx.get("request_id", "")

    await asyncio.create_task(child())
    assert captured["request_id"] == "parent-req"

    structlog.contextvars.clear_contextvars()
