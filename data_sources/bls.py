"""
Bureau of Labor Statistics (BLS) data provider.

Official API: https://www.bls.gov/developers/
Official documentation: https://www.bls.gov/developers/api_signature_v2.htm

Fetches:
- CPI component series (headline, core, food, energy, shelter, etc.)
- Employment series (NFP, unemployment, AHE, AWH, LFPR)
- PPI series

All data is real from the official BLS API.
No mock values, no hand-typed numbers.
If the API key is missing, raises ProviderConfigurationError.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from .base import BaseHTTPProvider, InsufficientDataError, ProviderDataError

logger = logging.getLogger("data_sources")

_BLS_BASE = "https://api.bls.gov/publicAPI/v2"


# ── BLS series registry ────────────────────────────────────────────────────────
# Series IDs used throughout the CPI and Employment models.
# Source: https://www.bls.gov/help/hlpforma.htm

BLS_SERIES: dict[str, dict] = {
    # CPI — All Urban Consumers (CPI-U), seasonally adjusted
    "CUSR0000SA0":   {"name": "CPI All Items (SA)",            "unit": "index",  "sa": True},
    "CUSR0000SA0L1E": {"name": "CPI Core (ex food & energy)", "unit": "index",  "sa": True},
    "CUSR0000SAF":   {"name": "CPI Food",                      "unit": "index",  "sa": True},
    "CUSR0000SA0E":  {"name": "CPI Energy",                    "unit": "index",  "sa": True},
    "CUSR0000SETB01": {"name": "CPI Gasoline",                 "unit": "index",  "sa": True},
    "CUSR0000SAH1":  {"name": "CPI Shelter",                   "unit": "index",  "sa": True},
    "CUSR0000SEHA":  {"name": "CPI Rent of Primary Res",       "unit": "index",  "sa": True},
    "CUSR0000SEHC":  {"name": "CPI Owners' Equiv Rent",        "unit": "index",  "sa": True},
    "CUSR0000SETA02": {"name": "CPI Used Cars & Trucks",       "unit": "index",  "sa": True},
    "CUSR0000SETA01": {"name": "CPI New Vehicles",             "unit": "index",  "sa": True},
    "CUSR0000SAM":   {"name": "CPI Medical Care",              "unit": "index",  "sa": True},
    "CUSR0000SAS":   {"name": "CPI Services",                  "unit": "index",  "sa": True},
    "CUSR0000SAA":   {"name": "CPI Apparel",                   "unit": "index",  "sa": True},
    "CUSR0000SAR":   {"name": "CPI Recreation",                "unit": "index",  "sa": True},
    "CUSR0000SACE":  {"name": "CPI Transportation Services",   "unit": "index",  "sa": True},
    # CPI — Not seasonally adjusted (for YoY calculations)
    "CUUR0000SA0":   {"name": "CPI All Items (NSA)",           "unit": "index",  "sa": False},
    "CUUR0000SA0L1E": {"name": "CPI Core (NSA)",               "unit": "index",  "sa": False},
    # PPI — Finished Goods
    "WPUFD49104":    {"name": "PPI Final Demand",              "unit": "index",  "sa": True},
    "WPUFD4131":     {"name": "PPI Final Demand ex Food/Energy", "unit": "index", "sa": True},
    "WPSFD4":        {"name": "PPI Finished Goods",            "unit": "index",  "sa": True},
    # Employment — CES (seasonally adjusted)
    "CES0000000001": {"name": "Nonfarm Payrolls (Total)",      "unit": "K",      "sa": True},
    "CES0500000001": {"name": "Private Nonfarm Payrolls",      "unit": "K",      "sa": True},
    "CES0000000003": {"name": "Average Weekly Hours",          "unit": "hours",  "sa": True},
    "CES0000000008": {"name": "Average Hourly Earnings",       "unit": "$/hr",   "sa": True},
    # Employment — CPS (household survey)
    "LNS14000000":   {"name": "Unemployment Rate",             "unit": "pct",    "sa": True},
    "LNS11300000":   {"name": "Labor Force Participation Rate","unit": "pct",    "sa": True},
    "LNS12000000":   {"name": "Civilian Employment Level",     "unit": "K",      "sa": True},
    # Initial/Continuing Jobless Claims
    "ICSA":          {"name": "Initial Jobless Claims",        "unit": "K",      "sa": True},
    "CCSA":          {"name": "Continuing Claims",             "unit": "K",      "sa": True},
}


class BLSProvider(BaseHTTPProvider):
    """
    Client for the Bureau of Labor Statistics public API v2.

    Requires BLS_API_KEY in environment settings.
    Without a key, requests are limited to 25/day; with key, 500/day.
    """

    provider_name = "bls"
    base_url = _BLS_BASE
    timeout_seconds = 60.0   # BLS can be slow

    def __init__(self):
        super().__init__()
        self._api_key = self._get_api_key("BLS_API_KEY")

    def fetch_series(
        self,
        series_ids: list[str],
        start_year: int,
        end_year: int,
        annual_average: bool = False,
        calculations: bool = True,
    ) -> dict[str, list[dict]]:
        """
        Fetch one or more BLS series using the v2 API.

        Parameters
        ----------
        series_ids : list of BLS series IDs (max 50 per call).
        start_year : First year to retrieve.
        end_year : Last year to retrieve (max 20-year window).
        annual_average : Include annual average in response.
        calculations : Include MoM / YoY calculations.

        Returns
        -------
        dict mapping series_id → list of observation dicts.
        """
        if not series_ids:
            return {}

        # BLS v2 allows at most 50 series per request
        all_results: dict[str, list[dict]] = {}

        for chunk_start in range(0, len(series_ids), 50):
            chunk = series_ids[chunk_start:chunk_start + 50]
            payload = {
                "seriesid": chunk,
                "startyear": str(start_year),
                "endyear": str(end_year),
                "annualaverage": annual_average,
                "calculations": calculations,
                "registrationkey": self._api_key,
            }

            url = f"{self.base_url}/timeseries/data/"
            raw = self.post(url, json_body=payload)

            parsed = self._parse_response(raw)
            all_results.update(parsed)

        return all_results

    def fetch_single_series(
        self, series_id: str, start_year: int, end_year: int
    ) -> list[dict]:
        """Convenience method — fetch a single series."""
        result = self.fetch_series([series_id], start_year, end_year)
        return result.get(series_id, [])

    def fetch_latest_cpi(self) -> dict[str, list[dict]]:
        """Fetch the most recent two years of key CPI series."""
        now = timezone.now()
        current_year = now.year
        start_year = current_year - 2
        series = [
            "CUSR0000SA0",    # All Items SA
            "CUSR0000SA0L1E", # Core SA
            "CUSR0000SAF",    # Food
            "CUSR0000SA0E",   # Energy
            "CUSR0000SETB01", # Gasoline
            "CUSR0000SAH1",   # Shelter
            "CUSR0000SEHA",   # Rent
            "CUSR0000SEHC",   # OER
            "CUSR0000SETA02", # Used Vehicles
            "CUSR0000SETA01", # New Vehicles
            "CUSR0000SAM",    # Medical
            "CUUR0000SA0",    # NSA headline
            "CUUR0000SA0L1E", # NSA core
        ]
        return self.fetch_series(series, start_year, current_year)

    def fetch_latest_employment(self) -> dict[str, list[dict]]:
        """Fetch the most recent two years of key employment series."""
        now = timezone.now()
        current_year = now.year
        start_year = current_year - 2
        series = [
            "CES0000000001",  # Total NFP
            "CES0500000001",  # Private NFP
            "CES0000000003",  # AWH
            "CES0000000008",  # AHE
            "LNS14000000",    # Unemployment rate
            "LNS11300000",    # LFPR
            "LNS12000000",    # Employment level
        ]
        return self.fetch_series(series, start_year, current_year)

    def fetch_latest_ppi(self) -> dict[str, list[dict]]:
        """Fetch the most recent two years of key PPI series."""
        now = timezone.now()
        current_year = now.year
        series = [
            "WPUFD49104",
            "WPUFD4131",
            "WPSFD4",
        ]
        return self.fetch_series(series, current_year - 2, current_year)

    # ── Ingestion to macro_data tables ────────────────────────────────────────

    def ingest_series(self, series_ids: list[str] | None = None) -> dict:
        """
        Fetch series and persist observations to DataObservation table.
        """
        from macro_data.ingestion import persist_data_observations

        if series_ids is None:
            series_ids = list(BLS_SERIES.keys())

        now = timezone.now()
        all_data = self.fetch_series(
            series_ids,
            start_year=now.year - 5,
            end_year=now.year,
        )

        saved = errors = 0
        for sid, observations in all_data.items():
            meta = BLS_SERIES.get(sid, {})
            try:
                n = persist_data_observations(
                    provider="bls",
                    series_id=sid,
                    observations=observations,
                    unit=meta.get("unit", ""),
                    seasonal_adjustment="SA" if meta.get("sa") else "NSA",
                )
                saved += n
            except Exception as exc:
                logger.error(f"BLS persist error {sid}: {exc}", exc_info=True)
                errors += 1

        return {"saved": saved, "errors": errors, "series_processed": len(all_data)}

    # ── Response parser ───────────────────────────────────────────────────────

    def _parse_response(self, raw: Any) -> dict[str, list[dict]]:
        """
        Parse BLS API v2 response into a dict of series_id → observations.

        BLS response structure:
        {
          "status": "REQUEST_SUCCEEDED",
          "responseTime": ...,
          "message": [],
          "Results": {
            "series": [
              {
                "seriesID": "CUSR0000SA0",
                "data": [
                  {"year": "2024", "period": "M06", "value": "314.0", ...},
                  ...
                ]
              }
            ]
          }
        }
        """
        if not isinstance(raw, dict):
            raise ProviderDataError(f"BLS: unexpected response type {type(raw)}")

        if raw.get("status") not in ("REQUEST_SUCCEEDED", "REQUEST_NOT_PROCESSED"):
            messages = raw.get("message", [])
            raise ProviderDataError(f"BLS API error: {raw.get('status')} — {messages}")

        results: dict[str, list[dict]] = {}
        for series in raw.get("Results", {}).get("series", []):
            series_id = series.get("seriesID", "")
            observations = []
            for item in series.get("data", []):
                obs = self._parse_observation(series_id, item)
                if obs:
                    observations.append(obs)
            results[series_id] = observations

        return results

    def _parse_observation(self, series_id: str, item: dict) -> dict | None:
        """Convert a BLS data item to a normalised observation dict."""
        try:
            year = int(item["year"])
            period = item["period"]  # e.g. "M06", "M13" (annual avg), "Q01"
            value_str = item.get("value", "")

            if value_str in ("", "-", "N/A"):
                return None

            # Parse period to observation_date
            obs_date = self._period_to_date(year, period)
            if obs_date is None:
                return None

            return {
                "series_id": series_id,
                "year": year,
                "period": period,
                "observation_date": obs_date,
                "value": float(value_str),
                "footnotes": item.get("footnotes", []),
                "calculations": item.get("calculations", {}),
            }
        except Exception as exc:
            logger.warning(f"BLS parse error for {series_id}: {exc}")
            return None

    @staticmethod
    def _period_to_date(year: int, period: str) -> datetime | None:
        """
        Convert BLS year + period code to a date.

        BLS period codes:
        M01–M12: monthly
        M13: annual average
        Q01–Q04: quarterly
        """
        import pytz
        utc = pytz.UTC
        try:
            if period.startswith("M"):
                month = int(period[1:])
                if month == 13:
                    return None   # Skip annual average
                return datetime(year, month, 1, tzinfo=utc)
            if period.startswith("Q"):
                quarter = int(period[1:])
                month = (quarter - 1) * 3 + 1
                return datetime(year, month, 1, tzinfo=utc)
            return None
        except Exception:
            return None

    def health_check(self) -> dict:
        """Probe BLS API with a single lightweight series request."""
        try:
            self.fetch_single_series("CUSR0000SA0", timezone.now().year, timezone.now().year)
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
