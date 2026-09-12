"""
Persistence helpers for macro and market data.

These functions translate provider-returned dicts into Django ORM records.
All functions use update_or_create with the vintage_date as part of
the natural key so historical revisions are preserved, not overwritten.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import DataObservation, MarketObservation

logger = logging.getLogger("macro_data")


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


@transaction.atomic
def persist_data_observations(
    provider: str,
    series_id: str,
    observations: list[dict],
    unit: str = "",
    seasonal_adjustment: str = "",
) -> int:
    """
    Persist a list of observation dicts to DataObservation.

    Each observation dict must contain at minimum:
    - observation_date (datetime)
    - value (float)

    Optional keys:
    - vintage_date (datetime)
    - publication_time_utc (datetime)
    - publication_approximate (bool)

    Returns the number of records created or updated.
    """
    saved = 0
    for obs in observations:
        obs_date = obs.get("observation_date")
        value = obs.get("value")
        if obs_date is None or value is None:
            continue

        vintage_date = obs.get("vintage_date")
        publication_time = obs.get("publication_time_utc")
        publication_approx = obs.get("publication_approximate", False)

        try:
            _, created = DataObservation.objects.update_or_create(
                provider=provider,
                series_id=series_id,
                observation_date=obs_date,
                vintage_date=vintage_date,
                defaults=dict(
                    publication_time_utc=publication_time,
                    retrieved_at=timezone.now(),
                    value=float(value),
                    unit=unit,
                    seasonal_adjustment=seasonal_adjustment,
                    publication_approximate=publication_approx,
                    raw_payload_hash=_hash(obs),
                ),
            )
            saved += 1
        except Exception as exc:
            logger.error(
                f"persist_data_observations error: {provider}/{series_id} "
                f"obs_date={obs_date}: {exc}",
                exc_info=True,
            )

    return saved


@transaction.atomic
def persist_market_observations(
    symbol: str,
    timeframe: str,
    candles: list[dict],
    provider: str = "twelvedata",
) -> int:
    """
    Persist OHLCV candles to MarketObservation.

    Each candle dict must contain:
    - timestamp_utc (datetime)
    - open, high, low, close (float)
    - volume (float, default 0)
    - is_delayed (bool, default False)
    """
    saved = 0
    for candle in candles:
        ts = candle.get("timestamp_utc")
        if ts is None:
            continue
        try:
            MarketObservation.objects.update_or_create(
                provider=provider,
                symbol=symbol,
                timeframe=timeframe,
                timestamp_utc=ts,
                defaults=dict(
                    open=float(candle["open"]),
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                    close=float(candle["close"]),
                    volume=float(candle.get("volume") or 0),
                    is_delayed=candle.get("is_delayed", False),
                ),
            )
            saved += 1
        except Exception as exc:
            logger.error(
                f"persist_market_observations error: {symbol}/{timeframe} ts={ts}: {exc}",
                exc_info=True,
            )

    return saved


@transaction.atomic
def persist_cleveland_fed_nowcast(record: dict) -> DataObservation | None:
    """
    Persist a Cleveland Fed nowcast entry as DataObservation rows.

    Stores headline and core estimates as separate series:
    - CLEVELAND_FED__HEADLINE_CPI_MOM
    - CLEVELAND_FED__HEADLINE_CPI_YOY
    - CLEVELAND_FED__CORE_CPI_MOM
    - CLEVELAND_FED__CORE_CPI_YOY
    """
    nowcast_date = record.get("nowcast_date")
    if not nowcast_date:
        return None

    fields = {
        "CLEVELAND_FED__HEADLINE_CPI_MOM": record.get("headline_cpi_mom"),
        "CLEVELAND_FED__HEADLINE_CPI_YOY": record.get("headline_cpi_yoy"),
        "CLEVELAND_FED__CORE_CPI_MOM": record.get("core_cpi_mom"),
        "CLEVELAND_FED__CORE_CPI_YOY": record.get("core_cpi_yoy"),
    }

    saved_count = 0
    for series_id, value in fields.items():
        if value is None:
            continue
        try:
            DataObservation.objects.update_or_create(
                provider="cleveland_fed",
                series_id=series_id,
                observation_date=nowcast_date,
                vintage_date=record.get("retrieved_at"),
                defaults=dict(
                    retrieved_at=record.get("retrieved_at", timezone.now()),
                    value=float(value),
                    unit="pct",
                    seasonal_adjustment="SA",
                    publication_approximate=True,
                    raw_payload_hash=_hash(record),
                ),
            )
            saved_count += 1
        except Exception as exc:
            logger.error(f"Cleveland Fed persist error {series_id}: {exc}", exc_info=True)

    return saved_count
