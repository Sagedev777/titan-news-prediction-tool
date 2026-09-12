"""
Federal Reserve Economic Data (FRED) provider.

Official API: https://fred.stlouisfed.org/docs/api/fred/
Supports vintage dates and real-time periods for point-in-time backtesting.

Fetches:
- Treasury yields (2Y, 10Y, spread)
- Oil prices (WTI, Brent)
- Gasoline prices
- Interest rate expectations
- Consumer surveys
- Financial conditions
- Import/export price indices
- JOLTS, ADP, Challenger layoffs
- Various macro series needed by event models
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.utils import timezone

from .base import BaseHTTPProvider, ProviderDataError

logger = logging.getLogger("data_sources")

_FRED_BASE = "https://api.stlouisfed.org/fred"


# ── FRED series registry ───────────────────────────────────────────────────────
FRED_SERIES: dict[str, dict] = {
    # Treasury yields
    "DGS2":    {"name": "2-Year Treasury Yield",              "unit": "pct"},
    "DGS10":   {"name": "10-Year Treasury Yield",             "unit": "pct"},
    "DGS30":   {"name": "30-Year Treasury Yield",             "unit": "pct"},
    "T10Y2Y":  {"name": "10Y-2Y Treasury Spread",             "unit": "pct"},
    "FEDFUNDS": {"name": "Fed Funds Rate",                    "unit": "pct"},
    # Oil & energy
    "DCOILWTICO": {"name": "WTI Crude Oil Price",             "unit": "$/bbl"},
    "DCOILBRENTEU": {"name": "Brent Crude Oil Price",         "unit": "$/bbl"},
    "GASREGCOVW": {"name": "Retail Gasoline Price (US avg)",  "unit": "$/gal"},
    # Import/export prices
    "IR":      {"name": "Import Price Index",                  "unit": "index"},
    "IQ":      {"name": "Export Price Index",                  "unit": "index"},
    # Consumer surveys
    "UMCSENT": {"name": "Univ. Michigan Consumer Sentiment",  "unit": "index"},
    "MICH":    {"name": "Univ. Michigan Inflation Expectations","unit": "pct"},
    "EXPINF1YR": {"name": "1-Year Inflation Expectations (NY Fed)", "unit": "pct"},
    # Labour market
    "JTSJOL":  {"name": "JOLTS Job Openings",                 "unit": "K"},
    "JTSHIR":  {"name": "JOLTS Hires",                        "unit": "K"},
    "JTSQUR":  {"name": "JOLTS Quits",                        "unit": "K"},
    "JTSLDR":  {"name": "JOLTS Layoffs & Discharges",         "unit": "K"},
    "ADPWNUSNERSA": {"name": "ADP Nonfarm Employment",        "unit": "K"},
    # Financial conditions
    "NFCI":    {"name": "Chicago Fed National Financial Conditions Index", "unit": "index"},
    "STLFSI4": {"name": "St. Louis Fed Financial Stress Index", "unit": "index"},
    # GDP components
    "A191RL1Q225SBEA": {"name": "Real GDP Growth (QoQ ann.)", "unit": "pct"},
    "DPCERE1Q156NBEA": {"name": "PCE Inflation (QoQ)",        "unit": "pct"},
    # Credit
    "BAA10Y":  {"name": "Baa-Treasury Spread (Credit Risk)", "unit": "pct"},
    "BAMLH0A0HYM2": {"name": "HY Credit Spread",             "unit": "pct"},
}


class FREDProvider(BaseHTTPProvider):
    """
    Client for the FRED REST API.

    Supports:
    - Regular observations with optional vintage filtering.
    - Real-time period lookups for point-in-time backtesting.
    """

    provider_name = "fred"
    base_url = _FRED_BASE
    timeout_seconds = 30.0

    def __init__(self):
        super().__init__()
        self._api_key = self._get_api_key("FRED_API_KEY")

    def fetch_series(
        self,
        series_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        realtime_start: datetime | None = None,
        realtime_end: datetime | None = None,
        units: str = "lin",
        frequency: str | None = None,
    ) -> list[dict]:
        """
        Fetch observations for a FRED series.

        Parameters
        ----------
        series_id : FRED series identifier, e.g. 'DGS2'.
        start_date / end_date : Observation date range.
        realtime_start / realtime_end : Vintage filter for point-in-time.
            If provided, only data that was available as of realtime_start
            will be returned.
        units : Transformation ('lin'=levels, 'chg'=change, 'pch'=pct change).
        frequency : Aggregation ('d','w','m','q','a'). None = native frequency.
        """
        params: dict = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "units": units,
        }
        if start_date:
            params["observation_start"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["observation_end"] = end_date.strftime("%Y-%m-%d")
        if realtime_start:
            params["realtime_start"] = realtime_start.strftime("%Y-%m-%d")
            params["realtime_end"] = (realtime_end or realtime_start).strftime("%Y-%m-%d")
        if frequency:
            params["frequency"] = frequency

        url = f"{self.base_url}/series/observations"
        raw = self.get(url, params=params)
        return self._parse_observations(series_id, raw)

    def fetch_series_metadata(self, series_id: str) -> dict:
        """Fetch metadata (title, units, frequency, last_updated) for a series."""
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
        }
        url = f"{self.base_url}/series"
        raw = self.get(url, params=params)
        if isinstance(raw, dict) and "seriess" in raw and raw["seriess"]:
            return raw["seriess"][0]
        return {}

    def fetch_vintage_dates(self, series_id: str) -> list[str]:
        """Return all available vintage dates for a series."""
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
        }
        url = f"{self.base_url}/series/vintagedates"
        raw = self.get(url, params=params)
        if isinstance(raw, dict) and "vintage_dates" in raw:
            return raw["vintage_dates"]
        return []

    def fetch_as_of(
        self, series_id: str, as_of_date: datetime, lookback_days: int = 365
    ) -> list[dict]:
        """
        Return observations that were available as of `as_of_date`.

        This is the point-in-time accessor used by the backtesting engine.
        Uses FRED's realtime_start / realtime_end parameters.
        """
        from datetime import timedelta
        start = as_of_date - timedelta(days=lookback_days)
        return self.fetch_series(
            series_id=series_id,
            start_date=start,
            end_date=as_of_date,
            realtime_start=as_of_date,
            realtime_end=as_of_date,
        )

    # ── Convenience fetchers ──────────────────────────────────────────────────

    def fetch_yields(self, lookback_days: int = 365) -> dict[str, list[dict]]:
        """Fetch 2Y and 10Y treasury yields."""
        from datetime import timedelta
        end = timezone.now()
        start = end - timedelta(days=lookback_days)
        return {
            "DGS2": self.fetch_series("DGS2", start, end),
            "DGS10": self.fetch_series("DGS10", start, end),
            "T10Y2Y": self.fetch_series("T10Y2Y", start, end),
        }

    def fetch_oil_prices(self, lookback_days: int = 365) -> dict[str, list[dict]]:
        """Fetch WTI and Brent crude prices."""
        from datetime import timedelta
        end = timezone.now()
        start = end - timedelta(days=lookback_days)
        return {
            "DCOILWTICO": self.fetch_series("DCOILWTICO", start, end),
            "DCOILBRENTEU": self.fetch_series("DCOILBRENTEU", start, end),
            "GASREGCOVW": self.fetch_series("GASREGCOVW", start, end),
        }

    def fetch_inflation_expectations(self, lookback_days: int = 365) -> dict[str, list[dict]]:
        """Fetch consumer inflation expectation surveys."""
        from datetime import timedelta
        end = timezone.now()
        start = end - timedelta(days=lookback_days)
        return {
            "MICH": self.fetch_series("MICH", start, end),
            "EXPINF1YR": self.fetch_series("EXPINF1YR", start, end),
        }

    def fetch_labor_market(self, lookback_days: int = 365) -> dict[str, list[dict]]:
        """Fetch JOLTS, ADP, and related labour-market series."""
        from datetime import timedelta
        end = timezone.now()
        start = end - timedelta(days=lookback_days)
        series = ["JTSJOL", "JTSHIR", "JTSQUR", "JTSLDR", "ADPWNUSNERSA"]
        return {s: self.fetch_series(s, start, end) for s in series}

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_series(self, series_ids: list[str] | None = None) -> dict:
        """Fetch and persist FRED observations to DataObservation table."""
        from datetime import timedelta

        from macro_data.ingestion import persist_data_observations

        if series_ids is None:
            series_ids = list(FRED_SERIES.keys())

        now = timezone.now()
        start = now - timedelta(days=365 * 5)
        saved = errors = 0

        for sid in series_ids:
            try:
                meta = FRED_SERIES.get(sid, {})
                observations = self.fetch_series(sid, start_date=start, end_date=now)
                n = persist_data_observations(
                    provider="fred",
                    series_id=sid,
                    observations=observations,
                    unit=meta.get("unit", ""),
                    seasonal_adjustment="",
                )
                saved += n
            except Exception as exc:
                logger.error(f"FRED persist error {sid}: {exc}", exc_info=True)
                errors += 1

        return {"saved": saved, "errors": errors, "series_processed": len(series_ids)}

    # ── Parser ────────────────────────────────────────────────────────────────

    def _parse_observations(self, series_id: str, raw: Any) -> list[dict]:
        """
        Parse FRED API observations response.

        FRED response structure:
        {
          "realtime_start": "...",
          "realtime_end": "...",
          "observation_start": "...",
          "observation_end": "...",
          "units": "lin",
          "output_type": 1,
          "file_type": "json",
          "order_by": "observation_date",
          "sort_order": "asc",
          "count": 100,
          "offset": 0,
          "limit": 100000,
          "observations": [
            {"realtime_start": "...", "realtime_end": "...",
             "date": "2024-01-01", "value": "4.87"},
            ...
          ]
        }
        """
        if not isinstance(raw, dict):
            raise ProviderDataError(f"FRED: unexpected response for {series_id}")

        if "error_message" in raw:
            raise ProviderDataError(f"FRED API error: {raw['error_message']}")

        results = []
        import pytz
        utc = pytz.UTC

        for item in raw.get("observations", []):
            value_str = item.get("value", ".")
            if value_str in (".", "", "N/A"):
                continue
            try:
                from datetime import datetime as dt
                obs_date = dt.strptime(item["date"], "%Y-%m-%d").replace(tzinfo=utc)
                vintage_start = item.get("realtime_start", "")
                vintage_date = None
                if vintage_start:
                    try:
                        vintage_date = dt.strptime(vintage_start, "%Y-%m-%d").replace(tzinfo=utc)
                    except Exception:
                        pass

                results.append({
                    "series_id": series_id,
                    "observation_date": obs_date,
                    "value": float(value_str),
                    "vintage_date": vintage_date,
                })
            except Exception as exc:
                logger.warning(f"FRED parse error for {series_id}: {exc}")

        return results

    def health_check(self) -> dict:
        """Probe FRED API with a minimal request."""
        try:
            self.fetch_series("DGS2", start_date=timezone.now())
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
