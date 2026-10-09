import logging
from collections import deque

import structlog

from app.config import get_settings


# Last few hundred log events, kept in memory for the admin log screen. Per process only.
RECENT_LOGS: deque[dict] = deque(maxlen=500)


def _remember(_, method: str, event: dict) -> dict:
    RECENT_LOGS.append({"level": method, "event": event.get("event"), "timestamp": event.get("timestamp"), "tenant": event.get("tenant"), "fields": {k: str(v)[:200] for k, v in event.items() if k not in ("event", "timestamp", "tenant", "level", "exc_info")}})
    return event


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _remember,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer() if settings.is_production else structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("claimshield")
