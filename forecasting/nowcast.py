"""
Nowcast orchestrator — assembles a full pre-release research snapshot.

This is the central coordinator that:
1. Validates the event (red-folder gate)
2. Retrieves all features
3. Runs the event-specific model
4. Runs scenarios
5. Persists ForecastRun + ForecastFeature records
6. Returns the complete research snapshot
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

from events.services import assert_red_folder
from .calibration import assess_calibration
from .event_models import get_event_model, is_model_implemented
from .feature_engineering import (
    FeatureMatrix,
    build_cpi_features,
    build_nfp_features,
    get_latest_feature_row,
)
from .explainability import generate_evidence_bullets
from .scenarios import build_scenarios

logger = logging.getLogger("forecasting")


_FEATURE_BUILDERS = {
    "US_CPI": build_cpi_features,
    "US_CORE_CPI": build_cpi_features,
    "US_NFP": build_nfp_features,
    "US_UNEMPLOYMENT_RATE": build_nfp_features,
    "US_AVERAGE_HOURLY_EARNINGS": build_nfp_features,
}


def run_forecast_for_release(
    release,  # EconomicRelease instance
    force: bool = False,
) -> dict:
    """
    Run a complete pre-release forecast for an EconomicRelease.

    Parameters
    ----------
    release : EconomicRelease — must be a future, unreleased red-folder event.
    force : If True, run even if a recent forecast already exists.

    Returns
    -------
    dict with full research snapshot including:
    - event metadata
    - model estimate and interval
    - surprise probabilities
    - scenarios
    - evidence bullets
    - data quality and warnings
    - ForecastRun.id if persisted
    """
    from events.models import ImpactLevel
    from .models import ForecastRun, ForecastFeature, DataQualityStatus, CalibrationStatus

    event = release.event
    now = timezone.now()
    result: dict[str, Any] = {
        "event_code": event.code,
        "event_name": event.name,
        "currency": event.currency,
        "country": event.country,
        "release_time_utc": release.release_time_utc.isoformat(),
        "research_time_utc": now.isoformat(),
        "data_cutoff_utc": now.isoformat(),
        "consensus": float(release.consensus) if release.consensus is not None else None,
        "previous": float(release.previous) if release.previous is not None else None,
        "forecast_run_id": None,
    }

    # ── Red-folder gate ────────────────────────────────────────────────────────
    try:
        assert_red_folder(event)
    except ValueError as exc:
        result["status"] = "EXCLUDED_NOT_RED_FOLDER"
        result["error"] = str(exc)
        logger.warning(f"Forecast rejected: {exc}")
        return result

    # ── Model availability gate ────────────────────────────────────────────────
    if not is_model_implemented(event.code):
        result["status"] = "NO_MODEL_IMPLEMENTED"
        result["message"] = (
            f"No event-specific model is implemented for {event.code}. "
            "Forecast unavailable."
        )
        return result

    # ── Feature engineering ───────────────────────────────────────────────────
    builder = _FEATURE_BUILDERS.get(event.code)
    if builder is None:
        result["status"] = "NO_FEATURE_BUILDER"
        return result

    consensus = float(release.consensus) if release.consensus is not None else None
    fm: FeatureMatrix = builder(as_of=now, consensus=consensus)

    # ── Run event model ───────────────────────────────────────────────────────
    model_class = get_event_model(event.code)
    model = model_class()
    near_band = float(getattr(settings, "NEAR_CONSENSUS_BAND", 0.05))
    model_result = model.run(
        feature_matrix=fm,
        consensus=consensus,
        previous=float(release.previous) if release.previous is not None else None,
        as_of=now,
        near_band=near_band,
    )

    # ── Scenarios ─────────────────────────────────────────────────────────────
    scenarios_data = []
    if model_result.is_forecast_available:
        scenarios = build_scenarios(
            event_code=event.code,
            estimate=model_result.estimate,
            consensus=consensus,
            p_above=model_result.probability_above,
            p_near=model_result.probability_near,
            p_below=model_result.probability_below,
            near_band=near_band,
        )
        for s in scenarios:
            scenarios_data.append({
                "name": s.name,
                "description": s.description,
                "condition": s.condition,
                "probability": s.probability,
                "currency_direction": s.currency_direction,
                "pair_reactions": s.pair_reactions,
                "rate_reaction": s.rate_reaction,
                "invalidating_conditions": s.invalidating_conditions,
                "pricing_note": s.pricing_note,
            })

    # ── Evidence bullets ──────────────────────────────────────────────────────
    latest_row = get_latest_feature_row(fm)
    feature_values = dict(latest_row) if latest_row is not None else {}
    evidence_bullets = generate_evidence_bullets(
        model_result.feature_importances,
        feature_values,
        event.code,
    )

    # ── Assemble result dict ──────────────────────────────────────────────────
    result.update(
        {
            "status": "OK" if model_result.is_forecast_available else "FORECAST_UNAVAILABLE",
            "model_name": model_result.model_name,
            "model_version": model_result.model_version,
            "estimate": model_result.estimate,
            "lower_bound": model_result.lower_bound,
            "upper_bound": model_result.upper_bound,
            "probability_above": model_result.probability_above,
            "probability_near": model_result.probability_near,
            "probability_below": model_result.probability_below,
            "near_consensus_band": near_band,
            "estimated_surprise": model_result.estimated_surprise,
            "event_bias": model_result.event_bias,
            "data_quality": model_result.data_quality,
            "calibration_status": model_result.calibration_status,
            "comparable_releases": model_result.comparable_releases,
            "warnings": model_result.warnings,
            "evidence_bullets": evidence_bullets,
            "scenarios": scenarios_data,
            "available_features": fm.available_features,
            "missing_features": fm.missing_features,
            "feature_quality_score": fm.quality_score,
        }
    )

    # ── Persist ForecastRun ───────────────────────────────────────────────────
    if model_result.is_forecast_available or model_result.warnings:
        try:
            feature_snapshot = {
                k: float(v) if v is not None else None
                for k, v in feature_values.items()
                if v is not None
            }
            snap_hash = hashlib.sha256(
                json.dumps(feature_snapshot, sort_keys=True, default=str).encode()
            ).hexdigest()

            dq_map = {
                "GOOD": DataQualityStatus.GOOD,
                "DEGRADED": DataQualityStatus.DEGRADED,
                "POOR": DataQualityStatus.POOR,
                "UNAVAILABLE": DataQualityStatus.UNAVAILABLE,
            }
            cal_map = {
                "VERIFIED": CalibrationStatus.VERIFIED,
                "UNVERIFIED": CalibrationStatus.UNVERIFIED,
                "INSUFFICIENT": CalibrationStatus.INSUFFICIENT,
            }

            run = ForecastRun.objects.create(
                event=event,
                economic_release=release,
                model_name=model_result.model_name,
                model_version=model_result.model_version,
                run_time_utc=now,
                data_cutoff_time_utc=now,
                estimate=model_result.estimate,
                lower_bound=model_result.lower_bound,
                upper_bound=model_result.upper_bound,
                probability_below_consensus=model_result.probability_below,
                probability_near_consensus=model_result.probability_near,
                probability_above_consensus=model_result.probability_above,
                near_consensus_band=near_band,
                event_bias=model_result.event_bias,
                data_quality_status=dq_map.get(
                    model_result.data_quality, DataQualityStatus.UNAVAILABLE
                ),
                calibration_status=cal_map.get(
                    model_result.calibration_status, CalibrationStatus.UNVERIFIED
                ),
                feature_snapshot_hash=snap_hash,
                warnings=model_result.warnings,
                data_sources_used=fm.available_features,
                comparable_releases_count=model_result.comparable_releases,
            )

            # Persist individual features
            for feat_name, feat_val in feature_values.items():
                ForecastFeature.objects.create(
                    forecast_run=run,
                    feature_name=feat_name,
                    value=float(feat_val) if feat_val is not None else None,
                    source="feature_matrix",
                    missing_flag=feat_name in fm.missing_features,
                )

            result["forecast_run_id"] = run.id
            logger.info(
                f"ForecastRun created: id={run.id} event={event.code} "
                f"estimate={model_result.estimate}"
            )

        except Exception as exc:
            logger.error(f"Failed to persist ForecastRun: {exc}", exc_info=True)
            result["persist_error"] = str(exc)

    return result
