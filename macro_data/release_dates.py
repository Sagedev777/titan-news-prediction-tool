"""
Release-date utilities for point-in-time data management.

The get_available_data function is the mandatory entry point for all
feature fetching.  No model may call DataObservation.objects.filter()
directly — it must go through this function to ensure point-in-time
correctness.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from django.utils import timezone

from .normalization import build_series_dataframe
from .series_registry import SeriesDefinition, get_event_series

logger = logging.getLogger("macro_data")


def get_available_data(
    provider: str,
    series_id: str,
    as_of: datetime,
    lookback_days: int = 730,
    seasonal_adjustment: str | None = None,
) -> pd.DataFrame:
    """
    Return observations available at `as_of` (point-in-time filter).

    MANDATORY: All feature fetching in forecasting and backtesting
    must use this function.  Never bypass the as_of filter.

    Parameters
    ----------
    provider : 'bls', 'fred', 'cleveland_fed', etc.
    series_id : Provider series identifier.
    as_of : Forecast timestamp.  Only data published <= as_of is returned.
    lookback_days : How many days back to look.
    seasonal_adjustment : Filter 'SA' or 'NSA' if needed.

    Returns
    -------
    pd.DataFrame with index=observation_date, column 'value'.
    May be empty if no data is available — callers must handle this.
    """
    start_cutoff = as_of - timedelta(days=lookback_days)

    df = build_series_dataframe(
        provider=provider,
        series_id=series_id,
        as_of=as_of,
        seasonal_adjustment=seasonal_adjustment,
    )

    if df.empty:
        logger.warning(
            f"get_available_data: No data for {provider}/{series_id} "
            f"as_of={as_of.isoformat()}"
        )
        return df

    # Apply lookback window
    df = df[df.index >= pd.Timestamp(start_cutoff, tz="UTC")]

    return df


def get_features_for_event(
    event_code: str,
    as_of: datetime,
    lookback_days: int = 730,
) -> dict[str, pd.DataFrame]:
    """
    Return all available feature series for an event at the given time.

    Uses the series registry to determine which series are relevant.
    Enforces point-in-time filtering on every series.

    Returns
    -------
    dict of {internal_name: DataFrame}.
    Empty DataFrames are included (callers must check .empty).
    """
    series_defs = get_event_series(event_code)
    result: dict[str, pd.DataFrame] = {}

    for sdef in series_defs:
        try:
            df = get_available_data(
                provider=sdef.provider,
                series_id=sdef.series_id,
                as_of=as_of,
                lookback_days=lookback_days,
            )
            result[sdef.internal_name] = df
        except Exception as exc:
            logger.error(
                f"get_features_for_event: error fetching {sdef.internal_name}: {exc}",
                exc_info=True,
            )
            result[sdef.internal_name] = pd.DataFrame()

    return result


def get_market_data_as_of(
    symbol: str,
    timeframe: str,
    as_of: datetime,
    lookback_candles: int = 200,
) -> pd.DataFrame:
    """
    Return market OHLCV data available at as_of.

    For backtesting: only candles with timestamp_utc < as_of are returned.
    """
    from .models import MarketObservation

    qs = MarketObservation.objects.filter(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc__lt=as_of,
    ).order_by("-timestamp_utc")[:lookback_candles]

    rows = list(qs.values("timestamp_utc", "open", "high", "low", "close", "volume"))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.sort_values("timestamp_utc").set_index("timestamp_utc")
