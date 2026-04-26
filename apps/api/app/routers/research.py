# apps/api/app/routers/research.py
import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.config.settings import settings
from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.services.prompt_registry import registry
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper
from app.streaming.events import FinalReportSource

log = structlog.get_logger(__name__)

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000

# Fallback threshold: when the main agent streams fewer assistant-text
# characters than this, we treat the run as a compliance failure (the model
# probably saved the final report to the virtual FS instead of replying with
# it).  If `draft.md` exists in state, we surface its content as the final
# report and mark the source as "file" so the UI can flag it.
MIN_STREAM_REPORT_CHARS = 200
FALLBACK_DRAFT_FILENAME = "draft.md"


def _extract_token_count(msg: Any) -> int:
    """Read usage_metadata from an AIMessageChunk. Returns 0 if absent.

    Cached input is billed at ~50% of the regular rate by OpenAI/Anthropic,
    so the budget guard subtracts half of any cache_read tokens to reflect
    the real spend. Without this, runs over-report by 30-50% on cache-heavy
    flows and trip the budget cap prematurely.

    LangChain populates usage_metadata on the final chunk of each message
    turn — the counter lags by at most one turn, acceptable for a budget
    guard that only needs to catch overruns.
    """
    meta = getattr(msg, "usage_metadata", None)
    if not meta:
        return 0
    input_tok = meta.get("input_tokens", 0)
    output_tok = meta.get("output_tokens", 0)
    cache_read = (meta.get("input_token_details") or {}).get("cache_read", 0)
    return input_tok - cache_read // 2 + output_tok


router = APIRouter(prefix="/research", tags=["research"])


@router.post("")
async def research(payload: ResearchRequest) -> EventSourceResponse:
    overrides = payload.prompt_versions or {}
    versions_used = registry.resolve_versions(overrides)
    thread_id = payload.thread_id or "default-user"

    structlog.contextvars.bind_contextvars(
        thread_id=thread_id,
        prompt_versions=versions_used,
    )

    try:
        agent = build_research_agent(
            main_prompt=registry.get("main", version=versions_used["main"]),
            researcher_prompt=registry.get("researcher", version=versions_used["researcher"]),
            critic_prompt=registry.get("critic", version=versions_used["critic"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    mapper = ChunkMapper()

    async def generator() -> AsyncGenerator[dict, None]:
        request_id = structlog.contextvars.get_contextvars().get("request_id", "")
        log.info(
            "research.invoked",
            question_preview=payload.question[:120],
        )
        yield events.stream_start(thread_id)

        # Local type is wider than ErrorReason because the budget sentinel
        # "budget_exceeded" drives the error `finally` path but is NOT a
        # valid argument to events.error().
        error_reason: str | None = None
        final_report_parts: list[str] = []
        usage: dict = {}
        files: dict = {}

        try:
            cumulative_tokens = 0
            async with asyncio.timeout(settings.RESEARCH_TIMEOUT_S):
                async for _ns, mode, chunk in agent.astream(
                    {"messages": [{"role": "user", "content": payload.question}]},
                    config={
                        "configurable": {"thread_id": thread_id},
                        "metadata": {
                            "request_id": request_id,
                            "prompt_versions": versions_used,
                        },
                        "tags": [settings.LLM_PROVIDER],
                    },
                    stream_mode=["values", "messages", "updates"],
                    subgraphs=True,
                ):
                    if mode == "messages":
                        # chunk is (AIMessageChunk, metadata_dict) in messages mode.
                        # The guard runs BEFORE mapper.process so no further
                        # tokens are billed — usage_metadata arrives on the final
                        # chunk of a turn, so any text_delta for that same chunk
                        # is dropped. Intentional trade-off: abort at overage
                        # rather than absorb one more turn's worth of tokens.
                        cumulative_tokens += _extract_token_count(chunk[0])
                        if cumulative_tokens > settings.MAX_TOKENS_PER_RUN:
                            log.warning(
                                "research.budget_exceeded",
                                tokens_used=cumulative_tokens,
                                limit=settings.MAX_TOKENS_PER_RUN,
                            )
                            error_reason = "budget_exceeded"
                            yield events.budget_exceeded(
                                tokens_used=cumulative_tokens,
                                limit=settings.MAX_TOKENS_PER_RUN,
                            )
                            return
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

        except TimeoutError:
            log.warning(
                "research.timeout",
                timeout_s=settings.RESEARCH_TIMEOUT_S,
            )
            error_reason = "timeout"
            yield events.error("timeout")
        except Exception as exc:
            if type(exc).__name__ == "RateLimitError":
                log.warning("research.rate_limited", error=str(exc))
                error_reason = "rate_limited"
                yield events.error("rate_limited")
            else:
                log.exception("research.internal_error")
                error_reason = "internal"
                yield events.error("internal")
        finally:
            if error_reason is not None:
                yield events.stream_end(
                    final_report="",
                    usage={},
                    versions_used=versions_used,
                    final_report_source="error",
                )
            else:
                streamed_report = "".join(final_report_parts)
                final_report = streamed_report
                final_report_source: FinalReportSource = "stream"

                draft = files.get(FALLBACK_DRAFT_FILENAME)
                if (
                    len(streamed_report) < MIN_STREAM_REPORT_CHARS
                    and isinstance(draft, str)
                    and len(draft) >= MIN_STREAM_REPORT_CHARS
                ):
                    log.warning(
                        "research.fallback_to_draft",
                        streamed_chars=len(streamed_report),
                        draft_filename=FALLBACK_DRAFT_FILENAME,
                        draft_chars=len(draft),
                        main_prompt_version=versions_used.get("main"),
                    )
                    final_report = draft
                    final_report_source = "file"

                log.info(
                    "research.stream_complete",
                    report_chars=len(final_report),
                    final_report_source=final_report_source,
                    nodes_seen=sorted(mapper.seen_nodes),
                    usage=usage,
                    tokens_by_role=mapper.tokens_by_role,
                )
                yield events.token_breakdown(mapper.tokens_by_role)
                yield events.stream_end(
                    final_report=final_report,
                    usage=usage,
                    versions_used=versions_used,
                    final_report_source=final_report_source,
                )

    return EventSourceResponse(generator())
