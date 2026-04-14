from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "chat", "research", "deep-research", "summarize", "code", "planner",
]


class ClassifierResult(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_used: bool = False


class RoutingEvent(BaseModel):
    turn: int
    intent: IntentName
    confidence: float
    fallback_used: bool
    ts: datetime
