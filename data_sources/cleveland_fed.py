"""
Cleveland Fed Inflation Nowcast provider.

Source: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting

The Cleveland Fed publishes daily inflation nowcasts for US CPI and
PCE based on a dynamic factor model.

IMPORTANT: The Cleveland Fed nowcast is treated as an external model
estimate and is one feature used by our CPI model.  It is never
treated as the ground truth or the final forecast answer.

Data is scraped from the published CSV files on the Cleveland Fed site.
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

# Cleveland Fed publishes nowcast CSV files at these URLs.
# These are public data pages — no API key required.
_CLEVELAND_FED_CPI_URL = (
    "https://www.clevelandfed.org/~/media/files/indicators-and-data/"
    "inflation-nowcasting/inflation-nowcast.csv"
)
_CLEVELAND_FED_ALT_URL = (
    "https://www.clevelandfed.org/en/indicators-and-data/inflation-nowcasting"
)


class ClevelandFedProvider(BaseHTTPProvider):
    """
    Client for Cleveland Fed published inflation nowcasts.

    No API key required — data is publicly available.
    This is treated as an external nowcast feature, not the authoritative number.
    """

    provider_name = "cleveland_fed"
    base_url = "https://www.clevelandfed.org"
    timeout_seconds = 30.0

    def __init__(self):
        # No API key check needed — public data
        import httpx
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "TitanForecast/1.0 (inflation research; contact: research@example.com)",
                "Accept": "text/csv,application/csv,*/*",
            },
            follow_redirects=True,
        )

    def fetch_nowcast(self) -> list[dict]:
        """
        Fetch the latest Cleveland Fed inflation nowcast data.

        Returns a list of dicts, each containing:
        - nowcast_date
        - headline_cpi_estimate
        - core_cpi_estimate
        - headline_pce_estimate (when available)
        - core_pce_estimate (when available)
        - vintage (retrieval time)
        - source_url
        """
        retrieved_at = timezone.now()

        try:
            resp = self._client.get(_CLEVELAND_FED_CPI_URL)
            if resp.status_code == 200:
                return self._parse_csv(resp.text, retrieved_at)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(f"Cleveland Fed primary URL failed: {exc}")

        # If CSV direct download fails, log the issue and return empty
        # — the model will proceed without this feature and note it as missing.
        logger.error(
            "Cleveland Fed nowcast unavailable. "
            "CPI model will proceed without this feature. "
            f"See: {_CLEVELAND_FED_ALT_URL}"
        )
        return []

    def _parse_csv(self, text: str, retrieved_at: datetime) -> list[dict]:
        """
        Parse Cleveland Fed nowcast CSV.

        The CSV format has changed over time.  We handle both old and new layouts.
        Expected columns (may vary):
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
            logger.error(f"Cleveland Fed CSV parse error: {exc}", exc_info=True)
        return results

    def _parse_row(self, row: dict, retrieved_at: datetime) -> dict | None:
        """Parse one CSV row into a normalised nowcast dict."""
        import pytz

        def safe_float(v):
            try:
                return float(v) if v not in (None, "", "N/A", "#N/A") else None
            except (TypeError, ValueError):
                return None

        # Detect date column
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

        # Map column names flexibly — Cleveland Fed has changed column names
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

        # Only return rows with at least one valid estimate
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
        """Fetch and persist Cleveland Fed nowcast to DataObservation table."""
        from macro_data.ingestion import persist_cleveland_fed_nowcast

        records = self.fetch_nowcast()
        if not records:
            return {"saved": 0, "errors": 0, "warning": "No Cleveland Fed data available"}

        saved = errors = 0
        for record in records:
            try:
                persist_cleveland_fed_nowcast(record)
                saved += 1
            except Exception as exc:
                logger.error(f"Cleveland Fed persist error: {exc}", exc_info=True)
                errors += 1

        return {"saved": saved, "errors": errors, "records_fetched": len(records)}

    def health_check(self) -> dict:
        """Check Cleveland Fed data availability."""
        try:
            records = self.fetch_nowcast()
            return {
                "provider": self.provider_name,
                "status": "ok" if records else "no_data",
                "records": len(records),
                "checked_at": timezone.now().isoformat(),
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "status": "error",
                "error": str(exc),
                "checked_at": timezone.now().isoformat(),
            }
