"""app/core/logging.py — Structured logging setup with deep sensitive data scrubbing (T-052).

- JSON renderer in production (APP_ENV=production)
- Console renderer in development
- UTC timestamp processor
- Multi-layer Scrub processor:
  * Masks sensitive field keys (token, password, secret, key, authorization, cookie, credential)
  * Pattern-scrubs sensitive values (Bearer tokens, Telegram bot tokens, Gemini API keys, Fernet keys, passwords in URLs)
  * Recursively scrubs nested dicts and lists
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

# Sensitive field name substrings to scrub from log values
_SENSITIVE_SUBSTRINGS = frozenset([
    "token",
    "password",
    "secret",
    "key",
    "authorization",
    "cookie",
    "credential",
    "access_token",
    "refresh_token",
])

_SCRUB_PLACEHOLDER = "[REDACTED]"

# Regex patterns for values that may leak in message text or unkeyed strings
_VALUE_PATTERNS = [
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED]"),
    # Gemini API keys (AIzaSy...)
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "[REDACTED_GEMINI_KEY]"),
    # Telegram Bot tokens (e.g. 123456789:ABCdefGHI...)
    (re.compile(r"\b[0-9]{9,10}:[a-zA-Z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_TOKEN]"),
    # Fernet encryption keys (44-char base64 ending in '=')
    (re.compile(r"\b[A-Za-z0-9_-]{43}=\b"), "[REDACTED_FERNET_KEY]"),
    # Passwords embedded in URLs (e.g. postgresql://user:pass@host)
    (re.compile(r"(://[^:]+:)([^@]+)(@)"), r"\1[REDACTED]\3"),
]


def scrub_string_value(val: str) -> str:
    """Apply all sensitive value regex patterns to a string."""
    cleaned = val
    for pattern, replacement in _VALUE_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def scrub_data_structure(data: Any) -> Any:
    """Recursively scrub sensitive keys and patterns from dicts, lists, and strings."""
    if isinstance(data, dict):
        scrubbed_dict = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(sub in k_str for sub in _SENSITIVE_SUBSTRINGS):
                scrubbed_dict[k] = _SCRUB_PLACEHOLDER
            else:
                scrubbed_dict[k] = scrub_data_structure(v)
        return scrubbed_dict

    if isinstance(data, list):
        return [scrub_data_structure(item) for item in data]

    if isinstance(data, str):
        return scrub_string_value(data)

    return data


def _scrub_sensitive_processor(
    logger: WrappedLogger,  # noqa: ARG001
    method: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Remove sensitive values from log event dict.

    Any key whose name contains sensitive substrings has its value replaced with [REDACTED].
    Any string value containing known secret patterns is pattern-scrubbed.
    """
    return scrub_data_structure(event_dict)


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
