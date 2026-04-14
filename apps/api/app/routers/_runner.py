import json
import logging
import traceback
from collections.abc import AsyncGenerator
from typing import Any

from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

logger = logging.getLogger(__name__)

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000


async def run_graph(
    graph: Any,
    question: str,
    thread_id: str,
    versions_used: dict[str, str],
    force_intent: str | None,
) -> AsyncGenerator[dict, None]:
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    logger.info(
        "[RUNNER] invoked thread_id=%s force_intent=%s question=%r",
        thread_id, force_intent, question[:120],
    )
    yield events.stream_start(thread_id)

    if force_intent is not None:
        # `/research` bypass — no classifier runs.
        yield events.intent_classified(
            intent=force_intent,
            confidence=1.0,
            fallback_used=False,
        )
        emitted_ic = True
    else:
        emitted_ic = False

    try:
        async for mode, chunk in graph.astream(
            {"messages": [{"role": "user", "content": question}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=["values", "messages", "updates"],
        ):
            if not emitted_ic and mode == "updates" and isinstance(chunk, dict):
                update = chunk.get("classifier")
                if isinstance(update, dict) and "current_intent" in update:
                    yield events.intent_classified(
                        intent=update["current_intent"],
                        confidence=float(update.get("confidence", 0.0)),
                        fallback_used=bool(update.get("fallback_used", False)),
                    )
                    emitted_ic = True

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
            final_state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            usage = final_state.values.get("usage", {}) if final_state else {}
        except Exception:
            usage = {}

        yield events.stream_end(
            final_report="".join(final_report_parts),
            usage=usage,
            versions_used=versions_used,
        )
    except Exception as exc:
        logger.error("[RUNNER] stream error\n%s", traceback.format_exc())
        yield events.error(str(exc), recoverable=False)
