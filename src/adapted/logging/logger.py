from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from ..config import settings

_LOG_LEVEL = logging.DEBUG if settings.debug else logging.INFO


def _configure() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=_LOG_LEVEL)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_LOG_LEVEL),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.getLogger("uvicorn").handlers.clear()
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str = "adapted") -> structlog.stdlib.BoundLogger:
    _configure()
    return structlog.get_logger(name)


def bind_task(logger: Any, task_id: str, correlation_id: str, **extra: Any) -> Any:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=task_id, correlation_id=correlation_id, **extra)
    return logger
