"""Celery tasks for macro and market data ingestion."""
import logging
from celery import shared_task

logger = logging.getLogger("macro_data")


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_bls_series(self) -> dict:
    try:
        from data_sources.bls import BLSProvider
        return BLSProvider().ingest_series()
    except Exception as exc:
        logger.error(f"BLS ingestion failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_fred_series(self) -> dict:
    try:
        from data_sources.fred import FREDProvider
        return FREDProvider().ingest_series()
    except Exception as exc:
        logger.error(f"FRED ingestion failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def ingest_cleveland_fed(self) -> dict:
    try:
        from data_sources.cleveland_fed import ClevelandFedProvider
        return ClevelandFedProvider().ingest_nowcast()
    except Exception as exc:
        logger.error(f"Cleveland Fed ingestion failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_market_data(self) -> dict:
    try:
        from data_sources.market_data import get_market_data_provider
        return get_market_data_provider().ingest_recent(days_back=7)
    except Exception as exc:
        logger.error(f"Market data ingestion failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
