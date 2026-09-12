"""Telegram alert sender for pre-release forecast notifications."""
from __future__ import annotations
import logging
import httpx
from django.conf import settings

logger = logging.getLogger("alerts")

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_telegram_message(text: str) -> bool:
    """Send a message via the configured Telegram bot."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured — skipping.")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Telegram alert sent.")
            return True
        logger.error(f"Telegram API error: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as exc:
        logger.error(f"Telegram send failed: {exc}", exc_info=True)
        return False


def send_forecast_telegram(forecast_data: dict) -> bool:
    """Format and send a forecast alert via Telegram."""
    event = forecast_data.get("event_name", "?")
    code = forecast_data.get("event_code", "")
    consensus = forecast_data.get("consensus")
    estimate = forecast_data.get("estimate")
    bias = forecast_data.get("event_bias", "N/A")
    p_above = forecast_data.get("probability_above")
    p_below = forecast_data.get("probability_below")
    release_utc = forecast_data.get("release_time_utc", "")
    quality = forecast_data.get("data_quality", "")
    warnings = forecast_data.get("warnings", [])

    p_above_str = f"{p_above:.0%}" if p_above is not None else "N/A"
    p_below_str = f"{p_below:.0%}" if p_below is not None else "N/A"
    est_str = f"{estimate:.4f}" if estimate is not None else "N/A"
    cons_str = f"{consensus:.4f}" if consensus is not None else "N/A"

    lines = [
        f"🔴 <b>RED FOLDER ALERT</b>",
        f"<b>{event}</b> ({code})",
        f"Release: {release_utc}",
        "",
        f"Consensus: {cons_str}",
        f"Model estimate: {est_str}",
        f"Bias: {bias}",
        f"P(above): {p_above_str} | P(below): {p_below_str}",
        f"Data quality: {quality}",
    ]

    if warnings:
        lines.append("")
        lines.append("⚠️ Warnings:")
        for w in warnings[:3]:
            lines.append(f"  • {w[:100]}")

    lines.append("")
    lines.append(
        "<i>Probabilistic model estimate — not a guaranteed signal. "
        "Use with other analysis.</i>"
    )

    return send_telegram_message("\n".join(lines))
