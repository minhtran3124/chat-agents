import logging

import structlog


def configure_structlog() -> None:
    """Configure structlog for JSON output with contextvar merging.

    Called once from the FastAPI lifespan. Processors, in order:
      - merge contextvars (request_id, thread_id, prompt_versions)
      - add log level
      - ISO timestamp
      - JSON render
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
