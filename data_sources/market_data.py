"""
Market data provider — OHLCV for forex pairs, gold, and indices.

Supports Twelve Data as the primary provider (configurable).
All data is stored with a is_delayed flag so delayed data is never
represented as real-time.

Supported instruments:
- EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD
- XAUUSD (Gold)
- DXY (US Dollar Index — via ETF proxy if direct unavailable)
- US02Y, US10Y (Treasury yield proxies via ETF or data series)

Timeframes: 1min, 5min, 15min, 1h, 1day
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from .base import BaseHTTPProvider, ProviderConfigurationError, ProviderDataError

logger = logging.getLogger("data_sources")

# ── Instrument registry ────────────────────────────────────────────────────────
SUPPORTED_INSTRUMENTS = {
    # Forex pairs
    "EURUSD": {"type": "forex",  "description": "Euro / US Dollar"},
    "GBPUSD": {"type": "forex",  "description": "British Pound / US Dollar"},
    "USDJPY": {"type": "forex",  "description": "US Dollar / Japanese Yen"},
    "USDCHF": {"type": "forex",  "description": "US Dollar / Swiss Franc"},
    "USDCAD": {"type": "forex",  "description": "US Dollar / Canadian Dollar"},
    "AUDUSD": {"type": "forex",  "description": "Australian Dollar / US Dollar"},
    "NZDUSD": {"type": "forex",  "description": "New Zealand Dollar / US Dollar"},
    # Commodities
    "XAUUSD": {"type": "commodity", "description": "Gold (Spot) / US Dollar"},
    # Indices / dollar
    "DXY":    {"type": "index",  "description": "US Dollar Index (DXY)"},
    # Yield proxies (via futures or ETF data if direct not available)
    "US02Y":  {"type": "yield",  "description": "2-Year US Treasury Yield Proxy"},
    "US10Y":  {"type": "yield",  "description": "10-Year US Treasury Yield Proxy"},
}

# Twelve Data symbol mapping (some symbols differ from our internal names)
_TWELVEDATA_SYMBOL_MAP: dict[str, str] = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCHF": "USD/CHF",
    "USDCAD": "USD/CAD",
    "AUDUSD": "AUD/USD",
    "NZDUSD": "NZD/USD",
    "XAUUSD": "XAU/USD",
    "DXY":    "DXY",
    "US02Y":  "US2Y",   # Twelve Data 2-year treasury note
    "US10Y":  "US10Y",  # Twelve Data 10-year treasury
}

# Internal timeframe → Twelve Data interval string
_TIMEFRAME_MAP: dict[str, str] = {
    "1min":  "1min",
    "5min":  "5min",
    "15min": "15min",
    "1h":    "1h",
    "4h":    "4h",
    "1day":  "1day",
}


class TwelveDataProvider(BaseHTTPProvider):
    """
    Market data client for Twelve Data API.

    API docs: https://twelvedata.com/docs
    Requires MARKET_DATA_API_KEY in settings.
    """

    provider_name = "twelvedata"
    timeout_seconds = 20.0

    def __init__(self):
        super().__init__()
        self._api_key = self._get_api_key("MARKET_DATA_API_KEY")
        self._base_url = getattr(settings, "MARKET_DATA_BASE_URL", "https://api.twelvedata.com")

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        output_size: int = 5000,
    ) -> list[dict]:
        """
        Fetch OHLCV candles for a symbol and timeframe.

        Parameters
        ----------
        symbol : Internal symbol name, e.g. 'EURUSD'.
        timeframe : '1min', '5min', '15min', '1h', '4h', '1day'.
        start / end : UTC datetime range.
        output_size : Max candles (Twelve Data max 5000 per request).

        Returns
        -------
        list of dicts with keys: timestamp_utc, open, high, low, close,
        volume, symbol, timeframe, is_delayed.
        """
        td_symbol = _TWELVEDATA_SYMBOL_MAP.get(symbol.upper())
        if not td_symbol:
            raise ProviderDataError(
                f"Symbol {symbol!r} not in Twelve Data symbol map. "
                f"Supported: {list(_TWELVEDATA_SYMBOL_MAP.keys())}"
            )

        td_interval = _TIMEFRAME_MAP.get(timeframe)
        if not td_interval:
            raise ProviderDataError(
                f"Timeframe {timeframe!r} not supported. "
                f"Supported: {list(_TIMEFRAME_MAP.keys())}"
            )

        url = f"{self._base_url}/time_series"
        params = {
            "symbol": td_symbol,
            "interval": td_interval,
            "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
            "outputsize": min(output_size, 5000),
            "format": "JSON",
            "timezone": "UTC",
            "apikey": self._api_key,
        }

        raw = self.get(url, params=params)
        return self._parse_ohlcv(symbol, timeframe, raw)

    def fetch_latest_price(self, symbol: str) -> dict | None:
        """Fetch the latest price for a single symbol."""
        td_symbol = _TWELVEDATA_SYMBOL_MAP.get(symbol.upper())
        if not td_symbol:
            return None

        url = f"{self._base_url}/price"
        params = {"symbol": td_symbol, "apikey": self._api_key, "format": "JSON"}
        try:
            raw = self.get(url, params=params)
            if isinstance(raw, dict) and "price" in raw:
                return {
                    "symbol": symbol,
                    "price": float(raw["price"]),
                    "timestamp_utc": timezone.now(),
                    "is_delayed": False,
                }
        except Exception as exc:
            logger.warning(f"Latest price fetch failed for {symbol}: {exc}")
        return None

    def fetch_all_latest(self) -> dict[str, dict | None]:
        """Fetch latest prices for all supported instruments."""
        return {sym: self.fetch_latest_price(sym) for sym in SUPPORTED_INSTRUMENTS}

    def fetch_event_window(
        self,
        symbols: list[str],
        event_time: datetime,
        minutes_before: int = 60,
        minutes_after: int = 240,
        timeframe: str = "1min",
    ) -> dict[str, list[dict]]:
        """
        Fetch price data in the window around an economic event.

        This is the primary market-reaction data collector.
        """
        start = event_time - timedelta(minutes=minutes_before)
        end = event_time + timedelta(minutes=minutes_after)
        results = {}
        for symbol in symbols:
            try:
                candles = self.fetch_ohlcv(symbol, timeframe, start, end)
                results[symbol] = candles
            except Exception as exc:
                logger.warning(f"Event window fetch failed for {symbol}: {exc}")
                results[symbol] = []
        return results

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_recent(
        self,
        symbols: list[str] | None = None,
        timeframe: str = "1h",
        days_back: int = 30,
    ) -> dict:
        """Fetch recent OHLCV data and persist to MarketObservation table."""
        from macro_data.ingestion import persist_market_observations

        if symbols is None:
            symbols = list(SUPPORTED_INSTRUMENTS.keys())

        now = timezone.now()
        start = now - timedelta(days=days_back)
        saved = errors = 0

        for symbol in symbols:
            try:
                candles = self.fetch_ohlcv(symbol, timeframe, start, now)
                n = persist_market_observations(symbol, timeframe, candles)
                saved += n
            except Exception as exc:
                logger.error(f"Market data ingest error {symbol}/{timeframe}: {exc}", exc_info=True)
                errors += 1

        return {"saved": saved, "errors": errors, "symbols_processed": len(symbols)}

    # ── Parser ────────────────────────────────────────────────────────────────

    def _parse_ohlcv(
        self, symbol: str, timeframe: str, raw: Any
    ) -> list[dict]:
        """
        Parse Twelve Data time_series response.

        Twelve Data response structure:
        {
          "meta": {"symbol": "EUR/USD", "interval": "1min", ...},
          "values": [
            {"datetime": "2024-06-14 12:01:00", "open": "1.08000",
             "high": "1.08100", "low": "1.07900", "close": "1.08050",
             "volume": "1234"},
            ...
          ],
          "status": "ok"
        }
        """
        if not isinstance(raw, dict):
            raise ProviderDataError(f"Twelve Data: unexpected response for {symbol}")

        if raw.get("status") == "error":
            msg = raw.get("message", "Unknown error")
            raise ProviderDataError(f"Twelve Data error for {symbol}: {msg}")

        if "values" not in raw:
            # May indicate symbol not supported or no data in range
            logger.warning(f"Twelve Data: no 'values' key for {symbol}. Response: {raw}")
            return []

        results = []
        import pytz
        utc = pytz.UTC

        for item in raw["values"]:
            try:
                from datetime import datetime as dt
                # Twelve Data returns datetimes in UTC when timezone=UTC
                ts = dt.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc)

                results.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp_utc": ts,
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item.get("volume") or 0),
                    "is_delayed": False,
                    "provider": self.provider_name,
                })
            except Exception as exc:
                logger.warning(f"Twelve Data parse error {symbol}: {exc}")

        # Return in chronological order
        return sorted(results, key=lambda x: x["timestamp_utc"])

    def health_check(self) -> dict:
        """Probe Twelve Data with a usage status check."""
        try:
            url = f"{self._base_url}/api_usage"
            params = {"apikey": self._api_key}
            raw = self.get(url, params=params)
            return {
                "provider": self.provider_name,
                "status": "ok",
                "api_usage": raw,
                "checked_at": timezone.now().isoformat(),
            }
        except Exception as exc:
            return {
                "provider": self.provider_name,
                "status": "error",
                "error": str(exc),
                "checked_at": timezone.now().isoformat(),
            }


def get_market_data_provider() -> TwelveDataProvider:
    """
    Factory function: return the configured market data provider instance.

    Currently only Twelve Data is implemented.  Adding a new provider
    means implementing the MarketDataProvider Protocol and switching here.
    """
    provider_name = getattr(settings, "MARKET_DATA_PROVIDER", "twelvedata")
    if provider_name == "twelvedata":
        return TwelveDataProvider()
    raise ProviderConfigurationError(
        f"Unknown market data provider: {provider_name!r}. "
        "Supported: ['twelvedata']"
    )
