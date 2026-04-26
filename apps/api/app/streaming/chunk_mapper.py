import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, Literal

import tiktoken

from app.config.settings import settings
from app.streaming import events
from app.streaming.events import AgentRole

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
        # Maps tool_call_id → subagent_type (e.g. "researcher", "critic") for
        # in-flight `task`-tool subagent invocations. Holding the type lets us
        # attribute reflections and tool calls to the actual subagent rather
        # than always saying "researcher" when any task is in flight.
        self._active_subagents: dict[str, str] = {}
        self._emitted_reflections: set[str] = set()
        self._emitted_tool_starts: set[str] = set()
        self._emitted_tool_completions: set[str] = set()
        self._tool_call_starts: dict[str, datetime] = {}
        self._prev_token_count: int | None = None

        # Public introspection for the router's synthetic-compression fallback
        self.saw_compression: bool = False
        self.peak_tokens: int = 0

        # Diagnostic: every LangGraph node name seen during this stream
        self.seen_nodes: set[str] = set()

        # Token tracking per agent role for observability
        self.tokens_by_role: dict[AgentRole, int] = {
            "main": 0,
            "researcher": 0,
            "critic": 0,
        }

    def _infer_role(self) -> AgentRole:
        if not self._active_subagents:
            return "main"

        last_type = next(reversed(self._active_subagents.values()))
        if last_type in ("researcher", "critic"):
            return last_type  # type: ignore[return-value]

        return "main"

    def _track_token_usage(self, msg: Any) -> None:
        """Update tokens_by_role from message usage_metadata."""
        meta = getattr(msg, "usage_metadata", None)
        if not meta:
            return
        role = self._infer_role()
        input_tok = meta.get("input_tokens", 0)
        output_tok = meta.get("output_tokens", 0)
        cache_read = (meta.get("input_token_details") or {}).get("cache_read", 0)
        # Cached input is billed at ~50% rate
        tokens = input_tok - cache_read // 2 + output_tok
        self.tokens_by_role[role] += tokens

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
            self._track_token_usage(msg_chunk)
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
                    tc_name = tc.get("name") or "unknown"
                    tc_id = tc.get("id")
                    args = tc.get("args") or {}

                    if tc_id and tc_id not in self._emitted_tool_starts:
                        self._emitted_tool_starts.add(tc_id)
                        self._tool_call_starts[tc_id] = datetime.now(UTC)
                        try:
                            args_preview = json.dumps(args, default=str)
                        except (TypeError, ValueError):
                            args_preview = str(args)
                        yield events.tool_call_started(
                            tc_id, self._infer_role(), tc_name, args_preview
                        )

                    if tc_name == "task":
                        if not tc_id or tc_id in self._active_subagents:
                            continue
                        subagent_type = args.get("subagent_type", "unknown")
                        description = args.get("description", "")
                        self._active_subagents[tc_id] = subagent_type
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

                        reflection = args.get("reflection", "")
                        if not isinstance(reflection, str) or not reflection:
                            continue

                        self._emitted_reflections.add(tc_id)
                        role = self._infer_role()
                        logger.info(
                            "[CHUNK_MAPPER] reflection_logged role=%s text=%r",
                            role,
                            reflection[:120],
                        )
                        yield events.reflection_logged(role, reflection)

                tool_call_id = getattr(msg, "tool_call_id", None)
                if tool_call_id:
                    content = getattr(msg, "content", "") or ""
                    content_str = content if isinstance(content, str) else str(content)
                    if (
                        tool_call_id in self._tool_call_starts
                        and tool_call_id not in self._emitted_tool_completions
                    ):
                        self._emitted_tool_completions.add(tool_call_id)
                        start = self._tool_call_starts[tool_call_id]
                        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
                        msg_status = getattr(msg, "status", None)
                        status: Literal["ok", "error"] = "error" if msg_status == "error" else "ok"
                        yield events.tool_call_completed(
                            tool_call_id, status, content_str, duration_ms
                        )

                    if tool_call_id in self._active_subagents:
                        self._active_subagents.pop(tool_call_id, None)
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
