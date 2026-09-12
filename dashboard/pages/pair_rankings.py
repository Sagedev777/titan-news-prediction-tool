"""
Page 3: Pair Rankings

All instrument signals across all recent forecast runs, ranked by
composite score.  Filterable by minimum confidence, horizon, signal type.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd


def render():
    st.title("📊 Pair Rankings")
    st.caption(
        "Signals ranked by composite evidence score. "
        "Always verify signal sample size and calibration before acting."
    )

    from market_reaction.models import InstrumentForecast
    from events.models import ImpactLevel
    from django.conf import settings

    # ── Filters ───────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        min_prob = st.slider(
            "Min confidence (%)",
            min_value=50, max_value=80, value=50,
            help="Show signals where the primary probability is at or above this threshold.",
        )
    with col2:
        horizon_filter = st.multiselect(
            "Horizons", ["5min", "15min", "1h", "4h"],
            default=["15min", "1h"]
        )
    with col3:
        signal_filter = st.multiselect(
            "Signal types", ["BUY", "SELL", "NEUTRAL"],
            default=["BUY", "SELL"]
        )
    with col4:
        min_sample = st.number_input("Min sample size", min_value=0, value=25)

    # ── Load data ─────────────────────────────────────────────────────────────
    qs = (
        InstrumentForecast.objects.select_related(
            "forecast_run__event", "forecast_run__economic_release"
        )
        .filter(
            forecast_run__event__normalized_impact_level=ImpactLevel.HIGH,
            forecast_run__event__is_allowlisted=True,
        )
        .exclude(signal="NO_SIGNAL")
        .order_by("-ranking_score")[:500]
    )

    instruments = list(qs)

    if not instruments:
        st.info("No instrument signals found. Run forecasts first.")
        return

    # ── Build DataFrame ───────────────────────────────────────────────────────
    rows = []
    for inst in instruments:
        disp_p = inst.display_probability
        if disp_p is None:
            continue

        # Apply filters
        if disp_p * 100 < min_prob:
            continue
        if horizon_filter and inst.horizon not in horizon_filter:
            continue
        if signal_filter and inst.signal not in signal_filter:
            continue
        if inst.sample_size < min_sample:
            continue

        event = inst.forecast_run.event
        rows.append({
            "Event": event.code,
            "Currency": event.currency,
            "Symbol": inst.symbol,
            "Signal": inst.signal,
            "Confidence": disp_p,
            "P(Up)": inst.probability_up,
            "P(Down)": inst.probability_down,
            "P(Flat)": inst.probability_flat,
            "Horizon": inst.horizon,
            "Exp. Return": inst.expected_return,
            "Hist. Accuracy": inst.historical_accuracy,
            "Sample n": inst.sample_size,
            "Evidence": inst.evidence_quality,
            "Score": inst.ranking_score,
            "Explanation": inst.explanation[:80] + "…" if inst.explanation and len(inst.explanation) > 80 else inst.explanation,
            "Warnings": " | ".join(inst.warnings[:2]) if inst.warnings else "",
        })

    if not rows:
        st.warning(
            f"No signals pass the current filters. "
            f"Try reducing min confidence ({min_prob}%) or min sample ({min_sample})."
        )
        return

    df = pd.DataFrame(rows).sort_values("Score", ascending=False)
    df.index = range(1, len(df) + 1)

    # Format display columns
    df["Confidence"] = df["Confidence"].apply(lambda x: f"{x:.0%}" if x else "N/A")
    df["P(Up)"] = df["P(Up)"].apply(lambda x: f"{x:.0%}" if x else "N/A")
    df["P(Down)"] = df["P(Down)"].apply(lambda x: f"{x:.0%}" if x else "N/A")
    df["P(Flat)"] = df["P(Flat)"].apply(lambda x: f"{x:.0%}" if x else "N/A")
    df["Hist. Accuracy"] = df["Hist. Accuracy"].apply(lambda x: f"{x:.0%}" if x else "N/A")
    df["Score"] = df["Score"].apply(lambda x: f"{x:.3f}" if x else "N/A")
    df["Exp. Return"] = df["Exp. Return"].apply(lambda x: f"{x:+.4f}" if x else "N/A")

    # Signal colouring
    def colour_signal(val):
        if val == "BUY":
            return "background-color: #0a3d1f; color: #00ff88; font-weight:bold"
        if val == "SELL":
            return "background-color: #3d0a0a; color: #ff6666; font-weight:bold"
        return ""

    def colour_evidence(val):
        colours = {"HIGH": "#00ff88", "MEDIUM": "#ffaa00", "LOW": "#ff6666", "INSUFFICIENT": "#888888"}
        c = colours.get(val, "")
        return f"color: {c}" if c else ""

    display_cols = [
        "Event", "Symbol", "Signal", "Confidence", "P(Up)", "P(Down)",
        "P(Flat)", "Horizon", "Exp. Return", "Hist. Accuracy", "Sample n",
        "Evidence", "Score"
    ]

    st.markdown(f"**{len(df)} signal(s) matching filters**")

    st.dataframe(
        df[display_cols].style
        .applymap(colour_signal, subset=["Signal"])
        .applymap(colour_evidence, subset=["Evidence"]),
        use_container_width=True,
        height=600,
    )

    # ── Explanations for top 5 ────────────────────────────────────────────────
    st.divider()
    st.subheader("Top Signal Explanations")
    for _, row in df.head(5).iterrows():
        inst_obj = next(
            (i for i in instruments
             if i.symbol == row["Symbol"]
             and i.forecast_run.event.code == row["Event"]),
            None,
        )
        if inst_obj:
            with st.expander(f"{row['Symbol']} — {row['Signal']} ({row['Event']})"):
                st.write(inst_obj.explanation)
                if inst_obj.warnings:
                    for w in inst_obj.warnings:
                        st.warning(w)

    # ── Sample-size disclaimer ────────────────────────────────────────────────
    low_sample_count = len([r for r in rows if isinstance(r.get("Sample n"), int) and r["Sample n"] < 25])
    if low_sample_count > 0:
        st.warning(
            f"{low_sample_count} signal(s) have fewer than 25 comparable historical events. "
            "Probability passes display threshold but has insufficient historical sample."
        )
