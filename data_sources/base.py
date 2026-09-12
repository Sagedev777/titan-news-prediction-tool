"""
Base classes and Protocol interfaces for all data providers.

Every provider must implement the relevant protocol(s).
No forecasting code may call a provider directly — it must go
through these interfaces so providers can be swapped without
changing forecasting logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("data_sources")


# ── Exceptions ────────────────────────────────────────────────────────────────

class ProviderConfigurationError(Exception):
    """Raised when a required API key or URL is not configured."""


class ProviderUnavailableError(Exception):
    """Raised when the provider API cannot be reached."""


class ProviderDataError(Exception):
    """Raised when the provider returns unexpected or invalid data."""


class InsufficientDataError(Exception):
    """Raised when a provider returns data but it is insufficient for a forecast."""


# ── Protocol interfaces ────────────────────────────────────────────────────────

@runtime_checkable
class EconomicCalendarProvider(Protocol):
    """Protocol for economic calendar data providers."""

    def fetch_events(self, start: datetime, end: datetime) -> list[dict]: ...

    def fetch_point_in_time_events(
        self, as_of: datetime, start: datetime, end: datetime
    ) -> list[dict]: ...

    def fetch_event_history(
        self, event_code: str, start: datetime, end: datetime
    ) -> list[dict]: ...


@runtime_checkable
class MacroSeriesProvider(Protocol):
    """Protocol for providers of macroeconomic time-series data."""

    def fetch_series(
        self, series_id: str, start: datetime, end: datetime
    ) -> list[dict]: ...

    def fetch_series_vintage(
        self, series_id: str, vintage_date: datetime
    ) -> list[dict]: ...


@runtime_checkable
class MarketDataProvider(Protocol):
    """Protocol for market OHLCV data providers."""

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]: ...


# ── Base HTTP client ──────────────────────────────────────────────────────────

class BaseHTTPProvider(ABC):
    """
    Abstract base for any HTTP-based data provider.

    Provides:
    - Shared httpx client with retry logic.
    - Automatic request/response logging to ProviderRequestLog.
    - Response hashing for audit.
    - Uniform error handling.
    """

    provider_name: str = "unknown"
    base_url: str = ""
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_backoff: float = 2.0

    def __init__(self):
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "TitanForecast/1.0"},
        )

    def _get_api_key(self, setting_name: str) -> str:
        """
        Retrieve an API key from settings.

        Raises ProviderConfigurationError if missing or empty.
        This is the correct behaviour — never fall back to mock data.
        """
        key = getattr(settings, setting_name, "")
        if not key:
            raise ProviderConfigurationError(
                f"Provider {self.provider_name!r} requires {setting_name} "
                "to be set in environment variables. "
                "Configure it in your .env file. "
                "Do not use mock data as a fallback."
            )
        return key

    @staticmethod
    def _hash_response(data: Any) -> str:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _strip_secrets(url: str) -> str:
        """Remove API keys from URLs before logging."""
        import re
        return re.sub(r"([?&])(api_key|apikey|key|token)=[^&]+", r"\1\2=REDACTED", url, flags=re.IGNORECASE)

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json_body: Any = None,
        headers: dict | None = None,
    ) -> Any:
        """
        Execute an HTTP request with retry logic and audit logging.

        Returns the parsed JSON response body.
        Raises ProviderUnavailableError or ProviderDataError on failure.
        """
        from events.services import log_provider_request

        request_time = timezone.now()
        safe_url = self._strip_secrets(url)
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                response_time = timezone.now()

                try:
                    data = resp.json()
                except Exception:
                    data = resp.text

                resp_hash = self._hash_response(data)

                log_provider_request(
                    provider=self.provider_name,
                    endpoint=safe_url,
                    request_time=request_time,
                    response_time=response_time,
                    http_status=resp.status_code,
                    response_hash=resp_hash,
                )

                if resp.status_code == 200:
                    logger.debug(
                        f"{self.provider_name} {method} {safe_url} → {resp.status_code}",
                        extra={"attempt": attempt},
                    )
                    return data

                if resp.status_code == 401:
                    raise ProviderConfigurationError(
                        f"{self.provider_name}: HTTP 401 — Invalid or missing API key. "
                        f"Check {self.provider_name.upper()}_API_KEY in .env."
                    )
                if resp.status_code == 429:
                    logger.warning(f"{self.provider_name}: Rate limited. Backing off.")
                    time.sleep(self.retry_backoff * attempt * 2)
                    continue

                raise ProviderDataError(
                    f"{self.provider_name}: HTTP {resp.status_code} for {safe_url}. "
                    f"Response: {str(data)[:200]}"
                )

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    f"{self.provider_name}: Connection error attempt {attempt}/{self.max_retries}: {exc}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * attempt)
                continue

        log_provider_request(
            provider=self.provider_name,
            endpoint=safe_url,
            request_time=request_time,
            response_time=timezone.now(),
            http_status=None,
            response_hash="",
            error_message=str(last_exc),
        )
        raise ProviderUnavailableError(
            f"{self.provider_name}: All {self.max_retries} attempts failed for {safe_url}. "
            f"Last error: {last_exc}"
        )

    def get(self, url: str, params: dict | None = None) -> Any:
        return self._request("GET", url, params=params)

    def post(self, url: str, json_body: Any = None) -> Any:
        return self._request("POST", url, json_body=json_body)

    def health_check(self) -> dict:
        """Override in subclasses to implement a provider health probe."""
        return {"provider": self.provider_name, "status": "not_implemented"}
