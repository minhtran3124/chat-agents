from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


@tool
def internet_search(query: str) -> dict:
    """Search the web for up-to-date information. Returns a list of relevant results."""
    return _tavily.search(query=query, max_results=5, topic="general")
