from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings
from app.tools.registry import register_tool

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


@register_tool("web_search")
@tool
def web_search(query: str) -> dict:
    """Search the web for up-to-date information. Returns a list of relevant results."""
    try:
        return _tavily.search(query=query, max_results=5, topic="general")
    except Exception as exc:
        return {"error": f"web_search failed: {exc}"}
