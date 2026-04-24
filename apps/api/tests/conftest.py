"""Root conftest: seed minimum env vars so Settings() can be instantiated
during imports in any test module, even those that don't call Settings() directly."""

import asyncio
import os

import pytest

# Set defaults if not already set — individual tests can override via monkeypatch.
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-default")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-default")


@pytest.fixture(autouse=True)
def reset_sse_starlette_app_status():
    """Reset sse_starlette's AppStatus global between tests.

    sse_starlette stores `should_exit_event` as a class-level anyio.Event
    that is bound to the event loop of the first test that uses it.
    Subsequent tests run on a different loop and hit 'bound to a different
    event loop'. Setting it to None forces sse_starlette to create a fresh
    event on the current test's loop.
    """
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit = False
        AppStatus.should_exit_event = None
    except ImportError:
        pass
    yield
    try:
        from sse_starlette.sse import AppStatus

        AppStatus.should_exit = False
        AppStatus.should_exit_event = None
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Helpers (not fixtures — importable directly)
# ---------------------------------------------------------------------------


async def collect_sse_events(event_source_response) -> list[dict]:
    """Drain an EventSourceResponse body_iterator into a list of {event, data} dicts."""
    gen = event_source_response.body_iterator

    def _normalize(item) -> dict:
        if isinstance(item, dict):
            return {"event": item.get("event", ""), "data": item.get("data", "")}
        if hasattr(item, "event") and hasattr(item, "data"):
            return {"event": item.event or "", "data": item.data or ""}
        if isinstance(item, (str, bytes)):
            text = item.decode() if isinstance(item, bytes) else item
            event_line = next((ln for ln in text.splitlines() if ln.startswith("event: ")), "")
            data_line = next((ln for ln in text.splitlines() if ln.startswith("data: ")), "")
            return {
                "event": event_line.removeprefix("event: ").strip(),
                "data": data_line.removeprefix("data: ").strip(),
            }
        raise AssertionError(f"Unrecognized SSE item shape: {type(item)!r}")

    return [_normalize(item) async for item in gen]


# ---------------------------------------------------------------------------
# Agent stub fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def failing_agent_factory():
    """Factory for fake agents whose .astream raises the given exception."""

    def _make(exception: Exception):
        class _FailingAgent:
            async def astream(self, *_args, **_kwargs):
                raise exception
                yield  # marks this as an async generator

            async def aget_state(self, *_args, **_kwargs):
                return None

        return _FailingAgent()

    return _make


@pytest.fixture
def slow_agent_factory():
    """Factory for fake agents whose .astream sleeps longer than RESEARCH_TIMEOUT_S."""

    def _make(sleep_s: float = 5.0):
        class _SlowAgent:
            async def astream(self, *_args, **_kwargs):
                await asyncio.sleep(sleep_s)
                yield "values", {}

            async def aget_state(self, *_args, **_kwargs):
                return None

        return _SlowAgent()

    return _make
