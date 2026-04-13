from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    thread_id: str | None = None
    prompt_versions: dict[str, str] | None = None
    # e.g. {"main": "v2", "researcher": "v2-concise"}
    # None or omitted → active.yaml defaults apply for all prompts
