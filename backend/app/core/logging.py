"""app/core/logging.py — Structured logging setup with structlog.

- JSON renderer in production (APP_ENV=production)
- Console renderer in development
- UTC timestamp processor
- Scrub processor: removes sensitive values containing token, password, secret, key, authorization
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

# Sensitive field name substrings to scrub from log values
_SENSITIVE_SUBSTRINGS = frozenset(["token", "password", "secret", "key", "authorization"])

_SCRUB_PLACEHOLDER = "[REDACTED]"


def _scrub_sensitive_processor(
    logger: WrappedLogger,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Remove sensitive values from log event dict.

    Any key whose name contains 'token', 'password', 'secret', 'key', or
    'authorization' (case-insensitive) has its value replaced with [REDACTED].
    """
    for field_name in list(event_dict.keys()):
        if any(sub in field_name.lower() for sub in _SENSITIVE_SUBSTRINGS):
            event_dict[field_name] = _SCRUB_PLACEHOLDER
    return event_dict


def configure_logging(app_env: str = "development") -> None:
    """Configure structlog for the application.

    Args:
        app_env: Application environment string ('production' or other).
    """
    is_production = app_env == "production"

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _scrub_sensitive_processor,
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger instance."""
    return structlog.get_logger(name)  # type: ignore[return-value]
