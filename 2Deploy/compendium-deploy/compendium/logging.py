"""Structured logging: single-line JSON to stderr via structlog."""

from __future__ import annotations

import sys

import structlog

_configured = False


def configure_logging() -> None:
    """Configure structlog to emit single-line JSON events to stderr.

    Each event carries ``event``, ``level``, and an ISO-8601 ``ts``.
    """
    global _configured
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger, configuring logging on first use."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
