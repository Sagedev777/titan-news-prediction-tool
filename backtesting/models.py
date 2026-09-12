"""Backtesting run and result models."""
from __future__ import annotations
from django.db import models
from django.utils import timezone


class BacktestRun(models.Model):
    name = models.CharField(max_length=128)
    event_code = models.CharField(max_length=64, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField()
    model_version = models.CharField(max_length=32)
    data_vintage_policy = models.CharField(
        max_length=32,
        default="strict_pit",
        help_text="'strict_pit' = only use data available at forecast time. Never 'latest'.",
    )
    status = models.CharField(max_length=16, default="pending")
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict)
    limitations = models.JSONField(
        default=list,
        help_text=(
            "List of known data-quality limitations that affect the accuracy of "
            "this backtest.  Each entry is a plain-English description. "
            "Always read this before interpreting the results."
        ),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Backtest {self.name} [{self.event_code}] {self.start_date}→{self.end_date}"


class BacktestResult(models.Model):
    backtest_run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="results")
    economic_release = models.ForeignKey(
        "events.EconomicRelease", on_delete=models.CASCADE, null=True, blank=True
    )
    forecast_estimate = models.FloatField(null=True, blank=True)
    forecast_lower = models.FloatField(null=True, blank=True)
    forecast_upper = models.FloatField(null=True, blank=True)
    consensus_at_cutoff = models.FloatField(null=True, blank=True)
    consensus_is_approximate = models.BooleanField(
        default=True,
        help_text=(
            "True when consensus_at_cutoff is the current stored value rather than "
            "the historically-correct value at the simulated forecast time. "
            "This is the case whenever point-in-time consensus history is not "
            "available from the calendar provider (e.g. Trading Economics free tier). "
            "Results where this is True should be interpreted with caution: "
            "surprise classification (ABOVE/NEAR/BELOW) may be slightly wrong "
            "if the consensus shifted materially before release day."
        ),
    )
    actual = models.FloatField(null=True, blank=True)
    forecast_error = models.FloatField(null=True, blank=True)
    surprise = models.FloatField(null=True, blank=True)
    predicted_class = models.CharField(max_length=8, blank=True, default="")
    actual_class = models.CharField(max_length=8, blank=True, default="")
    symbol = models.CharField(max_length=16, blank=True, default="")
    horizon = models.CharField(max_length=8, blank=True, default="")
    predicted_probability = models.FloatField(null=True, blank=True)
    realized_return = models.FloatField(null=True, blank=True)
    correct_direction = models.BooleanField(null=True, blank=True)
    brier_score = models.FloatField(null=True, blank=True)
    log_loss = models.FloatField(null=True, blank=True)
    interval_covered = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["backtest_run", "economic_release__release_time_utc"]

    def __str__(self) -> str:
        return f"BacktestResult {self.backtest_run_id}: {self.symbol or 'macro'}"
