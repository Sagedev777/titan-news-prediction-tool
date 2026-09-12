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

    def get_release_consensus(self, release) -> tuple[float | None, bool]:
        """
        Return the consensus value to use in a backtest simulation.

        Returns
        -------
        (consensus_value, is_approximate) tuple.

        is_approximate=True means the consensus value is the CURRENT stored
        value, NOT the value that existed at `as_of`.  This is an
        approximation caused by a data-source limitation:

        LIMITATION — CONSENSUS IS NOT POINT-IN-TIME
        -------------------------------------------
        Trading Economics provides historical consensus snapshots only on
        premium subscription plans.  On the free/standard tier (and when
        no provider-level PIT consensus data is stored in our database),
        we fall back to the consensus value stored at ingestion time.

        Impact on backtest accuracy:
        - Consensus values typically change by small amounts in the days
          before a release, so the bias is usually small.
        - Surprise classification (ABOVE/NEAR/BELOW) relative to consensus
          may be slightly wrong for releases where the consensus shifted
          materially before release day.
        - The BacktestResult.consensus_is_approximate flag is set to True
          for every result produced with this fallback, so you can filter
          or weight results accordingly.
        - Backtest direction-accuracy metrics should be interpreted as
          upper bounds when this flag is True.

        This limitation is recorded in:
        - BacktestResult.consensus_is_approximate
        - BacktestRun.summary["limitations"]
        - The dashboard backtesting page warning banner
        - Log messages at WARNING level
        """
        if release.consensus is None:
            logger.warning(
                "get_release_consensus: release %s (%s) has no stored consensus. "
                "Cannot compute surprise. consensus_is_approximate=True.",
                release.id,
                getattr(release.event, "code", "?"),
            )
            return None, True

        # No PIT consensus data available — using current stored value.
        # Log at WARNING so operators see this in the log stream.
        logger.warning(
            "get_release_consensus: using APPROXIMATE consensus for release %s (%s) "
            "as_of=%s. "
            "Reason: no point-in-time consensus history available on the current "
            "Trading Economics plan. "
            "The stored consensus (%.4f) is the value at last ingestion, not "
            "necessarily the value that existed at the simulated forecast time. "
            "Set BacktestResult.consensus_is_approximate=True.",
            release.id,
            getattr(release.event, "code", "?"),
            self.as_of.isoformat(),
            float(release.consensus),
        )
        return float(release.consensus), True
