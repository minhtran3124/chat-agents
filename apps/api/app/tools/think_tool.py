from langchain_core.tools import tool


@tool
def think_tool(reflection: str) -> str:
    """Reflect on research progress and identify gaps before the next step.

    Call this BEFORE starting a new search or spawning a subagent to state
    (a) what you already know from prior steps, and
    (b) the specific gap this next step must close.

    Call it AFTER a step returns to note what was learned and whether the
    next planned step is still relevant.

    The tool simply echoes your reflection back. Its purpose is behavioural:
    force serialised reasoning into the message log rather than emitting
    impulsive tool calls.
    """
    return f"Reflection recorded: {reflection}"
