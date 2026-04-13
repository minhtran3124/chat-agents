from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    thread_id: str | None = None
