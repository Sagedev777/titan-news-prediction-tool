"""
Data normalisation utilities.

Converts raw provider values into consistent pandas DataFrames
with proper index, units, and seasonal adjustment notes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from django.utils import timezone


def build_series_dataframe(
    provider: str,
    series_id: str,
    as_of: datetime | None = None,
    seasonal_adjustment: str | None = None,
) -> pd.DataFrame:
    """
    Return a pandas DataFrame for a DataObservation series.

    Applies the point-in-time filter if as_of is provided:
    only observations with publication_time_utc <= as_of are returned.

    Parameters
    ----------
    provider : Provider code, e.g. 'bls', 'fred'.
    series_id : BLS / FRED series identifier.
    as_of : If provided, enforce point-in-time: exclude obs published after this time.
    seasonal_adjustment : Filter by 'SA', 'NSA', or None (any).

    Returns
    -------
    DataFrame with columns: observation_date, value, vintage_date, publication_time_utc.
    Index is observation_date (UTC, sorted ascending).
    """
    from .models import DataObservation

    qs = DataObservation.objects.filter(provider=provider, series_id=series_id)

    if seasonal_adjustment:
        qs = qs.filter(seasonal_adjustment=seasonal_adjustment)

    if as_of is not None:
        # Point-in-time filter: exclude records published after as_of
        qs = qs.filter(
            publication_time_utc__isnull=False,
            publication_time_utc__lte=as_of,
        ) | DataObservation.objects.filter(
            provider=provider,
            series_id=series_id,
            publication_time_utc__isnull=True,
            retrieved_at__lte=as_of,
            publication_approximate=True,  # conservative fallback
        )

    rows = list(
        qs.values(
            "observation_date", "value", "vintage_date",
            "publication_time_utc", "retrieved_at", "revision_number",
        ).order_by("observation_date")
    )

    if not rows:
        return pd.DataFrame(
            columns=["observation_date", "value", "vintage_date", "publication_time_utc"]
        )

    df = pd.DataFrame(rows)
    df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True)
    df = df.sort_values("observation_date").set_index("observation_date")

    # Keep most recent vintage for each observation date
    df = df.groupby(df.index).last()

    return df


def compute_pct_change(series: pd.Series, periods: int = 1) -> pd.Series:
    """Compute percentage change. Periods=1 → MoM, 12 → YoY (monthly)."""
    return series.pct_change(periods=periods) * 100


def compute_yoy(series: pd.Series, freq: str = "M") -> pd.Series:
    """Compute YoY change for a monthly or quarterly index series."""
    periods = 12 if freq == "M" else 4
    return compute_pct_change(series, periods=periods)


def compute_mom(series: pd.Series) -> pd.Series:
    """Compute MoM change for a monthly index series."""
    return compute_pct_change(series, periods=1)


def align_series(
    dfs: dict[str, pd.DataFrame], value_col: str = "value"
) -> pd.DataFrame:
    """
    Align multiple series DataFrames on observation_date.

    Missing values are left as NaN (not imputed).
    The caller must decide how to handle gaps.
    """
    aligned = {}
    for name, df in dfs.items():
        if df.empty:
            continue
        if value_col in df.columns:
            aligned[name] = df[value_col]
        elif df.index.name == "observation_date" and not df.empty:
            aligned[name] = df.iloc[:, 0]

    if not aligned:
        return pd.DataFrame()

    return pd.DataFrame(aligned).sort_index()


def add_lags(df: pd.DataFrame, columns: list[str], lags: list[int]) -> pd.DataFrame:
    """
    Add lagged columns to a DataFrame.

    Naming convention: {column}_lag{n}
    """
    for col in columns:
        if col not in df.columns:
            continue
        for lag in lags:
            df[f"{col}_lag{lag}"] = df[col].shift(lag)
    return df


def add_rolling(
    df: pd.DataFrame,
    columns: list[str],
    windows: list[int],
    stat: str = "mean",
) -> pd.DataFrame:
    """Add rolling-window statistics (mean, std) to a DataFrame."""
    for col in columns:
        if col not in df.columns:
            continue
        for window in windows:
            fn = getattr(df[col].rolling(window, min_periods=1), stat)
            df[f"{col}_roll{window}_{stat}"] = fn()
    return df
