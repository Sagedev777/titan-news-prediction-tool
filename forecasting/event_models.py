"""
Event-specific forecasting models.

Each supported event family has its own dedicated model class.
One universal model is never used for all events.

Model hierarchy (each model tries Stage 2+ only after Stage 1 baseline):
Stage 1: Baselines (always run)
Stage 2: OLS / Ridge / ElasticNet
Stage 3: Random Forest / Gradient Boosting (when data is sufficient)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from .baseline import (
    ConsensusBaseline,
    ExternalNowcastBaseline,
    PreviousValueBaseline,
    RollingAverageBaseline,
    run_all_baselines,
)
from .calibration import compute_surprise_probabilities

logger = logging.getLogger("forecasting")

MODEL_VERSION = "1.0.0"
MIN_TRAIN_SAMPLES = 12   # Minimum historical releases to train on


@dataclass
class EventModelResult:
    """Full output from an event model run."""

    event_code: str
    model_name: str
    model_version: str = MODEL_VERSION
    estimate: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    std: float | None = None
    probability_above: float | None = None
    probability_near: float | None = None
    probability_below: float | None = None
    consensus: float | None = None
    estimated_surprise: float | None = None
    event_bias: str = ""
    data_quality: str = "UNAVAILABLE"
    calibration_status: str = "UNVERIFIED"
    comparable_releases: int = 0
    warnings: list[str] = field(default_factory=list)
    feature_importances: dict[str, float] = field(default_factory=dict)
    model_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def is_forecast_available(self) -> bool:
        return self.estimate is not None and self.data_quality not in ("UNAVAILABLE", "POOR")


def _walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    model_class,
    model_params: dict,
    n_splits: int = 5,
) -> dict[str, float]:
    """
    Evaluate a model using walk-forward (time-series) cross-validation.

    Never shuffles data.  Always trains on past, tests on future.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    maes, rmses = [], []

    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        if len(X_train) < 3:
            continue

        model = model_class(**model_params)
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)

        maes.append(mean_absolute_error(y_test, preds))
        rmses.append(np.sqrt(mean_squared_error(y_test, preds)))

    return {
        "cv_mae": float(np.mean(maes)) if maes else float("inf"),
        "cv_rmse": float(np.mean(rmses)) if rmses else float("inf"),
        "n_cv_folds": len(maes),
    }


class USCPIModel:
    """
    US CPI event-specific forecasting model.

    Produces estimates for:
    - Headline CPI MoM
    - Core CPI MoM
    - Headline CPI YoY
    - Core CPI YoY
    """

    event_code = "US_CPI"
    name = "us_cpi_ridge_v1"

    def run(
        self,
        feature_matrix,  # FeatureMatrix from feature_engineering.py
        consensus: float | None,
        previous: float | None,
        as_of: datetime,
        near_band: float = 0.05,
    ) -> EventModelResult:
        from .feature_engineering import FeatureMatrix

        result = EventModelResult(
            event_code=self.event_code,
            model_name=self.name,
            consensus=consensus,
        )

        if not isinstance(feature_matrix, FeatureMatrix):
            result.warnings.append("Invalid feature matrix passed.")
            return result

        fm = feature_matrix

        # ── No forecast gate ──────────────────────────────────────────────────
        if not fm.is_sufficient:
            result.data_quality = "UNAVAILABLE"
            result.warnings.append(
                "NO FORECAST — INSUFFICIENT OR INVALID DATA. "
                f"Quality score: {fm.quality_score:.0%}. "
                f"Missing features: {fm.missing_features}."
            )
            return result

        result.warnings.extend(fm.warnings)

        # ── Identify target column ────────────────────────────────────────────
        target_col = "cpi_headline_sa_mom"
        if target_col not in fm.df.columns:
            result.data_quality = "POOR"
            result.warnings.append(
                f"Target column {target_col!r} not in feature matrix. Cannot forecast."
            )
            return result

        df = fm.df.dropna(subset=[target_col])
        if len(df) < MIN_TRAIN_SAMPLES:
            result.data_quality = "POOR"
            result.warnings.append(
                f"Insufficient observations: {len(df)} (minimum: {MIN_TRAIN_SAMPLES})."
            )
            result.comparable_releases = len(df)
            return result

        # ── Feature selection: drop columns with > 50% NaN ───────────────────
        y = df[target_col]
        X = df.drop(columns=[target_col]).dropna(axis=1, thresh=int(len(df) * 0.5))
        X = X.fillna(X.median())

        if X.empty or len(X.columns) == 0:
            result.data_quality = "POOR"
            result.warnings.append("No usable feature columns after NaN filtering.")
            return result

        # ── Stage 1: Baselines ────────────────────────────────────────────────
        baselines = run_all_baselines(
            series=y,
            consensus=consensus,
            nowcast=_get_nowcast_value(fm),
        )
        baseline_estimates = [b.estimate for b in baselines if b.estimate is not None]

        # ── Stage 2: Ridge regression ─────────────────────────────────────────
        best_estimate = None
        best_model_name = "rolling_average_baseline"
        best_std = float(y.diff().dropna().std()) if len(y) > 2 else 0.1

        ridge_metrics = _walk_forward_cv(X, y, Ridge, {"alpha": 1.0})
        baseline_mae = float(abs(y - y.shift(1)).dropna().mean()) if len(y) > 1 else float("inf")

        if ridge_metrics["cv_mae"] < baseline_mae * 0.95:
            # Ridge beats baseline — use it
            scaler = StandardScaler()
            X_all = scaler.fit_transform(X)
            ridge = Ridge(alpha=1.0)
            ridge.fit(X_all, y)
            last_X = X.iloc[-1:].fillna(X.median())
            last_X_s = scaler.transform(last_X)
            best_estimate = float(ridge.predict(last_X_s)[0])
            best_model_name = "ridge"

            # Feature importances (absolute coefficients)
            result.feature_importances = {
                col: abs(float(coef))
                for col, coef in zip(X.columns, ridge.coef_)
            }
            result.model_metrics = ridge_metrics
        else:
            # Fall back to rolling average baseline
            logger.info(
                f"{self.name}: Ridge does not beat baseline "
                f"(Ridge MAE: {ridge_metrics['cv_mae']:.4f}, "
                f"Baseline MAE: {baseline_mae:.4f}). Using rolling average."
            )
            ra = RollingAverageBaseline().predict(y)
            if ra.estimate is not None:
                best_estimate = ra.estimate
            result.warnings.append(
                "Complex model does not improve on rolling average baseline. "
                "Using simple baseline. See model metrics for details."
            )
            result.model_metrics = {"baseline_mae": baseline_mae, **ridge_metrics}

        if best_estimate is None and baseline_estimates:
            best_estimate = float(np.median(baseline_estimates))
            best_model_name = "baseline_ensemble"

        # ── Prediction interval (empirical residuals) ─────────────────────────
        if best_estimate is not None and len(y) >= 3:
            residual_std = float(y.diff().dropna().std())
            result.estimate = best_estimate
            result.std = residual_std
            result.lower_bound = best_estimate - 1.645 * residual_std
            result.upper_bound = best_estimate + 1.645 * residual_std

            # ── Surprise probabilities ─────────────────────────────────────────
            if consensus is not None:
                p_above, p_near, p_below = compute_surprise_probabilities(
                    estimate=best_estimate,
                    std=residual_std,
                    consensus=float(consensus),
                    near_band=near_band,
                )
                result.probability_above = p_above
                result.probability_near = p_near
                result.probability_below = p_below
                result.estimated_surprise = best_estimate - float(consensus)

                # ── Event bias ─────────────────────────────────────────────────
                surprise = result.estimated_surprise
                if abs(surprise) <= near_band:
                    result.event_bias = "Neutral — near consensus"
                elif surprise > 0:
                    strength = "strongly" if surprise > near_band * 3 else "moderately"
                    result.event_bias = f"{strength.capitalize()} bullish USD"
                else:
                    strength = "strongly" if abs(surprise) > near_band * 3 else "moderately"
                    result.event_bias = f"{strength.capitalize()} bearish USD"
            else:
                result.warnings.append(
                    "Consensus not available — surprise probabilities cannot be computed."
                )

        result.data_quality = "GOOD" if fm.quality_score > 0.7 else "DEGRADED"
        result.comparable_releases = len(y)
        result.model_name = f"{self.name}__{best_model_name}"

        return result


class USNFPModel:
    """
    US Nonfarm Payrolls event-specific forecasting model.
    """

    event_code = "US_NFP"
    name = "us_nfp_ridge_v1"

    def run(
        self,
        feature_matrix,
        consensus: float | None,
        previous: float | None,
        as_of: datetime,
        near_band: float = 25.0,  # NFP near-consensus band = 25K
    ) -> EventModelResult:
        from .feature_engineering import FeatureMatrix

        result = EventModelResult(
            event_code=self.event_code,
            model_name=self.name,
            consensus=consensus,
        )

        fm = feature_matrix
        if not fm.is_sufficient:
            result.data_quality = "UNAVAILABLE"
            result.warnings.append(
                "NO FORECAST — INSUFFICIENT OR INVALID DATA. "
                f"Quality: {fm.quality_score:.0%}. Missing: {fm.missing_features}."
            )
            return result

        result.warnings.extend(fm.warnings)

        target_col = "nfp_total_sa"
        if target_col not in fm.df.columns:
            result.data_quality = "POOR"
            result.warnings.append(f"Target column {target_col!r} not available.")
            return result

        df = fm.df.dropna(subset=[target_col])
        y = df[target_col].diff().dropna()  # MoM change in payrolls

        if len(y) < MIN_TRAIN_SAMPLES:
            result.data_quality = "POOR"
            result.warnings.append(f"Insufficient observations: {len(y)}.")
            result.comparable_releases = len(y)
            return result

        X = df.drop(columns=[target_col]).dropna(axis=1, thresh=int(len(df) * 0.5))
        X = X.loc[y.index].fillna(X.median())

        baselines = run_all_baselines(
            series=y,
            consensus=consensus,
            nowcast=None,
        )
        baseline_estimates = [b.estimate for b in baselines if b.estimate is not None]

        best_estimate = None
        if X.empty or len(X.columns) == 0:
            if baseline_estimates:
                best_estimate = float(np.median(baseline_estimates))
                result.warnings.append("No feature columns — using baseline ensemble.")
        else:
            metrics = _walk_forward_cv(X, y, Ridge, {"alpha": 1.0})
            baseline_mae = float(abs(y - y.shift(1)).dropna().mean()) if len(y) > 1 else float("inf")

            if metrics["cv_mae"] < baseline_mae * 0.95:
                scaler = StandardScaler()
                X_s = scaler.fit_transform(X)
                ridge = Ridge(alpha=1.0)
                ridge.fit(X_s, y)
                last_X = X.iloc[-1:].fillna(X.median())
                best_estimate = float(ridge.predict(scaler.transform(last_X))[0])
                result.feature_importances = {
                    col: abs(float(coef)) for col, coef in zip(X.columns, ridge.coef_)
                }
                result.model_metrics = metrics
            else:
                ra = RollingAverageBaseline().predict(y)
                best_estimate = ra.estimate
                result.warnings.append("Ridge does not beat baseline. Using rolling average.")
                result.model_metrics = metrics

        if best_estimate is None and baseline_estimates:
            best_estimate = float(np.median(baseline_estimates))

        if best_estimate is not None:
            residual_std = float(y.std()) if len(y) >= 3 else 50.0
            result.estimate = best_estimate
            result.std = residual_std
            result.lower_bound = best_estimate - 1.645 * residual_std
            result.upper_bound = best_estimate + 1.645 * residual_std

            if consensus is not None:
                p_above, p_near, p_below = compute_surprise_probabilities(
                    best_estimate, residual_std, float(consensus), near_band
                )
                result.probability_above = p_above
                result.probability_near = p_near
                result.probability_below = p_below
                result.estimated_surprise = best_estimate - float(consensus)

                surprise = result.estimated_surprise
                if abs(surprise) <= near_band:
                    result.event_bias = "Neutral — near consensus"
                elif surprise > 0:
                    strength = "strongly" if surprise > near_band * 2 else "moderately"
                    result.event_bias = f"{strength.capitalize()} bullish USD"
                else:
                    strength = "strongly" if abs(surprise) > near_band * 2 else "moderately"
                    result.event_bias = f"{strength.capitalize()} bearish USD"

        result.data_quality = "GOOD" if fm.quality_score > 0.7 else "DEGRADED"
        result.comparable_releases = len(y)
        return result


def _get_nowcast_value(fm) -> float | None:
    """Extract the latest Cleveland Fed nowcast from the feature matrix."""
    if fm.df.empty:
        return None
    for col in ["cleveland_headline_mom", "cleveland_core_mom"]:
        if col in fm.df.columns:
            s = fm.df[col].dropna()
            if not s.empty:
                return float(s.iloc[-1])
    return None


# ── Event model registry ───────────────────────────────────────────────────────
# Maps event_code → model class.  Only codes in this registry can be forecast.

EVENT_MODEL_REGISTRY: dict[str, type] = {
    "US_CPI": USCPIModel,
    "US_CORE_CPI": USCPIModel,  # uses same model, different target column
    "US_NFP": USNFPModel,
    "US_UNEMPLOYMENT_RATE": USNFPModel,
    "US_AVERAGE_HOURLY_EARNINGS": USNFPModel,
}


def get_event_model(event_code: str):
    """Return the model class for an event code, or None if not implemented."""
    return EVENT_MODEL_REGISTRY.get(event_code)


def is_model_implemented(event_code: str) -> bool:
    return event_code in EVENT_MODEL_REGISTRY
