"""
Forecasting pipeline models.

ForecastRun — one complete forecast run for an event release.
ForecastFeature — individual feature values used in a run.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class CalibrationStatus(models.TextChoices):
    VERIFIED = "VERIFIED", "Calibration Verified"
    UNVERIFIED = "UNVERIFIED", "Not Yet Calibrated"
    INSUFFICIENT = "INSUFFICIENT", "Insufficient Sample"
    FAILED = "FAILED", "Calibration Failed"


class DataQualityStatus(models.TextChoices):
    GOOD = "GOOD", "Good"
    DEGRADED = "DEGRADED", "Degraded (some features missing)"
    POOR = "POOR", "Poor (critical features missing)"
    UNAVAILABLE = "UNAVAILABLE", "Forecast Unavailable"


class ForecastRun(models.Model):
    """
    A complete forecast produced before an economic release.

    The snapshot is permanent: after the actual is released,
    the actual is recorded in EconomicRelease but this record
    is never modified.
    """

    event = models.ForeignKey(
        "events.EconomicEvent",
        on_delete=models.CASCADE,
        related_name="forecast_runs",
    )
    economic_release = models.ForeignKey(
        "events.EconomicRelease",
        on_delete=models.CASCADE,
        related_name="forecast_runs",
        null=True,
        blank=True,
    )
    model_name = models.CharField(max_length=64)
    model_version = models.CharField(max_length=32)
    run_time_utc = models.DateTimeField(default=timezone.now, db_index=True)
    data_cutoff_time_utc = models.DateTimeField(
        help_text="Latest data timestamp used in this forecast.",
    )
    # ── Economic estimate ─────────────────────────────────────────────────────
    estimate = models.FloatField(
        null=True,
        blank=True,
        help_text="Point estimate of the official number.",
    )
    lower_bound = models.FloatField(
        null=True,
        blank=True,
        help_text="Lower bound of the 90% prediction interval.",
    )
    upper_bound = models.FloatField(
        null=True,
        blank=True,
        help_text="Upper bound of the 90% prediction interval.",
    )
    # ── Surprise probabilities ────────────────────────────────────────────────
    probability_below_consensus = models.FloatField(
        null=True, blank=True,
        help_text="Calibrated probability of outcome below consensus.",
    )
    probability_near_consensus = models.FloatField(
        null=True, blank=True,
        help_text="Calibrated probability of outcome near consensus (within configured band).",
    )
    probability_above_consensus = models.FloatField(
        null=True, blank=True,
        help_text="Calibrated probability of outcome above consensus.",
    )
    near_consensus_band = models.FloatField(
        default=0.05,
        help_text="Half-width of the 'near consensus' band (percentage points).",
    )
    # ── Event bias ────────────────────────────────────────────────────────────
    event_bias = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="e.g. 'Moderately bullish USD', 'Bearish EUR', 'Neutral'.",
    )
    # ── Quality metadata ──────────────────────────────────────────────────────
    data_quality_status = models.CharField(
        max_length=16,
        choices=DataQualityStatus.choices,
        default=DataQualityStatus.UNAVAILABLE,
    )
    calibration_status = models.CharField(
        max_length=16,
        choices=CalibrationStatus.choices,
        default=CalibrationStatus.UNVERIFIED,
    )
    feature_snapshot_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 of the feature values at forecast time.",
    )
    warnings = models.JSONField(
        default=list,
        help_text="List of warning strings attached to this forecast.",
    )
    data_sources_used = models.JSONField(
        default=list,
        help_text="List of provider/series IDs used in this run.",
    )
    comparable_releases_count = models.IntegerField(
        default=0,
        help_text="Number of comparable historical releases used in calibration.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-run_time_utc"]
        verbose_name = "Forecast Run"
        verbose_name_plural = "Forecast Runs"
        indexes = [
            models.Index(fields=["event", "run_time_utc"]),
            models.Index(fields=["economic_release", "run_time_utc"]),
        ]

    def __str__(self) -> str:
        return f"ForecastRun {self.event.code} [{self.model_name}] @ {self.run_time_utc}"

    @property
    def is_valid(self) -> bool:
        return self.data_quality_status not in (
            DataQualityStatus.UNAVAILABLE,
            DataQualityStatus.POOR,
        )

    @property
    def estimated_surprise(self) -> float | None:
        """Estimate minus consensus."""
        if self.estimate is None:
            return None
        release = self.economic_release
        if release and release.consensus is not None:
            return self.estimate - float(release.consensus)
        return None


class ForecastFeature(models.Model):
    """
    Individual feature value recorded at forecast time.

    Every feature used in a ForecastRun is persisted here for
    reproducibility, explainability, and backtesting.
    """

    forecast_run = models.ForeignKey(
        ForecastRun,
        on_delete=models.CASCADE,
        related_name="features",
    )
    feature_name = models.CharField(max_length=128)
    value = models.FloatField(null=True, blank=True)
    source = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="provider/series_id",
    )
    publication_time_utc = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this value was published — for PIT audit.",
    )
    lag_days = models.IntegerField(
        default=0,
        help_text="Number of days between observation date and forecast date.",
    )
    contribution = models.FloatField(
        null=True,
        blank=True,
        help_text="Feature's contribution to the forecast (SHAP value or regression coefficient).",
    )
    missing_flag = models.BooleanField(
        default=False,
        help_text="True if the feature was unavailable and a fallback was used.",
    )
    revised_flag = models.BooleanField(
        default=False,
        help_text="True if the value used was later revised (for backtest analysis).",
    )

    class Meta:
        verbose_name = "Forecast Feature"
        verbose_name_plural = "Forecast Features"
        unique_together = [("forecast_run", "feature_name")]

    def __str__(self) -> str:
        return f"{self.forecast_run_id}: {self.feature_name}={self.value}"
