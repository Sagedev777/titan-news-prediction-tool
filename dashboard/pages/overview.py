"""
Page 1: Red-Folder Overview

Shows all upcoming HIGH-impact allowlisted events with their
model estimates, consensus, bias, and quality indicators.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from django.utils import timezone


def render():
    st.title("🔴 Red Folder — Upcoming Events")
    st.caption(
        "Only HIGH-impact allowlisted events are shown here. "
        "All other events are excluded from the forecasting system."
    )

    from events.services import get_upcoming_red_folder_releases
    from forecasting.models import ForecastRun
    from dashboard.components.formatting import (
        to_eat, countdown, signal_badge, quality_badge, format_float, format_surprise
    )

    # ── Controls ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        hours_ahead = st.slider("Hours ahead", min_value=12, max_value=168, value=48, step=12)
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (60s)", value=False)
    with col3:
        if st.button("🔄 Refresh"):
            st.rerun()

    if auto_refresh:
        import time
        time.sleep(60)
        st.rerun()

    # ── Fetch data ────────────────────────────────────────────────────────────
    releases = get_upcoming_red_folder_releases(hours_ahead=hours_ahead)

    if not releases:
        st.info(
            f"No upcoming red-folder events in the next {hours_ahead} hours. "
            "Check the calendar again closer to the next release."
        )
        _show_no_data_help()
        return

    st.success(f"Found {len(releases)} upcoming red-folder event(s).")

    # ── Event cards ────────────────────────────────────────────────────────────
    for release in releases:
        event = release.event
        run = (
            ForecastRun.objects.filter(economic_release=release)
            .order_by("-run_time_utc")
            .first()
        )

        _render_event_card(release, event, run)
        st.divider()


def _render_event_card(release, event, run):
    from dashboard.components.formatting import (
        to_eat, countdown, quality_badge, format_float, format_surprise
    )

    # Header
    col_title, col_time, col_countdown = st.columns([3, 2, 1])
    with col_title:
        st.markdown(f"### 🔴 {event.name}")
        st.markdown(f"**{event.country}** | **{event.currency}** | `{event.code}`")
    with col_time:
        st.markdown(f"**Release (EAT):** {to_eat(release.release_time_utc)}")
        st.markdown(f"**Release (UTC):** {release.release_time_utc.strftime('%Y-%m-%d %H:%M UTC') if release.release_time_utc else '—'}")
    with col_countdown:
        st.metric("Countdown", countdown(release.release_time_utc))

    # Data row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Previous", format_float(float(release.previous) if release.previous else None, 4))
    with col2:
        st.metric("Consensus", format_float(float(release.consensus) if release.consensus else None, 4))

    if run:
        with col3:
            st.metric(
                "Model Estimate",
                format_float(run.estimate, 4),
                help="Point estimate from the event-specific model.",
            )
        with col4:
            range_str = (
                f"[{format_float(run.lower_bound, 3)}, {format_float(run.upper_bound, 3)}]"
                if run.lower_bound and run.upper_bound else "N/A"
            )
            st.metric("90% Range", range_str)
        with col5:
            bias_color = "🟢" if "bullish" in (run.event_bias or "").lower() else ("🔴" if "bearish" in (run.event_bias or "").lower() else "🟡")
            st.metric("Bias", f"{bias_color} {run.event_bias or 'N/A'}")

        # Probabilities
        st.markdown("**Event Probabilities:**")
        pcol1, pcol2, pcol3 = st.columns(3)
        with pcol1:
            p_above = run.probability_above_consensus
            st.metric(
                "P(Above Consensus)",
                f"{p_above:.0%}" if p_above else "N/A",
                help="Calibrated probability of outcome above consensus.",
            )
        with pcol2:
            p_near = run.probability_near_consensus
            st.metric("P(Near Consensus)", f"{p_near:.0%}" if p_near else "N/A")
        with pcol3:
            p_below = run.probability_below_consensus
            st.metric("P(Below Consensus)", f"{p_below:.0%}" if p_below else "N/A")

        # Metadata
        mcol1, mcol2, mcol3 = st.columns(3)
        with mcol1:
            st.caption(f"Data quality: {quality_badge(run.data_quality_status)}")
        with mcol2:
            st.caption(f"Calibration: {run.calibration_status}")
        with mcol3:
            st.caption(
                f"Last updated: {to_eat(run.run_time_utc)} | "
                f"Comparable releases: {run.comparable_releases_count}"
            )

        # Warnings
        if run.warnings:
            with st.expander(f"⚠️ {len(run.warnings)} Warning(s)"):
                for w in run.warnings:
                    st.warning(w)

        # Top instruments
        instruments = list(
            run.instrument_forecasts.exclude(signal="NO_SIGNAL")
            .order_by("-ranking_score")[:5]
        )
        if instruments:
            st.markdown("**Top Instrument Signals:**")
            for i, inst in enumerate(instruments, 1):
                disp_prob = inst.display_probability
                signal_str = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}.get(inst.signal, "⚪")
                prob_str = f"{disp_prob:.0%}" if disp_prob else ""
                sample_warn = (
                    " ⚠️ low sample"
                    if inst.sample_size < 25 else ""
                )
                st.markdown(
                    f"{i}. **{inst.symbol}** — {signal_str} {inst.signal} "
                    f"{prob_str} | {inst.horizon} | n={inst.sample_size}{sample_warn}"
                )

    else:
        with col3:
            st.metric("Model Estimate", "Pending")
        st.info(
            "Forecast not yet available for this event. "
            "Forecasts are generated automatically every 2 hours. "
            "Check data health if this persists."
        )


def _show_no_data_help():
    with st.expander("Why are no events showing?"):
        st.markdown("""
        **Possible reasons:**

        1. **No calendar data ingested** — Run `python manage.py ingest_calendar` or
           trigger the Celery beat task.
        2. **API key not configured** — Check `TRADING_ECONOMICS_API_KEY` in `.env`.
        3. **No upcoming events in the selected window** — Try increasing hours ahead.
        4. **Events are not red-folder** — Only HIGH-impact allowlisted events appear here.

        Check the **Data Health** page for provider status.
        """)
