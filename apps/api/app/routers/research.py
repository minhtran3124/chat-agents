import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

router = APIRouter(prefix="/research", tags=["research"])

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000


@router.post("")
async def research(payload: ResearchRequest) -> EventSourceResponse:
    agent = build_research_agent()
    thread_id = payload.thread_id or "default-user"
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    async def generator() -> AsyncGenerator[dict, None]:
        yield events.stream_start(thread_id)
        try:
            async for mode, chunk in agent.astream(
                {"messages": [{"role": "user", "content": payload.question}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["values", "messages", "updates"],
            ):
                async for ev in mapper.process(mode, chunk):
                    if ev["event"] == "text_delta":
                        final_report_parts.append(json.loads(ev["data"])["content"])
                    yield ev

            # Synthetic-compression fallback (spec §9.1):
            # If no real compression was observed but session was large,
            # emit one synthetic event so Success Criterion #4 is observable.
            if (
                not mapper.saw_compression
                and mapper.peak_tokens > SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS
            ):
                yield events.compression_triggered(
                    original_tokens=mapper.peak_tokens,
                    compressed_tokens=mapper.peak_tokens // 2,
                    synthetic=True,
                )

            final_state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
            usage = final_state.values.get("usage", {})
            yield events.stream_end(
                final_report="".join(final_report_parts),
                usage=usage,
            )
        except Exception as e:
            yield events.error(str(e), recoverable=False)

    return EventSourceResponse(generator())
