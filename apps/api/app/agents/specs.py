from typing import Literal

from pydantic import BaseModel

IntentName = Literal[
    "chat",
    "research",
    "deep-research",
    "summarize",
    "code",
    "planner",
]

SubAgentName = Literal["researcher", "critic"]


class AgentSpec(BaseModel):
    name: IntentName | SubAgentName
    model_role: str
    tools: list[str] = []
    prompt_name: str
    subagents: list["AgentSpec"] = []

    model_config = {"frozen": True}


REGISTERED_SPECS: list[AgentSpec] = [
    AgentSpec(name="chat", model_role="fast", prompt_name="chat"),
    AgentSpec(
        name="research",
        model_role="main",
        tools=["web_search", "fetch_url"],
        prompt_name="research",
    ),
    AgentSpec(
        name="deep-research",
        model_role="main",
        tools=["web_search"],
        prompt_name="main",
        subagents=[
            AgentSpec(
                name="researcher",
                model_role="fast",
                tools=["web_search"],
                prompt_name="researcher",
            ),
            AgentSpec(
                name="critic",
                model_role="fast",
                tools=[],
                prompt_name="critic",
            ),
        ],
    ),
    AgentSpec(name="summarize", model_role="fast", prompt_name="summarize"),
    AgentSpec(
        name="code",
        model_role="main",
        tools=["repo_search", "fetch_url"],
        prompt_name="code",
    ),
    AgentSpec(name="planner", model_role="fast", prompt_name="planner"),
]
