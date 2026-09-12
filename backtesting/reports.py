"""Backtest report generation utilities."""
from __future__ import annotations
import pandas as pd

# Canonical limitation text — duplicated from runner.py for report independence.
_PIT_CONSENSUS_LIMITATION = (
    "CONSENSUS IS NOT POINT-IN-TIME: "
    "The consensus values used in this backtest are the values stored at "
    "calendar ingestion time, not the values that existed at the simulated "
    "forecast time. Trading Economics point-in-time consensus history requires "
    "a premium subscription. "
    "Surprise classification (ABOVE/NEAR/BELOW) may be slightly wrong for "
    "releases where the consensus shifted materially before release day. "
    "Direction-accuracy metrics should be treated as upper bounds. "
    "BacktestResult.consensus_is_approximate=True for all results in this run."
)


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

    # Count how many results have approximate consensus.
    approx_count = sum(1 for r in results if getattr(r, "consensus_is_approximate", True))

    # Collect limitations from the run record, then ensure the PIT consensus
    # limitation is always present (it applies to every backtest until a
    # real PIT consensus source is integrated).
    limitations: list[str] = list(backtest_run.limitations or [])
    if _PIT_CONSENSUS_LIMITATION not in limitations:
        limitations.insert(0, _PIT_CONSENSUS_LIMITATION)

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
        "limitations": limitations,
        "consensus_approximate_count": approx_count,
        "consensus_approximate_fraction": (
            approx_count / len(results) if results else 0.0
        ),
    }
