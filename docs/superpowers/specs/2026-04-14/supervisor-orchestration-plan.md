# Supervisor Orchestration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-14/supervisor-orchestration-design.md`

**Goal:** Refactor the FastAPI backend from a single deepagents pipeline to a supervisor-routed graph with six specialists (chat, research, deep-research, summarize, code, planner), a classifier node, and three collaborating registries (Model + Tool + AgentSpec).

**Architecture:** LangGraph outer graph with a classifier node that uses `add_conditional_edges` to dispatch to one of six specialist nodes. Five specialists are single-loop ReAct agents sharing one builder; the sixth (`deep-research`) composes the existing `create_deep_agent(...)` as a native subgraph. OpenAI is the primary LLM provider; Anthropic and Google are optional per-role via `models.yaml` + env overrides.

**Tech Stack:** Python 3.11+, FastAPI 0.115+, LangGraph 1.0+, deepagents 0.5.2+, LangChain 1.0+, sse-starlette, pytest + pytest-asyncio, OpenAI `gpt-4o` / `gpt-4o-mini` (defaults). Frontend: Next.js 14 App Router, React 18, TypeScript strict, vitest.

**Invariant (hard constraint):** The existing `/research` SSE flow keeps working end-to-end after every chunk. The only breaking change is that `/research` emits one additional event (`intent_classified`) — the frontend handler tolerates unknown events, so this is forward-compatible. All existing tests must pass green at every chunk boundary; tests are only rewritten in the chunk that changes the behavior under test.

---

## Pre-flight

- [ ] **P1: Confirm working directory and branch**

  Run: `cd /Users/minhtran/Documents/minhtran3124/developer/chat-agents && git status && git rev-parse --abbrev-ref HEAD`
  Expected: on `main`, working tree may have untracked files but no blockers.

- [ ] **P2: Verify baseline tests are green**

  Run:
  ```bash
  cd apps/api && pytest -x --tb=short
  ```
  Expected: all tests pass.

- [ ] **P3: Verify environment has required keys**

  Required for lifespan startup and integration tests: `OPENAI_API_KEY` (after this plan, OpenAI is primary), `TAVILY_API_KEY`. Unit tests do not call real APIs.

  Run: `grep -E '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|TAVILY_API_KEY)=' apps/api/.env`
  Expected: at least `OPENAI_API_KEY` and `TAVILY_API_KEY` present.

---

## Chunk 1: ModelRegistry

Spec §5.1, Rollout §14 step 1 (part 1 of 3).

**Files:**
- Create: `apps/api/models.yaml`
- Create: `apps/api/app/models/__init__.py`
- Create: `apps/api/app/models/registry.py`
- Create: `apps/api/tests/unit/test_model_registry.py`
- Modify: `apps/api/app/config/settings.py` (default provider → `openai`)

### Tasks

- [ ] **1.1: Create `apps/api/models.yaml` with OpenAI defaults**

  Write:
  ```yaml
  # apps/api/models.yaml
  # Primary provider: OpenAI. Swap a role by editing this file
  # or by setting <ROLE>_MODEL / <ROLE>_PROVIDER env vars.

  classifier:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.0
    streaming: false
    response_format: json_schema

  fast:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.3
    streaming: true

  main:
    provider: openai
    model: gpt-4o
    temperature: 0.7
    streaming: true
  ```

- [ ] **1.2: Write failing test — YAML load + `get()`**

  Create `apps/api/tests/unit/test_model_registry.py`:
  ```python
  from pathlib import Path
  from textwrap import dedent

  import pytest

  from app.models.registry import ModelRegistry, ModelSpec


  @pytest.mark.unit
  def test_loads_yaml_and_returns_specs(tmp_path: Path) -> None:
      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          classifier:
            provider: openai
            model: gpt-4o-mini
            temperature: 0.0
            streaming: false
          fast:
            provider: openai
            model: gpt-4o-mini
            temperature: 0.3
            streaming: true
          main:
            provider: openai
            model: gpt-4o
            temperature: 0.7
            streaming: true
      """))

      reg = ModelRegistry(yaml_path=yaml_path, env={})
      spec = reg.get("classifier")

      assert isinstance(spec, ModelSpec)
      assert spec.provider == "openai"
      assert spec.model == "gpt-4o-mini"
      assert spec.temperature == 0.0
      assert spec.streaming is False
  ```

- [ ] **1.3: Run test — expect FAIL (module not found)**

  Run: `cd apps/api && pytest tests/unit/test_model_registry.py -v`
  Expected: `ModuleNotFoundError: No module named 'app.models.registry'`.

- [ ] **1.4: Implement `app/models/__init__.py` (empty) and `registry.py` minimal**

  Create `apps/api/app/models/__init__.py`:
  ```python
  ```

  Create `apps/api/app/models/registry.py`:
  ```python
  import os
  from collections.abc import Mapping
  from pathlib import Path
  from typing import Any, Literal

  import yaml
  from pydantic import BaseModel


  class ModelSpec(BaseModel):
      provider: Literal["openai", "anthropic", "google"]
      model: str
      temperature: float = 0.7
      streaming: bool = True
      response_format: str | None = None

      model_config = {"frozen": True}


  class ModelRegistry:
      def __init__(self, yaml_path: Path, env: Mapping[str, str] | None = None) -> None:
          self._yaml_path = yaml_path
          self._env = dict(env if env is not None else os.environ)
          self._specs: dict[str, ModelSpec] = {}
          self._clients: dict[str, Any] = {}
          self.reload()

      def reload(self) -> None:
          if not self._yaml_path.exists():
              raise RuntimeError(f"models.yaml not found: {self._yaml_path}")
          with self._yaml_path.open() as f:
              raw = yaml.safe_load(f) or {}

          specs: dict[str, ModelSpec] = {}
          for role, block in raw.items():
              merged = dict(block)
              env_model = self._env.get(f"{role.upper()}_MODEL")
              env_provider = self._env.get(f"{role.upper()}_PROVIDER")
              if env_model:
                  merged["model"] = env_model
              if env_provider:
                  merged["provider"] = env_provider
              specs[role] = ModelSpec(**merged)

          self._specs = specs
          self._clients.clear()

      def get(self, role: str) -> ModelSpec:
          if role not in self._specs:
              raise KeyError(f"Unknown model role '{role}'. Available: {sorted(self._specs)}")
          return self._specs[role]

      def build(self, role: str) -> Any:
          if role in self._clients:
              return self._clients[role]
          from langchain.chat_models import init_chat_model

          spec = self.get(role)
          kwargs: dict[str, Any] = {
              "model": spec.model,
              "model_provider": spec.provider,
              "temperature": spec.temperature,
              "streaming": spec.streaming,
          }
          client = init_chat_model(**kwargs)
          self._clients[role] = client
          return client

      def roles(self) -> list[str]:
          return sorted(self._specs)

      def required_providers(self) -> set[str]:
          return {s.provider for s in self._specs.values()}
  ```

- [ ] **1.5: Run test — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_model_registry.py -v`
  Expected: `test_loads_yaml_and_returns_specs PASSED`.

- [ ] **1.6: Add env-override tests**

  Append to `apps/api/tests/unit/test_model_registry.py`:
  ```python
  @pytest.mark.unit
  def test_env_model_overrides_yaml(tmp_path: Path) -> None:
      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          main:
            provider: openai
            model: gpt-4o
            temperature: 0.7
            streaming: true
      """))
      reg = ModelRegistry(yaml_path=yaml_path, env={"MAIN_MODEL": "gpt-4o-2024-11-20"})
      assert reg.get("main").model == "gpt-4o-2024-11-20"
      assert reg.get("main").provider == "openai"


  @pytest.mark.unit
  def test_env_provider_plus_model_swap_provider(tmp_path: Path) -> None:
      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          main:
            provider: openai
            model: gpt-4o
            temperature: 0.7
            streaming: true
      """))
      reg = ModelRegistry(
          yaml_path=yaml_path,
          env={"MAIN_PROVIDER": "anthropic", "MAIN_MODEL": "claude-sonnet-4-6"},
      )
      assert reg.get("main").provider == "anthropic"
      assert reg.get("main").model == "claude-sonnet-4-6"


  @pytest.mark.unit
  def test_unknown_role_raises(tmp_path: Path) -> None:
      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          main:
            provider: openai
            model: gpt-4o
      """))
      reg = ModelRegistry(yaml_path=yaml_path, env={})
      with pytest.raises(KeyError, match="Unknown model role 'missing'"):
          reg.get("missing")


  @pytest.mark.unit
  def test_required_providers_dedup(tmp_path: Path) -> None:
      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          classifier:
            provider: openai
            model: gpt-4o-mini
          fast:
            provider: anthropic
            model: claude-haiku-4-5
          main:
            provider: openai
            model: gpt-4o
      """))
      reg = ModelRegistry(yaml_path=yaml_path, env={})
      assert reg.required_providers() == {"openai", "anthropic"}
  ```

- [ ] **1.7: Run tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_model_registry.py -v`
  Expected: 4 passed.

- [ ] **1.8: Update Settings default provider to `openai`**

  In `apps/api/app/config/settings.py`, modify the line declaring `LLM_PROVIDER`:
  ```python
  LLM_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"  # was "anthropic"
  ```
  Leave everything else intact — `LLM_MODEL` defaults, env key resolution, and the validator stay as-is for back-compat with the legacy `llm_factory.py` (deleted later in chunk 11).

- [ ] **1.9: Run lint + type-check**

  Run: `cd apps/api && ruff check app/models/ tests/unit/test_model_registry.py && mypy app/models/`
  Expected: clean.

- [ ] **1.10: Run full test suite — must stay green**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass.

- [ ] **1.11: Commit**

  ```bash
  git add apps/api/models.yaml \
          apps/api/app/models/ \
          apps/api/app/config/settings.py \
          apps/api/tests/unit/test_model_registry.py
  git commit -m "feat(api): add ModelRegistry with YAML config and env overrides"
  ```

---

## Chunk 2: ToolRegistry

Spec §5.2, Rollout §14 step 1 (part 2 of 3).

**Files:**
- Create: `apps/api/app/tools/__init__.py`
- Create: `apps/api/app/tools/registry.py`
- Create: `apps/api/tests/unit/test_tool_registry.py`

### Tasks

- [ ] **2.1: Write failing test — `@register_tool` decorator**

  Create `apps/api/tests/unit/test_tool_registry.py`:
  ```python
  import pytest
  from langchain_core.tools import tool

  from app.tools.registry import ToolRegistry


  @pytest.mark.unit
  def test_register_and_get() -> None:
      reg = ToolRegistry()

      @reg.register("echo")
      @tool
      def echo(text: str) -> str:
          """Echo back the input."""
          return text

      retrieved = reg.get("echo")
      assert retrieved.name == "echo"


  @pytest.mark.unit
  def test_duplicate_registration_raises() -> None:
      reg = ToolRegistry()

      @reg.register("twice")
      @tool
      def first(text: str) -> str:
          """first"""
          return text

      with pytest.raises(RuntimeError, match="already registered"):
          @reg.register("twice")
          @tool
          def second(text: str) -> str:
              """second"""
              return text


  @pytest.mark.unit
  def test_unknown_tool_raises() -> None:
      reg = ToolRegistry()
      with pytest.raises(KeyError, match="Unknown tool 'missing'"):
          reg.get("missing")


  @pytest.mark.unit
  def test_get_many_preserves_order() -> None:
      reg = ToolRegistry()

      @reg.register("a")
      @tool
      def a(x: str) -> str:
          """a"""
          return x

      @reg.register("b")
      @tool
      def b(x: str) -> str:
          """b"""
          return x

      names = [t.name for t in reg.get_many(["b", "a"])]
      assert names == ["b", "a"]
  ```

- [ ] **2.2: Run test — expect FAIL (module not found)**

  Run: `cd apps/api && pytest tests/unit/test_tool_registry.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **2.3: Implement registry**

  Create `apps/api/app/tools/__init__.py`:
  ```python
  # Eager import of every tool module so @register_tool decorators fire.
  # Add one import per tool file here.
  ```
  (tool imports are added in chunk 4.)

  Create `apps/api/app/tools/registry.py`:
  ```python
  from collections.abc import Callable
  from typing import TypeVar

  from langchain_core.tools import BaseTool

  T = TypeVar("T", bound=BaseTool)


  class ToolRegistry:
      def __init__(self) -> None:
          self._tools: dict[str, BaseTool] = {}

      def register(self, name: str) -> Callable[[T], T]:
          def decorator(tool_obj: T) -> T:
              if name in self._tools:
                  raise RuntimeError(f"Tool '{name}' already registered")
              self._tools[name] = tool_obj
              return tool_obj
          return decorator

      def get(self, name: str) -> BaseTool:
          if name not in self._tools:
              raise KeyError(f"Unknown tool '{name}'. Available: {sorted(self._tools)}")
          return self._tools[name]

      def get_many(self, names: list[str]) -> list[BaseTool]:
          return [self.get(n) for n in names]

      def names(self) -> list[str]:
          return sorted(self._tools)


  # Module-level singleton. Use this in application code.
  # Tests should construct their own ToolRegistry() instance.
  registry = ToolRegistry()
  register_tool = registry.register
  ```

- [ ] **2.4: Run tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_tool_registry.py -v`
  Expected: 4 passed.

- [ ] **2.5: Run lint + type-check**

  Run: `cd apps/api && ruff check app/tools/ tests/unit/test_tool_registry.py && mypy app/tools/`
  Expected: clean.

- [ ] **2.6: Full suite green**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass.

- [ ] **2.7: Commit**

  ```bash
  git add apps/api/app/tools/ apps/api/tests/unit/test_tool_registry.py
  git commit -m "feat(api): add ToolRegistry with decorator auto-registration"
  ```

---

## Chunk 3: AgentSpec + REGISTERED_SPECS integrity tests

Spec §5.3, Rollout §14 step 1 (part 3 of 3).

**Files:**
- Create: `apps/api/app/agents/__init__.py`
- Create: `apps/api/app/agents/specs.py`
- Create: `apps/api/tests/unit/test_agent_specs.py`

### Tasks

- [ ] **3.1: Write failing test — spec declarations + integrity**

  Create `apps/api/tests/unit/test_agent_specs.py`:
  ```python
  import pytest

  from app.agents.specs import REGISTERED_SPECS, AgentSpec


  @pytest.mark.unit
  def test_six_specialists_declared() -> None:
      names = {s.name for s in REGISTERED_SPECS}
      assert names == {"chat", "research", "deep-research", "summarize", "code", "planner"}


  @pytest.mark.unit
  def test_deep_research_has_subagents() -> None:
      deep = next(s for s in REGISTERED_SPECS if s.name == "deep-research")
      sub_names = {s.name for s in deep.subagents}
      assert sub_names == {"researcher", "critic"}


  @pytest.mark.unit
  def test_simple_specialists_have_no_subagents() -> None:
      for s in REGISTERED_SPECS:
          if s.name == "deep-research":
              continue
          assert s.subagents == [], f"{s.name} must not have subagents"


  @pytest.mark.unit
  def test_spec_name_is_unique() -> None:
      names = [s.name for s in REGISTERED_SPECS]
      assert len(names) == len(set(names))


  @pytest.mark.unit
  def test_agent_spec_rejects_unknown_intent_name() -> None:
      with pytest.raises(ValueError):
          AgentSpec(name="unknown", model_role="fast", prompt_name="chat")  # type: ignore[arg-type]
  ```

- [ ] **3.2: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/unit/test_agent_specs.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **3.3: Implement specs**

  Create `apps/api/app/agents/__init__.py`:
  ```python
  ```

  Create `apps/api/app/agents/specs.py`:
  ```python
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
  ```

- [ ] **3.4: Run tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_agent_specs.py -v`
  Expected: 5 passed.

- [ ] **3.5: Lint + type-check**

  Run: `cd apps/api && ruff check app/agents/specs.py tests/unit/test_agent_specs.py && mypy app/agents/`
  Expected: clean.

- [ ] **3.6: Full suite green**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass.

- [ ] **3.7: Commit**

  ```bash
  git add apps/api/app/agents/ apps/api/tests/unit/test_agent_specs.py
  git commit -m "feat(api): add AgentSpec and REGISTERED_SPECS for six specialists"
  ```

---

## Chunk 4: Tools — web_search migration, fetch_url, repo_search

Rollout §14 step 2.

**Files:**
- Create: `apps/api/app/tools/web_search.py` (copy + register from `services/search_tool.py`)
- Create: `apps/api/app/tools/fetch_url.py`
- Create: `apps/api/app/tools/repo_search.py`
- Modify: `apps/api/app/tools/__init__.py` (register imports)
- Create: `apps/api/tests/unit/test_tool_web_search.py`
- Create: `apps/api/tests/unit/test_tool_fetch_url.py`
- Create: `apps/api/tests/unit/test_tool_repo_search.py`
- **Do NOT delete** `apps/api/app/services/search_tool.py` — legacy callers still need it until chunk 11.

### Tasks

- [ ] **4.1: Create `web_search.py` — decorated tool mirroring `services/search_tool.py`**

  Create `apps/api/app/tools/web_search.py`:
  ```python
  from langchain_core.tools import tool
  from tavily import TavilyClient

  from app.config.settings import settings
  from app.tools.registry import register_tool

  _tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


  @register_tool("web_search")
  @tool
  def web_search(query: str) -> dict:
      """Search the web for up-to-date information. Returns a list of relevant results."""
      try:
          return _tavily.search(query=query, max_results=5, topic="general")
      except Exception as exc:
          return {"error": f"web_search failed: {exc}"}
  ```

- [ ] **4.2: Write test for `web_search`**

  Create `apps/api/tests/unit/test_tool_web_search.py`:
  ```python
  from unittest.mock import MagicMock, patch

  import pytest


  @pytest.mark.unit
  def test_web_search_returns_tavily_results() -> None:
      fake = {"results": [{"title": "a", "url": "http://a"}], "query": "q"}
      with patch("app.tools.web_search._tavily") as mock_client:
          mock_client.search.return_value = fake
          from app.tools import web_search as mod
          result = mod.web_search.invoke({"query": "q"})
      assert result == fake


  @pytest.mark.unit
  def test_web_search_wraps_exceptions() -> None:
      with patch("app.tools.web_search._tavily") as mock_client:
          mock_client.search.side_effect = RuntimeError("boom")
          from app.tools import web_search as mod
          result = mod.web_search.invoke({"query": "q"})
      assert "error" in result
      assert "boom" in result["error"]
  ```

- [ ] **4.3: Add `web_search` to `__init__.py` imports**

  Modify `apps/api/app/tools/__init__.py`:
  ```python
  # Eager import of every tool module so @register_tool decorators fire.
  from app.tools import web_search  # noqa: F401
  ```

- [ ] **4.4: Run web_search tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_tool_web_search.py -v`
  Expected: 2 passed.

- [ ] **4.5: Create `fetch_url.py`**

  Create `apps/api/app/tools/fetch_url.py`:
  ```python
  import logging

  import httpx
  from langchain_core.tools import tool

  from app.tools.registry import register_tool

  logger = logging.getLogger(__name__)

  _MAX_BYTES = 50 * 1024
  _TIMEOUT_S = 10.0


  @register_tool("fetch_url")
  @tool
  async def fetch_url(url: str) -> dict:
      """Fetch the text body of a URL. Returns up to 50 KB or an error dict."""
      try:
          async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
              resp = await client.get(url)
              resp.raise_for_status()
              text = resp.text[:_MAX_BYTES]
              return {"url": str(resp.url), "status": resp.status_code, "text": text}
      except Exception as exc:
          logger.info("[fetch_url] failed url=%s error=%s", url, exc)
          return {"url": url, "error": f"fetch_url failed: {exc}"}
  ```

- [ ] **4.6: Test `fetch_url`**

  Create `apps/api/tests/unit/test_tool_fetch_url.py`:
  ```python
  from unittest.mock import AsyncMock, patch

  import httpx
  import pytest


  @pytest.mark.unit
  async def test_fetch_url_returns_body() -> None:
      mock_resp = AsyncMock()
      mock_resp.text = "hello"
      mock_resp.status_code = 200
      mock_resp.url = "http://example.com/"
      mock_resp.raise_for_status = lambda: None

      with patch("app.tools.fetch_url.httpx.AsyncClient") as mock_ctor:
          mock_client = AsyncMock()
          mock_client.get.return_value = mock_resp
          mock_ctor.return_value.__aenter__.return_value = mock_client

          from app.tools.fetch_url import fetch_url
          result = await fetch_url.ainvoke({"url": "http://example.com/"})

      assert result["status"] == 200
      assert result["text"] == "hello"


  @pytest.mark.unit
  async def test_fetch_url_returns_error_on_exception() -> None:
      with patch("app.tools.fetch_url.httpx.AsyncClient") as mock_ctor:
          mock_ctor.return_value.__aenter__.side_effect = httpx.ConnectError("dns")
          from app.tools.fetch_url import fetch_url
          result = await fetch_url.ainvoke({"url": "http://bad"})
      assert "error" in result
      assert "dns" in result["error"]
  ```

- [ ] **4.7: Add `fetch_url` to `__init__.py`**

  Modify `apps/api/app/tools/__init__.py`:
  ```python
  from app.tools import web_search  # noqa: F401
  from app.tools import fetch_url  # noqa: F401
  ```

- [ ] **4.8: Run fetch_url tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_tool_fetch_url.py -v`
  Expected: 2 passed.

- [ ] **4.9: Create `repo_search.py`**

  Create `apps/api/app/tools/repo_search.py`:
  ```python
  import asyncio
  import logging
  import shlex
  from pathlib import Path

  from langchain_core.tools import tool

  from app.tools.registry import register_tool

  logger = logging.getLogger(__name__)

  _REPO_ROOT = Path(__file__).resolve().parents[3]  # apps/api/app/tools/repo_search.py → repo root
  _MAX_LINES = 200
  _TIMEOUT_S = 5.0


  @register_tool("repo_search")
  @tool
  async def repo_search(pattern: str) -> dict:
      """Search the repository for a literal or regex pattern via `git grep`.

      Returns up to 200 matching lines with file:line:text format, or an error dict.
      """
      safe = shlex.quote(pattern)
      cmd = f"git -C {shlex.quote(str(_REPO_ROOT))} grep -n --heading -E -e {safe}"
      try:
          proc = await asyncio.wait_for(
              asyncio.create_subprocess_shell(
                  cmd,
                  stdout=asyncio.subprocess.PIPE,
                  stderr=asyncio.subprocess.PIPE,
              ),
              timeout=_TIMEOUT_S,
          )
          stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_S)
          if proc.returncode == 1:
              return {"pattern": pattern, "matches": [], "note": "no matches"}
          if proc.returncode != 0:
              return {"pattern": pattern, "error": stderr.decode(errors="replace")[:2000]}
          lines = stdout.decode(errors="replace").splitlines()[:_MAX_LINES]
          return {"pattern": pattern, "matches": lines}
      except TimeoutError:
          return {"pattern": pattern, "error": "repo_search timed out"}
      except Exception as exc:
          logger.info("[repo_search] failed pattern=%r error=%s", pattern, exc)
          return {"pattern": pattern, "error": f"repo_search failed: {exc}"}
  ```

- [ ] **4.10: Test `repo_search` — exercise the real tree (integration-ish unit)**

  Create `apps/api/tests/unit/test_tool_repo_search.py`:
  ```python
  import pytest

  from app.tools.repo_search import repo_search


  @pytest.mark.unit
  async def test_repo_search_finds_known_symbol() -> None:
      result = await repo_search.ainvoke({"pattern": "create_deep_agent"})
      assert "matches" in result
      assert any("agent_factory.py" in line for line in result["matches"])


  @pytest.mark.unit
  async def test_repo_search_empty_on_garbage() -> None:
      result = await repo_search.ainvoke({"pattern": "zzz_this_should_not_exist_12345"})
      assert result.get("matches") == [] or result.get("note") == "no matches"
  ```

- [ ] **4.11: Add `repo_search` to `__init__.py`**

  Modify `apps/api/app/tools/__init__.py`:
  ```python
  from app.tools import web_search  # noqa: F401
  from app.tools import fetch_url  # noqa: F401
  from app.tools import repo_search  # noqa: F401
  ```

- [ ] **4.12: Run repo_search tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_tool_repo_search.py -v`
  Expected: 2 passed.

- [ ] **4.13: Verify all three tools register via singleton**

  Append to `apps/api/tests/unit/test_tool_registry.py`:
  ```python
  @pytest.mark.unit
  def test_singleton_registers_all_initial_tools() -> None:
      import app.tools  # noqa: F401 — triggers registration
      from app.tools.registry import registry
      assert {"web_search", "fetch_url", "repo_search"}.issubset(set(registry.names()))
  ```

- [ ] **4.14: Run full suite — must be green**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass (existing `/research` e2e still works because `services/search_tool.py` remains untouched).

- [ ] **4.15: Commit**

  ```bash
  git add apps/api/app/tools/ apps/api/tests/unit/test_tool_*.py apps/api/tests/unit/test_tool_registry.py
  git commit -m "feat(api): add web_search/fetch_url/repo_search tools with registration"
  ```

---

## Chunk 5: Classifier node + prompt

Rollout §14 step 3.

**Files:**
- Create: `apps/api/prompts/classifier/v1.md`
- Modify: `apps/api/prompts/active.yaml`
- Create: `apps/api/app/schemas/routing.py`
- Create: `apps/api/app/agents/classifier.py`
- Create: `apps/api/tests/unit/test_classifier.py`

### Tasks

- [ ] **5.1: Create classifier prompt**

  Create `apps/api/prompts/classifier/v1.md`:
  ```markdown
  You are a routing classifier. You MUST reply with exactly one JSON
  object matching this schema:

  {"intent": "<one of: chat, research, deep-research, summarize, code, planner>",
   "confidence": <float 0..1>}

  Rules:
  - "chat"          — casual Q&A, greetings, short factual questions.
  - "research"      — needs fresh web info but fits one agent loop (≤ 3 searches).
  - "deep-research" — multi-phase investigation; compound questions;
                      the user explicitly asks for a deep dive, comprehensive, or full report.
  - "summarize"     — user pastes content and asks for reduction, extraction, or tldr.
  - "code"          — code review, codebase Q&A, design critique on a snippet.
  - "planner"       — user asks for a checklist, plan, roadmap, or step-by-step breakdown.

  When uncertain, prefer a conservative confidence under 0.55 so the system
  falls back to "chat". If the current_intent hint matches your best guess,
  you may return that intent with any confidence ≥ 0.40.

  current_intent_hint: {current_intent}
  ```

- [ ] **5.2: Register classifier prompt in `active.yaml`**

  Modify `apps/api/prompts/active.yaml` — append:
  ```yaml
  main: v1
  researcher: v1
  critic: v1
  classifier: v1
  chat: v1
  research: v1
  summarize: v1
  code: v1
  planner: v1
  ```
  (Other new prompts are created in chunk 6; this single write keeps `active.yaml` in its final shape but will only load the files that exist. We verify this in step 5.3.)

- [ ] **5.3: Create placeholder prompts to keep registry loading clean**

  The `PromptRegistry.reload()` raises on empty `.md` files, and logs a warning when `active.yaml` names a prompt not yet on disk. To keep the module importable between chunks, create minimal placeholders now — chunks 6 refines them:

  Create `apps/api/prompts/chat/v1.md`:
  ```markdown
  You are a helpful assistant. Answer briefly.
  ```

  Create `apps/api/prompts/research/v1.md`:
  ```markdown
  You are a research assistant. Use the available tools when you need fresh
  information, then answer with citations.
  ```

  Create `apps/api/prompts/summarize/v1.md`:
  ```markdown
  Summarize the user's content. Preserve key facts; omit filler.
  ```

  Create `apps/api/prompts/code/v1.md`:
  ```markdown
  You are a code reviewer. Use repo_search and fetch_url when helpful.
  Cite file:line references.
  ```

  Create `apps/api/prompts/planner/v1.md`:
  ```markdown
  You turn goals into actionable step-by-step plans. Respond as a numbered list.
  ```

- [ ] **5.4: Write failing test — `ClassifierResult` schema**

  Create `apps/api/tests/unit/test_classifier.py`:
  ```python
  from unittest.mock import AsyncMock

  import pytest
  from langchain_core.messages import AIMessage, HumanMessage

  from app.agents.classifier import classify
  from app.schemas.routing import ClassifierResult


  @pytest.mark.unit
  async def test_classifier_returns_intent_and_confidence() -> None:
      fake_llm = AsyncMock()
      fake_llm.with_structured_output.return_value = fake_llm
      fake_llm.ainvoke.return_value = ClassifierResult(intent="chat", confidence=0.9, fallback_used=False)

      result = await classify(
          messages=[HumanMessage("hi")],
          current_intent=None,
          llm=fake_llm,
          prompt="stub",
      )
      assert result.intent == "chat"
      assert result.confidence == 0.9
      assert result.fallback_used is False


  @pytest.mark.unit
  async def test_classifier_exception_returns_fallback() -> None:
      fake_llm = AsyncMock()
      fake_llm.with_structured_output.return_value = fake_llm
      fake_llm.ainvoke.side_effect = RuntimeError("429")

      result = await classify(
          messages=[HumanMessage("hi")],
          current_intent=None,
          llm=fake_llm,
          prompt="stub",
      )
      assert result.intent == "chat"
      assert result.confidence == 0.0
      assert result.fallback_used is True
  ```

- [ ] **5.5: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/unit/test_classifier.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **5.6: Implement `ClassifierResult` schema + `RoutingEvent`**

  Create `apps/api/app/schemas/routing.py`:
  ```python
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
  ```

- [ ] **5.7: Implement `classify()`**

  Create `apps/api/app/agents/classifier.py`:
  ```python
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

      # Apply threshold + stickiness
      final = result
      if result.confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
          final = ClassifierResult(intent="chat", confidence=result.confidence, fallback_used=True)
      elif (
          current_intent == result.intent
          and result.confidence >= _STICKINESS_THRESHOLD
      ):
          final = result  # stickiness match — explicit no-op for readability

      return final
  ```

- [ ] **5.8: Run tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_classifier.py -v`
  Expected: 2 passed.

- [ ] **5.9: Add low-confidence + stickiness tests**

  Append to `apps/api/tests/unit/test_classifier.py`:
  ```python
  @pytest.mark.unit
  async def test_low_confidence_falls_back_to_chat() -> None:
      fake_llm = AsyncMock()
      fake_llm.with_structured_output.return_value = fake_llm
      fake_llm.ainvoke.return_value = ClassifierResult(
          intent="research", confidence=0.30, fallback_used=False,
      )
      result = await classify(
          messages=[HumanMessage("asdf qwerty")],
          current_intent=None,
          llm=fake_llm,
          prompt="stub",
      )
      assert result.intent == "chat"
      assert result.fallback_used is True


  @pytest.mark.unit
  async def test_stickiness_preserves_current_intent() -> None:
      fake_llm = AsyncMock()
      fake_llm.with_structured_output.return_value = fake_llm
      fake_llm.ainvoke.return_value = ClassifierResult(
          intent="research", confidence=0.45, fallback_used=False,
      )
      result = await classify(
          messages=[HumanMessage("tell me more")],
          current_intent="research",
          llm=fake_llm,
          prompt="stub",
      )
      assert result.intent == "research"
      assert result.fallback_used is False
  ```

- [ ] **5.10: Run tests — expect 4 passed**

  Run: `cd apps/api && pytest tests/unit/test_classifier.py -v`
  Expected: 4 passed.

- [ ] **5.11: Lint + type-check**

  Run: `cd apps/api && ruff check app/agents/classifier.py app/schemas/routing.py tests/unit/test_classifier.py && mypy app/agents/ app/schemas/routing.py`
  Expected: clean.

- [ ] **5.12: Full suite green (registry must still load all prompts)**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass — the new prompt files are valid, `PromptRegistry` loads them without warnings.

- [ ] **5.13: Commit**

  ```bash
  git add apps/api/prompts/ \
          apps/api/app/schemas/routing.py \
          apps/api/app/agents/classifier.py \
          apps/api/tests/unit/test_classifier.py
  git commit -m "feat(api): add classifier node with structured output and stickiness"
  ```

---

## Chunk 6: ReAct builder + five simple specialists

Rollout §14 step 4.

**Files:**
- Create: `apps/api/app/agents/builders/__init__.py`
- Create: `apps/api/app/agents/builders/react.py`
- Create: `apps/api/tests/unit/test_react_builder.py`

Prompts in `apps/api/prompts/chat/v1.md`, `research/v1.md`, `summarize/v1.md`, `code/v1.md`, `planner/v1.md` already exist from chunk 5 placeholders. Refine content here.

### Tasks

- [ ] **6.1: Refine the five specialist prompts**

  Overwrite `apps/api/prompts/chat/v1.md`:
  ```markdown
  You are a concise helpful assistant. Answer the user's question directly.
  If you do not know, say so. Do not invent facts. No preamble, no trailing summary.
  ```

  Overwrite `apps/api/prompts/research/v1.md`:
  ```markdown
  You are a research assistant. For questions needing fresh or external
  information, use the web_search or fetch_url tools. Cap yourself at 3
  tool calls. Answer with inline citations using [n] notation and list the
  sources at the end.
  ```

  Overwrite `apps/api/prompts/summarize/v1.md`:
  ```markdown
  Summarize the content the user provides. Preserve entities, numbers,
  and decisions. Drop filler and redundancy. Default format: a short
  paragraph followed by 3–7 bullet points unless the user asks otherwise.
  ```

  Overwrite `apps/api/prompts/code/v1.md`:
  ```markdown
  You are a code reviewer and codebase-aware assistant. Use repo_search to
  locate symbols and fetch_url for public docs. Cite file:line in every claim.
  Prefer pointing at existing code over writing new code unless asked.
  ```

  Overwrite `apps/api/prompts/planner/v1.md`:
  ```markdown
  You turn goals into actionable plans. Respond as an ordered list of steps
  with expected outcomes and rough effort estimates. Keep steps ≤ 1 day of work.
  Never invent prerequisites the user did not mention.
  ```

- [ ] **6.2: Write failing test for `build_react_agent`**

  Create `apps/api/tests/unit/test_react_builder.py`:
  ```python
  from pathlib import Path
  from textwrap import dedent
  from unittest.mock import MagicMock, patch

  import pytest

  from app.agents.specs import AgentSpec


  @pytest.fixture
  def fake_registries(tmp_path: Path) -> tuple[MagicMock, MagicMock, MagicMock]:
      from app.models.registry import ModelRegistry, ModelSpec
      from app.tools.registry import ToolRegistry

      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          fast:
            provider: openai
            model: gpt-4o-mini
            temperature: 0.3
            streaming: true
          main:
            provider: openai
            model: gpt-4o
            temperature: 0.7
            streaming: true
      """))
      model_reg = ModelRegistry(yaml_path=yaml_path, env={})
      # Mock build() so we do not initialize a real LLM client.
      model_reg.build = MagicMock(return_value=MagicMock(name="fake_llm"))  # type: ignore[method-assign]

      tool_reg = ToolRegistry()

      prompt_reg = MagicMock()
      prompt_reg.get.return_value = "You are a test agent."

      return model_reg, tool_reg, prompt_reg


  @pytest.mark.unit
  def test_build_react_agent_no_tools(fake_registries) -> None:
      model_reg, tool_reg, prompt_reg = fake_registries
      spec = AgentSpec(name="chat", model_role="fast", tools=[], prompt_name="chat")

      from app.agents.builders.react import build_react_agent

      with patch("app.agents.builders.react.create_react_agent") as mock_create:
          mock_create.return_value = "compiled-graph"
          result = build_react_agent(
              spec=spec,
              model_registry=model_reg,
              tool_registry=tool_reg,
              prompt_registry=prompt_reg,
          )

      assert result == "compiled-graph"
      args, kwargs = mock_create.call_args
      assert kwargs["tools"] == []
      assert kwargs["prompt"] == "You are a test agent."


  @pytest.mark.unit
  def test_build_react_agent_with_tools(fake_registries) -> None:
      from langchain_core.tools import tool as tool_deco

      model_reg, tool_reg, prompt_reg = fake_registries

      @tool_reg.register("web_search")
      @tool_deco
      def web_search(q: str) -> str:
          """stub"""
          return q

      @tool_reg.register("fetch_url")
      @tool_deco
      def fetch_url(u: str) -> str:
          """stub"""
          return u

      spec = AgentSpec(
          name="research",
          model_role="main",
          tools=["web_search", "fetch_url"],
          prompt_name="research",
      )

      from app.agents.builders.react import build_react_agent

      with patch("app.agents.builders.react.create_react_agent") as mock_create:
          mock_create.return_value = "compiled-graph"
          build_react_agent(
              spec=spec,
              model_registry=model_reg,
              tool_registry=tool_reg,
              prompt_registry=prompt_reg,
          )

      _, kwargs = mock_create.call_args
      assert [t.name for t in kwargs["tools"]] == ["web_search", "fetch_url"]
  ```

- [ ] **6.3: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/unit/test_react_builder.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **6.4: Implement `build_react_agent`**

  Create `apps/api/app/agents/builders/__init__.py`:
  ```python
  ```

  Create `apps/api/app/agents/builders/react.py`:
  ```python
  from typing import Any, Protocol

  from langgraph.prebuilt import create_react_agent

  from app.agents.specs import AgentSpec


  class _PromptRegistryProto(Protocol):
      def get(self, name: str, version: str | None = None) -> str: ...


  def build_react_agent(
      spec: AgentSpec,
      model_registry: Any,
      tool_registry: Any,
      prompt_registry: _PromptRegistryProto,
      prompt_version: str | None = None,
  ) -> Any:
      model = model_registry.build(spec.model_role)
      tools = tool_registry.get_many(spec.tools)
      prompt = prompt_registry.get(spec.prompt_name, version=prompt_version)
      return create_react_agent(
          model=model,
          tools=tools,
          prompt=prompt,
          name=spec.name,
      )
  ```

- [ ] **6.5: Run tests — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_react_builder.py -v`
  Expected: 2 passed.

- [ ] **6.6: Lint + type-check**

  Run: `cd apps/api && ruff check app/agents/builders/ tests/unit/test_react_builder.py && mypy app/agents/builders/`
  Expected: clean.

- [ ] **6.7: Full suite green**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass.

- [ ] **6.8: Commit**

  ```bash
  git add apps/api/prompts/ apps/api/app/agents/builders/ apps/api/tests/unit/test_react_builder.py
  git commit -m "feat(api): add ReAct builder and refined prompts for five specialists"
  ```

---

## Chunk 7: Deep-research builder

Rollout §14 step 5.

**Files:**
- Create: `apps/api/app/agents/builders/deep_research.py`
- Create: `apps/api/tests/unit/test_deep_research_builder.py`

Keep the existing `app/services/agent_factory.py` untouched — this chunk adds a NEW path. The existing path still works for the legacy `/research` tests.

### Tasks

- [ ] **7.1: Write failing test**

  Create `apps/api/tests/unit/test_deep_research_builder.py`:
  ```python
  from pathlib import Path
  from textwrap import dedent
  from unittest.mock import MagicMock, patch

  import pytest

  from app.agents.specs import AgentSpec


  @pytest.fixture
  def fake_registries(tmp_path: Path):
      from app.models.registry import ModelRegistry
      from app.tools.registry import ToolRegistry
      from langchain_core.tools import tool as tool_deco

      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          fast:
            provider: openai
            model: gpt-4o-mini
          main:
            provider: openai
            model: gpt-4o
      """))
      model_reg = ModelRegistry(yaml_path=yaml_path, env={})
      model_reg.build = MagicMock(return_value=MagicMock(name="fake_llm"))  # type: ignore[method-assign]

      tool_reg = ToolRegistry()

      @tool_reg.register("web_search")
      @tool_deco
      def web_search(q: str) -> str:
          """stub"""
          return q

      prompt_reg = MagicMock()
      prompt_reg.get.side_effect = lambda name, version=None: f"{name}-prompt"

      return model_reg, tool_reg, prompt_reg


  @pytest.mark.unit
  def test_build_deep_research_composes_subagents(fake_registries) -> None:
      model_reg, tool_reg, prompt_reg = fake_registries
      spec = next(
          s for s in __import__(
              "app.agents.specs", fromlist=["REGISTERED_SPECS"]
          ).REGISTERED_SPECS
          if s.name == "deep-research"
      )

      from app.agents.builders.deep_research import build_deep_research_agent

      with patch("app.agents.builders.deep_research.create_deep_agent") as mock_create:
          mock_create.return_value = MagicMock(name="deep_agent")
          build_deep_research_agent(
              spec=spec,
              model_registry=model_reg,
              tool_registry=tool_reg,
              prompt_registry=prompt_reg,
              checkpointer=None,
              store=None,
          )

      args, kwargs = mock_create.call_args
      assert kwargs["system_prompt"] == "main-prompt"
      assert [t.name for t in kwargs["tools"]] == ["web_search"]
      sub_names = {s.name for s in kwargs["subagents"]}
      assert sub_names == {"researcher", "critic"}
  ```

- [ ] **7.2: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/unit/test_deep_research_builder.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **7.3: Implement builder**

  Create `apps/api/app/agents/builders/deep_research.py`:
  ```python
  from typing import Any

  from deepagents import SubAgent, create_deep_agent

  from app.agents.specs import AgentSpec


  def build_deep_research_agent(
      spec: AgentSpec,
      model_registry: Any,
      tool_registry: Any,
      prompt_registry: Any,
      checkpointer: Any,
      store: Any,
      prompt_versions: dict[str, str] | None = None,
  ) -> Any:
      versions = prompt_versions or {}
      main_llm = model_registry.build(spec.model_role)

      sub_specs: list[SubAgent] = []
      for sub in spec.subagents:
          sub_specs.append(
              SubAgent(
                  name=sub.name,
                  description=_description_for(sub.name),
                  system_prompt=prompt_registry.get(sub.prompt_name, version=versions.get(sub.prompt_name)),
                  tools=tool_registry.get_many(sub.tools),
                  model=model_registry.build(sub.model_role),
              )
          )

      return create_deep_agent(
          model=main_llm,
          tools=tool_registry.get_many(spec.tools),
          subagents=sub_specs,
          system_prompt=prompt_registry.get(spec.prompt_name, version=versions.get(spec.prompt_name)),
          store=store,
          checkpointer=checkpointer,
      )


  def _description_for(name: str) -> str:
      return {
          "researcher": (
              "Deep-dive a single sub-topic: run searches, save raw results, "
              "return 150-word summary with citations."
          ),
          "critic": (
              "Review the draft report and list issues (unsupported claims, "
              "outdated info, contradictions)."
          ),
      }.get(name, name)
  ```

- [ ] **7.4: Run test — expect PASS**

  Run: `cd apps/api && pytest tests/unit/test_deep_research_builder.py -v`
  Expected: 1 passed.

- [ ] **7.5: Lint + type-check + full suite**

  Run: `cd apps/api && ruff check app/agents/builders/deep_research.py tests/unit/test_deep_research_builder.py && mypy app/agents/builders/ && pytest -x --tb=short`
  Expected: clean + all pass.

- [ ] **7.6: Commit**

  ```bash
  git add apps/api/app/agents/builders/deep_research.py apps/api/tests/unit/test_deep_research_builder.py
  git commit -m "feat(api): add deep_research builder wrapping create_deep_agent"
  ```

---

## Chunk 8: Supervisor graph

Rollout §14 step 6.

**Files:**
- Create: `apps/api/app/agents/supervisor_graph.py`
- Create: `apps/api/tests/integration/test_supervisor_graph.py`

### Tasks

- [ ] **8.1: Write failing integration test — graph compiles and has six specialist nodes + classifier**

  Create `apps/api/tests/integration/test_supervisor_graph.py`:
  ```python
  from pathlib import Path
  from textwrap import dedent
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest


  @pytest.fixture
  def registries(tmp_path: Path):
      from app.models.registry import ModelRegistry
      from app.tools.registry import ToolRegistry
      from langchain_core.tools import tool as tool_deco

      yaml_path = tmp_path / "models.yaml"
      yaml_path.write_text(dedent("""
          classifier:
            provider: openai
            model: gpt-4o-mini
            streaming: false
          fast:
            provider: openai
            model: gpt-4o-mini
          main:
            provider: openai
            model: gpt-4o
      """))
      model_reg = ModelRegistry(yaml_path=yaml_path, env={})
      model_reg.build = MagicMock(return_value=MagicMock(name="llm"))  # type: ignore[method-assign]

      tool_reg = ToolRegistry()
      for name in ("web_search", "fetch_url", "repo_search"):
          @tool_reg.register(name)
          @tool_deco
          def _stub(q: str, _n=name) -> str:
              """stub"""
              return f"{_n}:{q}"

      prompt_reg = MagicMock()
      prompt_reg.get.side_effect = lambda name, version=None: f"{name}-prompt"

      return model_reg, tool_reg, prompt_reg


  @pytest.mark.integration
  def test_supervisor_graph_compiles_with_all_six_specialists(registries) -> None:
      model_reg, tool_reg, prompt_reg = registries
      from app.agents.supervisor_graph import build_supervisor_graph

      with patch("app.agents.builders.deep_research.create_deep_agent") as mock_deep:
          mock_deep.return_value = MagicMock(name="deep_agent_subgraph")
          with patch("app.agents.builders.react.create_react_agent") as mock_react:
              mock_react.return_value = MagicMock(name="react_agent")
              graph = build_supervisor_graph(
                  model_registry=model_reg,
                  tool_registry=tool_reg,
                  prompt_registry=prompt_reg,
                  checkpointer=None,
                  store=None,
              )

      # All six specialist node names must be registered on the graph.
      node_names = set(graph.nodes.keys())
      assert {"classifier", "chat", "research", "deep-research",
              "summarize", "code", "planner"}.issubset(node_names)
  ```

- [ ] **8.2: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/integration/test_supervisor_graph.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **8.3: Implement `supervisor_graph.py`**

  Create `apps/api/app/agents/supervisor_graph.py`:
  ```python
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
  ```

- [ ] **8.4: Run test — expect PASS**

  Run: `cd apps/api && pytest tests/integration/test_supervisor_graph.py -v`
  Expected: 1 passed.

- [ ] **8.5: Lint + type-check + full suite**

  Run: `cd apps/api && ruff check app/agents/supervisor_graph.py tests/integration/test_supervisor_graph.py && mypy app/agents/ && pytest -x --tb=short`
  Expected: clean + all pass.

- [ ] **8.6: Commit**

  ```bash
  git add apps/api/app/agents/supervisor_graph.py apps/api/tests/integration/test_supervisor_graph.py
  git commit -m "feat(api): add supervisor graph wiring classifier and six specialists"
  ```

---

## Chunk 9: Shared runner

Rollout §14 step 7.

**Files:**
- Create: `apps/api/app/routers/_runner.py`
- Create: `apps/api/tests/integration/test_runner.py`

This chunk introduces the shared generator that both `/chat` (chunk 10) and the refactored `/research` (chunk 10) will call. It is pure wiring — no behavior change visible to callers yet.

### Tasks

- [ ] **9.1: Write failing test — runner emits `stream_start`, `intent_classified`, `text_delta`, `stream_end`**

  Create `apps/api/tests/integration/test_runner.py`:
  ```python
  import json
  from unittest.mock import AsyncMock, MagicMock

  import pytest


  @pytest.mark.integration
  async def test_runner_emits_expected_event_sequence() -> None:
      from app.routers._runner import run_graph

      # Fake graph: yields one AIMessageChunk via messages mode, then ends.
      from langchain_core.messages import AIMessageChunk

      async def fake_astream(*args, **kwargs):
          # Values snapshot (empty) then one AI chunk then final values snapshot
          yield ("values", {"messages": [], "files": {}})
          yield ("messages", (AIMessageChunk(content="Hello"), {}))

      fake_graph = MagicMock()
      fake_graph.astream = fake_astream
      fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

      events = []
      async for ev in run_graph(
          graph=fake_graph,
          question="hi",
          thread_id="t1",
          versions_used={"classifier": "v1"},
          force_intent="chat",   # short-circuit the classifier path
      ):
          events.append(ev)

      names = [e["event"] for e in events]
      assert names[0] == "stream_start"
      assert "intent_classified" in names
      assert "stream_end" == names[-1]

      ic = next(e for e in events if e["event"] == "intent_classified")
      data = json.loads(ic["data"])
      assert data["intent"] == "chat"
      assert data["fallback_used"] is False
  ```

- [ ] **9.2: Run test — expect FAIL**

  Run: `cd apps/api && pytest tests/integration/test_runner.py -v`
  Expected: `ModuleNotFoundError`.

- [ ] **9.3: Implement `_runner.py`**

  Create `apps/api/app/routers/_runner.py`:
  ```python
  import json
  import logging
  import traceback
  from collections.abc import AsyncGenerator
  from typing import Any

  from app.streaming import events
  from app.streaming.chunk_mapper import ChunkMapper

  logger = logging.getLogger(__name__)

  SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000


  async def run_graph(
      graph: Any,
      question: str,
      thread_id: str,
      versions_used: dict[str, str],
      force_intent: str | None,
  ) -> AsyncGenerator[dict, None]:
      mapper = ChunkMapper()
      final_report_parts: list[str] = []

      logger.info(
          "[RUNNER] invoked thread_id=%s force_intent=%s question=%r",
          thread_id, force_intent, question[:120],
      )
      yield events.stream_start(thread_id)

      if force_intent is not None:
          # `/research` bypass — no classifier runs.
          yield events.intent_classified(
              intent=force_intent,
              confidence=1.0,
              fallback_used=False,
          )
          emitted_ic = True
      else:
          emitted_ic = False

      try:
          async for mode, chunk in graph.astream(
              {"messages": [{"role": "user", "content": question}]},
              config={"configurable": {"thread_id": thread_id}},
              stream_mode=["values", "messages", "updates"],
          ):
              if not emitted_ic and mode == "updates" and isinstance(chunk, dict):
                  update = chunk.get("classifier")
                  if isinstance(update, dict) and "current_intent" in update:
                      yield events.intent_classified(
                          intent=update["current_intent"],
                          confidence=float(update.get("confidence", 0.0)),
                          fallback_used=bool(update.get("fallback_used", False)),
                      )
                      emitted_ic = True

              async for ev in mapper.process(mode, chunk):
                  if ev["event"] == "text_delta":
                      final_report_parts.append(json.loads(ev["data"])["content"])
                  yield ev

          if (
              not mapper.saw_compression
              and mapper.peak_tokens > SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS
          ):
              yield events.compression_triggered(
                  original_tokens=mapper.peak_tokens,
                  compressed_tokens=mapper.peak_tokens // 2,
                  synthetic=True,
              )

          try:
              final_state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
              usage = final_state.values.get("usage", {}) if final_state else {}
          except Exception:
              usage = {}

          yield events.stream_end(
              final_report="".join(final_report_parts),
              usage=usage,
              versions_used=versions_used,
          )
      except Exception as exc:
          logger.error("[RUNNER] stream error\n%s", traceback.format_exc())
          yield events.error(str(exc), recoverable=False)
  ```

- [ ] **9.4: Add `intent_classified` factory (required by runner)**

  Modify `apps/api/app/streaming/events.py` — append at the end:
  ```python
  def intent_classified(intent: str, confidence: float, fallback_used: bool) -> dict:
      return _sse(
          "intent_classified",
          {
              "intent": intent,
              "confidence": confidence,
              "fallback_used": fallback_used,
          },
      )
  ```

- [ ] **9.5: Run runner test — expect PASS**

  Run: `cd apps/api && pytest tests/integration/test_runner.py -v`
  Expected: 1 passed.

- [ ] **9.6: Lint + type-check + full suite**

  Run: `cd apps/api && ruff check app/routers/_runner.py app/streaming/events.py tests/integration/test_runner.py && mypy app/routers/_runner.py app/streaming/ && pytest -x --tb=short`
  Expected: clean + all pass.

- [ ] **9.7: Commit**

  ```bash
  git add apps/api/app/routers/_runner.py apps/api/app/streaming/events.py apps/api/tests/integration/test_runner.py
  git commit -m "feat(api): add shared graph runner with intent_classified SSE event"
  ```

---

## Chunk 10: `/chat` router, `/research` refactor, SSE + frontend

Rollout §14 steps 8–10.

**Files:**
- Create: `apps/api/app/schemas/chat.py`
- Create: `apps/api/app/routers/chat.py`
- Modify: `apps/api/app/routers/research.py` (refactor to use `_runner.run_graph`)
- Modify: `apps/api/app/main.py` (register chat router; build registries in lifespan)
- Create: `apps/api/tests/integration/test_chat_endpoint.py`
- Modify: `apps/api/tests/integration/test_research_endpoint.py` (assert new event)
- Modify: `apps/web/lib/types.ts`
- Modify: `apps/web/lib/useResearchStream.ts`
- Create: `apps/web/app/research/components/RoutedIntentBadge.tsx` (optional small UI)
- Modify: `apps/web/app/research/page.tsx` (render badge)
- Modify: relevant frontend tests in `apps/web/`

### Tasks

- [ ] **10.1: Add `ChatRequest` schema**

  Create `apps/api/app/schemas/chat.py`:
  ```python
  from pydantic import BaseModel, Field


  class ChatRequest(BaseModel):
      question: str = Field(..., min_length=3, max_length=2000)
      thread_id: str | None = None
      prompt_versions: dict[str, str] | None = None
  ```

- [ ] **10.2: Implement `/chat` router**

  Create `apps/api/app/routers/chat.py`:
  ```python
  from fastapi import APIRouter, Request
  from sse_starlette.sse import EventSourceResponse

  from app.routers._runner import run_graph
  from app.schemas.chat import ChatRequest
  from app.services.prompt_registry import registry as prompt_registry

  router = APIRouter(prefix="/chat", tags=["chat"])


  @router.post("")
  async def chat(payload: ChatRequest, request: Request) -> EventSourceResponse:
      overrides = payload.prompt_versions or {}
      versions_used = prompt_registry.resolve_versions(overrides)
      thread_id = payload.thread_id or "default-user"

      graph = request.app.state.supervisor_graph
      return EventSourceResponse(
          run_graph(
              graph=graph,
              question=payload.question,
              thread_id=thread_id,
              versions_used=versions_used,
              force_intent=None,
          )
      )
  ```

- [ ] **10.3: Refactor `/research` to reuse the runner with `force_intent="deep-research"`**

  Overwrite `apps/api/app/routers/research.py`:
  ```python
  from fastapi import APIRouter, Request
  from sse_starlette.sse import EventSourceResponse

  from app.routers._runner import run_graph
  from app.schemas.research import ResearchRequest
  from app.services.prompt_registry import registry as prompt_registry

  router = APIRouter(prefix="/research", tags=["research"])


  @router.post("")
  async def research(payload: ResearchRequest, request: Request) -> EventSourceResponse:
      overrides = payload.prompt_versions or {}
      versions_used = prompt_registry.resolve_versions(overrides)
      thread_id = payload.thread_id or "default-user"

      graph = request.app.state.deep_research_only_graph
      return EventSourceResponse(
          run_graph(
              graph=graph,
              question=payload.question,
              thread_id=thread_id,
              versions_used=versions_used,
              force_intent="deep-research",
          )
      )
  ```

- [ ] **10.4: Wire graphs into `main.py` lifespan**

  Overwrite `apps/api/app/main.py`:
  ```python
  import logging
  import os
  from collections.abc import AsyncGenerator
  from contextlib import asynccontextmanager
  from pathlib import Path

  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware

  from app.agents.supervisor_graph import (
      build_deep_research_only_graph,
      build_supervisor_graph,
  )
  from app.config.settings import settings
  from app.models.registry import ModelRegistry
  from app.routers import chat as chat_router
  from app.routers import research as research_router
  from app.services.prompt_registry import registry as prompt_registry
  from app.stores.memory_store import (
      get_checkpointer,
      get_store,
      lifespan_stores,
  )

  # Import tools package to trigger @register_tool decorators.
  import app.tools  # noqa: F401
  from app.tools.registry import registry as tool_registry

  logging.basicConfig(
      level=settings.LOG_LEVEL.upper(),
      format="%(levelname)-8s %(name)s — %(message)s",
  )


  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      prompt_registry.reload()

      model_registry = ModelRegistry(
          yaml_path=Path(__file__).parents[1] / "models.yaml",
          env=os.environ,
      )
      app.state.model_registry = model_registry
      app.state.tool_registry = tool_registry

      async with lifespan_stores():
          checkpointer = get_checkpointer()
          store = get_store()

          app.state.supervisor_graph = build_supervisor_graph(
              model_registry=model_registry,
              tool_registry=tool_registry,
              prompt_registry=prompt_registry,
              checkpointer=checkpointer,
              store=store,
          )
          app.state.deep_research_only_graph = build_deep_research_only_graph(
              model_registry=model_registry,
              tool_registry=tool_registry,
              prompt_registry=prompt_registry,
              checkpointer=checkpointer,
              store=store,
          )
          yield


  app = FastAPI(title="Deep Agents Research API", lifespan=lifespan)

  app.add_middleware(
      CORSMiddleware,
      allow_origins=settings.CORS_ORIGINS,
      allow_credentials=False,
      allow_methods=["POST", "OPTIONS"],
      allow_headers=["*"],
  )

  app.include_router(research_router.router)
  app.include_router(chat_router.router)


  @app.get("/health")
  def health() -> dict:
      return {"status": "ok"}
  ```

- [ ] **10.5: Integration test — `/chat` with `chat` intent (SSE happy path)**

  Create `apps/api/tests/integration/test_chat_endpoint.py`:
  ```python
  import json
  from unittest.mock import AsyncMock, MagicMock, patch

  import pytest
  from fastapi.testclient import TestClient


  @pytest.fixture
  def app_with_fakes():
      """Minimal app with the graph replaced by a fake that short-circuits routing."""
      from app.main import app

      async def fake_astream(*args, **kwargs):
          from langchain_core.messages import AIMessageChunk
          yield ("updates", {"classifier": {
              "current_intent": "chat",
              "confidence": 0.92,
              "fallback_used": False,
              "routing_history": [],
          }})
          yield ("messages", (AIMessageChunk(content="Hello!"), {}))

      fake_graph = MagicMock()
      fake_graph.astream = fake_astream
      fake_graph.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

      app.state.supervisor_graph = fake_graph
      yield app


  @pytest.mark.integration
  def test_chat_endpoint_emits_intent_classified(app_with_fakes) -> None:
      with TestClient(app_with_fakes) as client:
          with client.stream("POST", "/chat", json={"question": "hi there"}) as resp:
              assert resp.status_code == 200
              body = "".join(resp.iter_text())

      assert "event: stream_start" in body
      assert "event: intent_classified" in body
      assert "event: text_delta" in body
      assert "event: stream_end" in body

      # Parse the intent_classified event payload
      for chunk in body.split("\n\n"):
          if "event: intent_classified" in chunk:
              data_line = next(l for l in chunk.splitlines() if l.startswith("data: "))
              data = json.loads(data_line[len("data: "):])
              assert data["intent"] == "chat"
              assert data["confidence"] == 0.92
              assert data["fallback_used"] is False
              break
      else:
          pytest.fail("no intent_classified event found")
  ```

- [ ] **10.6: Update `test_research_endpoint.py` to expect the bypass `intent_classified` event**

  Find the existing `/research` SSE test (likely at `apps/api/tests/integration/test_research_endpoint.py` or similar). Add an assertion that the stream contains `event: intent_classified` with payload `{"intent":"deep-research","confidence":1.0,"fallback_used":false}` between `stream_start` and the first `text_delta`. If the file does not exist, create a sibling to 10.5 that targets `/research` and asserts the bypass payload.

- [ ] **10.7: Run backend tests — expect PASS**

  Run: `cd apps/api && pytest -x --tb=short`
  Expected: all pass, including the updated `/research` assertions.

- [ ] **10.8: Frontend — extend `SSEEventMap`**

  Modify `apps/web/lib/types.ts`. Locate the `SSEEventMap` type and add:
  ```ts
  intent_classified: {
    intent: string;
    confidence: number;
    fallback_used: boolean;
  };
  ```

- [ ] **10.9: Frontend — handle `intent_classified` in the reducer**

  Modify `apps/web/lib/useResearchStream.ts`. Find the reducer/switch that maps SSE events to state and add:
  - A new state field `routedIntent: string | null` (initial `null`).
  - Case for `intent_classified` that sets `routedIntent = event.intent`.
  - Expose `routedIntent` in the hook's return value.

- [ ] **10.10: Frontend — badge component**

  Create `apps/web/app/research/components/RoutedIntentBadge.tsx`:
  ```tsx
  type Props = { intent: string | null };

  export function RoutedIntentBadge({ intent }: Props) {
    if (!intent) return null;
    return (
      <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
        routed to: {intent}
      </span>
    );
  }
  ```

  Modify `apps/web/app/research/page.tsx` to import and render `<RoutedIntentBadge intent={routedIntent} />` near the header/status line.

- [ ] **10.11: Frontend — test the hook handles the new event**

  Add a vitest unit test for `useResearchStream`: feed a stream containing `intent_classified` and assert `routedIntent` updates. Follow the file's existing test pattern.

- [ ] **10.12: Run frontend tests + lint**

  Run:
  ```bash
  cd apps/web && npm test -- --run && npm run lint
  ```
  Expected: all pass.

- [ ] **10.13: Smoke-test end-to-end by hand (optional, requires real API keys)**

  Run the backend: `cd apps/api && uvicorn app.main:app --reload --port 8000`
  Run the frontend: `cd apps/web && npm run dev`
  Open `http://localhost:3000/research`, submit a question, verify:
  - `intent_classified` badge appears
  - text streams
  - deep-research panel fills only when the intent is `deep-research`

- [ ] **10.14: Commit**

  ```bash
  git add apps/api/app/schemas/chat.py \
          apps/api/app/routers/chat.py \
          apps/api/app/routers/research.py \
          apps/api/app/main.py \
          apps/api/tests/integration/test_chat_endpoint.py \
          apps/api/tests/integration/test_research_endpoint.py \
          apps/web/lib/types.ts \
          apps/web/lib/useResearchStream.ts \
          apps/web/app/research/components/RoutedIntentBadge.tsx \
          apps/web/app/research/page.tsx
  git commit -m "feat(api,web): add /chat router, refactor /research bypass, wire intent_classified SSE"
  ```

---

## Chunk 11: Cleanup — delete legacy code paths

Rollout §14 step 11.

**Files:**
- Delete: `apps/api/app/services/llm_factory.py` (replaced by `ModelRegistry.build()`)
- Delete: `apps/api/app/services/search_tool.py` (replaced by `app/tools/web_search.py`)
- Modify: `apps/api/app/services/agent_factory.py` (thin shim or delete if no callers)
- Delete: obsolete tests for the removed modules (if any)

### Tasks

- [ ] **11.1: Search for callers of `llm_factory` and `search_tool`**

  Run:
  ```bash
  grep -rn "from app.services.llm_factory" apps/api/app apps/api/tests
  grep -rn "from app.services.search_tool" apps/api/app apps/api/tests
  grep -rn "from app.services.agent_factory" apps/api/app apps/api/tests
  ```
  Expected: **no** production callers for `llm_factory` or `search_tool` (they were fully replaced). `agent_factory` may still be imported in tests.

- [ ] **11.2: Delete `llm_factory.py`**

  Run: `rm apps/api/app/services/llm_factory.py`

- [ ] **11.3: Delete `search_tool.py`**

  Run: `rm apps/api/app/services/search_tool.py`

- [ ] **11.4: Decide `agent_factory.py` — thin shim or delete**

  If step 11.1 shows `build_research_agent` is unused outside its own tests, delete both the module and its tests:
  ```bash
  rm apps/api/app/services/agent_factory.py
  rm apps/api/tests/unit/test_agent_factory.py   # if present
  ```
  Otherwise, leave it and mark the shim deprecated with a single comment.

- [ ] **11.5: Full suite green (final)**

  Run:
  ```bash
  cd apps/api && pytest -x --tb=short && ruff check . && mypy app/
  cd apps/web && npm test -- --run && npm run lint && npx tsc --noEmit
  ```
  Expected: everything clean and green.

- [ ] **11.6: Commit**

  ```bash
  git add -u apps/api/app/services/ apps/api/tests/
  git commit -m "chore(api): remove legacy llm_factory, search_tool, and agent_factory"
  ```

---

## Acceptance Criteria (entire plan)

1. **All tests green** after every chunk — `pytest -x` passes in `apps/api/`, `npm test -- --run` passes in `apps/web/`.
2. **`/chat`** routes correctly for each of the six intents (verified by integration tests with mocked LLMs).
3. **`/research`** preserves its current SSE event sequence, adding only one new event (`intent_classified`) with `{intent: "deep-research", confidence: 1.0, fallback_used: false}` emitted exactly once between `stream_start` and the first `text_delta`.
4. **Six specialist nodes** exist on the supervisor graph, plus the classifier node. Verified by `test_supervisor_graph.py`.
5. **Registries in lifespan**: `app.state.model_registry`, `app.state.tool_registry`, `app.state.supervisor_graph`, `app.state.deep_research_only_graph` all set after startup.
6. **OpenAI default**: with only `OPENAI_API_KEY` + `TAVILY_API_KEY` in `.env`, the API starts cleanly and all integration tests pass.
7. **No legacy code** remains: `llm_factory.py` and `search_tool.py` are gone; `agent_factory.py` is either a documented shim or deleted.
8. **Frontend badge**: `routed to: <intent>` appears in the UI after every `/chat` request.

---

## Hand-off

**Plan complete and saved to `docs/superpowers/specs/2026-04-14/supervisor-orchestration-plan.md`.**

**Execution path:** this harness supports subagents. After your review, the plan should be executed via **superpowers:subagent-driven-development** — one fresh subagent per chunk, with a two-stage review between chunks.

**Open hand-off questions:**

1. Commit this plan now, or hold until you've reviewed?
2. Run the implementation in the current branch (`main`) or spin up a worktree first (via `using-git-worktrees`)?
3. One subagent per chunk (11 subagents total) or one per rollout-step grouping (fewer)? My lean: one per chunk — matches `subagent-driven-development`'s context-hygiene model.

*End of plan.*
