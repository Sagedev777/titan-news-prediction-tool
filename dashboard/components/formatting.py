"""
Shared formatting helpers for the dashboard.
"""

from __future__ import annotations

import pytz
from datetime import datetime

DISPLAY_TZ_NAME = "Africa/Nairobi"
DISPLAY_TZ = pytz.timezone(DISPLAY_TZ_NAME)


def to_eat(dt: datetime | None) -> str:
    """Convert a UTC datetime to East Africa Time string."""
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    eat = dt.astimezone(DISPLAY_TZ)
    return eat.strftime("%Y-%m-%d %H:%M EAT")


def countdown(dt: datetime | None) -> str:
    """Return human-readable countdown to dt."""
    if dt is None:
        return "—"
    from django.utils import timezone
    now = timezone.now()
    if dt.tzinfo is None:
        import pytz
        dt = pytz.utc.localize(dt)
    diff = dt - now
    if diff.total_seconds() < 0:
        return "Released"
    total = int(diff.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def signal_badge(signal: str) -> str:
    """Return an emoji badge for a signal type."""
    return {
        "BUY": "🟢 BUY",
        "SELL": "🔴 SELL",
        "NEUTRAL": "🟡 NEUTRAL",
        "NO_SIGNAL": "⚪ NO SIGNAL",
    }.get(signal, signal)


def quality_badge(quality: str) -> str:
    return {
        "GOOD": "✅ Good",
        "DEGRADED": "⚠️ Degraded",
        "POOR": "🔴 Poor",
        "UNAVAILABLE": "❌ Unavailable",
    }.get(quality, quality)


def probability_bar(p: float | None, label: str = "") -> str:
    """Return a text probability bar."""
    if p is None:
        return f"{label}: N/A"
    pct = int(p * 100)
    filled = pct // 5
    bar = "█" * filled + "░" * (20 - filled)
    return f"{label}: {bar} {pct}%"


def format_float(v: float | None, decimals: int = 4) -> str:
    if v is None:
        return "N/A"
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(v)


def format_surprise(surprise: float | None) -> str:
    if surprise is None:
        return "N/A"
    sign = "+" if surprise > 0 else ""
    return f"{sign}{surprise:.4f}"
