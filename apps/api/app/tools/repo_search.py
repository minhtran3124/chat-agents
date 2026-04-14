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
