import json
from datetime import datetime, timezone
from typing import Any


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, default=str)}


def stream_start(thread_id: str) -> dict:
    return _sse("stream_start", {
        "thread_id": thread_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })


def todo_updated(items: list[dict]) -> dict:
    return _sse("todo_updated", {"items": items})


def file_saved(path: str, size_tokens: int, preview: str) -> dict:
    return _sse("file_saved", {
        "path": path, "size_tokens": size_tokens, "preview": preview[:500],
    })


def subagent_started(run_id: str, name: str, task: str) -> dict:
    return _sse("subagent_started", {"id": run_id, "name": name, "task": task})


def subagent_completed(run_id: str, summary: str) -> dict:
    return _sse("subagent_completed", {"id": run_id, "summary": summary})


def compression_triggered(
    original_tokens: int,
    compressed_tokens: int,
    synthetic: bool = False,
) -> dict:
    return _sse("compression_triggered", {
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "synthetic": synthetic,
    })


def text_delta(content: str) -> dict:
    return _sse("text_delta", {"content": content})


def memory_updated(namespace: str, key: str) -> dict:
    return _sse("memory_updated", {"namespace": namespace, "key": key})


def error(message: str, recoverable: bool = False) -> dict:
    return _sse("error", {"message": message, "recoverable": recoverable})


def stream_end(final_report: str, usage: dict[str, Any]) -> dict:
    return _sse("stream_end", {"final_report": final_report, "usage": usage})
