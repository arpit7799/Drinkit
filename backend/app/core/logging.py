"""
Structured logging setup using `structlog`.

We standardize on structured (key-value / JSON) logs so that logs are
machine-parseable in production (e.g. shipped to a log aggregator) while
staying human-readable during local development.

Call `configure_logging()` once at application startup (see
`app/main.py`). After that, any module can do:

    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("report_created", report_id=report.id, user_id=user.id)
"""

import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure stdlib logging + structlog processors based on app settings."""
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.LOG_JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )