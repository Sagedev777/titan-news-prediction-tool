"""
Backtesting runner.

Executes a walk-forward simulation over historical red-folder releases
using strict point-in-time data rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, date

import numpy as np
from django.utils import timezone

logger = logging.getLogger("backtesting")


def run_backtest(
    event_code: str,
    start_date: date,
    end_date: date,
    model_version: str = "1.0.0",
    strict_pit: bool = True,
    name: str | None = None,
) -> dict:
    """
    Run a walk-forward backtest for an event code over a date range.

    Parameters
    ----------
    event_code : e.g. 'US_CPI'.
    start_date / end_date : Date range.
    model_version : Model version string.
    strict_pit : If True, exclude records with approximate publication times.
    name : Optional descriptive name for the BacktestRun.

    Returns
    -------
    dict with BacktestRun.id and summary metrics.
    """
    from events.models import EconomicRelease, ImpactLevel
    from events.services import assert_red_folder
    from forecasting.event_models import is_model_implemented, get_event_model
    from forecasting.feature_engineering import (
        build_cpi_features, build_nfp_features
    )
    from .models import BacktestRun, BacktestResult
    from .point_in_time import PointInTimeDataAccessor
    from .metrics import compute_backtest_metrics

    _FEATURE_BUILDERS = {
        "US_CPI": build_cpi_features,
        "US_CORE_CPI": build_cpi_features,
        "US_NFP": build_nfp_features,
        "US_UNEMPLOYMENT_RATE": build_nfp_features,
        "US_AVERAGE_HOURLY_EARNINGS": build_nfp_features,
    }

    if not is_model_implemented(event_code):
        return {"error": f"No model implemented for {event_code}"}

    run = BacktestRun.objects.create(
        name=name or f"Backtest {event_code} {start_date}—{end_date}",
        event_code=event_code,
        start_date=start_date,
        end_date=end_date,
        model_version=model_version,
        data_vintage_policy="strict_pit" if strict_pit else "lenient",
        status="running",
    )

    releases = list(
        EconomicRelease.objects.select_related("event")
        .filter(
            event__code=event_code,
            event__normalized_impact_level=ImpactLevel.HIGH,
            event__is_allowlisted=True,
            release_time_utc__date__gte=start_date,
            release_time_utc__date__lte=end_date,
            actual__isnull=False,
        )
        .order_by("release_time_utc")
    )

    if not releases:
        run.status = "no_data"
        run.save()
        return {"backtest_run_id": run.id, "error": "No historical releases found."}

    results_to_create = []
    errors = 0

    for release in releases:
        try:
            # Simulate forecast at release time minus 1 hour
            simulated_time = release.release_time_utc - timezone.timedelta(hours=1)
            accessor = PointInTimeDataAccessor(as_of=simulated_time, strict=strict_pit)
            consensus_at_cutoff = accessor.get_release_consensus(release)

            builder = _FEATURE_BUILDERS.get(event_code)
            if builder is None:
                continue

            fm = builder(as_of=simulated_time, consensus=consensus_at_cutoff)

            model_class = get_event_model(event_code)
            model = model_class()
            model_result = model.run(
                feature_matrix=fm,
                consensus=consensus_at_cutoff,
                previous=float(release.previous) if release.previous is not None else None,
                as_of=simulated_time,
            )

            actual = float(release.actual)
            error = (model_result.estimate - actual) if model_result.estimate is not None else None

            # Classify predicted class
            if model_result.estimate is not None and consensus_at_cutoff is not None:
                band = 0.05
                diff = model_result.estimate - consensus_at_cutoff
                if abs(diff) <= band:
                    predicted_class = "NEAR"
                elif diff > 0:
                    predicted_class = "ABOVE"
                else:
                    predicted_class = "BELOW"
            else:
                predicted_class = "UNKNOWN"

            # Actual class
            if consensus_at_cutoff is not None:
                diff_actual = actual - consensus_at_cutoff
                if abs(diff_actual) <= 0.05:
                    actual_class = "NEAR"
                elif diff_actual > 0:
                    actual_class = "ABOVE"
                else:
                    actual_class = "BELOW"
            else:
                actual_class = "UNKNOWN"

            # Prediction interval coverage
            interval_covered = None
            if (model_result.lower_bound is not None and
                    model_result.upper_bound is not None):
                interval_covered = (
                    model_result.lower_bound <= actual <= model_result.upper_bound
                )

            results_to_create.append(
                BacktestResult(
                    backtest_run=run,
                    economic_release=release,
                    forecast_estimate=model_result.estimate,
                    forecast_lower=model_result.lower_bound,
                    forecast_upper=model_result.upper_bound,
                    consensus_at_cutoff=consensus_at_cutoff,
                    actual=actual,
                    forecast_error=error,
                    surprise=float(actual) - float(consensus_at_cutoff)
                    if consensus_at_cutoff is not None else None,
                    predicted_class=predicted_class,
                    actual_class=actual_class,
                    interval_covered=interval_covered,
                )
            )

        except Exception as exc:
            logger.error(
                f"Backtest error for {event_code} release {release.id}: {exc}",
                exc_info=True,
            )
            errors += 1

    BacktestResult.objects.bulk_create(results_to_create)
    summary = compute_backtest_metrics(results_to_create)
    summary["errors"] = errors
    summary["n_releases"] = len(releases)

    run.status = "completed"
    run.completed_at = timezone.now()
    run.summary = summary
    run.save()

    logger.info(f"Backtest complete: {run.name}. Summary: {summary}")
    return {"backtest_run_id": run.id, "summary": summary}
