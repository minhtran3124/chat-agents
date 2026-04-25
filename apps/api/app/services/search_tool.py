import re
import uuid
from typing import Any
from urllib.parse import urlparse

import tiktoken
from deepagents.backends.state import StateBackend
from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)
_enc = tiktoken.encoding_for_model("gpt-4o")
_state_backend = StateBackend()

_SNIPPET_CHAR_LIMIT = 600
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _slug(text: str, limit: int = 40) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (s[:limit] or "untitled").rstrip("-")


def _result_path(query_slug: str, idx: int, url: str) -> str:
    host = urlparse(url).hostname or "unknown"
    return f"/research/searches/{query_slug}/{idx:02d}-{_slug(host, limit=30)}.md"


def _format_full_content(result: dict[str, Any]) -> str:
    return (
        f"# {result.get('title', 'Untitled')}\n"
        f"Source: {result.get('url', '')}\n"
        f"Score: {result.get('score', 'n/a')}\n\n"
        f"{result.get('content', '')}"
    )


def _build_offloaded_response(
    raw: dict[str, Any],
    threshold: int,
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """Decide whether to offload Tavily results to the virtual filesystem.

    Returns (response, files_to_write). When the total content tokens are at
    or below `threshold`, returns `raw` unchanged and an empty file list.
    Otherwise returns a response where each result carries a `snippet` plus
    `full_content_path`, and a list of `(path, content)` tuples for the
    caller to persist via the state backend.
    """
    results = raw.get("results", []) or []
    total_tokens = sum(_count_tokens(str(r.get("content", ""))) for r in results)

    if total_tokens <= threshold or not results:
        return raw, []

    query_slug = _slug(str(raw.get("query", "query")))
    files_to_write: list[tuple[str, str]] = []
    new_results: list[dict[str, Any]] = []
    for idx, r in enumerate(results, start=1):
        content = str(r.get("content", ""))
        path = _result_path(query_slug, idx, str(r.get("url", "")))
        files_to_write.append((path, _format_full_content(r)))
        new_results.append(
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "score": r.get("score"),
                "snippet": content[:_SNIPPET_CHAR_LIMIT],
                "full_content_path": path,
            }
        )

    return {
        **raw,
        "results": new_results,
        "offloaded": True,
        "total_tokens": total_tokens,
    }, files_to_write


@tool
def internet_search(query: str) -> dict:
    """Search the web for up-to-date information.

    Returns a list of relevant results. When the combined content size
    exceeds the configured offload threshold, full result bodies are saved
    to the virtual filesystem and each result carries a `snippet` plus a
    `full_content_path`. Use `read_file(<full_content_path>)` only when you
    need the entire article — the snippet is enough for most decisions.
    """
    raw = _tavily.search(query=query, max_results=5, topic="general")
    response, files_to_write = _build_offloaded_response(
        raw, threshold=settings.VFS_OFFLOAD_THRESHOLD_TOKENS
    )
    for path, content in files_to_write:
        result = _state_backend.write(path, content)
        if result.error:
            fallback = path.replace(".md", f"-{uuid.uuid4().hex[:6]}.md")
            _state_backend.write(fallback, content)
            for r in response["results"]:
                if r.get("full_content_path") == path:
                    r["full_content_path"] = fallback
                    break
    return response
