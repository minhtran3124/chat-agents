import operator
from datetime import UTC, datetime
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from app.agents.builders.deep_research import build_deep_research_agent
from app.agents.builders.react import build_react_agent
from app.agents.classifier import classify
from app.agents.specs import REGISTERED_SPECS
from app.schemas.routing import IntentName, RoutingEvent


class GraphState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    current_intent: IntentName
    confidence: float
    fallback_used: bool
    routing_history: Annotated[list[RoutingEvent], operator.add]


def build_supervisor_graph(
    model_registry: Any,
    tool_registry: Any,
    prompt_registry: Any,
    checkpointer: Any,
    store: Any,
) -> Any:
    specs_by_name = {s.name: s for s in REGISTERED_SPECS}
    classifier_llm = model_registry.build("classifier")
    classifier_prompt = prompt_registry.get("classifier")

    async def classifier_node(state: GraphState) -> Command:
        result = await classify(
            messages=state.get("messages", []),
            current_intent=state.get("current_intent"),
            llm=classifier_llm,
            prompt=classifier_prompt,
        )
        event = RoutingEvent(
            turn=len(state.get("routing_history", [])) + 1,
            intent=result.intent,
            confidence=result.confidence,
            fallback_used=result.fallback_used,
            ts=datetime.now(UTC),
        )
        return Command(
            goto=result.intent,
            update={
                "current_intent": result.intent,
                "confidence": result.confidence,
                "fallback_used": result.fallback_used,
                "routing_history": [event],
            },
        )

    builder = StateGraph(GraphState)
    builder.add_node("classifier", classifier_node)
    builder.add_edge(START, "classifier")

    deep_spec = specs_by_name["deep-research"]
    deep_node = build_deep_research_agent(
        spec=deep_spec,
        model_registry=model_registry,
        tool_registry=tool_registry,
        prompt_registry=prompt_registry,
        checkpointer=checkpointer,
        store=store,
    )
    builder.add_node("deep-research", deep_node)
    builder.add_edge("deep-research", END)

    for name in ("chat", "research", "summarize", "code", "planner"):
        spec = specs_by_name[name]
        node = build_react_agent(
            spec=spec,
            model_registry=model_registry,
            tool_registry=tool_registry,
            prompt_registry=prompt_registry,
        )
        builder.add_node(name, node)
        builder.add_edge(name, END)

    return builder.compile(checkpointer=checkpointer, store=store)


def build_deep_research_only_graph(
    model_registry: Any,
    tool_registry: Any,
    prompt_registry: Any,
    checkpointer: Any,
    store: Any,
) -> Any:
    """Bypass graph for `/research` — no classifier, jumps straight to deep-research."""
    specs_by_name = {s.name: s for s in REGISTERED_SPECS}
    deep_spec = specs_by_name["deep-research"]
    deep_node = build_deep_research_agent(
        spec=deep_spec,
        model_registry=model_registry,
        tool_registry=tool_registry,
        prompt_registry=prompt_registry,
        checkpointer=checkpointer,
        store=store,
    )
    builder = StateGraph(GraphState)
    builder.add_node("deep-research", deep_node)
    builder.add_edge(START, "deep-research")
    builder.add_edge("deep-research", END)
    return builder.compile(checkpointer=checkpointer, store=store)
