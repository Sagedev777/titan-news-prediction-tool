"""
Baseline models — Stage 1 of the model development hierarchy.

These are the benchmarks that all subsequent models must beat.
If a complex model does not outperform the best baseline on
out-of-sample data, the baseline is used and that result is reported.

Baselines:
1. SeasonalNaiveBaseline    — same month / quarter one year ago
2. PreviousValueBaseline    — just use the previous print
3. RollingAverageBaseline   — rolling mean of recent prints
4. ConsensusBaseline        — just use the consensus forecast
5. ExternalNowcastBaseline  — use the Cleveland Fed or other external model
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger("forecasting")


@dataclass
class BaselineResult:
    model_name: str
    estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    note: str
    data_available: bool


class SeasonalNaiveBaseline:
    """Estimate = same-period value from one year ago."""

    name = "seasonal_naive"

    def predict(self, series: pd.Series, periods_per_year: int = 12) -> BaselineResult:
        if len(series) < periods_per_year + 1:
            return BaselineResult(
                model_name=self.name,
                estimate=None, lower_bound=None, upper_bound=None,
                note="Insufficient history for seasonal naive baseline.",
                data_available=False,
            )
        estimate = float(series.iloc[-periods_per_year])
        std = float(series.diff(periods_per_year).dropna().std())
        return BaselineResult(
            model_name=self.name,
            estimate=estimate,
            lower_bound=estimate - 1.645 * std,
            upper_bound=estimate + 1.645 * std,
            note=f"Seasonal naive: using value from {periods_per_year} periods ago.",
            data_available=True,
        )


class PreviousValueBaseline:
    """Estimate = most recent prior print."""

    name = "previous_value"

    def predict(self, series: pd.Series) -> BaselineResult:
        if series.empty or series.dropna().empty:
            return BaselineResult(
                model_name=self.name,
                estimate=None, lower_bound=None, upper_bound=None,
                note="No previous value available.",
                data_available=False,
            )
        estimate = float(series.dropna().iloc[-1])
        changes = series.diff().dropna()
        std = float(changes.std()) if len(changes) >= 3 else float(abs(estimate) * 0.1)
        return BaselineResult(
            model_name=self.name,
            estimate=estimate,
            lower_bound=estimate - 1.645 * std,
            upper_bound=estimate + 1.645 * std,
            note="Previous-value baseline: last observed print.",
            data_available=True,
        )


class RollingAverageBaseline:
    """Estimate = rolling mean of recent N prints."""

    name = "rolling_average"

    def predict(self, series: pd.Series, window: int = 6) -> BaselineResult:
        clean = series.dropna()
        if len(clean) < 2:
            return BaselineResult(
                model_name=self.name,
                estimate=None, lower_bound=None, upper_bound=None,
                note="Insufficient data for rolling average.",
                data_available=False,
            )
        n = min(window, len(clean))
        recent = clean.iloc[-n:]
        estimate = float(recent.mean())
        std = float(recent.std()) if len(recent) >= 2 else float(abs(estimate) * 0.1)
        return BaselineResult(
            model_name=self.name,
            estimate=estimate,
            lower_bound=estimate - 1.645 * std,
            upper_bound=estimate + 1.645 * std,
            note=f"Rolling average ({n}-period window).",
            data_available=True,
        )


class ConsensusBaseline:
    """Estimate = analyst consensus (if available)."""

    name = "consensus"

    def predict(self, consensus: float | None) -> BaselineResult:
        if consensus is None:
            return BaselineResult(
                model_name=self.name,
                estimate=None, lower_bound=None, upper_bound=None,
                note="Consensus not available.",
                data_available=False,
            )
        return BaselineResult(
            model_name=self.name,
            estimate=consensus,
            lower_bound=None,
            upper_bound=None,
            note="Consensus baseline: analyst median forecast.",
            data_available=True,
        )


class ExternalNowcastBaseline:
    """Estimate = external nowcast (e.g. Cleveland Fed)."""

    name = "external_nowcast"

    def predict(self, nowcast: float | None, source: str = "") -> BaselineResult:
        if nowcast is None:
            return BaselineResult(
                model_name=self.name,
                estimate=None, lower_bound=None, upper_bound=None,
                note="External nowcast not available.",
                data_available=False,
            )
        return BaselineResult(
            model_name=self.name,
            estimate=nowcast,
            lower_bound=None,
            upper_bound=None,
            note=f"External nowcast ({source}). This is one model's estimate, not ground truth.",
            data_available=True,
        )


def run_all_baselines(
    series: pd.Series,
    consensus: float | None,
    nowcast: float | None,
    nowcast_source: str = "cleveland_fed",
) -> list[BaselineResult]:
    """Run all baseline models and return their results."""
    return [
        SeasonalNaiveBaseline().predict(series),
        PreviousValueBaseline().predict(series),
        RollingAverageBaseline().predict(series),
        ConsensusBaseline().predict(consensus),
        ExternalNowcastBaseline().predict(nowcast, source=nowcast_source),
    ]
