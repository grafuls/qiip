"""Structured logging configuration using structlog.

Provides JSON output for production and colored console output for
development.  Call ``configure_logging()`` once during application
startup (inside the FastAPI lifespan context manager).
"""

import logging

import structlog


def configure_logging(
    *,
    json_output: bool = False,
    log_level: int = logging.INFO,
) -> None:
    """Configure structlog with the appropriate renderer and log level.

    Args:
        json_output: Use JSON renderer when ``True``, console renderer
            when ``False``.
        log_level: Minimum log level to emit (default ``logging.INFO``).
    """
    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=json_output,
    )
