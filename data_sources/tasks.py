"""Celery tasks for data-source health checks."""
from celery import shared_task
import logging

logger = logging.getLogger("data_sources")


@shared_task(bind=True, max_retries=2)
def run_data_quality_checks(self) -> dict:
    """Run all provider health checks and record any issues found."""
    try:
        from .health import run_all_health_checks, check_data_staleness
        from events.services import record_data_quality_issue
        from events.models import DataQualityIssueType, DataQualitySeverity

        health = run_all_health_checks()
        staleness = check_data_staleness()

        for provider_result in health["providers"]:
            if provider_result.get("status") not in ("ok", "not_configured"):
                record_data_quality_issue(
                    provider=provider_result["provider"],
                    series_id="",
                    issue_type=DataQualityIssueType.PROVIDER_UNAVAILABLE,
                    severity=DataQualitySeverity.CRITICAL,
                    message=provider_result.get("error", "Provider health check failed"),
                )

        for warning in staleness.get("warnings", []):
            record_data_quality_issue(
                provider="internal",
                series_id=warning.get("series_id") or warning.get("symbol", ""),
                issue_type=DataQualityIssueType.STALE_DATA,
                severity=DataQualitySeverity.WARNING,
                message=warning["message"],
            )

        return {
            "overall_status": health["overall_status"],
            "issues_recorded": len(health["errors"]) + len(staleness["warnings"]),
        }
    except Exception as exc:
        logger.error(f"Data quality check task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
