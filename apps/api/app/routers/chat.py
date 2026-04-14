from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.routers._runner import run_graph
from app.schemas.chat import ChatRequest
from app.services.prompt_registry import registry as prompt_registry

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(payload: ChatRequest, request: Request) -> EventSourceResponse:
    overrides = payload.prompt_versions or {}
    versions_used = prompt_registry.resolve_versions(overrides)
    thread_id = payload.thread_id or "default-user"

    graph = request.app.state.supervisor_graph
    return EventSourceResponse(
        run_graph(
            graph=graph,
            question=payload.question,
            thread_id=thread_id,
            versions_used=versions_used,
            force_intent=None,
        )
    )
