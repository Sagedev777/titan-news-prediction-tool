"""
Ensemble combiner for Stage 2/3 models.

Combines multiple model estimates into a single ensemble forecast
using inverse-MAE weighting from walk-forward cross-validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .baseline import BaselineResult
from .event_models import EventModelResult

logger = logging.getLogger("forecasting")


@dataclass
class EnsembleResult:
    estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    std: float | None
    weights: dict[str, float]
    component_estimates: dict[str, float]
    note: str


def inverse_mae_weights(maes: dict[str, float]) -> dict[str, float]:
    """
    Compute weights proportional to 1 / MAE.

    Models with lower MAE receive higher weight.
    Models with MAE = 0 or inf are excluded.
    """
    valid = {k: v for k, v in maes.items() if v > 0 and np.isfinite(v)}
    if not valid:
        n = len(maes)
        return {k: 1.0 / n for k in maes}

    inv = {k: 1.0 / v for k, v in valid.items()}
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()}


def combine_estimates(
    estimates: dict[str, float],
    weights: dict[str, float],
) -> float | None:
    """
    Compute weighted average of model estimates.

    Parameters
    ----------
    estimates : {model_name: estimate}
    weights : {model_name: weight}

    Returns
    -------
    Weighted average estimate, or None if no valid estimates.
    """
    valid_pairs = [(w, estimates[k]) for k, w in weights.items() if k in estimates]
    if not valid_pairs:
        return None
    total_w = sum(w for w, _ in valid_pairs)
    if total_w == 0:
        return None
    return sum(w * e for w, e in valid_pairs) / total_w


def ensemble_from_baselines(
    baselines: list[BaselineResult],
    consensus: float | None,
) -> EnsembleResult:
    """
    Create an ensemble estimate from Stage 1 baseline results.

    Used when Stage 2 models are not available or do not beat baselines.
    """
    valid = [(b.model_name, b.estimate) for b in baselines if b.estimate is not None]
    if not valid:
        return EnsembleResult(
            estimate=None, lower_bound=None, upper_bound=None, std=None,
            weights={}, component_estimates={},
            note="No baseline estimates available.",
        )

    estimates = [e for _, e in valid]
    median_est = float(np.median(estimates))
    std_est = float(np.std(estimates)) if len(estimates) > 1 else float(abs(median_est) * 0.05)

    weights = {name: 1.0 / len(valid) for name, _ in valid}
    component_estimates = dict(valid)

    return EnsembleResult(
        estimate=median_est,
        lower_bound=median_est - 1.645 * std_est,
        upper_bound=median_est + 1.645 * std_est,
        std=std_est,
        weights=weights,
        component_estimates=component_estimates,
        note=f"Baseline ensemble of {len(valid)} models (median).",
    )
