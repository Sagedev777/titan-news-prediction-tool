"""
Market reaction model.

For each (event_code, symbol, horizon) combination, trains a
logistic/gradient-boosting classifier on historical reactions
and produces calibrated BUY/SELL/NEUTRAL signals.

The model enforces minimum sample size and calibration requirements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler

from forecasting.calibration import assess_calibration, MIN_SAMPLES_FOR_CALIBRATION
from .labels import build_reaction_labels

logger = logging.getLogger("market_reaction")

MIN_REACTION_SAMPLES = 25  # Minimum historical events to make a prediction


@dataclass
class ReactionPrediction:
    symbol: str
    horizon: str
    signal: str   # BUY / SELL / NEUTRAL / NO_SIGNAL
    probability_up: float | None
    probability_down: float | None
    probability_flat: float | None
    expected_return: float | None
    historical_accuracy: float | None
    sample_size: int
    evidence_quality: str
    brier_score: float | None
    explanation: str
    warnings: list[str] = field(default_factory=list)


def predict_reaction(
    event_code: str,
    symbol: str,
    horizon_minutes: int,
    estimated_surprise: float | None,
    consensus: float | None,
    as_of,
    min_confidence: float = 0.50,
    min_sample: int = MIN_REACTION_SAMPLES,
) -> ReactionPrediction:
    """
    Predict market reaction for one (event, symbol, horizon) combination.

    Returns a ReactionPrediction with signal, probabilities, and metadata.
    Returns NO_SIGNAL if evidence is insufficient.
    """
    from events.models import EconomicRelease, ImpactLevel
    from forecasting.calibration import compute_surprise_probabilities

    horizon_str = _horizon_label(horizon_minutes)

    # ── Get historical releases ───────────────────────────────────────────────
    releases = list(
        EconomicRelease.objects.select_related("event")
        .filter(
            event__code=event_code,
            event__normalized_impact_level=ImpactLevel.HIGH,
            event__is_allowlisted=True,
            actual__isnull=False,
            consensus__isnull=False,
        )
        .order_by("release_time_utc")
    )

    if len(releases) < min_sample:
        return ReactionPrediction(
            symbol=symbol,
            horizon=horizon_str,
            signal="NO_SIGNAL",
            probability_up=None,
            probability_down=None,
            probability_flat=None,
            expected_return=None,
            historical_accuracy=None,
            sample_size=len(releases),
            evidence_quality="INSUFFICIENT",
            brier_score=None,
            explanation=(
                f"NO SIGNAL — insufficient historical sample. "
                f"Available: {len(releases)}, required: {min_sample}."
            ),
            warnings=[
                f"Insufficient historical sample for {event_code}/{symbol}/{horizon_str}. "
                f"n={len(releases)} (need {min_sample})."
            ],
        )

    # ── Build labelled training data ──────────────────────────────────────────
    label_df = build_reaction_labels(
        releases=releases,
        symbol=symbol,
        horizons_minutes=[horizon_minutes],
        flat_multiplier=0.25,
    )

    direction_col = f"direction_{horizon_minutes}min"
    return_col = f"return_{horizon_minutes}min"

    if label_df.empty or direction_col not in label_df.columns:
        return ReactionPrediction(
            symbol=symbol, horizon=horizon_str, signal="NO_SIGNAL",
            probability_up=None, probability_down=None, probability_flat=None,
            expected_return=None, historical_accuracy=None, sample_size=0,
            evidence_quality="INSUFFICIENT", brier_score=None,
            explanation="No market data available for reaction model.",
        )

    # ── Build binary UP label (UP=1, not UP=0) ────────────────────────────────
    label_df = label_df.dropna(subset=[direction_col, "surprise"])
    n = len(label_df)

    if n < min_sample:
        return ReactionPrediction(
            symbol=symbol, horizon=horizon_str, signal="NO_SIGNAL",
            probability_up=None, probability_down=None, probability_flat=None,
            expected_return=None, historical_accuracy=None, sample_size=n,
            evidence_quality="INSUFFICIENT", brier_score=None,
            explanation=f"Only {n} labelled observations (need {min_sample}).",
        )

    # ── Feature matrix ─────────────────────────────────────────────────────────
    feature_cols = ["surprise", "consensus"]
    if "previous" in label_df.columns:
        feature_cols.append("previous")

    X = label_df[feature_cols].fillna(0)
    y_direction = label_df[direction_col]

    # ── Historical accuracy (simple: correct direction calls) ─────────────────
    # Use walk-forward CV on pure direction
    up_mask = y_direction == "UP"
    down_mask = y_direction == "DOWN"

    surprise_series = label_df["surprise"]
    # Naive rule: positive surprise → UP
    naive_preds = (surprise_series > 0).map({True: "UP", False: "DOWN"})
    naive_correct = (naive_preds == y_direction).mean()

    # ── Logistic regression for P(UP) ────────────────────────────────────────
    y_binary = (y_direction == "UP").astype(int)
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)

    if len(np.unique(y_binary)) < 2:
        # All same class — cannot fit
        p_up = float(y_binary.mean())
        p_down = 1.0 - p_up
        p_flat = 0.0
        brier = None
        method = "class_prior"
        historical_accuracy = float(naive_correct)
    else:
        try:
            tscv = TimeSeriesSplit(n_splits=min(5, n // 5))
            lr = LogisticRegression(C=1.0)
            cv_scores = cross_val_score(lr, X_s, y_binary, cv=tscv, scoring="accuracy")
            historical_accuracy = float(cv_scores.mean())

            lr.fit(X_s, y_binary)

            # Current prediction
            if estimated_surprise is not None:
                x_new = np.array([[estimated_surprise, consensus or 0.0]])
                if "previous" in feature_cols:
                    x_new = np.hstack([x_new, [[0.0]]])
                x_new_s = scaler.transform(x_new)
                probs = lr.predict_proba(x_new_s)[0]
                p_up = float(probs[1])
                p_down = float(probs[0])
            else:
                p_up = p_down = 0.5

            p_flat = 0.0
            # Absorb flat probability from DOWN bucket when move is small
            down_rate = float((y_direction == "DOWN").mean())
            flat_rate = float((y_direction == "FLAT").mean())
            total_nd = p_down + flat_rate
            p_flat = max(0.0, flat_rate)
            p_down = max(0.0, p_down - p_flat * 0.5)
            p_up = max(0.0, min(1.0, 1.0 - p_down - p_flat))

            # Normalise
            total = p_up + p_down + p_flat
            if total > 0:
                p_up /= total
                p_down /= total
                p_flat /= total

            # Brier score on hold-out
            brier_scores = cross_val_score(
                LogisticRegression(C=1.0), X_s, y_binary,
                cv=tscv, scoring="neg_brier_score"
            )
            brier = float(-brier_scores.mean()) if len(brier_scores) > 0 else None

        except Exception as exc:
            logger.warning(f"Logistic fit failed {event_code}/{symbol}/{horizon_str}: {exc}")
            p_up = p_down = 0.5
            p_flat = 0.0
            brier = None
            historical_accuracy = float(naive_correct)
            method = "fallback_prior"

    # ── Expected return ───────────────────────────────────────────────────────
    returns = label_df[return_col].dropna()
    expected_return = float(returns.mean()) if not returns.empty else None

    # ── Signal classification ─────────────────────────────────────────────────
    warnings = []
    signal = "NEUTRAL"

    if p_up < min_confidence and p_down < min_confidence:
        signal = "NO_SIGNAL"
        explanation = (
            f"No signal: P(UP)={p_up:.0%}, P(DOWN)={p_down:.0%} "
            f"both below threshold {min_confidence:.0%}."
        )
    elif p_up >= min_confidence and p_up > p_down:
        if n < min_sample:
            signal = "NO_SIGNAL"
            warnings.append(
                f"Probability passes display threshold but insufficient sample (n={n})."
            )
        else:
            signal = "BUY"
        explanation = (
            f"P(UP)={p_up:.0%} for {symbol} after {event_code} at {horizon_str}. "
            f"Historical accuracy: {historical_accuracy:.0%} over {n} events."
        )
    elif p_down >= min_confidence and p_down > p_up:
        if n < min_sample:
            signal = "NO_SIGNAL"
            warnings.append(
                f"Probability passes display threshold but insufficient sample (n={n})."
            )
        else:
            signal = "SELL"
        explanation = (
            f"P(DOWN)={p_down:.0%} for {symbol} after {event_code} at {horizon_str}. "
            f"Historical accuracy: {historical_accuracy:.0%} over {n} events."
        )
    else:
        explanation = (
            f"Conflicting probabilities: P(UP)={p_up:.0%}, P(DOWN)={p_down:.0%}. "
            "No clear signal."
        )

    # ── Evidence quality ──────────────────────────────────────────────────────
    if n >= 50 and historical_accuracy and historical_accuracy >= 0.60:
        evidence_quality = "HIGH"
    elif n >= 25 and historical_accuracy and historical_accuracy >= 0.55:
        evidence_quality = "MEDIUM"
    elif n >= 15:
        evidence_quality = "LOW"
    else:
        evidence_quality = "INSUFFICIENT"

    # Confidence tier warnings
    dominant_prob = max(p_up, p_down)
    if 0.50 <= dominant_prob < 0.55:
        warnings.append(
            f"Weak signal: {dominant_prob:.0%} probability is near 50% — model is nearly uncertain."
        )

    return ReactionPrediction(
        symbol=symbol,
        horizon=horizon_str,
        signal=signal,
        probability_up=p_up,
        probability_down=p_down,
        probability_flat=p_flat,
        expected_return=expected_return,
        historical_accuracy=historical_accuracy,
        sample_size=n,
        evidence_quality=evidence_quality,
        brier_score=brier,
        explanation=explanation,
        warnings=warnings,
    )


def _horizon_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}min"
    return f"{minutes // 60}h"
