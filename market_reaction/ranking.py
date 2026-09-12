"""
Pair-ranking system.

Ranks all instrument forecasts from strongest to weakest evidence
using a composite scoring formula.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("market_reaction")

DEFAULT_INSTRUMENTS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "XAUUSD", "DXY", "US02Y", "US10Y",
]

DEFAULT_HORIZON_MINUTES = [15, 60]


def compute_ranking_score(
    probability_edge: float,
    historical_accuracy: float,
    sample_size: int,
    calibration_quality: float = 1.0,
    data_quality: float = 1.0,
    model_agreement: float = 1.0,
    transaction_cost_penalty: float = 0.01,
    min_sample: int = 25,
) -> float:
    """
    Composite ranking score.

    ranking_score =
        probability_edge
        * calibration_quality
        * sample_size_factor
        * data_quality
        * model_agreement
        - transaction_cost_penalty

    All inputs should be 0.0–1.0 (or edge in pips/pct).
    """
    sample_size_factor = min(1.0, sample_size / min_sample)
    score = (
        probability_edge
        * calibration_quality
        * sample_size_factor
        * data_quality
        * model_agreement
        - transaction_cost_penalty
    )
    return max(0.0, score)


def run_all_instrument_forecasts(
    forecast_run,
    estimated_surprise: float | None,
    event_code: str,
    consensus: float | None,
    as_of,
    instruments: list[str] | None = None,
    horizons: list[int] | None = None,
    min_confidence: float | None = None,
) -> list:
    """
    Generate InstrumentForecast records for all instruments.

    Returns list of InstrumentForecast instances (not yet saved).
    Caller is responsible for bulk_create.
    """
    from .reaction_model import predict_reaction
    from .models import InstrumentForecast

    if instruments is None:
        instruments = DEFAULT_INSTRUMENTS
    if horizons is None:
        horizons = DEFAULT_HORIZON_MINUTES
    if min_confidence is None:
        min_confidence = float(getattr(settings, "MIN_SIGNAL_PROBABILITY", 50)) / 100

    min_sample = int(getattr(settings, "MIN_HISTORICAL_SAMPLE", 25))

    results = []
    for symbol in instruments:
        for horizon_min in horizons:
            try:
                pred = predict_reaction(
                    event_code=event_code,
                    symbol=symbol,
                    horizon_minutes=horizon_min,
                    estimated_surprise=estimated_surprise,
                    consensus=consensus,
                    as_of=as_of,
                    min_confidence=min_confidence,
                    min_sample=min_sample,
                )

                # Compute ranking score
                edge = 0.0
                if pred.probability_up and pred.signal == "BUY":
                    edge = pred.probability_up - 0.5
                elif pred.probability_down and pred.signal == "SELL":
                    edge = pred.probability_down - 0.5

                score = compute_ranking_score(
                    probability_edge=edge,
                    historical_accuracy=pred.historical_accuracy or 0.0,
                    sample_size=pred.sample_size,
                    data_quality=1.0 if pred.evidence_quality != "INSUFFICIENT" else 0.0,
                    min_sample=min_sample,
                )

                inst_forecast = InstrumentForecast(
                    forecast_run=forecast_run,
                    symbol=symbol,
                    horizon=pred.horizon,
                    signal=pred.signal,
                    probability_up=pred.probability_up,
                    probability_down=pred.probability_down,
                    probability_flat=pred.probability_flat,
                    expected_return=pred.expected_return,
                    historical_accuracy=pred.historical_accuracy,
                    sample_size=pred.sample_size,
                    ranking_score=score,
                    evidence_quality=pred.evidence_quality,
                    explanation=pred.explanation,
                    warnings=pred.warnings,
                )
                results.append(inst_forecast)

            except Exception as exc:
                logger.error(
                    f"Instrument forecast failed {symbol}/{horizon_min}: {exc}",
                    exc_info=True,
                )

    # Sort by ranking score descending
    results.sort(key=lambda x: (x.ranking_score or 0.0), reverse=True)
    return results
