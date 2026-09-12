"""
Scenario engine — generates three scenarios for every red-folder event.

Scenarios:
1. Below consensus
2. Near consensus
3. Above consensus

Each scenario includes:
- Numerical condition
- Estimated probability
- Currency and pair reactions
- Interest-rate reaction
- Invalidating conditions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("forecasting")


@dataclass
class Scenario:
    name: str
    description: str
    condition: str        # e.g. "CPI < consensus - 0.1"
    probability: float    # 0.0 to 1.0
    currency_direction: str    # "bullish USD" / "bearish USD" / "neutral" / "depends"
    pair_reactions: dict[str, str]  # symbol → "BUY" / "SELL" / "NEUTRAL" / "UNCERTAIN"
    rate_reaction: str    # e.g. "US 2Y lower", "US 10Y higher"
    invalidating_conditions: list[str] = field(default_factory=list)
    pricing_note: str = ""
    key_pairs: list[str] = field(default_factory=list)


def build_us_cpi_scenarios(
    estimate: float | None,
    consensus: float | None,
    p_above: float | None,
    p_near: float | None,
    p_below: float | None,
    near_band: float = 0.05,
) -> list[Scenario]:
    """
    Build three US CPI scenarios.

    The scenario engine does not assume every positive economic result
    produces a positive USD reaction.  It considers prior pricing.
    """
    p_ab = p_above or 0.33
    p_nr = p_near or 0.33
    p_bw = p_below or 0.34

    band_str = f"{near_band:.2f}pp"

    above = Scenario(
        name="above_consensus",
        description=f"CPI prints above consensus by more than {band_str}",
        condition=f"actual > consensus + {band_str}",
        probability=p_ab,
        currency_direction="bullish USD",
        pair_reactions={
            "EURUSD": "SELL",
            "GBPUSD": "SELL",
            "USDJPY": "BUY",
            "USDCHF": "BUY",
            "USDCAD": "UNCERTAIN",  # BoC also sensitive to inflation
            "AUDUSD": "SELL",
            "NZDUSD": "SELL",
            "XAUUSD": "SELL",      # hot CPI → higher rates → bearish gold
            "DXY": "BUY",
            "US02Y": "HIGHER",
            "US10Y": "HIGHER",
        },
        rate_reaction="US 2Y yield higher. US 10Y yield higher. Rate cut expectations reduced.",
        invalidating_conditions=[
            "Fed has already priced in very high rates — limited room to move higher.",
            "USD is heavily long-positioned — some 'buy the rumor sell the fact' risk.",
            "Core CPI below consensus even if headline is above.",
        ],
        pricing_note=(
            "Check market-implied rate expectations before the release. "
            "If markets already price 3 rate hikes, an above-consensus print "
            "may not move rates further."
        ),
    )

    near = Scenario(
        name="near_consensus",
        description=f"CPI within {band_str} of consensus",
        condition=f"abs(actual - consensus) <= {band_str}",
        probability=p_nr,
        currency_direction="depends",
        pair_reactions={
            "EURUSD": "NEUTRAL",
            "GBPUSD": "NEUTRAL",
            "USDJPY": "NEUTRAL",
            "USDCHF": "NEUTRAL",
            "USDCAD": "NEUTRAL",
            "AUDUSD": "NEUTRAL",
            "NZDUSD": "NEUTRAL",
            "XAUUSD": "NEUTRAL",
            "DXY": "NEUTRAL",
            "US02Y": "UNCHANGED",
            "US10Y": "UNCHANGED",
        },
        rate_reaction="Limited rate reaction expected. Focus shifts to core components and revisions.",
        invalidating_conditions=[
            "Shelter or core components surprise materially.",
            "Previous revision changes the picture.",
        ],
        pricing_note=(
            "Near-consensus print: reaction depends on core details and revisions. "
            "Initial move may be choppy."
        ),
    )

    below = Scenario(
        name="below_consensus",
        description=f"CPI prints below consensus by more than {band_str}",
        condition=f"actual < consensus - {band_str}",
        probability=p_bw,
        currency_direction="bearish USD",
        pair_reactions={
            "EURUSD": "BUY",
            "GBPUSD": "BUY",
            "USDJPY": "SELL",
            "USDCHF": "SELL",
            "USDCAD": "UNCERTAIN",
            "AUDUSD": "BUY",
            "NZDUSD": "BUY",
            "XAUUSD": "BUY",      # cooler CPI → rate cut hopes → bullish gold
            "DXY": "SELL",
            "US02Y": "LOWER",
            "US10Y": "LOWER",
        },
        rate_reaction="US 2Y yield lower. US 10Y yield lower. Rate cut probability increases.",
        invalidating_conditions=[
            "Fed has signalled no rate cuts regardless of inflation path.",
            "Energy prices artificially depressing headline but core is still high.",
        ],
        pricing_note=(
            "Cooler CPI is generally gold-positive if it raises rate-cut expectations. "
            "Confirm the rate path before sizing any trade."
        ),
    )

    return [above, near, below]


def build_us_nfp_scenarios(
    estimate: float | None,
    consensus: float | None,
    p_above: float | None,
    p_near: float | None,
    p_below: float | None,
    near_band: float = 25.0,
) -> list[Scenario]:
    """Build three US NFP scenarios."""
    p_ab = p_above or 0.33
    p_nr = p_near or 0.33
    p_bw = p_below or 0.34
    band_str = f"{int(near_band)}K"

    above = Scenario(
        name="above_consensus",
        description=f"NFP > consensus + {band_str}",
        condition=f"actual > consensus + {band_str}",
        probability=p_ab,
        currency_direction="bullish USD",
        pair_reactions={
            "EURUSD": "SELL",
            "GBPUSD": "SELL",
            "USDJPY": "BUY",
            "USDCHF": "BUY",
            "USDCAD": "UNCERTAIN",
            "AUDUSD": "SELL",
            "NZDUSD": "SELL",
            "XAUUSD": "SELL",
            "DXY": "BUY",
            "US02Y": "HIGHER",
            "US10Y": "HIGHER",
        },
        rate_reaction="Strong payrolls reduce rate cut probability. Yields higher.",
        invalidating_conditions=[
            "Unemployment rate rises alongside strong payrolls.",
            "Average hourly earnings disappoint — less inflationary.",
            "Prior month revised sharply lower.",
        ],
        pricing_note="Watch the unemployment rate and AHE alongside the headline number.",
    )

    near = Scenario(
        name="near_consensus",
        description=f"NFP within {band_str} of consensus",
        condition=f"abs(actual - consensus) <= {band_str}",
        probability=p_nr,
        currency_direction="depends",
        pair_reactions={k: "NEUTRAL" for k in ["EURUSD", "GBPUSD", "USDJPY", "USDCHF",
                                                 "USDCAD", "AUDUSD", "NZDUSD", "XAUUSD"]},
        rate_reaction="Limited reaction. Focus on AHE, participation rate, and revisions.",
        invalidating_conditions=["AHE or unemployment rate materially surprise."],
        pricing_note="Near-consensus NFP: detail matters more than headline.",
    )

    below = Scenario(
        name="below_consensus",
        description=f"NFP < consensus - {band_str}",
        condition=f"actual < consensus - {band_str}",
        probability=p_bw,
        currency_direction="bearish USD",
        pair_reactions={
            "EURUSD": "BUY",
            "GBPUSD": "BUY",
            "USDJPY": "SELL",
            "USDCHF": "SELL",
            "USDCAD": "UNCERTAIN",
            "AUDUSD": "BUY",
            "NZDUSD": "BUY",
            "XAUUSD": "BUY",
            "DXY": "SELL",
            "US02Y": "LOWER",
            "US10Y": "LOWER",
        },
        rate_reaction="Weak payrolls raise rate cut probability. Yields lower.",
        invalidating_conditions=[
            "Unemployment rate falls despite weak payrolls.",
            "AHE accelerates — wages still inflationary even with weak jobs.",
        ],
        pricing_note="Weak NFP is generally gold-positive via rate-cut expectations.",
    )

    return [above, near, below]


SCENARIO_BUILDERS = {
    "US_CPI": build_us_cpi_scenarios,
    "US_CORE_CPI": build_us_cpi_scenarios,
    "US_NFP": build_us_nfp_scenarios,
    "US_UNEMPLOYMENT_RATE": build_us_nfp_scenarios,
    "US_AVERAGE_HOURLY_EARNINGS": build_us_nfp_scenarios,
}


def build_scenarios(
    event_code: str,
    estimate: float | None,
    consensus: float | None,
    p_above: float | None,
    p_near: float | None,
    p_below: float | None,
    near_band: float = 0.05,
) -> list[Scenario]:
    """Build scenarios for any supported event code."""
    builder = SCENARIO_BUILDERS.get(event_code)
    if builder is None:
        return []
    return builder(
        estimate=estimate,
        consensus=consensus,
        p_above=p_above,
        p_near=p_near,
        p_below=p_below,
        near_band=near_band,
    )
