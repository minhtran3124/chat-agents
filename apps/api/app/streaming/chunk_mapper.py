import uuid
from collections.abc import AsyncGenerator
from typing import Any

import tiktoken

from app.config.settings import settings
from app.streaming import events

_enc = tiktoken.encoding_for_model("gpt-4o")


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _new_id() -> str:
    return uuid.uuid4().hex


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
        self._active_subagents: dict[str, str] = {}
        self._prev_token_count: int | None = None
        self._report_phase: bool = False

        # Public introspection for the router's synthetic-compression fallback
        self.saw_compression: bool = False
        self.peak_tokens: int = 0

    async def process(self, mode: str, chunk: Any) -> AsyncGenerator[dict, None]:
        if mode == "updates":
            async for ev in self._handle_updates(chunk):
                yield ev
        elif mode == "messages":
            msg_chunk, _meta = chunk
            content: str = getattr(msg_chunk, "content", None) or ""
            if self._report_phase and content:
                yield events.text_delta(content)
        elif mode == "values":
            async for ev in self._handle_values_snapshot(chunk):
                yield ev

    async def _handle_updates(self, chunk: dict) -> AsyncGenerator[dict, None]:
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue

            if "todos" in update and update["todos"] != self._prev_todos:
                self._prev_todos = update["todos"]
                yield events.todo_updated(update["todos"])

            if "files" in update:
                for path, content in update["files"].items():
                    if self._prev_files.get(path) != content:
                        self._prev_files[path] = content
                        yield events.file_saved(
                            path=path,
                            size_tokens=_count_tokens(content),
                            preview=content[:500],
                        )

            if node_name in {"researcher", "critic"}:
                # elif (not two ifs) — a single chunk is treated as either
                # a start or an end, never both. Matches spec §7 semantics.
                if node_name not in self._active_subagents:
                    run_id = _new_id()
                    self._active_subagents[node_name] = run_id
                    yield events.subagent_started(run_id, node_name, update.get("task", ""))
                elif update.get("__end__") or update.get("summary"):
                    run_id = self._active_subagents.pop(node_name)
                    yield events.subagent_completed(run_id, update.get("summary", ""))
                    if node_name == "critic":
                        self._report_phase = True

    async def _handle_values_snapshot(self, snapshot: dict) -> AsyncGenerator[dict, None]:
        current = _estimate_state_tokens(snapshot)
        self.peak_tokens = max(self.peak_tokens, current)
        if (
            self._prev_token_count
            and current < self._prev_token_count * settings.COMPRESSION_DETECTION_RATIO
        ):
            self.saw_compression = True
            yield events.compression_triggered(self._prev_token_count, current)
        self._prev_token_count = current
