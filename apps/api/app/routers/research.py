# apps/api/app/routers/research.py
import json
import logging
import traceback
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.services.prompt_registry import registry
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000

# Fallback threshold: when the main agent streams fewer assistant-text
# characters than this, we treat the run as a compliance failure (the model
# probably saved the final report to the virtual FS instead of replying with
# it).  If `draft.md` exists in state, we surface its content as the final
# report and mark the source as "file" so the UI can flag it.
MIN_STREAM_REPORT_CHARS = 200
FALLBACK_DRAFT_FILENAME = "draft.md"


@router.post("")
async def research(payload: ResearchRequest) -> EventSourceResponse:
    overrides = payload.prompt_versions or {}
    versions_used = registry.resolve_versions(overrides)
    thread_id = payload.thread_id or "default-user"

    try:
        agent = build_research_agent(
            main_prompt=registry.get("main", version=versions_used["main"]),
            researcher_prompt=registry.get("researcher", version=versions_used["researcher"]),
            critic_prompt=registry.get("critic", version=versions_used["critic"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    async def generator() -> AsyncGenerator[dict, None]:
        logger.info(
            "[RESEARCH] Agent invoked thread_id=%s prompt_versions=%s question=%r",
            thread_id, versions_used, payload.question[:120],
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
                files = final_state.values.get("files", {}) if final_state else {}
            except Exception:
                usage = {}
                files = {}

            streamed_report = "".join(final_report_parts)
            final_report = streamed_report
            final_report_source: str = "stream"

            draft = files.get(FALLBACK_DRAFT_FILENAME)
            if (
                len(streamed_report) < MIN_STREAM_REPORT_CHARS
                and isinstance(draft, str)
                and len(draft) >= MIN_STREAM_REPORT_CHARS
            ):
                logger.warning(
                    "[RESEARCH] Final-report fallback triggered — streamed only %d "
                    "chars; using %s (%d chars). Prompt compliance issue worth "
                    "investigating (main prompt version=%s).",
                    len(streamed_report), FALLBACK_DRAFT_FILENAME, len(draft),
                    versions_used.get("main"),
                )
                final_report = draft
                final_report_source = "file"

            logger.info(
                "[RESEARCH] Stream complete thread_id=%s report_chars=%d source=%s "
                "nodes_seen=%s prompt_versions=%s usage=%s",
                thread_id, len(final_report), final_report_source,
                sorted(mapper.seen_nodes), versions_used, usage,
            )
            yield events.stream_end(
                final_report=final_report,
                usage=usage,
                versions_used=versions_used,
                final_report_source=final_report_source,
            )
        except Exception as e:
            logger.error(
                "[RESEARCH] Stream error — agent run abandoned:\n%s",
                traceback.format_exc(),
            )
            yield events.error(str(e), recoverable=False)

    return EventSourceResponse(generator())
