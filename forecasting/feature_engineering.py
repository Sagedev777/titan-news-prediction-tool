"""
Feature engineering for economic event forecasting models.

Converts raw DataObservation records into model-ready feature matrices.
All data access goes through get_available_data() for PIT correctness.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from macro_data.normalization import (
    add_lags,
    add_rolling,
    align_series,
    compute_mom,
    compute_yoy,
)
from macro_data.release_dates import get_available_data, get_features_for_event

logger = logging.getLogger("forecasting")


class FeatureMatrix:
    """
    Holds the feature DataFrame plus quality metadata.

    Attributes
    ----------
    df : The feature DataFrame (index = observation_date, cols = features).
    missing_features : List of feature names that were unavailable.
    quality_score : Float 0.0–1.0 (1.0 = all features available).
    warnings : List of warning strings.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        missing_features: list[str],
        available_features: list[str],
        warnings: list[str],
    ):
        self.df = df
        self.missing_features = missing_features
        self.available_features = available_features
        self.warnings = warnings
        total = len(missing_features) + len(available_features)
        self.quality_score = len(available_features) / total if total > 0 else 0.0

    @property
    def is_sufficient(self) -> bool:
        """Return True if at least 50% of features are available."""
        return self.quality_score >= 0.5

    def to_dict(self) -> dict:
        return {
            "available_features": self.available_features,
            "missing_features": self.missing_features,
            "quality_score": self.quality_score,
            "warnings": self.warnings,
        }


def build_cpi_features(as_of: datetime, consensus: float | None = None) -> FeatureMatrix:
    """
    Build the feature matrix for the US CPI model.

    Returns a FeatureMatrix.  If insufficient data is available,
    quality_score will be low and the caller should return NO FORECAST.
    """
    series_data = get_features_for_event("US_CPI", as_of)
    available = []
    missing = []
    warnings = []
    frames: dict[str, pd.Series] = {}

    # ── CPI level series → compute MoM and YoY changes ───────────────────────
    for name in ["cpi_headline_sa", "cpi_core_sa", "cpi_food_sa", "cpi_energy_sa",
                 "cpi_shelter_sa", "cpi_rent_sa", "cpi_oer_sa",
                 "cpi_used_vehicles_sa", "cpi_new_vehicles_sa"]:
        df = series_data.get(name, pd.DataFrame())
        if df.empty:
            missing.append(name)
            warnings.append(f"Feature unavailable: {name}")
        else:
            s = df["value"]
            frames[f"{name}_mom"] = compute_mom(s)
            frames[f"{name}_yoy"] = compute_yoy(s)
            available.append(name)

    # ── Price-based leading indicators (already in level/price) ──────────────
    for name in ["oil_wti", "gasoline_price_us", "ppi_final_demand", "ppi_core", "import_prices"]:
        df = series_data.get(name, pd.DataFrame())
        if df.empty:
            missing.append(name)
        else:
            frames[name] = df["value"]
            frames[f"{name}_mom"] = compute_mom(df["value"])
            available.append(name)

    # ── Expectation / nowcast series ──────────────────────────────────────────
    for name in ["inflation_exp_mich", "inflation_exp_1yr",
                 "cleveland_headline_mom", "cleveland_core_mom"]:
        df = series_data.get(name, pd.DataFrame())
        if df.empty:
            missing.append(name)
        else:
            frames[name] = df["value"]
            available.append(name)
            if "cleveland" in name:
                warnings.append(
                    f"Cleveland Fed nowcast ({name}) is an external estimate, "
                    "not ground truth."
                )

    # ── Add consensus as a feature ────────────────────────────────────────────
    if consensus is not None:
        # Broadcast consensus to a series matching the last index date
        last_dates = [s.index[-1] for s in frames.values() if len(s) > 0]
        if last_dates:
            latest_date = max(last_dates)
            consensus_series = pd.Series([consensus], index=[latest_date], name="consensus")
            frames["consensus"] = consensus_series
            available.append("consensus")
    else:
        missing.append("consensus")
        warnings.append("Consensus forecast not available — probability estimates will be wider.")

    # ── Align all series to a common monthly index ────────────────────────────
    if not frames:
        return FeatureMatrix(
            df=pd.DataFrame(),
            missing_features=missing,
            available_features=available,
            warnings=warnings + ["NO DATA: All CPI feature series are empty."],
        )

    aligned = pd.DataFrame({k: v for k, v in frames.items()}).sort_index()

    # ── Add lags ──────────────────────────────────────────────────────────────
    lag_cols = [c for c in aligned.columns if "mom" in c or "yoy" in c]
    aligned = add_lags(aligned, lag_cols, lags=[1, 2, 3])

    # ── Add rolling features ──────────────────────────────────────────────────
    aligned = add_rolling(aligned, lag_cols, windows=[3, 6], stat="mean")

    return FeatureMatrix(
        df=aligned,
        missing_features=missing,
        available_features=available,
        warnings=warnings,
    )


def build_nfp_features(as_of: datetime, consensus: float | None = None) -> FeatureMatrix:
    """Build feature matrix for the US NFP model."""
    series_data = get_features_for_event("US_NFP", as_of)
    available = []
    missing = []
    warnings = []
    frames: dict[str, pd.Series] = {}

    for name in ["nfp_total_sa", "nfp_private_sa", "awh_sa", "ahe_sa",
                 "unemployment_rate", "lfpr"]:
        df = series_data.get(name, pd.DataFrame())
        if df.empty:
            missing.append(name)
        else:
            frames[name] = df["value"]
            frames[f"{name}_mom"] = compute_mom(df["value"])
            available.append(name)

    for name in ["adp_employment", "jolts_openings", "jolts_hires",
                 "jolts_quits", "jolts_layoffs", "nfci"]:
        df = series_data.get(name, pd.DataFrame())
        if df.empty:
            missing.append(name)
            if name == "adp_employment":
                warnings.append(
                    "ADP employment is unavailable — this is a key leading indicator for NFP. "
                    "Model accuracy will be reduced."
                )
        else:
            frames[name] = df["value"]
            if name == "adp_employment":
                warnings.append(
                    "ADP is a leading indicator, not a direct NFP measure. "
                    "Do not treat ADP as the NFP forecast."
                )
            available.append(name)

    if consensus is not None:
        last_dates = [s.index[-1] for s in frames.values() if len(s) > 0]
        if last_dates:
            latest_date = max(last_dates)
            frames["consensus"] = pd.Series([consensus], index=[latest_date])
            available.append("consensus")
    else:
        missing.append("consensus")

    if not frames:
        return FeatureMatrix(
            df=pd.DataFrame(),
            missing_features=missing,
            available_features=available,
            warnings=warnings + ["NO DATA: All NFP feature series are empty."],
        )

    aligned = pd.DataFrame({k: v for k, v in frames.items()}).sort_index()
    lag_cols = [c for c in aligned.columns if "_mom" in c or "adp" in c or "jolts" in c]
    aligned = add_lags(aligned, lag_cols, lags=[1, 2])
    aligned = add_rolling(aligned, ["nfp_total_sa"], windows=[3, 6, 12], stat="mean")

    return FeatureMatrix(
        df=aligned,
        missing_features=missing,
        available_features=available,
        warnings=warnings,
    )


def get_latest_feature_row(fm: FeatureMatrix) -> pd.Series | None:
    """
    Return the most recent complete feature row from a FeatureMatrix.

    Returns None if the DataFrame is empty or has no non-NaN rows.
    """
    if fm.df.empty:
        return None

    # Drop columns that are entirely NaN
    df = fm.df.dropna(axis=1, how="all")

    # Get the last row that has at least 50% non-NaN values
    thresh = int(len(df.columns) * 0.5)
    valid_rows = df.dropna(thresh=thresh)

    if valid_rows.empty:
        return None

    return valid_rows.iloc[-1]
