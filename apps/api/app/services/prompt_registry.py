# apps/api/app/services/prompt_registry.py
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_V1_FALLBACK = "v1"
_ACTIVE_FILE = "active.yaml"


class PromptRegistry:
    """File-backed prompt version registry.

    Loads all ``prompts/{name}/{version}.md`` files at construction time.
    Reads ``active.yaml`` to determine the production default version per prompt.

    Use the module-level ``registry`` singleton in application code.
    Construct a fresh instance (with tmp_path) in tests.
    """

    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir
        self._prompts: dict[str, dict[str, str]] = {}
        self._active: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Re-read all prompt files and active.yaml from disk."""
        if not self._dir.is_dir():
            raise RuntimeError(
                f"Prompts directory not found: {self._dir}. "
                "Create the prompts/ directory at the repo root."
            )

        active_path = self._dir / _ACTIVE_FILE
        if not active_path.exists():
            raise RuntimeError(
                f"prompts/active.yaml not found: {active_path}. "
                "Create active.yaml mapping each prompt name to its active version."
            )

        with active_path.open() as f:
            raw_active: dict[str, Any] = yaml.safe_load(f) or {}

        prompts: dict[str, dict[str, str]] = {}
        for name_dir in sorted(self._dir.iterdir()):
            if not name_dir.is_dir():
                continue
            name = name_dir.name
            versions: dict[str, str] = {}
            for md_file in sorted(name_dir.glob("*.md")):
                version = md_file.stem
                text = md_file.read_text().strip()
                if not text:
                    raise ValueError(
                        f"Prompt file '{name}/{md_file.name}' is empty. "
                        "Add prompt text or delete the file."
                    )
                versions[version] = text
            if versions:
                prompts[name] = versions

        active: dict[str, str] = {}
        for name in prompts:
            if name in raw_active:
                active[name] = raw_active[name]
            else:
                logger.warning(
                    "[PROMPT_REGISTRY] No active.yaml entry for '%s', falling back to '%s'",
                    name,
                    _V1_FALLBACK,
                )
                active[name] = _V1_FALLBACK

        self._prompts = prompts
        self._active = active
        logger.info(
            "[PROMPT_REGISTRY] Loaded prompts=%s active=%s",
            sorted(prompts),
            active,
        )

    def get(self, name: str, version: str | None = None) -> str:
        """Return prompt text for *name*, using *version* or the active default."""
        if name not in self._prompts:
            raise KeyError(
                f"Unknown prompt '{name}'. Available: {', '.join(sorted(self._prompts))}"
            )
        resolved = version or self._active.get(name, _V1_FALLBACK)
        versions = self._prompts[name]
        if resolved not in versions:
            raise KeyError(
                f"Unknown version '{resolved}' for '{name}'. "
                f"Available: {', '.join(sorted(versions))}"
            )
        return versions[resolved]

    def resolve_versions(self, overrides: dict[str, str]) -> dict[str, str]:
        """Merge overrides with active defaults.

        Only known prompt names are included in the result.
        Unknown keys in *overrides* are silently ignored.
        """
        return {name: overrides.get(name, active_ver) for name, active_ver in self._active.items()}

    def list_versions(self, name: str) -> list[str]:
        """Return sorted list of available version keys for *name*."""
        if name not in self._prompts:
            raise KeyError(
                f"Unknown prompt '{name}'. Available: {', '.join(sorted(self._prompts))}"
            )
        return sorted(self._prompts[name])

    def active_versions(self) -> dict[str, str]:
        """Return a copy of the active.yaml mapping."""
        return dict(self._active)


# Module-level singleton — import and use directly in application code.
# Path resolution: chat-agents/apps/api/app/services/prompt_registry.py
#   parents[0] = services/  parents[1] = app/  parents[2] = api/  (prompts/ lives here)
registry = PromptRegistry(prompts_dir=Path(__file__).parents[2] / "prompts")
