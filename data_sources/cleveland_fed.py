"""
Cleveland Fed Inflation Nowcast provider.

Official page: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting

PROVIDER STATUS — DISABLED (URL unverified)
============================================
The old CSV download URL used in the scaffold:

    https://www.clevelandfed.org/~/media/files/indicators-and-data/
    inflation-nowcasting/inflation-nowcast.csv

returns HTTP 404 as of September 2026.  The Cleveland Fed website was
redesigned and now delivers nowcast data via a JavaScript-rendered page.
No stable, verified, direct-download CSV URL has been confirmed.

Per project policy: if the correct endpoint cannot be verified, the
provider is disabled with a clear health error.  No data is substituted.
No fake values are returned.  The CPI model will proceed without this
feature and will note it as missing in the forecast warnings.

TO RE-ENABLE THIS PROVIDER
---------------------------
1. Find the current direct-download URL for the inflation nowcast CSV
   on the official Cleveland Fed site.
2. Update _CLEVELAND_FED_CPI_URL below with the verified URL.
3. Run: python manage.py shell -c "
       from data_sources.cleveland_fed import ClevelandFedProvider
       print(ClevelandFedProvider().health_check())
   "
4. If the health check returns status='ok' with records > 0,
   set CLEVELAND_FED_ENABLED = True in this file.
5. Re-run the test suite.

IMPORTANT: The Cleveland Fed nowcast is treated as ONE external model
feature, not the authoritative number.  It is never the forecast answer.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any

import httpx
from django.utils import timezone

from .base import BaseHTTPProvider, ProviderDataError, ProviderUnavailableError

logger = logging.getLogger("data_sources")

# ── Configuration ─────────────────────────────────────────────────────────────

# Set to True only after verifying the URL below returns a valid CSV.
CLEVELAND_FED_ENABLED: bool = False

# The OLD URL confirmed to return 404 — kept for reference.
_CLEVELAND_FED_OLD_URL = (
    "https://www.clevelandfed.org/~/media/files/indicators-and-data/"
    "inflation-nowcasting/inflation-nowcast.csv"
)

# Replace this with the correct verified URL when the provider is re-enabled.
# Do NOT change CLEVELAND_FED_ENABLED to True until you have confirmed the URL
# returns a valid CSV with a 200 response.
_CLEVELAND_FED_CPI_URL: str = _CLEVELAND_FED_OLD_URL  # ← NOT verified, returns 404

_CLEVELAND_FED_PAGE_URL = (
    "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
)

# Human-readable error message shown in health checks and forecast warnings.
_DISABLED_MESSAGE = (
    "CLEVELAND FED PROVIDER DISABLED — no verified CSV download URL. "
    "The old URL (~/media/files/...) returns HTTP 404. "
    "The nowcast page now appears to serve data dynamically. "
    f"Check {_CLEVELAND_FED_PAGE_URL} for a current download link, "
    "then update _CLEVELAND_FED_CPI_URL and set CLEVELAND_FED_ENABLED=True "
    "in data_sources/cleveland_fed.py."
)


class ClevelandFedProvider(BaseHTTPProvider):
    """
    Client for Cleveland Fed published inflation nowcasts.

    No API key required — data is publicly available when the URL is working.

    CURRENT STATUS: DISABLED.
    See module docstring for re-enablement instructions.

    This is treated as an external nowcast feature, not the authoritative number.
    When disabled, all methods return empty results or an explicit error status.
    No mock or substitute data is returned.
    """

    provider_name = "cleveland_fed"
    base_url = "https://www.clevelandfed.org"
    timeout_seconds = 30.0

    def __init__(self):
        # Use a plain httpx client — no API key needed.
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": (
                    "TitanForecast/1.0 "
                    "(inflation research; contact: research@example.com)"
                ),
                "Accept": "text/csv,application/csv,*/*",
            },
            follow_redirects=True,
        )

    def fetch_nowcast(self) -> list[dict]:
        """
        Fetch the latest Cleveland Fed inflation nowcast CSV.

        Returns
        -------
        list of observation dicts, or empty list if the provider is
        disabled or the URL fails.

        When the provider is disabled, logs a clear WARNING (not silently
        returns empty) so the CPI model can note the missing feature.
        """
        if not CLEVELAND_FED_ENABLED:
            logger.warning(
                "Cleveland Fed provider is disabled. %s", _DISABLED_MESSAGE
            )
            return []

        retrieved_at = timezone.now()

        try:
            resp = self._client.get(_CLEVELAND_FED_CPI_URL)
            if resp.status_code == 200:
                records = self._parse_csv(resp.text, retrieved_at)
                if records:
                    logger.info(
                        "Cleveland Fed nowcast fetched: %d records from %s",
                        len(records), _CLEVELAND_FED_CPI_URL,
                    )
                    return records
                else:
                    logger.error(
                        "Cleveland Fed URL returned 200 but no parseable records. "
                        "The CSV format may have changed. URL: %s",
                        _CLEVELAND_FED_CPI_URL,
                    )
                    return []
            else:
                logger.error(
                    "Cleveland Fed URL returned HTTP %d. "
                    "Set CLEVELAND_FED_ENABLED=False until a valid URL is found. "
                    "URL: %s",
                    resp.status_code, _CLEVELAND_FED_CPI_URL,
                )
                return []

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.error(
                "Cleveland Fed network error: %s. URL: %s",
                exc, _CLEVELAND_FED_CPI_URL,
            )
            return []

    def _parse_csv(self, text: str, retrieved_at: datetime) -> list[dict]:
        """
        Parse Cleveland Fed nowcast CSV.

        The CSV format has changed over time.  We handle both old and new
        column-name layouts.  Expected columns (may vary):
            Date, CPI MoM, CPI YoY, Core CPI MoM, Core CPI YoY, ...
        """
        results = []
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                entry = self._parse_row(row, retrieved_at)
                if entry:
                    results.append(entry)
        except Exception as exc:
            logger.error("Cleveland Fed CSV parse error: %s", exc, exc_info=True)
        return results

    def _parse_row(self, row: dict, retrieved_at: datetime) -> dict | None:
        """Parse one CSV row into a normalised nowcast dict."""
        import pytz

        def safe_float(v: Any) -> float | None:
            try:
                return float(v) if v not in (None, "", "N/A", "#N/A") else None
            except (TypeError, ValueError):
                return None

        # Detect date column — the column name has changed across versions.
        date_col = None
        for c in ("Date", "date", "DATE", "Period"):
            if c in row:
                date_col = c
                break
        if not date_col:
            return None

        date_str = row[date_col].strip()
        if not date_str:
            return None

        try:
            from dateutil import parser as dtparser
            nowcast_date = dtparser.parse(date_str).replace(tzinfo=pytz.UTC)
        except Exception:
            return None

        # Map column names flexibly — Cleveland Fed has changed column names.
        headline_mom = safe_float(
            row.get("CPI MoM") or row.get("Headline CPI MoM") or row.get("cpi_mom")
        )
        headline_yoy = safe_float(
            row.get("CPI YoY") or row.get("Headline CPI YoY") or row.get("cpi_yoy")
        )
        core_mom = safe_float(
            row.get("Core CPI MoM") or row.get("core_cpi_mom") or row.get("Core MoM")
        )
        core_yoy = safe_float(
            row.get("Core CPI YoY") or row.get("core_cpi_yoy") or row.get("Core YoY")
        )

        # Return None for rows with no valid estimates.
        if all(v is None for v in (headline_mom, headline_yoy, core_mom, core_yoy)):
            return None

        return {
            "nowcast_date": nowcast_date,
            "headline_cpi_mom": headline_mom,
            "headline_cpi_yoy": headline_yoy,
            "core_cpi_mom": core_mom,
            "core_cpi_yoy": core_yoy,
            "retrieved_at": retrieved_at,
            "source_url": _CLEVELAND_FED_CPI_URL,
            "provider": "cleveland_fed",
            "is_external_nowcast": True,
            "usage_note": (
                "Cleveland Fed nowcast is an external model estimate. "
                "Used as one feature in the CPI model, not as the forecast answer."
            ),
        }

    def ingest_nowcast(self) -> dict:
        """
        Fetch and persist Cleveland Fed nowcast observations.

        Returns a status dict.  When the provider is disabled, returns
        a status of 'disabled' — never silently returns empty without
        an explanatory message.
        """
        if not CLEVELAND_FED_ENABLED:
            msg = f"Cleveland Fed provider disabled. {_DISABLED_MESSAGE}"
            logger.warning(msg)
            return {
                "saved": 0,
                "errors": 0,
                "status": "disabled",
                "warning": msg,
            }

        from macro_data.ingestion import persist_cleveland_fed_nowcast

        records = self.fetch_nowcast()
        if not records:
            return {
                "saved": 0,
                "errors": 0,
                "status": "no_data",
                "warning": (
                    "Cleveland Fed fetch returned no records. "
                    "The feature will be absent from the CPI model. "
                    f"URL checked: {_CLEVELAND_FED_CPI_URL}"
                ),
            }

        saved = errors = 0
        for record in records:
            try:
                persist_cleveland_fed_nowcast(record)
                saved += 1
            except Exception as exc:
                logger.error("Cleveland Fed persist error: %s", exc, exc_info=True)
                errors += 1

        return {
            "saved": saved,
            "errors": errors,
            "records_fetched": len(records),
            "status": "ok",
        }

    def health_check(self) -> dict:
        """
        Return provider health status.

        When disabled, returns status='disabled' with the full explanation.
        Never returns status='ok' when the provider is disabled.
        """
        if not CLEVELAND_FED_ENABLED:
            return {
                "provider": self.provider_name,
                "status": "disabled",
                "enabled": False,
                "message": _DISABLED_MESSAGE,
                "action_required": (
                    "Find the current CSV download URL on "
                    f"{_CLEVELAND_FED_PAGE_URL}, "
                    "update _CLEVELAND_FED_CPI_URL in data_sources/cleveland_fed.py, "
                    "and set CLEVELAND_FED_ENABLED=True."
                ),
                "checked_at": timezone.now().isoformat(),
            }

        try:
            records = self.fetch_nowcast()
            return {
                "provider": self.provider_name,
                "status": "ok" if records else "no_data",
                "enabled": True,
                "records": len(records),
                "url": _CLEVELAND_FED_CPI_URL,
                "checked_at": timezone.now().isoformat(),
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "status": "error",
                "enabled": True,
                "error": str(exc),
                "checked_at": timezone.now().isoformat(),
            }
