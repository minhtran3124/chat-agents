import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

import tiktoken

from app.config.settings import settings
from app.streaming import events

logger = logging.getLogger(__name__)

_enc = tiktoken.encoding_for_model("gpt-4o")


def _count_tokens(text: object) -> int:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return len(_enc.encode(text))


def _new_id() -> str:
    return uuid.uuid4().hex


def _as_list(val: object) -> list:
    """Return a plain list from val, unwrapping LangGraph channel wrappers.

    LangGraph update dicts can contain channel-annotation objects such as
    ``Overwrite(value=[...])`` or ``Add([...])`` instead of bare lists.
    Both expose the underlying sequence via a ``.value`` or ``.values``
    attribute; fall back to an empty list for anything else.
    """
    if isinstance(val, list):
        return val
    for attr in ("value", "values"):
        inner = getattr(val, attr, None)
        if isinstance(inner, list):
            return inner
    return []


def _estimate_state_tokens(snapshot: dict) -> int:
    total = 0
    for m in snapshot.get("messages", []):
        content = getattr(m, "content", m) if not isinstance(m, str) else m
        total += _count_tokens(str(content))
    for content in snapshot.get("files", {}).values():
        total += _count_tokens(content)
    return total


class ChunkMapper:
    def __init__(self) -> None:
        self._prev_files: dict[str, str] = {}
        self._prev_todos: list[dict] = []
        # Tracks tool_call_ids for in-flight `task`-tool subagent invocations.
        # deepagents invokes subagents inside the `task` tool, so tool_call_id
        # is the stable identifier across start/complete.
        self._active_subagents: set[str] = set()
        # Tool-call ids we've already emitted a reflection_logged event for.
        # Prevents duplicates when LangGraph re-broadcasts the same message.
        self._emitted_reflections: set[str] = set()
        self._prev_token_count: int | None = None

        # Public introspection for the router's synthetic-compression fallback
        self.saw_compression: bool = False
        self.peak_tokens: int = 0

        # Diagnostic: every LangGraph node name seen during this stream
        self.seen_nodes: set[str] = set()

    async def process(self, mode: str, chunk: Any) -> AsyncGenerator[dict, None]:
        logger.debug("[CHUNK_MAPPER] mode=%s", mode)
        if mode == "updates":
            async for ev in self._handle_updates(chunk):
                yield ev
        elif mode == "messages":
            msg_chunk, _meta = chunk
            # Only stream text from AI (assistant) message chunks.
            # ToolMessage, HumanMessage, SystemMessage, etc. must not leak
            # into the report — their content is internal agent state.
            msg_type: str = getattr(msg_chunk, "type", "") or ""
            if msg_type not in ("ai", "AIMessageChunk"):
                logger.debug("[CHUNK_MAPPER] messages: skipping non-AI chunk type=%s", msg_type)
                return
            tool_calls = getattr(msg_chunk, "tool_calls", None) or []
            for tc in tool_calls:
                logger.info(
                    "[CHUNK_MAPPER] tool_call name=%s args=%s",
                    tc.get("name"),
                    str(tc.get("args", {}))[:200],
                )
            content: str = getattr(msg_chunk, "content", None) or ""
            if content:
                yield events.text_delta(content)
        elif mode == "values":
            async for ev in self._handle_values_snapshot(chunk):
                yield ev

    async def _handle_updates(self, chunk: dict) -> AsyncGenerator[dict, None]:
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue

            is_new = node_name not in self.seen_nodes
            self.seen_nodes.add(node_name)
            logger.info(
                "[CHUNK_MAPPER] node=%s keys=%s%s",
                node_name,
                list(update.keys()),
                " (first-seen)" if is_new else "",
            )

            if "todos" in update and update["todos"] != self._prev_todos:
                self._prev_todos = update["todos"]
                logger.debug("[CHUNK_MAPPER] todo_updated count=%d", len(update["todos"]))
                yield events.todo_updated(update["todos"])

            if "files" in update:
                for path, content in update["files"].items():
                    if self._prev_files.get(path) != content:
                        self._prev_files[path] = content
                        content_str = content if isinstance(content, str) else str(content)
                        size = _count_tokens(content_str)
                        logger.debug("[CHUNK_MAPPER] file_saved path=%s tokens=%d", path, size)
                        yield events.file_saved(
                            path=path,
                            size_tokens=size,
                            preview=content_str[:500],
                        )

            # Detect `task` subagent invocations via tool-call metadata.
            # AIMessage with tool_calls where name == "task" → subagent_started.
            # ToolMessage whose tool_call_id matches an in-flight task → subagent_completed.
            # AIMessage with tool_calls where name == "think_tool" → reflection_logged.
            # Role is inferred temporally: if a task is in flight when the think_tool
            # call is seen, the reflection came from the researcher subagent;
            # otherwise it came from the main agent.
            for msg in _as_list(update.get("messages")):
                for tc in getattr(msg, "tool_calls", None) or []:
                    tc_name = tc.get("name")
                    tc_id = tc.get("id")
                    if tc_name == "task":
                        if not tc_id or tc_id in self._active_subagents:
                            continue
                        args = tc.get("args") or {}
                        subagent_type = args.get("subagent_type", "unknown")
                        description = args.get("description", "")
                        self._active_subagents.add(tc_id)
                        logger.info(
                            "[CHUNK_MAPPER] subagent_started tool_call_id=%s type=%s desc=%r",
                            tc_id,
                            subagent_type,
                            description[:120],
                        )
                        yield events.subagent_started(tc_id, subagent_type, description)
                    elif tc_name == "think_tool":
                        if not tc_id or tc_id in self._emitted_reflections:
                            continue
                        args = tc.get("args") or {}
                        reflection = args.get("reflection", "")
                        if not isinstance(reflection, str) or not reflection:
                            continue
                        role: Literal["main", "researcher"] = (
                            "researcher" if self._active_subagents else "main"
                        )
                        self._emitted_reflections.add(tc_id)
                        logger.info(
                            "[CHUNK_MAPPER] reflection_logged role=%s text=%r",
                            role,
                            reflection[:120],
                        )
                        yield events.reflection_logged(role, reflection)

                tool_call_id = getattr(msg, "tool_call_id", None)
                if tool_call_id and tool_call_id in self._active_subagents:
                    self._active_subagents.discard(tool_call_id)
                    content = getattr(msg, "content", "") or ""
                    content_str = content if isinstance(content, str) else str(content)
                    logger.info(
                        "[CHUNK_MAPPER] subagent_completed tool_call_id=%s summary=%r",
                        tool_call_id,
                        content_str[:120],
                    )
                    yield events.subagent_completed(tool_call_id, content_str[:500])

    async def _handle_values_snapshot(self, snapshot: dict) -> AsyncGenerator[dict, None]:
        try:
            current = _estimate_state_tokens(snapshot)
        except Exception:
            current = 0
        self.peak_tokens = max(self.peak_tokens, current)
        logger.debug("[CHUNK_MAPPER] values_snapshot tokens=%d peak=%d", current, self.peak_tokens)
        if (
            self._prev_token_count
            and current < self._prev_token_count * settings.COMPRESSION_DETECTION_RATIO
        ):
            self.saw_compression = True
            logger.info(
                "[CHUNK_MAPPER] compression_triggered prev=%d current=%d ratio=%.2f",
                self._prev_token_count,
                current,
                current / self._prev_token_count,
            )
            yield events.compression_triggered(self._prev_token_count, current)
        self._prev_token_count = current
