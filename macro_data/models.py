"""
Macro-data storage models.

DataObservation  — one time-series observation from any macro provider.
MarketObservation — one OHLCV candle from the market data provider.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class DataObservation(models.Model):
    """
    One observation from a macro time series.

    Stores the value as it was known at retrieved_at, with vintage tracking
    for point-in-time correctness.

    IMPORTANT: Never use the latest value in a historical backtest if
    publication_time_utc > backtest cutoff time.
    """

    provider = models.CharField(max_length=64, db_index=True)
    series_id = models.CharField(max_length=128, db_index=True)
    observation_date = models.DateTimeField(
        db_index=True,
        help_text="Date the economic observation refers to (not the publication date).",
    )
    publication_time_utc = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When this observation was publicly available. "
            "Used for point-in-time filtering. "
            "Null means publication time is unknown — treat as lower quality."
        ),
    )
    retrieved_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When this record was fetched from the provider.",
    )
    value = models.FloatField()
    unit = models.CharField(max_length=32, blank=True, default="")
    seasonal_adjustment = models.CharField(
        max_length=8,
        blank=True,
        default="",
        help_text="'SA' = seasonally adjusted, 'NSA' = not adjusted, '' = unknown.",
    )
    vintage_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "FRED realtime_start / vintage date. "
            "Identifies which revision of the data this represents."
        ),
    )
    revision_number = models.IntegerField(
        default=0,
        help_text="0 = initial release, 1+ = revision number.",
    )
    publication_approximate = models.BooleanField(
        default=False,
        help_text=(
            "True if publication_time_utc is an estimate, not the exact publication time. "
            "Excluded from strict backtests."
        ),
    )
    raw_payload_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "Data Observation"
        verbose_name_plural = "Data Observations"
        unique_together = [("provider", "series_id", "observation_date", "vintage_date")]
        indexes = [
            models.Index(fields=["provider", "series_id", "observation_date"]),
            models.Index(fields=["series_id", "publication_time_utc"]),
            models.Index(fields=["provider", "series_id", "retrieved_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provider}/{self.series_id} "
            f"{self.observation_date.date()} = {self.value}"
        )


class MarketObservation(models.Model):
    """
    One OHLCV candle for a financial instrument.
    """

    provider = models.CharField(max_length=64, db_index=True)
    symbol = models.CharField(max_length=16, db_index=True)
    timestamp_utc = models.DateTimeField(db_index=True)
    timeframe = models.CharField(
        max_length=8,
        db_index=True,
        help_text="'1min', '5min', '15min', '1h', '4h', '1day'",
    )
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField(default=0.0)
    is_delayed = models.BooleanField(
        default=False,
        help_text="True if the data feed is delayed (e.g. 15 min delay). Never treat as real-time.",
    )

    class Meta:
        verbose_name = "Market Observation"
        verbose_name_plural = "Market Observations"
        unique_together = [("provider", "symbol", "timeframe", "timestamp_utc")]
        indexes = [
            models.Index(fields=["symbol", "timeframe", "timestamp_utc"]),
            models.Index(fields=["symbol", "timestamp_utc"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.symbol} {self.timeframe} "
            f"{self.timestamp_utc.strftime('%Y-%m-%d %H:%M')} "
            f"C={self.close}"
        )
