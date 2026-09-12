"""
Celery application configuration for the forecasting platform.

Task beat schedule defines recurring data-ingestion, forecasting,
and alert jobs.  All times are UTC.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("titan_forecast")

# Read configuration from Django settings (CELERY_ prefix)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()


# ── Periodic task schedule ────────────────────────────────────────────────────
app.conf.beat_schedule = {

    # ── Economic calendar ingestion ───────────────────────────────────────────
    "ingest-calendar-every-6-hours": {
        "task": "events.tasks.ingest_economic_calendar",
        "schedule": crontab(minute=0, hour="*/6"),
        "kwargs": {"days_ahead": 14},
    },

    # ── Macro data ingestion ──────────────────────────────────────────────────
    "ingest-bls-daily": {
        "task": "macro_data.tasks.ingest_bls_series",
        "schedule": crontab(minute=30, hour=8),   # 08:30 UTC
    },
    "ingest-fred-daily": {
        "task": "macro_data.tasks.ingest_fred_series",
        "schedule": crontab(minute=0, hour=9),    # 09:00 UTC
    },
    "ingest-cleveland-fed-daily": {
        "task": "macro_data.tasks.ingest_cleveland_fed",
        "schedule": crontab(minute=0, hour=10),
    },

    # ── Market data ingestion ─────────────────────────────────────────────────
    "ingest-market-data-every-hour": {
        "task": "macro_data.tasks.ingest_market_data",
        "schedule": crontab(minute=5),            # 5 minutes past every hour
    },

    # ── Forecast runs ─────────────────────────────────────────────────────────
    # Run a full forecast for every upcoming event 24 h before release
    "run-forecasts-every-2-hours": {
        "task": "forecasting.tasks.run_upcoming_event_forecasts",
        "schedule": crontab(minute=15, hour="*/2"),
    },

    # ── Data quality check ────────────────────────────────────────────────────
    "data-quality-check-daily": {
        "task": "data_sources.tasks.run_data_quality_checks",
        "schedule": crontab(minute=0, hour=6),
    },

    # ── Alert dispatch ────────────────────────────────────────────────────────
    # Dispatch pre-release alerts 30 min before scheduled release
    "send-pre-release-alerts-every-5-min": {
        "task": "alerts.tasks.dispatch_pre_release_alerts",
        "schedule": crontab(minute="*/5"),
    },
}
