from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    include_raw_content: bool = False,
) -> dict:
    """Search the web for up-to-date information on a topic."""
    return _tavily.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )
