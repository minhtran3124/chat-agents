from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a fresh `request_id` to structlog contextvars on every request.

    Values bound here propagate through `await` chains and into tasks
    spawned from the same context (structlog.contextvars -> ContextVar).
    """

    async def dispatch(self, request: Request, call_next: "RequestResponseEndpoint") -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=str(uuid4()))
        return await call_next(request)
