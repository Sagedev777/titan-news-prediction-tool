"""
Celery tasks for alert dispatch.

Dispatches pre-release alerts 30 minutes before each scheduled release.
"""

from __future__ import annotations
import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("alerts")


@shared_task(bind=True, max_retries=2)
def dispatch_pre_release_alerts(self) -> dict:
    """
    Check for events releasing within the next 30 minutes and
    send email + Telegram alerts if a forecast is available.
    """
    try:
        from events.services import get_upcoming_red_folder_releases
        from forecasting.models import ForecastRun
        from .email import send_forecast_email
        from .telegram import send_forecast_telegram

        now = timezone.now()
        window_minutes = 30
        releases = get_upcoming_red_folder_releases(hours_ahead=1)

        sent = 0
        for release in releases:
            minutes_away = (release.release_time_utc - now).total_seconds() / 60
            if minutes_away > window_minutes:
                continue

            # Get latest forecast for this release
            run = (
                ForecastRun.objects.filter(economic_release=release)
                .order_by("-run_time_utc")
                .first()
            )

            if not run:
                logger.info(
                    f"No forecast available for {release.event.code} "
                    f"releasing at {release.release_time_utc}"
                )
                continue

            # Don't re-send if already sent in last 25 minutes
            cache_key = f"alert_sent_{release.id}"
            from django.core.cache import cache
            if cache.get(cache_key):
                continue

            forecast_data = {
                "event_code": release.event.code,
                "event_name": release.event.name,
                "currency": release.event.currency,
                "release_time_utc": release.release_time_utc.isoformat(),
                "consensus": float(release.consensus) if release.consensus else None,
                "previous": float(release.previous) if release.previous else None,
                "estimate": run.estimate,
                "event_bias": run.event_bias,
                "probability_above": run.probability_above_consensus,
                "probability_near": run.probability_near_consensus,
                "probability_below": run.probability_below_consensus,
                "data_quality": run.data_quality_status,
                "warnings": run.warnings,
            }

            send_forecast_email(forecast_data)
            send_forecast_telegram(forecast_data)

            # Mark as sent for 25 minutes
            cache.set(cache_key, True, timeout=25 * 60)
            sent += 1

        return {"dispatched": sent}

    except Exception as exc:
        logger.error(f"Alert dispatch failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
