"""
Page 6: Excluded Events — Diagnostics

Clearly labelled: these events are NOT used by the forecasting system.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd


def render():
    st.title("🗑️ Excluded Events — Diagnostics")
    st.error(
        "⛔ EXCLUDED NON-RED EVENTS — NOT USED BY THE FORECASTING SYSTEM.\n\n"
        "These events were filtered out because they are NOT high-impact "
        "or NOT in the allowlist. They are shown here for diagnostics only."
    )

    from events.models import EconomicEvent, ImpactLevel

    qs = EconomicEvent.objects.exclude(
        normalized_impact_level=ImpactLevel.HIGH,
        is_allowlisted=True,
    ).order_by("normalized_impact_level", "country", "code")

    total = qs.count()
    st.caption(f"Total excluded events: {total}")

    if total == 0:
        st.info("No excluded events found in the database.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        impact_filter = st.multiselect(
            "Filter by impact",
            ["HIGH (non-allowlisted)", "MEDIUM", "LOW", "UNKNOWN"],
            default=["MEDIUM", "LOW", "UNKNOWN"],
        )
    with col2:
        country_filter = st.text_input("Filter by country (partial match)")

    # ── Build table ───────────────────────────────────────────────────────────
    events = list(qs)
    rows = []
    for e in events:
        # Exclusion reason
        if e.normalized_impact_level == ImpactLevel.HIGH and not e.is_allowlisted:
            reason = "High impact but not in allowlist"
        elif e.normalized_impact_level == "MEDIUM":
            reason = "Medium impact — not red folder"
        elif e.normalized_impact_level == "LOW":
            reason = "Low impact — not red folder"
        elif e.normalized_impact_level == "UNKNOWN":
            reason = "Unknown impact — cannot classify"
        else:
            reason = "Does not meet red-folder criteria"

        rows.append({
            "Code": e.code,
            "Event": e.name,
            "Country": e.country,
            "Currency": e.currency,
            "Provider Impact": e.provider_impact_level,
            "Normalised Impact": e.normalized_impact_level,
            "Allowlisted": "✅" if e.is_allowlisted else "❌",
            "Exclusion Reason": reason,
            "Provider": e.provider,
            "Last Updated": e.updated_at.strftime("%Y-%m-%d") if e.updated_at else "",
        })

    df = pd.DataFrame(rows)

    # Apply filters
    impact_map = {
        "HIGH (non-allowlisted)": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
        "UNKNOWN": "UNKNOWN",
    }
    selected_impacts = [impact_map.get(i, i) for i in impact_filter]
    if selected_impacts:
        df = df[df["Normalised Impact"].isin(selected_impacts)]

    if country_filter:
        df = df[df["Country"].str.contains(country_filter, case=False, na=False)]

    st.markdown(f"**{len(df)} events shown (after filters)**")

    def colour_impact(val):
        if val == "HIGH":
            return "color: #ff4444"
        if val == "MEDIUM":
            return "color: #ffaa00"
        if val == "LOW":
            return "color: #888888"
        return "color: #444444"

    st.dataframe(
        df.style.applymap(colour_impact, subset=["Normalised Impact"]),
        use_container_width=True,
        height=600,
    )

    st.divider()
    st.info(
        "To add an event to the forecasting pipeline, it must:\n"
        "1. Be classified as HIGH impact by the calendar provider.\n"
        "2. Have its code in `ALLOWLISTED_EVENT_CODES` in `events/models.py`.\n"
        "3. Have an event-specific model implemented in `forecasting/event_models.py`.\n"
        "4. Pass the `is_forecastable=True` gate after model validation."
    )
