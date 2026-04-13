"""Root conftest: seed minimum env vars so Settings() can be instantiated
during imports in any test module, even those that don't call Settings() directly."""

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
