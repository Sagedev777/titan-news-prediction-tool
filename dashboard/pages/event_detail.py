"""
Page 2: Event Detail

Full research card for a single event: estimate, interval, scenarios,
evidence bullets, comparable releases, pair signals, data warnings.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def render():
    st.title("📋 Event Detail")

    from events.models import EconomicEvent, ImpactLevel
    from forecasting.models import ForecastRun
    from dashboard.components.formatting import (
        to_eat, format_float, format_surprise, quality_badge
    )

    # ── Event selector ────────────────────────────────────────────────────────
    events = list(
        EconomicEvent.objects.filter(
            normalized_impact_level=ImpactLevel.HIGH,
            is_allowlisted=True,
            is_forecastable=True,
        ).order_by("country", "name")
    )

    if not events:
        st.warning(
            "No forecastable red-folder events in the database. "
            "Run `python manage.py bootstrap_events` and then ingest calendar data."
        )
        return

    event_options = {f"{e.country} — {e.name} ({e.code})": e for e in events}
    selected_label = st.selectbox("Select Event", list(event_options.keys()))
    selected_event = event_options[selected_label]

    # ── Load latest forecast run ──────────────────────────────────────────────
    run = (
        ForecastRun.objects.select_related("event", "economic_release")
        .prefetch_related("features", "instrument_forecasts")
        .filter(event=selected_event)
        .order_by("-run_time_utc")
        .first()
    )

    if not run:
        st.warning(
            f"No forecast run found for {selected_event.code}. "
            "Forecasts are generated automatically 2 hours before each release."
        )
        return

    # ── Header ────────────────────────────────────────────────────────────────
    release = run.economic_release
    st.markdown(f"## 🔴 {selected_event.name}")
    st.markdown(
        f"**Country:** {selected_event.country} | "
        f"**Currency:** {selected_event.currency} | "
        f"**Code:** `{selected_event.code}`"
    )

    if release:
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**Release time (EAT):** {to_eat(release.release_time_utc)}")
        with c2:
            st.info(f"**Period:** {release.period}")

    st.divider()

    # ── Forecast summary ──────────────────────────────────────────────────────
    st.subheader("Research Conclusion")

    fc1, fc2, fc3, fc4 = st.columns(4)
    consensus = float(release.consensus) if release and release.consensus else None
    with fc1:
        st.metric("Previous", format_float(float(release.previous) if release and release.previous else None))
    with fc2:
        st.metric("Consensus", format_float(consensus))
    with fc3:
        st.metric("Model Estimate", format_float(run.estimate))
    with fc4:
        surprise = run.estimated_surprise
        st.metric("Est. Surprise", format_surprise(surprise))

    # Probabilities
    p1, p2, p3 = st.columns(3)
    with p1:
        _prob_gauge("P(Above Consensus)", run.probability_above_consensus)
    with p2:
        _prob_gauge("P(Near Consensus)", run.probability_near_consensus)
    with p3:
        _prob_gauge("P(Below Consensus)", run.probability_below_consensus)

    # Bias and quality
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        st.info(f"**Bias:** {run.event_bias or 'N/A'}")
    with b2:
        st.info(f"**Data quality:** {quality_badge(run.data_quality_status)}")
    with b3:
        st.info(f"**Calibration:** {run.calibration_status}")
    with b4:
        st.info(f"**Comparable releases:** {run.comparable_releases_count}")

    # Prediction interval
    if run.lower_bound and run.upper_bound:
        st.markdown(
            f"**90% Prediction Interval:** "
            f"[{format_float(run.lower_bound)}, {format_float(run.upper_bound)}]"
        )

    st.divider()

    # ── Warnings ──────────────────────────────────────────────────────────────
    if run.warnings:
        st.subheader("⚠️ Warnings")
        for w in run.warnings:
            st.warning(w)

    # ── Evidence bullets ──────────────────────────────────────────────────────
    features_qs = list(run.features.filter(missing_flag=False).order_by("-contribution"))
    if features_qs:
        st.subheader("Main Evidence")
        for f in features_qs[:6]:
            icon = "🟢" if (f.contribution or 0) > 0 else "🔴"
            val_str = format_float(f.value, 4) if f.value is not None else "N/A"
            st.markdown(f"- {icon} **{f.feature_name}**: {val_str}")

    # Missing features
    missing = list(run.features.filter(missing_flag=True))
    if missing:
        with st.expander(f"⚠️ {len(missing)} Missing Feature(s)"):
            for f in missing:
                st.markdown(f"- `{f.feature_name}` — unavailable at forecast time")

    st.divider()

    # ── Pair signal table ─────────────────────────────────────────────────────
    st.subheader("Pair Signal Table")
    instruments = list(run.instrument_forecasts.order_by("-ranking_score"))

    if instruments:
        rows = []
        for inst in instruments:
            disp_p = inst.display_probability
            rows.append({
                "Rank": "",
                "Symbol": inst.symbol,
                "Signal": inst.signal,
                "Confidence": f"{disp_p:.0%}" if disp_p else "N/A",
                "P(Up)": f"{inst.probability_up:.0%}" if inst.probability_up else "N/A",
                "P(Down)": f"{inst.probability_down:.0%}" if inst.probability_down else "N/A",
                "P(Flat)": f"{inst.probability_flat:.0%}" if inst.probability_flat else "N/A",
                "Horizon": inst.horizon,
                "Accuracy": f"{inst.historical_accuracy:.0%}" if inst.historical_accuracy else "N/A",
                "Sample (n)": inst.sample_size,
                "Evidence": inst.evidence_quality,
                "Score": f"{inst.ranking_score:.3f}" if inst.ranking_score else "N/A",
            })

        df = pd.DataFrame(rows)
        df.index += 1
        df["Rank"] = df.index

        def colour_signal(val):
            if val == "BUY":
                return "color: #00ff88; font-weight:bold"
            if val == "SELL":
                return "color: #ff4444; font-weight:bold"
            if val == "NO_SIGNAL":
                return "color: #888888"
            return ""

        st.dataframe(
            df.style.applymap(colour_signal, subset=["Signal"]),
            use_container_width=True,
            height=400,
        )

        # Sample-size warnings
        low_sample = [i for i in instruments if i.sample_size < 25]
        if low_sample:
            st.warning(
                f"{len(low_sample)} instrument(s) have fewer than 25 comparable events. "
                "Probabilities pass the display threshold but have insufficient historical sample."
            )
    else:
        st.info("Instrument forecasts not yet generated for this run.")

    st.divider()

    # ── Scenarios ─────────────────────────────────────────────────────────────
    st.subheader("Scenario Analysis")
    if run.economic_release:
        from forecasting.scenarios import build_scenarios
        scenarios = build_scenarios(
            event_code=selected_event.code,
            estimate=run.estimate,
            consensus=consensus,
            p_above=run.probability_above_consensus,
            p_near=run.probability_near_consensus,
            p_below=run.probability_below_consensus,
        )
        for s in scenarios:
            colour = {"above_consensus": "🟢", "near_consensus": "🟡", "below_consensus": "🔴"}.get(s.name, "⚪")
            with st.expander(f"{colour} {s.name.replace('_', ' ').title()} — P={s.probability:.0%}"):
                st.markdown(f"**Condition:** {s.condition}")
                st.markdown(f"**Currency direction:** {s.currency_direction}")
                st.markdown(f"**Rate reaction:** {s.rate_reaction}")
                if s.pricing_note:
                    st.info(f"**Note:** {s.pricing_note}")
                if s.invalidating_conditions:
                    st.markdown("**Invalidating conditions:**")
                    for c in s.invalidating_conditions:
                        st.markdown(f"  - {c}")

    # ── Metadata ──────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        f"Model: {run.model_name} v{run.model_version} | "
        f"Run time: {to_eat(run.run_time_utc)} | "
        f"Data cutoff: {to_eat(run.data_cutoff_time_utc)} | "
        f"Sources: {', '.join(run.data_sources_used[:5])}"
    )


def _prob_gauge(label: str, value: float | None):
    if value is None:
        st.metric(label, "N/A")
        return
    pct = int(value * 100)
    colour = "normal" if pct >= 55 else "off"
    st.metric(label, f"{pct}%")
