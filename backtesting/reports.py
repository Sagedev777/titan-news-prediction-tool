"""Backtest report generation utilities."""
from __future__ import annotations
import pandas as pd


def generate_backtest_report(backtest_run) -> dict:
    """Generate a full backtesting report for dashboard display."""
    results = list(backtest_run.results.select_related("economic_release").all())

    if not results:
        return {"backtest_run_id": backtest_run.id, "error": "No results found."}

    from .metrics import compute_backtest_metrics
    from .calibration_report import generate_calibration_report

    metrics = compute_backtest_metrics(results)
    calibration = generate_calibration_report(results)

    # Results by year
    by_year = {}
    for r in results:
        if r.economic_release:
            year = str(r.economic_release.release_time_utc.year)
            by_year.setdefault(year, []).append(r)
    year_metrics = {y: compute_backtest_metrics(rs) for y, rs in by_year.items()}

    return {
        "backtest_run_id": backtest_run.id,
        "name": backtest_run.name,
        "event_code": backtest_run.event_code,
        "start_date": str(backtest_run.start_date),
        "end_date": str(backtest_run.end_date),
        "model_version": backtest_run.model_version,
        "data_vintage_policy": backtest_run.data_vintage_policy,
        "summary_metrics": metrics,
        "calibration": calibration,
        "by_year": year_metrics,
        "n_results": len(results),
    }
