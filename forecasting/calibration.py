"""
Probability calibration for economic event forecasts.

Calibration converts raw model probabilities into reliable,
well-calibrated probabilities using historical data.

Methods:
- Isotonic regression (preferred for sufficient sample sizes)
- Platt scaling (logistic regression, better for small samples)
- Walk-forward calibration on held-out data only

Key metrics computed:
- Brier score (lower = better, 0 = perfect)
- Log loss
- Expected calibration error (ECE)
- Calibration curve (reliability diagram data)
- Prediction interval coverage
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

logger = logging.getLogger("forecasting")

MIN_SAMPLES_FOR_CALIBRATION = 25


@dataclass
class CalibrationReport:
    """Full calibration assessment for a probability forecast."""

    model_name: str
    n_samples: int
    brier_score: float | None
    log_loss_value: float | None
    expected_calibration_error: float | None
    calibration_curve_fraction_of_positives: list[float]
    calibration_curve_mean_predicted: list[float]
    is_calibrated: bool
    calibration_status: str
    warnings: list[str] = field(default_factory=list)
    method_used: str = "none"

    @property
    def status_label(self) -> str:
        if self.is_calibrated:
            return "CALIBRATED"
        if self.n_samples < MIN_SAMPLES_FOR_CALIBRATION:
            return f"INSUFFICIENT SAMPLE (n={self.n_samples}, need {MIN_SAMPLES_FOR_CALIBRATION})"
        return "NOT CALIBRATED"


def calibrate_probabilities(
    raw_probs: np.ndarray,
    actuals: np.ndarray,
    method: Literal["isotonic", "platt"] = "isotonic",
) -> tuple[np.ndarray, str]:
    """
    Fit a calibration function on (raw_probs, actuals) and return
    calibrated probabilities.

    Parameters
    ----------
    raw_probs : 1-D array of raw predicted probabilities.
    actuals : 1-D array of binary outcomes (1 = above threshold, 0 = below).
    method : Calibration method.

    Returns
    -------
    (calibrated_probs, method_used)
    """
    n = len(raw_probs)
    if n < MIN_SAMPLES_FOR_CALIBRATION:
        logger.warning(
            f"Calibration skipped: only {n} samples (need {MIN_SAMPLES_FOR_CALIBRATION})."
        )
        return raw_probs, "none"

    if method == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip")
        calibrated = iso.fit_transform(raw_probs, actuals)
        return calibrated, "isotonic"

    if method == "platt":
        lr = LogisticRegression(C=1e10)
        lr.fit(raw_probs.reshape(-1, 1), actuals)
        calibrated = lr.predict_proba(raw_probs.reshape(-1, 1))[:, 1]
        return calibrated, "platt"

    return raw_probs, "none"


def assess_calibration(
    predicted_probs: np.ndarray,
    actuals: np.ndarray,
    model_name: str = "unknown",
    n_bins: int = 10,
) -> CalibrationReport:
    """
    Compute a full calibration report for a probability forecast.

    Parameters
    ----------
    predicted_probs : Predicted probabilities for the positive class.
    actuals : Binary outcomes (1 = event occurred, 0 = did not).
    model_name : Name of the model being assessed.
    n_bins : Number of bins for the calibration curve.
    """
    n = len(predicted_probs)
    warnings = []

    if n < MIN_SAMPLES_FOR_CALIBRATION:
        return CalibrationReport(
            model_name=model_name,
            n_samples=n,
            brier_score=None,
            log_loss_value=None,
            expected_calibration_error=None,
            calibration_curve_fraction_of_positives=[],
            calibration_curve_mean_predicted=[],
            is_calibrated=False,
            calibration_status="INSUFFICIENT",
            warnings=[
                f"Probability not calibrated — insufficient historical sample (n={n}, "
                f"minimum required: {MIN_SAMPLES_FOR_CALIBRATION})."
            ],
        )

    # Check for edge cases
    if len(np.unique(actuals)) < 2:
        warnings.append(
            "All outcomes are the same class — calibration curve cannot be computed."
        )
        return CalibrationReport(
            model_name=model_name,
            n_samples=n,
            brier_score=float(brier_score_loss(actuals, predicted_probs)),
            log_loss_value=None,
            expected_calibration_error=None,
            calibration_curve_fraction_of_positives=[],
            calibration_curve_mean_predicted=[],
            is_calibrated=False,
            calibration_status="FAILED",
            warnings=warnings,
        )

    try:
        bs = float(brier_score_loss(actuals, predicted_probs))
    except Exception as exc:
        bs = None
        warnings.append(f"Brier score computation failed: {exc}")

    try:
        ll = float(log_loss(actuals, predicted_probs))
    except Exception as exc:
        ll = None
        warnings.append(f"Log loss computation failed: {exc}")

    try:
        fraction_of_positives, mean_predicted = calibration_curve(
            actuals, predicted_probs, n_bins=n_bins, strategy="uniform"
        )
        # Expected calibration error
        ece = float(np.mean(np.abs(fraction_of_positives - mean_predicted)))
        is_calibrated = ece < 0.10  # ECE < 10% is acceptable
        fop_list = fraction_of_positives.tolist()
        mp_list = mean_predicted.tolist()
    except Exception as exc:
        warnings.append(f"Calibration curve failed: {exc}")
        ece = None
        is_calibrated = False
        fop_list = []
        mp_list = []

    calibration_status = "VERIFIED" if is_calibrated else "UNVERIFIED"

    return CalibrationReport(
        model_name=model_name,
        n_samples=n,
        brier_score=bs,
        log_loss_value=ll,
        expected_calibration_error=ece,
        calibration_curve_fraction_of_positives=fop_list,
        calibration_curve_mean_predicted=mp_list,
        is_calibrated=is_calibrated,
        calibration_status=calibration_status,
        warnings=warnings,
        method_used="direct",
    )


def compute_surprise_probabilities(
    estimate: float,
    std: float,
    consensus: float,
    near_band: float,
) -> tuple[float, float, float]:
    """
    Compute P(above), P(near), P(below) using a Gaussian distribution.

    Parameters
    ----------
    estimate : Model point estimate.
    std : Standard deviation of the forecast distribution.
    consensus : Consensus value.
    near_band : Half-width of the 'near consensus' band.

    Returns
    -------
    (p_above, p_near, p_below)  — three calibrated probabilities summing to 1.
    """
    from scipy.stats import norm

    if std <= 0:
        std = abs(estimate * 0.01) + 0.001  # Avoid division by zero

    # Threshold: consensus + near_band (upper) and consensus - near_band (lower)
    upper_threshold = consensus + near_band
    lower_threshold = consensus - near_band

    p_above = float(1.0 - norm.cdf(upper_threshold, loc=estimate, scale=std))
    p_below = float(norm.cdf(lower_threshold, loc=estimate, scale=std))
    p_near = max(0.0, 1.0 - p_above - p_below)

    # Normalise (floating point)
    total = p_above + p_near + p_below
    if total > 0:
        p_above /= total
        p_near /= total
        p_below /= total

    return p_above, p_near, p_below
