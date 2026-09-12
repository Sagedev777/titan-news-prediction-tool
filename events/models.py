"""
Core event and release models.

EconomicEvent  — the template / definition of a recurring release.
EconomicRelease — one specific scheduled release instance.
DataQualityIssue — data-quality problems detected by health checks.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


# ── Constants ─────────────────────────────────────────────────────────────────

class ImpactLevel(models.TextChoices):
    HIGH = "HIGH", "High (Red Folder)"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"
    UNKNOWN = "UNKNOWN", "Unknown"


class DataQualitySeverity(models.TextChoices):
    CRITICAL = "CRITICAL", "Critical"
    WARNING = "WARNING", "Warning"
    INFO = "INFO", "Info"


class DataQualityIssueType(models.TextChoices):
    MISSING_DATA = "MISSING_DATA", "Missing Data"
    STALE_DATA = "STALE_DATA", "Stale Data"
    DUPLICATE = "DUPLICATE", "Duplicate Record"
    TIMEZONE_ERROR = "TIMEZONE_ERROR", "Timezone Error"
    REVISION = "REVISION", "Data Revision"
    API_ERROR = "API_ERROR", "API Error"
    INVALID_VALUE = "INVALID_VALUE", "Invalid Value"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE", "Provider Unavailable"


# ── Supported event allowlist ─────────────────────────────────────────────────
# This is the canonical source of truth.  Only events in this registry
# can enter the forecasting pipeline.

ALLOWLISTED_EVENT_CODES: frozenset[str] = frozenset(
    [
        # United States
        "US_CPI",
        "US_CORE_CPI",
        "US_NFP",
        "US_UNEMPLOYMENT_RATE",
        "US_AVERAGE_HOURLY_EARNINGS",
        "US_FOMC_RATE_DECISION",
        "US_FOMC_STATEMENT",
        "US_GDP",
        "US_PPI",
        "US_CORE_PPI",
        "US_RETAIL_SALES",
        # Euro Area
        "EUROZONE_CPI",
        "EUROZONE_CORE_CPI",
        "ECB_RATE_DECISION",
        "EUROZONE_GDP",
        # United Kingdom
        "UK_CPI",
        "UK_CORE_CPI",
        "BOE_RATE_DECISION",
        "UK_GDP",
        # Canada
        "CANADA_CPI",
        "CANADA_EMPLOYMENT_CHANGE",
        "CANADA_UNEMPLOYMENT_RATE",
        "BOC_RATE_DECISION",
        # Australia
        "AUSTRALIA_CPI",
        "AUSTRALIA_EMPLOYMENT_CHANGE",
        "AUSTRALIA_UNEMPLOYMENT_RATE",
        "RBA_RATE_DECISION",
        # New Zealand
        "NEW_ZEALAND_CPI",
        "NEW_ZEALAND_EMPLOYMENT_CHANGE",
        "NEW_ZEALAND_UNEMPLOYMENT_RATE",
        "RBNZ_RATE_DECISION",
        # Japan
        "JAPAN_CPI",
        "BOJ_RATE_DECISION",
    ]
)


# ── EconomicEvent ─────────────────────────────────────────────────────────────

class EconomicEvent(models.Model):
    """
    Template record for a recurring economic event.

    One row per event type (e.g. US_CPI).  Individual scheduled
    releases are stored in EconomicRelease.
    """

    code = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Internal event code, e.g. US_CPI.  Must match ALLOWLISTED_EVENT_CODES.",
    )
    provider_event_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Provider's own ID for this event, used for API lookups.",
    )
    name = models.CharField(max_length=255, help_text="Human-readable event name.")
    country = models.CharField(max_length=64)
    currency = models.CharField(max_length=8, help_text="ISO 4217 currency code, e.g. USD.")
    category = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Provider-supplied category string.",
    )
    provider_impact_level = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Raw impact string from the provider before normalisation.",
    )
    normalized_impact_level = models.CharField(
        max_length=16,
        choices=ImpactLevel.choices,
        default=ImpactLevel.UNKNOWN,
        db_index=True,
        help_text="Normalised impact level.  Only HIGH events enter the pipeline.",
    )
    is_allowlisted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True iff the event code is in ALLOWLISTED_EVENT_CODES.",
    )
    is_forecastable = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when an event-specific model is implemented and passes validation.",
    )
    official_source = models.URLField(
        blank=True,
        default="",
        help_text="URL of the official statistical release page.",
    )
    provider = models.CharField(
        max_length=64,
        default="trading_economics",
        help_text="Primary data provider for this event.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["country", "name"]
        verbose_name = "Economic Event"
        verbose_name_plural = "Economic Events"
        indexes = [
            models.Index(fields=["normalized_impact_level", "is_allowlisted"]),
            models.Index(fields=["normalized_impact_level", "is_allowlisted", "is_forecastable"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name} ({self.country})"

    # ── Red-folder gate ───────────────────────────────────────────────────────
    @property
    def is_red_folder(self) -> bool:
        """
        True iff the event passes ALL red-folder criteria.

        This is the single authoritative gate.  Every part of the
        application that needs to enforce the red-folder policy must
        call this property (or use the is_red_folder_qs queryset helper).
        """
        return (
            self.normalized_impact_level == ImpactLevel.HIGH
            and self.is_allowlisted is True
        )

    @property
    def is_pipeline_ready(self) -> bool:
        """True iff the event is red-folder AND has a working model."""
        return self.is_red_folder and self.is_forecastable is True

    def save(self, *args, **kwargs):
        # Auto-populate is_allowlisted from the registry on every save.
        self.is_allowlisted = self.code in ALLOWLISTED_EVENT_CODES
        super().save(*args, **kwargs)


# ── EconomicRelease ───────────────────────────────────────────────────────────

class EconomicRelease(models.Model):
    """
    One scheduled release of an economic event.

    Stores the figures known at ingestion time.  After release,
    the actual and revised_previous fields are filled in without
    overwriting any pre-release snapshot.
    """

    event = models.ForeignKey(
        EconomicEvent,
        on_delete=models.CASCADE,
        related_name="releases",
        db_index=True,
    )
    period = models.CharField(
        max_length=32,
        help_text="Reference period, e.g. '2024-06' or 'Q2 2024'.",
    )
    forecast = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Provider-supplied analyst consensus (may change before release).",
    )
    consensus = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Most recent consensus at last ingestion.",
    )
    previous = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Prior release value as shown by the provider.",
    )
    actual = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Officially released value.  Null before release.",
    )
    revised_previous = models.DecimalField(
        max_digits=16,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Revised prior value released alongside the current print.",
    )
    unit = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Unit of measurement, e.g. 'pct', 'K', 'bps'.",
    )
    release_time_utc = models.DateTimeField(
        db_index=True,
        help_text="Scheduled (or actual) release time in UTC.",
    )
    retrieved_at = models.DateTimeField(
        default=timezone.now,
        help_text="When this row was last updated from the provider.",
    )
    is_revised = models.BooleanField(
        default=False,
        help_text="True if a subsequent release revised the official number.",
    )
    raw_payload_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 of the raw provider JSON for audit purposes.",
    )

    class Meta:
        ordering = ["-release_time_utc"]
        verbose_name = "Economic Release"
        verbose_name_plural = "Economic Releases"
        unique_together = [("event", "period")]
        indexes = [
            models.Index(fields=["event", "release_time_utc"]),
            models.Index(fields=["release_time_utc"]),
        ]

    def __str__(self) -> str:
        actual_str = f"  actual={self.actual}" if self.actual is not None else ""
        return f"{self.event.code} [{self.period}]{actual_str}"

    @property
    def surprise(self):
        """Actual minus consensus.  None if either is missing."""
        if self.actual is not None and self.consensus is not None:
            return float(self.actual) - float(self.consensus)
        return None

    @property
    def is_released(self) -> bool:
        return self.actual is not None


# ── DataQualityIssue ──────────────────────────────────────────────────────────

class DataQualityIssue(models.Model):
    """Detected data-quality problem from any provider or series."""

    provider = models.CharField(max_length=64)
    series_id = models.CharField(max_length=128, blank=True, default="")
    issue_type = models.CharField(
        max_length=32,
        choices=DataQualityIssueType.choices,
    )
    severity = models.CharField(
        max_length=16,
        choices=DataQualitySeverity.choices,
        default=DataQualitySeverity.WARNING,
    )
    message = models.TextField()
    detected_at = models.DateTimeField(default=timezone.now)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        verbose_name = "Data Quality Issue"
        verbose_name_plural = "Data Quality Issues"
        indexes = [
            models.Index(fields=["provider", "resolved"]),
            models.Index(fields=["severity", "resolved"]),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.provider}/{self.series_id}: {self.issue_type}"


# ── Provider API log ──────────────────────────────────────────────────────────

class ProviderRequestLog(models.Model):
    """Audit log of every outbound API request to a data provider."""

    provider = models.CharField(max_length=64, db_index=True)
    endpoint = models.CharField(
        max_length=512,
        help_text="URL with secrets stripped.",
    )
    request_time_utc = models.DateTimeField()
    response_time_utc = models.DateTimeField(null=True, blank=True)
    http_status = models.IntegerField(null=True, blank=True)
    latency_ms = models.IntegerField(null=True, blank=True)
    response_hash = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    success = models.BooleanField(default=False)

    class Meta:
        ordering = ["-request_time_utc"]
        verbose_name = "Provider Request Log"
        verbose_name_plural = "Provider Request Logs"
        indexes = [
            models.Index(fields=["provider", "request_time_utc"]),
            models.Index(fields=["provider", "success"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.endpoint} [{self.http_status}] {self.request_time_utc}"
