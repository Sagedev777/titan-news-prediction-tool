"""Email alert sender for pre-release forecast notifications."""
from __future__ import annotations
import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("alerts")


def send_forecast_email(forecast_data: dict) -> bool:
    """Send a pre-release forecast alert via email."""
    recipients = getattr(settings, "ALERT_TO_EMAILS", [])
    if not recipients:
        logger.warning("No ALERT_TO_EMAILS configured — email alert skipped.")
        return False

    event = forecast_data.get("event_name", "Unknown Event")
    code = forecast_data.get("event_code", "")
    release_time = forecast_data.get("release_time_utc", "")
    estimate = forecast_data.get("estimate")
    consensus = forecast_data.get("consensus")
    bias = forecast_data.get("event_bias", "N/A")
    p_above = forecast_data.get("probability_above")
    warnings = forecast_data.get("warnings", [])

    subject = f"[RED FOLDER] {event} — Pre-release Forecast"

    body_lines = [
        f"RED FOLDER ALERT: {event} ({code})",
        f"Release time (UTC): {release_time}",
        "",
        f"Consensus: {consensus}",
        f"Model estimate: {estimate}",
        f"Estimated bias: {bias}",
        f"Probability above consensus: {f'{p_above:.0%}' if p_above else 'N/A'}",
        "",
    ]

    if warnings:
        body_lines += ["WARNINGS:", *[f"  • {w}" for w in warnings[:5]], ""]

    body_lines.append(
        "DISCLAIMER: This is a probabilistic model estimate. "
        "Never trade on a single indicator. No guarantee of accuracy."
    )

    body = "\n".join(body_lines)

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        logger.info(f"Email alert sent for {code} to {len(recipients)} recipients.")
        return True
    except Exception as exc:
        logger.error(f"Email alert failed for {code}: {exc}", exc_info=True)
        return False
