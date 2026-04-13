"""Root conftest: seed minimum env vars so Settings() can be instantiated
during imports in any test module, even those that don't call Settings() directly."""
import os

# Set defaults if not already set — individual tests can override via monkeypatch.
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-default")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-default")
