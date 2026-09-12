"""Celery tasks for forecasting."""
import logging
from celery import shared_task

logger = logging.getLogger("forecasting")


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def run_upcoming_event_forecasts(self) -> dict:
    """Run forecasts for all upcoming red-folder events in the next 48 hours."""
    try:
        from events.services import get_upcoming_red_folder_releases
        from .nowcast import run_forecast_for_release

        releases = get_upcoming_red_folder_releases(hours_ahead=48)
        results = {"processed": 0, "skipped": 0, "errors": 0}

        for release in releases:
            try:
                run_forecast_for_release(release)
                results["processed"] += 1
            except Exception as exc:
                logger.error(
                    f"Forecast task failed for {release.event.code}: {exc}",
                    exc_info=True,
                )
                results["errors"] += 1

        logger.info(f"Forecast batch complete: {results}")
        return results
    except Exception as exc:
        logger.error(f"run_upcoming_event_forecasts failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
