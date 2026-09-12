"""
Structured logging configuration for the forecasting platform.

Uses structlog for structured JSON output in production and
coloured console output in development (DEBUG=True).

IMPORT SAFETY NOTE
------------------
This file is loaded by config/settings.py via importlib.util, NOT via the
normal `import config.logging` path.  That is intentional: importing via the
`config` package would trigger config/__init__.py which imports the Celery app
mid-way through settings initialisation and causes a circular import.

Do NOT add any import of `config`, `celery`, or any Django app module at the
top level of this file.  Only stdlib imports are safe here.
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path


def configure_logging(debug: bool, base_dir: Path) -> None:
    """
    Configure the Python / Django logging stack.

    This is called from settings.py after LOGGING_CONFIG = None.
    Setting LOGGING_CONFIG = None prevents Django from applying its
    default configuration so we can apply our own here.
    """

    log_level = "DEBUG" if debug else "INFO"

    # Create logs directory for file handler
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": (
                    "%(asctime)s [%(levelname)s] %(name)s "
                    "(%(filename)s:%(lineno)d) — %(message)s"
                ),
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            },
            "json": {
                "()": "logging.Formatter",
                "fmt": (
                    '{"time":"%(asctime)s","level":"%(levelname)s",'
                    '"logger":"%(name)s","module":"%(module)s",'
                    '"line":%(lineno)d,"message":"%(message)s"}'
                ),
                "datefmt": "%Y-%m-%dT%H:%M:%SZ",
            },
            "simple": {
                "format": "%(levelname)s %(name)s — %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose" if debug else "json",
                "level": log_level,
            },
            "file_general": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "general.log"),
                "maxBytes": 10 * 1024 * 1024,   # 10 MB
                "backupCount": 5,
                "formatter": "json",
                "level": "INFO",
            },
            "file_forecast": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "forecast.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "formatter": "json",
                "level": "DEBUG",
            },
            "file_data_sources": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "data_sources.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,
                "formatter": "json",
                "level": "DEBUG",
            },
            "file_errors": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "errors.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "json",
                "level": "ERROR",
            },
        },
        "loggers": {
            # Django internals
            "django": {
                "handlers": ["console", "file_general"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console", "file_errors"],
                "level": "ERROR",
                "propagate": False,
            },
            # Our application modules
            "events": {
                "handlers": ["console", "file_general"],
                "level": log_level,
                "propagate": False,
            },
            "data_sources": {
                "handlers": ["console", "file_data_sources"],
                "level": log_level,
                "propagate": False,
            },
            "macro_data": {
                "handlers": ["console", "file_general"],
                "level": log_level,
                "propagate": False,
            },
            "forecasting": {
                "handlers": ["console", "file_forecast"],
                "level": log_level,
                "propagate": False,
            },
            "market_reaction": {
                "handlers": ["console", "file_forecast"],
                "level": log_level,
                "propagate": False,
            },
            "backtesting": {
                "handlers": ["console", "file_forecast"],
                "level": log_level,
                "propagate": False,
            },
            "alerts": {
                "handlers": ["console", "file_general"],
                "level": log_level,
                "propagate": False,
            },
            # Celery
            "celery": {
                "handlers": ["console", "file_general"],
                "level": "INFO",
                "propagate": False,
            },
            # Root catch-all
            "": {
                "handlers": ["console", "file_general", "file_errors"],
                "level": log_level,
            },
        },
    }

    logging.config.dictConfig(config)
