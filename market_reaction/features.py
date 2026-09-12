"""
Feature engineering for market reaction models.

Features for predicting post-release currency / instrument moves.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger("market_reaction")


def build_reaction_features(
    symbol: str,
    event_code: str,
    release_time: datetime,
    estimated_surprise: float | None,
    consensus: float | None,
    previous: float | None,
    as_of: datetime,
) -> dict[str, float | None]:
    """
    Build feature dict for the market reaction model.

    All data is fetched as-of as_of to maintain point-in-time correctness.
    """
    from macro_data.release_dates import get_market_data_as_of, get_available_data

    features: dict[str, float | None] = {
        "estimated_surprise": estimated_surprise,
        "consensus": consensus,
        "previous": previous,
    }

    # ── Market features: pre-release state of the instrument ─────────────────
    market_df = get_market_data_as_of(symbol, "1h", as_of, lookback_candles=100)
    if not market_df.empty:
        close = market_df["close"].astype(float)
        features["pre_release_trend_5d"] = float(
            (close.iloc[-1] - close.iloc[max(0, len(close) - 5 * 24)]) / close.iloc[0]
            if len(close) >= 24 else 0.0
        )
        features["pre_release_atr_norm"] = float(
            (market_df["high"].astype(float) - market_df["low"].astype(float)).rolling(14).mean().iloc[-1]
            / close.mean()
            if len(close) >= 14 else 0.0
        )
    else:
        features["pre_release_trend_5d"] = None
        features["pre_release_atr_norm"] = None

    # ── Yield features (US02Y, US10Y) ─────────────────────────────────────────
    for yield_series, yield_name in [("DGS2", "us2y_change"), ("DGS10", "us10y_change")]:
        df = get_available_data("fred", yield_series, as_of, lookback_days=30)
        if not df.empty:
            s = df["value"]
            features[yield_name] = float(s.diff().dropna().iloc[-1]) if len(s) >= 2 else None
        else:
            features[yield_name] = None

    # ── Dollar trend (if symbol is a USD pair) ────────────────────────────────
    if "USD" in symbol:
        dxy_df = get_market_data_as_of("DXY", "1h", as_of, lookback_candles=120)
        if not dxy_df.empty:
            dxy_close = dxy_df["close"].astype(float)
            features["dxy_trend_1d"] = float(
                dxy_close.iloc[-1] - dxy_close.iloc[-24] if len(dxy_close) >= 24 else 0.0
            )
        else:
            features["dxy_trend_1d"] = None

    return features
