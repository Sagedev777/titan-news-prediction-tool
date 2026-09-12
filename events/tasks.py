"""
Celery tasks for event ingestion.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("events")


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_economic_calendar(self, days_ahead: int = 14) -> dict:
    """
    Pull economic calendar events from the configured provider.

    Only HIGH-impact events are persisted in the database.
    All other events are written to the diagnostics/excluded table.
    """
    try:
        from data_sources.trading_economics import TradingEconomicsProvider
        from .services import upsert_economic_event, upsert_economic_release

        provider = TradingEconomicsProvider()
        result = provider.ingest_calendar(days_ahead=days_ahead)

        logger.info(
            "ingest_economic_calendar complete",
            extra={
                "ingested": result.get("ingested", 0),
                "excluded": result.get("excluded", 0),
                "errors": result.get("errors", 0),
            },
        )
        return result

    except Exception as exc:
        logger.error(f"ingest_economic_calendar failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
