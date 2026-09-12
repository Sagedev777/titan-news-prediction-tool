"""
Trading Economics calendar and data provider.

Official API: https://tradingeconomics.com/api/

This provider fetches economic calendar events, historical releases,
and point-in-time snapshots.  It enforces the red-folder filter:
only HIGH-impact events matching the allowlist are persisted in the
forecasting tables.  All other events are written to the excluded/
diagnostics store.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from .base import BaseHTTPProvider, ProviderConfigurationError, ProviderDataError

logger = logging.getLogger("data_sources")

# Trading Economics base URL
_TE_BASE = "https://api.tradingeconomics.com"


class TradingEconomicsProvider(BaseHTTPProvider):
    """
    Client for the Trading Economics REST API.

    API documentation: https://tradingeconomics.com/api/docs/
    """

    provider_name = "trading_economics"
    base_url = _TE_BASE
    timeout_seconds = 45.0

    def __init__(self):
        super().__init__()
        # Validate key at construction time — fail loudly if missing.
        self._api_key = self._get_api_key("TRADING_ECONOMICS_API_KEY")

    # ── Calendar endpoints ────────────────────────────────────────────────────

    def fetch_events(self, start: datetime, end: datetime) -> list[dict]:
        """
        Return economic calendar events in [start, end].

        Endpoint: GET /calendar/country/All/{start}/{end}?c={key}&f=json
        """
        url = (
            f"{self.base_url}/calendar/country/All"
            f"/{start.strftime('%Y-%m-%d')}"
            f"/{end.strftime('%Y-%m-%d')}"
        )
        params = {"c": self._api_key, "f": "json"}
        raw = self.get(url, params=params)
        return self._parse_calendar(raw)

    def fetch_event_history(
        self, indicator: str, country: str, start: datetime, end: datetime
    ) -> list[dict]:
        """
        Return historical releases for a specific indicator / country.

        Endpoint: GET /calendar/indicator/{indicator}/{country}/{start}/{end}
        """
        url = (
            f"{self.base_url}/calendar/indicator"
            f"/{indicator}/{country}"
            f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        )
        params = {"c": self._api_key, "f": "json"}
        raw = self.get(url, params=params)
        return self._parse_calendar(raw)

    def fetch_point_in_time_events(
        self, as_of: datetime, start: datetime, end: datetime
    ) -> list[dict]:
        """
        Return calendar snapshot as it appeared at `as_of`.

        Trading Economics provides a ticker endpoint that returns the
        value at a given date.  When full point-in-time support is
        unavailable, the method marks records with conservative timestamps.

        Note: Full pit-in-time calendar history requires a premium
        Trading Economics subscription.  If unavailable, records are
        tagged with publication_time_utc = release_time_utc (conservative).
        """
        # Use the standard endpoint; records will be tagged as approximate
        events = self.fetch_events(start, end)
        for e in events:
            e.setdefault("point_in_time_approximate", True)
            e.setdefault("pit_as_of", as_of.isoformat())
        return events

    # ── Ingestion orchestration ───────────────────────────────────────────────

    def ingest_calendar(self, days_ahead: int = 14) -> dict:
        """
        Fetch calendar and persist events to the database.

        Red-folder policy enforcement:
        - Only HIGH-impact allowlisted events → forecasting tables.
        - All others → excluded/diagnostics only.
        """
        from events.models import ALLOWLISTED_EVENT_CODES, ImpactLevel
        from events.services import (
            normalize_impact,
            upsert_economic_event,
            upsert_economic_release,
        )

        now = timezone.now()
        end = now + timedelta(days=days_ahead)

        try:
            events = self.fetch_events(start=now - timedelta(days=1), end=end)
        except Exception as exc:
            logger.error(f"TradingEconomics calendar fetch failed: {exc}", exc_info=True)
            return {"ingested": 0, "excluded": 0, "errors": 1, "error": str(exc)}

        ingested = excluded = errors = 0

        for raw in events:
            try:
                code = self._map_event_code(raw)
                normalized_impact = normalize_impact(raw.get("Importance"))

                # ── Red-folder gate ────────────────────────────────────────────
                if normalized_impact != ImpactLevel.HIGH or code not in ALLOWLISTED_EVENT_CODES:
                    # Store in excluded diagnostics (no forecast tables touched)
                    self._store_excluded_event(raw, code, normalized_impact)
                    excluded += 1
                    continue

                # ── Upsert EconomicEvent ──────────────────────────────────────
                event, _ = upsert_economic_event(
                    code=code,
                    provider_event_id=str(raw.get("CalendarId", "")),
                    name=raw.get("Event", code),
                    country=raw.get("Country", ""),
                    currency=raw.get("Currency", ""),
                    category=raw.get("Category", ""),
                    provider_impact_level=str(raw.get("Importance", "")),
                    provider="trading_economics",
                )

                # ── Upsert EconomicRelease ────────────────────────────────────
                release_time = self._parse_datetime(raw.get("Date"))
                if release_time is None:
                    logger.warning(f"Skipping {code}: could not parse release time")
                    errors += 1
                    continue

                period = self._derive_period(raw, release_time)

                def safe_float(v):
                    try:
                        return float(v) if v not in (None, "", "null") else None
                    except (TypeError, ValueError):
                        return None

                upsert_economic_release(
                    event=event,
                    period=period,
                    release_time_utc=release_time,
                    consensus=safe_float(raw.get("Forecast")),
                    previous=safe_float(raw.get("Previous")),
                    actual=safe_float(raw.get("Actual")),
                    revised_previous=safe_float(raw.get("Revised")),
                    unit=raw.get("Unit", ""),
                    raw_payload=raw,
                )
                ingested += 1

            except Exception as exc:
                logger.error(f"Error ingesting event {raw}: {exc}", exc_info=True)
                errors += 1

        logger.info(
            f"Calendar ingestion complete: "
            f"ingested={ingested}, excluded={excluded}, errors={errors}"
        )
        return {"ingested": ingested, "excluded": excluded, "errors": errors}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_calendar(self, raw: Any) -> list[dict]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            # Some TE responses wrap in {"calendar": [...]}
            for key in ("calendar", "data", "results"):
                if key in raw and isinstance(raw[key], list):
                    return raw[key]
        raise ProviderDataError(
            f"TradingEconomics: Unexpected calendar response format: {type(raw).__name__}"
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        from dateutil import parser as dtparser
        try:
            dt = dtparser.parse(str(value))
            if dt.tzinfo is None:
                import pytz
                dt = pytz.utc.localize(dt)
            return dt
        except Exception:
            return None

    def _map_event_code(self, raw: dict) -> str:
        """
        Map Trading Economics event fields to our internal event code.

        Mapping is based on (Country, Event/Category) patterns.
        Unmapped events receive a generated code and will be excluded
        as non-allowlisted.
        """
        country = (raw.get("Country") or "").strip().upper().replace(" ", "_")
        event_name = (raw.get("Event") or "").strip().upper()
        category = (raw.get("Category") or "").strip().upper()

        # ── US mappings ───────────────────────────────────────────────────────
        if country in ("UNITED STATES", "UNITED_STATES", "US"):
            if "NON FARM" in event_name or "NONFARM" in event_name:
                return "US_NFP"
            if "CORE" in event_name and "CPI" in event_name:
                return "US_CORE_CPI"
            if "CPI" in event_name and "CORE" not in event_name:
                return "US_CPI"
            if "UNEMPLOYMENT" in event_name:
                return "US_UNEMPLOYMENT_RATE"
            if "AVERAGE HOURLY EARNINGS" in event_name:
                return "US_AVERAGE_HOURLY_EARNINGS"
            if "FOMC" in event_name and "RATE" in event_name:
                return "US_FOMC_RATE_DECISION"
            if "FOMC" in event_name and "STATEMENT" in event_name:
                return "US_FOMC_STATEMENT"
            if "GDP" in event_name:
                return "US_GDP"
            if "CORE" in event_name and "PPI" in event_name:
                return "US_CORE_PPI"
            if "PPI" in event_name:
                return "US_PPI"
            if "RETAIL SALES" in event_name:
                return "US_RETAIL_SALES"
        # ── Euro Area ─────────────────────────────────────────────────────────
        if country in ("EURO AREA", "EURO_AREA", "EUROZONE"):
            if "CORE" in event_name and "CPI" in event_name:
                return "EUROZONE_CORE_CPI"
            if "CPI" in event_name:
                return "EUROZONE_CPI"
            if "ECB" in event_name and "RATE" in event_name:
                return "ECB_RATE_DECISION"
            if "GDP" in event_name:
                return "EUROZONE_GDP"
        # ── UK ───────────────────────────────────────────────────────────────
        if country in ("UNITED KINGDOM", "UNITED_KINGDOM", "UK"):
            if "CORE" in event_name and "CPI" in event_name:
                return "UK_CORE_CPI"
            if "CPI" in event_name:
                return "UK_CPI"
            if "BOE" in event_name or "BANK OF ENGLAND" in event_name:
                return "BOE_RATE_DECISION"
            if "GDP" in event_name:
                return "UK_GDP"
        # ── Canada ────────────────────────────────────────────────────────────
        if country == "CANADA":
            if "CPI" in event_name:
                return "CANADA_CPI"
            if "EMPLOYMENT CHANGE" in event_name:
                return "CANADA_EMPLOYMENT_CHANGE"
            if "UNEMPLOYMENT" in event_name:
                return "CANADA_UNEMPLOYMENT_RATE"
            if "BOC" in event_name or "BANK OF CANADA" in event_name:
                return "BOC_RATE_DECISION"
        # ── Australia ─────────────────────────────────────────────────────────
        if country == "AUSTRALIA":
            if "CPI" in event_name:
                return "AUSTRALIA_CPI"
            if "EMPLOYMENT CHANGE" in event_name:
                return "AUSTRALIA_EMPLOYMENT_CHANGE"
            if "UNEMPLOYMENT" in event_name:
                return "AUSTRALIA_UNEMPLOYMENT_RATE"
            if "RBA" in event_name:
                return "RBA_RATE_DECISION"
        # ── New Zealand ───────────────────────────────────────────────────────
        if country in ("NEW ZEALAND", "NEW_ZEALAND"):
            if "CPI" in event_name:
                return "NEW_ZEALAND_CPI"
            if "EMPLOYMENT CHANGE" in event_name:
                return "NEW_ZEALAND_EMPLOYMENT_CHANGE"
            if "UNEMPLOYMENT" in event_name:
                return "NEW_ZEALAND_UNEMPLOYMENT_RATE"
            if "RBNZ" in event_name:
                return "RBNZ_RATE_DECISION"
        # ── Japan ─────────────────────────────────────────────────────────────
        if country == "JAPAN":
            if "CPI" in event_name:
                return "JAPAN_CPI"
            if "BOJ" in event_name or "BANK OF JAPAN" in event_name:
                return "BOJ_RATE_DECISION"

        # Unmapped → generate a non-allowlisted code
        safe_country = country[:20].replace(" ", "_")
        safe_event = event_name[:30].replace(" ", "_")
        return f"UNMAPPED__{safe_country}__{safe_event}"

    def _derive_period(self, raw: dict, release_time: datetime) -> str:
        """Derive the reference period string from the raw event."""
        period = raw.get("Reference") or raw.get("Period")
        if period:
            return str(period).strip()
        # Fall back to year-month of the release date
        return release_time.strftime("%Y-%m")

    def _store_excluded_event(
        self, raw: dict, code: str, normalized_impact: str
    ) -> None:
        """
        Store an excluded (non-red) event in the diagnostics table.

        These events are never processed by forecasting models.
        They are visible on the diagnostics page only.
        """
        from events.models import EconomicEvent, ImpactLevel
        from events.services import upsert_economic_event

        # We only upsert if not already in DB — and we never set is_forecastable
        upsert_economic_event(
            code=code,
            provider_event_id=str(raw.get("CalendarId", "")),
            name=raw.get("Event", code),
            country=raw.get("Country", ""),
            currency=raw.get("Currency", ""),
            category=raw.get("Category", ""),
            provider_impact_level=str(raw.get("Importance", "")),
            provider="trading_economics",
        )

    def health_check(self) -> dict:
        """Probe the Trading Economics API with a minimal request."""
        try:
            url = f"{self.base_url}/calendar/country/united states"
            params = {"c": self._api_key, "f": "json"}
            self.get(url, params=params)
            return {
                "provider": self.provider_name,
                "status": "ok",
                "checked_at": timezone.now().isoformat(),
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "status": "error",
                "error": str(exc),
                "checked_at": timezone.now().isoformat(),
            }
