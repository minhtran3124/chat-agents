import json
import logging
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000


@router.post("")
async def research(payload: ResearchRequest) -> EventSourceResponse:
    agent = build_research_agent()
    thread_id = payload.thread_id or "default-user"
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    async def generator() -> AsyncGenerator[dict, None]:
        logger.info(
            "[RESEARCH] Agent invoked thread_id=%s question=%r",
            thread_id, payload.question[:120],
        )
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

            try:
                final_state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
                usage = final_state.values.get("usage", {}) if final_state else {}
            except Exception:
                usage = {}

            report_chars = sum(len(p) for p in final_report_parts)
            logger.info(
                "[RESEARCH] Stream complete thread_id=%s report_chars=%d usage=%s",
                thread_id, report_chars, usage,
            )
            yield events.stream_end(
                final_report="".join(final_report_parts),
                usage=usage,
            )
        except Exception as e:
            logger.error(
                "[RESEARCH] Stream error — agent run abandoned:\n%s",
                traceback.format_exc(),
            )
            yield events.error(str(e), recoverable=False)

    return EventSourceResponse(generator())
