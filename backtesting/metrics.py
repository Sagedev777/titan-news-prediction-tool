"""Backtesting evaluation metrics."""
from __future__ import annotations
import numpy as np
from typing import List


def compute_backtest_metrics(results: list) -> dict:
    """
    Compute aggregate performance metrics from BacktestResult rows.
    """
    errors = [r.forecast_error for r in results if r.forecast_error is not None]
    coverages = [r.interval_covered for r in results if r.interval_covered is not None]
    correct_dir = [r.correct_direction for r in results if r.correct_direction is not None]

    # Classification accuracy (predicted vs actual class)
    class_matches = [
        r.predicted_class == r.actual_class
        for r in results
        if r.predicted_class and r.actual_class
        and "UNKNOWN" not in (r.predicted_class, r.actual_class)
    ]

    mae = float(np.mean(np.abs(errors))) if errors else None
    rmse = float(np.sqrt(np.mean(np.square(errors)))) if errors else None
    bias = float(np.mean(errors)) if errors else None
    interval_coverage = float(np.mean(coverages)) if coverages else None
    direction_accuracy = float(np.mean(correct_dir)) if correct_dir else None
    class_accuracy = float(np.mean(class_matches)) if class_matches else None
    n = len(results)

    return {
        "n": n,
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
        "interval_coverage_90pct": interval_coverage,
        "direction_accuracy": direction_accuracy,
        "class_accuracy_above_near_below": class_accuracy,
    }
