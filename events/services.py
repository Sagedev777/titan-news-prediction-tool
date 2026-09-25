"""
Business-logic services for the events app.

All red-folder enforcement happens here.  No other layer may
accept an event without going through these services.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ALLOWLISTED_EVENT_CODES,
    DataQualityIssue,
    DataQualityIssueType,
    DataQualitySeverity,
    EconomicEvent,
    EconomicRelease,
    ImpactLevel,
    ProviderRequestLog,
)

logger = logging.getLogger("events")


# ── Impact normalisation ───────────────────────────────────────────────────────

# Map provider-supplied strings to our normalised levels.
# Be explicit: anything not mapped goes to UNKNOWN.
_IMPACT_MAP: dict[str, str] = {
    # Trading Economics
    "3": ImpactLevel.HIGH,
    "high": ImpactLevel.HIGH,
    "2": ImpactLevel.MEDIUM,
    "medium": ImpactLevel.MEDIUM,
    "1": ImpactLevel.LOW,
    "low": ImpactLevel.LOW,
    # Generic
    "red": ImpactLevel.HIGH,
    "orange": ImpactLevel.MEDIUM,
    "yellow": ImpactLevel.LOW,
}


def normalize_impact(raw: Any) -> str:
    """
    Convert provider impact value to one of HIGH / MEDIUM / LOW / UNKNOWN.

    Parameters
    ----------
    raw : Any
        Provider-supplied impact value (string, int, or None).

    Returns
    -------
    str
        One of the ImpactLevel choices.
    """
    if raw is None:
        return ImpactLevel.UNKNOWN
    key = str(raw).strip().lower()
    return _IMPACT_MAP.get(key, ImpactLevel.UNKNOWN)


# ── Red-folder gate ────────────────────────────────────────────────────────────

def is_red_folder(event: EconomicEvent) -> bool:
    """
    Return True iff the event passes the red-folder criteria.

    This function is the canonical enforcement point.
    Call it everywhere; do not duplicate the logic.
    """
    return (
        event.normalized_impact_level == ImpactLevel.HIGH
        and event.is_allowlisted is True
    )


def assert_red_folder(event: EconomicEvent) -> None:
    """
    Raise ValueError if the event does not pass the red-folder gate.

    Use this at the start of any service that must only accept red-folder
    events (forecasting, alert dispatch, etc.).
    """
    if not is_red_folder(event):
        raise ValueError(
            f"Event {event.code!r} is not a red-folder event. "
            f"impact={event.normalized_impact_level!r}, "
            f"allowlisted={event.is_allowlisted}. "
            "Only HIGH-impact allowlisted events enter the forecasting pipeline."
        )


# ── Payload hashing ────────────────────────────────────────────────────────────

def hash_payload(payload: Any) -> str:
    """Return SHA-256 hex digest of the serialised payload."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


# ── Event upsert service ───────────────────────────────────────────────────────

@transaction.atomic
def upsert_economic_event(
    code: str,
    provider_event_id: str,
    name: str,
    country: str,
    currency: str,
    category: str,
    provider_impact_level: str,
    official_source: str = "",
    provider: str = "trading_economics",
) -> tuple[EconomicEvent, bool]:
    """
    Create or update an EconomicEvent record.

    Returns (event, created).

    normalised_impact_level and is_allowlisted are computed automatically.
    """
    normalized = normalize_impact(provider_impact_level)

    event, created = EconomicEvent.objects.update_or_create(
        code=code,
        defaults=dict(
            provider_event_id=provider_event_id,
            name=name,
            country=country,
            currency=currency,
            category=category,
            provider_impact_level=str(provider_impact_level),
            normalized_impact_level=normalized,
            # is_allowlisted is set in model.save()
            official_source=official_source,
            provider=provider,
        ),
    )

    logger.info(
        "upsert_economic_event",
        extra={
            "event_code": code,
            "normalized_impact": normalized,
            "is_allowlisted": event.is_allowlisted,
            "was_created": created,
        },
    )

    return event, created


# ── Release upsert service ─────────────────────────────────────────────────────

@transaction.atomic
def upsert_economic_release(
    event: EconomicEvent,
    period: str,
    release_time_utc: datetime,
    consensus: float | None,
    previous: float | None,
    actual: float | None,
    revised_previous: float | None,
    unit: str,
    raw_payload: Any,
) -> tuple[EconomicRelease, bool]:
    """
    Create or update an EconomicRelease.

    Never overwrites the actual field with None once it is set
    (protects the permanent record of the official print).
    """
    payload_hash = hash_payload(raw_payload)

    release, created = EconomicRelease.objects.get_or_create(
        event=event,
        period=period,
        defaults=dict(
            release_time_utc=release_time_utc,
            consensus=consensus,
            previous=previous,
            actual=actual,
            revised_previous=revised_previous,
            unit=unit,
            retrieved_at=timezone.now(),
            raw_payload_hash=payload_hash,
        ),
    )

    if not created:
        # Always update non-actual fields (consensus changes pre-release)
        release.release_time_utc = release_time_utc
        release.consensus = consensus
        release.previous = previous
        release.unit = unit
        release.retrieved_at = timezone.now()
        release.raw_payload_hash = payload_hash

        # Only update actual if provider now has it
        if actual is not None:
            release.actual = actual

        if revised_previous is not None:
            release.revised_previous = revised_previous
            release.is_revised = True

        release.save()

    return release, created


# ── Upcoming red-folder releases ───────────────────────────────────────────────

def get_upcoming_red_folder_releases(
    hours_ahead: int = 48,
) -> list[EconomicRelease]:
    """
    Return upcoming EconomicRelease rows that pass the red-folder gate.

    Only events that are HIGH + allowlisted + forecastable are returned.
    Never returns excluded or non-red events.
    """
    now = timezone.now()
    cutoff = now + timedelta(hours=hours_ahead)

    return list(
        EconomicRelease.objects.select_related("event")
        .filter(
            release_time_utc__gte=now,
            release_time_utc__lte=cutoff,
            actual__isnull=True,  # Not yet released
            event__normalized_impact_level=ImpactLevel.HIGH,
            event__is_allowlisted=True,
            event__is_forecastable=True,
        )
        .order_by("release_time_utc")
    )


def get_all_red_folder_releases(
    start: datetime,
    end: datetime,
    forecastable_only: bool = True,
) -> list[EconomicRelease]:
    """
    Return historical red-folder releases in a date range.

    Enforces the red-folder filter at the database level.
    """
    qs = EconomicRelease.objects.select_related("event").filter(
        release_time_utc__gte=start,
        release_time_utc__lte=end,
        event__normalized_impact_level=ImpactLevel.HIGH,
        event__is_allowlisted=True,
    )
    if forecastable_only:
        qs = qs.filter(event__is_forecastable=True)
    return list(qs.order_by("release_time_utc"))


# ── Data-quality issue recording ───────────────────────────────────────────────

def record_data_quality_issue(
    provider: str,
    series_id: str,
    issue_type: str,
    severity: str,
    message: str,
) -> DataQualityIssue:
    """Create a DataQualityIssue record and log it."""
    issue = DataQualityIssue.objects.create(
        provider=provider,
        series_id=series_id,
        issue_type=issue_type,
        severity=severity,
        message=message,
    )
    log_fn = logger.error if severity == DataQualitySeverity.CRITICAL else logger.warning
    log_fn(f"DataQualityIssue: [{severity}] {provider}/{series_id}: {message}")
    return issue


# ── Provider request log ───────────────────────────────────────────────────────

def log_provider_request(
    provider: str,
    endpoint: str,
    request_time: datetime,
    response_time: datetime | None,
    http_status: int | None,
    response_hash: str,
    error_message: str = "",
) -> ProviderRequestLog:
    """Persist an audit log entry for a provider API call."""
    latency = None
    if response_time and request_time:
        latency = int((response_time - request_time).total_seconds() * 1000)

    return ProviderRequestLog.objects.create(
        provider=provider,
        endpoint=endpoint,
        request_time_utc=request_time,
        response_time_utc=response_time,
        http_status=http_status,
        latency_ms=latency,
        response_hash=response_hash,
        error_message=error_message,
        success=(http_status is not None and 200 <= http_status < 300),
    )
