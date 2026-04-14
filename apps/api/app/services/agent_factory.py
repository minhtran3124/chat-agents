from typing import Any

from deepagents import SubAgent, create_deep_agent

from app.services.llm_factory import get_fast_llm, get_llm
from app.services.search_tool import internet_search
from app.stores.memory_store import get_checkpointer, get_store


def build_research_agent(
    main_prompt: str,
    researcher_prompt: str,
    critic_prompt: str,
) -> Any:
    main_llm = get_llm()
    fast_llm = get_fast_llm()

    subagents = [
        SubAgent(
            name="researcher",
            description=(
                "Deep-dive a single sub-topic: run searches, save raw "
                "results, return 150-word summary with citations."
            ),
            system_prompt=researcher_prompt,
            tools=[internet_search],
            model=fast_llm,
        ),
        SubAgent(
            name="critic",
            description=(
                "Review the draft report on virtual FS and list issues "
                "(unsupported claims, outdated info, contradictions)."
            ),
            system_prompt=critic_prompt,
            tools=[],
            model=fast_llm,
        ),
    ]

    return create_deep_agent(
        model=main_llm,
        tools=[internet_search],
        subagents=subagents,
        system_prompt=main_prompt,
        store=get_store(),
        checkpointer=get_checkpointer(),
    )
