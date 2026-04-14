import logging

import httpx
from langchain_core.tools import tool

from app.tools.registry import register_tool

logger = logging.getLogger(__name__)

_MAX_BYTES = 50 * 1024
_TIMEOUT_S = 10.0


@register_tool("fetch_url")
@tool
async def fetch_url(url: str) -> dict:
    """Fetch the text body of a URL. Returns up to 50 KB or an error dict."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text[:_MAX_BYTES]
            return {"url": str(resp.url), "status": resp.status_code, "text": text}
    except Exception as exc:
        logger.info("[fetch_url] failed url=%s error=%s", url, exc)
        return {"url": url, "error": f"fetch_url failed: {exc}"}
