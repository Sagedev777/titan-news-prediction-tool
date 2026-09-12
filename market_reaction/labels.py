"""
Label generation for market reaction training data.

Labels historical market moves around economic events as UP / DOWN / FLAT
using a volatility-adjusted flat threshold.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("market_reaction")


def compute_event_returns(
    market_df: pd.DataFrame,
    event_time,
    horizons_minutes: list[int] = (5, 15, 60, 240),
) -> dict[int, float | None]:
    """
    Compute returns for each horizon after event_time.

    Parameters
    ----------
    market_df : DataFrame with index=timestamp_utc and column 'close'.
    event_time : UTC datetime of the release.
    horizons_minutes : List of horizons in minutes.

    Returns
    -------
    dict {horizon_minutes: return_pct} — None if candle not available.
    """
    if market_df.empty or "close" not in market_df.columns:
        return {h: None for h in horizons_minutes}

    # Find the close price just before the event
    pre_release = market_df[market_df.index < event_time]
    if pre_release.empty:
        return {h: None for h in horizons_minutes}

    entry_price = float(pre_release.iloc[-1]["close"])
    if entry_price == 0:
        return {h: None for h in horizons_minutes}

    results = {}
    for horizon in horizons_minutes:
        from datetime import timedelta
        horizon_time = event_time + timedelta(minutes=horizon)
        post = market_df[
            (market_df.index >= event_time) &
            (market_df.index <= horizon_time)
        ]
        if post.empty:
            results[horizon] = None
        else:
            exit_price = float(post.iloc[-1]["close"])
            results[horizon] = (exit_price - entry_price) / entry_price * 100

    return results


def classify_direction(
    return_pct: float | None,
    atr_threshold: float,
    flat_multiplier: float = 0.25,
) -> str:
    """
    Classify a return as UP / DOWN / FLAT using ATR-adjusted threshold.

    Parameters
    ----------
    return_pct : Percentage return.
    atr_threshold : ATR as a percentage of price (e.g. 0.1 = 0.1%).
    flat_multiplier : Fraction of ATR defining the flat zone.

    Returns
    -------
    'UP', 'DOWN', or 'FLAT'
    """
    if return_pct is None:
        return "FLAT"

    flat_zone = flat_multiplier * atr_threshold
    if abs(return_pct) < flat_zone:
        return "FLAT"
    return "UP" if return_pct > 0 else "DOWN"


def compute_atr_pct(market_df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute ATR as a percentage of price (for threshold setting).
    """
    if len(market_df) < period + 1:
        return 0.1  # Default 0.1% if insufficient data

    df = market_df.copy()
    if not {"high", "low", "close"}.issubset(df.columns):
        return 0.1

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = float(tr.rolling(period).mean().iloc[-1])
    avg_close = float(close.mean())

    return (atr / avg_close * 100) if avg_close > 0 else 0.1


def build_reaction_labels(
    releases,  # queryset of EconomicRelease
    symbol: str,
    horizons_minutes: list[int] = (5, 15, 60, 240),
    flat_multiplier: float = 0.25,
) -> pd.DataFrame:
    """
    Build a labelled dataset of historical market reactions.

    For each historical release + symbol combination, compute the
    post-release return and classify direction.

    Returns
    -------
    DataFrame with columns:
    - release_id, event_code, release_time_utc, period
    - return_{h}min, direction_{h}min  (for each horizon)
    - surprise (actual - consensus)
    - consensus, actual
    """
    from macro_data.release_dates import get_market_data_as_of

    rows = []
    for release in releases:
        if release.actual is None or release.consensus is None:
            continue

        surprise = float(release.actual) - float(release.consensus)

        # Get market data available at release time
        market_df = get_market_data_as_of(
            symbol=symbol,
            timeframe="1min",
            as_of=release.release_time_utc,
            lookback_candles=500,
        )

        if market_df.empty:
            continue

        atr = compute_atr_pct(market_df, period=14)
        returns = compute_event_returns(market_df, release.release_time_utc, horizons_minutes)

        row = {
            "release_id": release.id,
            "event_code": release.event.code,
            "release_time_utc": release.release_time_utc,
            "period": release.period,
            "surprise": surprise,
            "consensus": float(release.consensus),
            "actual": float(release.actual),
        }

        for h in horizons_minutes:
            ret = returns.get(h)
            row[f"return_{h}min"] = ret
            row[f"direction_{h}min"] = classify_direction(ret, atr, flat_multiplier)

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
