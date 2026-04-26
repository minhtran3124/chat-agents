from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)

_MAX_SEARCHES_PER_AGENT = 4


def _count_searches_in_messages(messages: list[Any]) -> int:
    """Count AIMessage tool_calls of name='internet_search' in the agent's state.

    Includes the in-flight call (the one being executed now), because the
    LLM's AIMessage that triggered it is already in state by the time the
    tool runs.
    """
    n = 0
    for m in messages or []:
        for tc in getattr(m, "tool_calls", None) or []:
            if tc.get("name") == "internet_search":
                n += 1
    return n


@tool
def internet_search(
    query: str,
    state: Annotated[dict, InjectedState],
) -> dict:
    """Search the web for up-to-date information.

    Each agent (the main agent and each researcher/critic subagent) is
    capped at 4 `internet_search` calls per invocation. The cap is enforced
    by counting AIMessage tool_calls in the agent's state — each subagent
    has its own state, so the quota is naturally per-subagent. Once
    reached, the tool refuses further calls so the agent must synthesize
    from existing results.
    """
    count_including_self = _count_searches_in_messages(state.get("messages", []))
    if count_including_self > _MAX_SEARCHES_PER_AGENT:
        return {
            "error": "search_budget_exhausted",
            "message": (
                f"You have already made {_MAX_SEARCHES_PER_AGENT} searches in this "
                "agent run. Synthesize a summary from the search results you already "
                "have — do not call internet_search again."
            ),
        }
    return _tavily.search(query=query, max_results=5, topic="general")
