import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.schemas.routing import ClassifierResult

logger = logging.getLogger(__name__)

_CONFIDENCE_FALLBACK_THRESHOLD = 0.55
_STICKINESS_THRESHOLD = 0.40


async def classify(
    messages: list[Any],
    current_intent: str | None,
    llm: Any,
    prompt: str,
) -> ClassifierResult:
    last_user = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    user_text = last_user.content if last_user is not None else ""
    filled_prompt = prompt.format(current_intent=current_intent or "none")

    try:
        structured_llm = llm.with_structured_output(ClassifierResult)
        raw = await structured_llm.ainvoke(
            [
                ("system", filled_prompt),
                ("human", str(user_text)),
            ]
        )
        result = raw if isinstance(raw, ClassifierResult) else ClassifierResult(**raw)
    except Exception as exc:
        logger.info("[classifier] fallback — error=%s", exc)
        return ClassifierResult(intent="chat", confidence=0.0, fallback_used=True)

    # Apply stickiness first, then fallback threshold.
    # Stickiness (>=0.40) overrides the fallback threshold (0.55) when the
    # current intent already matches — prevents thrashing on borderline inputs.
    if (
        current_intent == result.intent
        and result.confidence >= _STICKINESS_THRESHOLD
    ):
        return result  # stickiness match — keep the current routing

    if result.confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
        return ClassifierResult(intent="chat", confidence=result.confidence, fallback_used=True)

    return result
