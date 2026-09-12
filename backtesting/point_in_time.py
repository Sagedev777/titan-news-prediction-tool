"""
Point-in-time data accessor for backtesting.

MANDATORY rules:
- A backtest simulated at time T may only use data with publication_time_utc <= T.
- Never use current (revised) values in place of vintage values.
- Never use future market candles.
- If exact publication time is unknown, use retrieved_at as conservative proxy
  and mark the record with publication_approximate=True.
- Records marked approximate are excluded from strict backtests.

This module implements all PIT-correct data access for backtesting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd

from macro_data.release_dates import get_available_data, get_market_data_as_of

logger = logging.getLogger("backtesting")


class PointInTimeDataAccessor:
    """
    PIT-correct data accessor for backtesting.

    Usage:
        accessor = PointInTimeDataAccessor(as_of=forecast_time)
        cpi_df = accessor.get_series("bls", "CUSR0000SA0")
        market_df = accessor.get_market("EURUSD", "1h")
    """

    def __init__(self, as_of: datetime, strict: bool = True):
        """
        Parameters
        ----------
        as_of : The simulated forecast time.
        strict : If True, exclude records with publication_approximate=True.
        """
        self.as_of = as_of
        self.strict = strict

    def get_series(
        self,
        provider: str,
        series_id: str,
        lookback_days: int = 730,
    ) -> pd.DataFrame:
        """Return series observations available at as_of."""
        df = get_available_data(
            provider=provider,
            series_id=series_id,
            as_of=self.as_of,
            lookback_days=lookback_days,
        )

        if self.strict and not df.empty and "publication_approximate" in df.columns:
            df = df[~df["publication_approximate"].fillna(False)]

        return df

    def get_market(
        self,
        symbol: str,
        timeframe: str,
        lookback_candles: int = 200,
    ) -> pd.DataFrame:
        """Return market data available at as_of (strictly before as_of)."""
        return get_market_data_as_of(
            symbol=symbol,
            timeframe=timeframe,
            as_of=self.as_of,
            lookback_candles=lookback_candles,
        )

    def get_release_consensus(self, release) -> float | None:
        """
        Return the consensus value as it was known at as_of.

        For a strict backtest, this should be the consensus
        at the time of the simulated forecast, not the final revised consensus.
        Trading Economics provides historical consensus values only on
        premium plans.  If unavailable, we use the stored consensus
        and note the limitation.
        """
        # TODO: implement with provider-specific PIT consensus if available
        return float(release.consensus) if release.consensus is not None else None
