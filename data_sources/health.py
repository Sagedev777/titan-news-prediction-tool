"""
Data-source health checks.

Runs probes against all configured providers and returns a structured
health report used by the dashboard Data Health page and the monitoring
endpoint.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("data_sources")


def run_all_health_checks() -> dict:
    """
    Run health checks for every configured provider.

    Returns a dict with:
    - providers: list of per-provider status dicts
    - overall_status: "ok" | "degraded" | "down"
    - checked_at: UTC timestamp
    """
    results = []
    errors = []

    # Trading Economics
    try:
        if settings.TRADING_ECONOMICS_API_KEY:
            from .trading_economics import TradingEconomicsProvider
            results.append(TradingEconomicsProvider().health_check())
        else:
            results.append({
                "provider": "trading_economics",
                "status": "not_configured",
                "error": "TRADING_ECONOMICS_API_KEY not set",
                "checked_at": timezone.now().isoformat(),
            })
    except Exception as exc:
        results.append({"provider": "trading_economics", "status": "error", "error": str(exc)})
        errors.append("trading_economics")

    # BLS
    try:
        if settings.BLS_API_KEY:
            from .bls import BLSProvider
            results.append(BLSProvider().health_check())
        else:
            results.append({
                "provider": "bls",
                "status": "not_configured",
                "error": "BLS_API_KEY not set",
                "checked_at": timezone.now().isoformat(),
            })
    except Exception as exc:
        results.append({"provider": "bls", "status": "error", "error": str(exc)})
        errors.append("bls")

    # FRED
    try:
        if settings.FRED_API_KEY:
            from .fred import FREDProvider
            results.append(FREDProvider().health_check())
        else:
            results.append({
                "provider": "fred",
                "status": "not_configured",
                "error": "FRED_API_KEY not set",
                "checked_at": timezone.now().isoformat(),
            })
    except Exception as exc:
        results.append({"provider": "fred", "status": "error", "error": str(exc)})
        errors.append("fred")

    # Cleveland Fed (no key required)
    try:
        from .cleveland_fed import ClevelandFedProvider
        results.append(ClevelandFedProvider().health_check())
    except Exception as exc:
        results.append({"provider": "cleveland_fed", "status": "error", "error": str(exc)})
        errors.append("cleveland_fed")

    # Market Data
    try:
        if settings.MARKET_DATA_API_KEY:
            from .market_data import get_market_data_provider
            results.append(get_market_data_provider().health_check())
        else:
            results.append({
                "provider": "market_data",
                "status": "not_configured",
                "error": "MARKET_DATA_API_KEY not set",
                "checked_at": timezone.now().isoformat(),
            })
    except Exception as exc:
        results.append({"provider": "market_data", "status": "error", "error": str(exc)})
        errors.append("market_data")

    # Determine overall status
    statuses = [r.get("status") for r in results]
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif any(s in ("error", "down") for s in statuses):
        overall = "degraded" if len(errors) < len(results) else "down"
    else:
        overall = "degraded"

    return {
        "providers": results,
        "overall_status": overall,
        "checked_at": timezone.now().isoformat(),
        "errors": errors,
    }


def check_data_staleness() -> dict:
    """
    Check whether macro and market data is within acceptable age limits.

    Returns warnings for series that haven't been updated recently.
    """
    from macro_data.models import DataObservation, MarketObservation

    warnings = []
    max_macro_age = timedelta(days=settings.MACRO_DATA_MAX_AGE_DAYS)
    max_market_age = timedelta(minutes=settings.MARKET_DATA_MAX_AGE_MINUTES)
    now = timezone.now()

    # Check macro series freshness
    key_series = ["CUSR0000SA0", "CES0000000001", "LNS14000000", "DGS2", "DCOILWTICO"]
    for series_id in key_series:
        latest = (
            DataObservation.objects.filter(series_id=series_id)
            .order_by("-retrieved_at")
            .first()
        )
        if not latest:
            warnings.append({
                "type": "missing_series",
                "series_id": series_id,
                "message": f"No data found for {series_id}",
            })
        elif now - latest.retrieved_at > max_macro_age:
            age_hours = (now - latest.retrieved_at).total_seconds() / 3600
            warnings.append({
                "type": "stale_data",
                "series_id": series_id,
                "message": f"{series_id} last retrieved {age_hours:.1f}h ago",
                "last_retrieved": latest.retrieved_at.isoformat(),
            })

    # Check market data freshness (only during trading hours)
    key_symbols = ["EURUSD", "XAUUSD", "USDJPY"]
    for symbol in key_symbols:
        latest = (
            MarketObservation.objects.filter(symbol=symbol, timeframe="1h")
            .order_by("-timestamp_utc")
            .first()
        )
        if not latest:
            warnings.append({
                "type": "missing_market_data",
                "symbol": symbol,
                "message": f"No 1h market data found for {symbol}",
            })

    return {
        "warnings": warnings,
        "warning_count": len(warnings),
        "checked_at": now.isoformat(),
    }
