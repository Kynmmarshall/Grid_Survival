"""Simple logging helper for the online_play stack.

Provides a lightweight, centralized logger configuration and a small
wrapper to obtain a module-scoped logger. This aims to replace ad-hoc
print() statements with proper logging while keeping the surface area small
and opt-in via environment variable.
"""

import logging
import os


_LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


def _configured_level() -> int:
    lvl = os.getenv("GRID_SURVIVAL_LOG_LEVEL", "INFO").upper()
    return _LEVEL_MAP.get(lvl, logging.INFO)


def _ensure_configured():
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=_configured_level(),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def get_logger(name: str | None = None) -> logging.Logger:
    _ensure_configured()
    if name:
        return logging.getLogger(f"grid_survival.online_play.{name}")
    return logging.getLogger("grid_survival.online_play")
