"""
Market reaction models.

InstrumentForecast — per-instrument signal for a ForecastRun.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class SignalType(models.TextChoices):
    BUY = "BUY", "Buy"
    SELL = "SELL", "Sell"
    NEUTRAL = "NEUTRAL", "Neutral"
    NO_SIGNAL = "NO_SIGNAL", "No Signal"


class EvidenceQuality(models.TextChoices):
    HIGH = "HIGH", "High"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"
    INSUFFICIENT = "INSUFFICIENT", "Insufficient"


class InstrumentForecast(models.Model):
    """
    Forecast of market reaction for one instrument after an economic event.

    Stores per-instrument, per-horizon signal with all supporting metrics.
    """

    forecast_run = models.ForeignKey(
        "forecasting.ForecastRun",
        on_delete=models.CASCADE,
        related_name="instrument_forecasts",
    )
    symbol = models.CharField(max_length=16, db_index=True)
    horizon = models.CharField(
        max_length=8,
        help_text="'5min', '15min', '1h', '4h', '1day'",
    )
    signal = models.CharField(
        max_length=16,
        choices=SignalType.choices,
        default=SignalType.NO_SIGNAL,
    )
    probability_up = models.FloatField(null=True, blank=True)
    probability_down = models.FloatField(null=True, blank=True)
    probability_flat = models.FloatField(null=True, blank=True)
    expected_return = models.FloatField(
        null=True, blank=True,
        help_text="Expected return in pips or percent.",
    )
    lower_return_bound = models.FloatField(null=True, blank=True)
    upper_return_bound = models.FloatField(null=True, blank=True)
    historical_accuracy = models.FloatField(
        null=True, blank=True,
        help_text="Historical direction accuracy (0.0–1.0) for this event/symbol/horizon.",
    )
    sample_size = models.IntegerField(
        default=0,
        help_text="Number of comparable historical observations.",
    )
    ranking_score = models.FloatField(
        null=True, blank=True,
        help_text="Composite ranking score (higher = stronger evidence).",
    )
    evidence_quality = models.CharField(
        max_length=16,
        choices=EvidenceQuality.choices,
        default=EvidenceQuality.INSUFFICIENT,
    )
    explanation = models.TextField(blank=True, default="")
    warnings = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-ranking_score"]
        verbose_name = "Instrument Forecast"
        verbose_name_plural = "Instrument Forecasts"
        unique_together = [("forecast_run", "symbol", "horizon")]
        indexes = [
            models.Index(fields=["forecast_run", "ranking_score"]),
            models.Index(fields=["symbol", "horizon"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.horizon}: {self.signal} ({self.forecast_run_id})"

    @property
    def probability_edge(self) -> float | None:
        """Probability of the primary direction minus 0.5."""
        if self.signal == SignalType.BUY and self.probability_up is not None:
            return self.probability_up - 0.5
        if self.signal == SignalType.SELL and self.probability_down is not None:
            return self.probability_down - 0.5
        return None

    @property
    def display_probability(self) -> float | None:
        """The probability shown on the dashboard for this signal."""
        if self.signal == SignalType.BUY:
            return self.probability_up
        if self.signal == SignalType.SELL:
            return self.probability_down
        return None
