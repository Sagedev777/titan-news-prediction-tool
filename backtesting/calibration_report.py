"""Calibration report for backtests."""
from __future__ import annotations
import numpy as np


def generate_calibration_report(results: list) -> dict:
    """Generate a calibration report from BacktestResult rows."""
    probs = [r.predicted_probability for r in results if r.predicted_probability is not None]
    actuals = [1 if r.correct_direction else 0 for r in results if r.correct_direction is not None]

    if len(probs) < 10:
        return {"status": "INSUFFICIENT", "n": len(probs), "message": "Insufficient sample for calibration."}

    from forecasting.calibration import assess_calibration
    import numpy as np
    report = assess_calibration(
        predicted_probs=np.array(probs),
        actuals=np.array(actuals),
        model_name="backtest",
    )
    return {
        "status": report.calibration_status,
        "brier_score": report.brier_score,
        "log_loss": report.log_loss_value,
        "ece": report.expected_calibration_error,
        "n": report.n_samples,
        "is_calibrated": report.is_calibrated,
        "warnings": report.warnings,
    }
