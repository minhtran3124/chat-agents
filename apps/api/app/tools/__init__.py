# Eager import of every tool module so @register_tool decorators fire.
from app.tools import (
    fetch_url,  # noqa: F401
    repo_search,  # noqa: F401
    web_search,  # noqa: F401
)
