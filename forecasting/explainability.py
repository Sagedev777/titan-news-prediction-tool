"""
Model explainability — converts feature importances into human-readable text.

Produces 'main evidence' bullet points shown on the event card.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("forecasting")


def generate_evidence_bullets(
    feature_importances: dict[str, float],
    feature_values: dict[str, float | None],
    event_code: str,
    top_n: int = 5,
) -> list[str]:
    """
    Generate human-readable evidence bullets from feature importances.

    Parameters
    ----------
    feature_importances : {feature_name: importance_score}
    feature_values : {feature_name: latest_value}
    event_code : e.g. 'US_CPI'
    top_n : Number of top features to explain.

    Returns
    -------
    List of strings, each a plain-English evidence bullet.
    """
    if not feature_importances:
        return ["Insufficient feature data for detailed explanation."]

    sorted_features = sorted(
        feature_importances.items(), key=lambda x: abs(x[1]), reverse=True
    )[:top_n]

    bullets = []
    for feature_name, importance in sorted_features:
        value = feature_values.get(feature_name)
        description = _describe_feature(feature_name, value, importance)
        if description:
            bullets.append(description)

    if not bullets:
        bullets.append("Model evidence available — see feature table for details.")

    return bullets


def _describe_feature(name: str, value: float | None, importance: float) -> str:
    """Translate a feature name + value into a plain-English sentence."""
    direction = "positive" if importance > 0 else "negative"
    value_str = f"{value:.3f}" if value is not None else "N/A"

    descriptions = {
        "cpi_headline_sa_mom": (
            f"Headline CPI MoM ({value_str}): "
            + ("above recent trend — supports higher estimate."
               if importance > 0 else "below recent trend — supports lower estimate.")
        ),
        "cpi_core_sa_mom": (
            f"Core CPI MoM ({value_str}): "
            + ("elevated — persistent underlying inflation."
               if importance > 0 else "cooling — underlying inflation slowing.")
        ),
        "oil_wti_mom": (
            f"WTI oil MoM change ({value_str}): "
            + ("rising oil feeds through to energy CPI."
               if importance > 0 else "falling oil will weigh on energy CPI.")
        ),
        "cpi_gasoline_sa_mom": (
            f"Gasoline prices MoM ({value_str}): "
            + ("up — adds to headline CPI." if importance > 0 else "down — reduces headline CPI.")
        ),
        "cpi_shelter_sa_mom": (
            f"Shelter CPI MoM ({value_str}): "
            + ("still elevated — key driver of core persistence."
               if importance > 0 else "easing — key driver of core disinflation.")
        ),
        "adp_employment": (
            f"ADP employment ({value_str}K): "
            + ("above average — labour market still strong."
               if importance > 0 else "below average — labour market cooling.")
            + " Note: ADP is a leading indicator, not a direct NFP proxy."
        ),
        "jolts_openings": (
            f"JOLTS job openings ({value_str}K): "
            + ("elevated — demand for labour remains high."
               if importance > 0 else "falling — labour demand moderating.")
        ),
        "nfci": (
            f"Financial conditions index ({value_str}): "
            + ("accommodative — supportive of growth and hiring."
               if importance > 0 else "tight — may weigh on employment.")
        ),
        "consensus": (
            f"Analyst consensus ({value_str}): "
            "The consensus forecast is a key reference level for this model."
        ),
        "cleveland_headline_mom": (
            f"Cleveland Fed nowcast ({value_str}%): "
            "External model estimate used as one input (not the forecast answer)."
        ),
    }

    if name in descriptions:
        return descriptions[name]

    # Generic fallback
    return (
        f"{name.replace('_', ' ').title()} ({value_str}): "
        f"{'Contributes positively' if importance > 0 else 'Contributes negatively'} "
        f"to the estimate (importance: {abs(importance):.3f})."
    )
