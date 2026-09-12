"""
Page 5: Data Health

Provider status, stale data warnings, missing series, failed jobs.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from django.utils import timezone


def render():
    st.title("🩺 Data Health")

    col1, col2 = st.columns([4, 1])
    with col1:
        st.caption("Live status of all data providers and series freshness.")
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    # ── Provider health checks ────────────────────────────────────────────────
    with st.spinner("Running provider health checks…"):
        from data_sources.health import run_all_health_checks, check_data_staleness
        health = run_all_health_checks()
        staleness = check_data_staleness()

    overall = health.get("overall_status", "unknown")
    status_emoji = {"ok": "✅", "degraded": "⚠️", "down": "🔴"}.get(overall, "❓")
    st.metric("Overall Status", f"{status_emoji} {overall.upper()}")

    st.divider()

    # ── Provider status table ─────────────────────────────────────────────────
    st.subheader("Provider Status")
    providers = health.get("providers", [])
    if providers:
        rows = []
        for p in providers:
            rows.append({
                "Provider": p.get("provider", "?"),
                "Status": p.get("status", "unknown"),
                "Checked At": p.get("checked_at", ""),
                "Error": p.get("error", "") or p.get("api_usage", ""),
            })
        df = pd.DataFrame(rows)

        def colour_status(val):
            if val == "ok":
                return "color: #00ff88"
            if val == "error":
                return "color: #ff4444"
            if val == "not_configured":
                return "color: #ffaa00"
            return ""

        st.dataframe(
            df.style.applymap(colour_status, subset=["Status"]),
            use_container_width=True,
        )
    else:
        st.warning("No provider health data available.")

    st.divider()

    # ── Staleness warnings ────────────────────────────────────────────────────
    st.subheader("Data Freshness")
    warnings = staleness.get("warnings", [])
    if warnings:
        st.warning(f"{len(warnings)} freshness warning(s) detected.")
        for w in warnings:
            st.markdown(f"- ⚠️ **{w.get('type', '')}** `{w.get('series_id') or w.get('symbol', '')}`: {w.get('message', '')}")
    else:
        st.success("All monitored series are within acceptable freshness limits.")

    st.divider()

    # ── Open data quality issues ──────────────────────────────────────────────
    st.subheader("Open Data Quality Issues")
    from events.models import DataQualityIssue
    issues = list(
        DataQualityIssue.objects.filter(resolved=False)
        .order_by("-detected_at")[:50]
    )

    if issues:
        rows = [
            {
                "Provider": i.provider,
                "Series": i.series_id,
                "Type": i.issue_type,
                "Severity": i.severity,
                "Message": i.message[:80],
                "Detected": i.detected_at.strftime("%Y-%m-%d %H:%M UTC"),
            }
            for i in issues
        ]
        df = pd.DataFrame(rows)
        def colour_sev(val):
            if val == "CRITICAL":
                return "color: #ff2222; font-weight:bold"
            if val == "WARNING":
                return "color: #ffaa00"
            return ""
        st.dataframe(
            df.style.applymap(colour_sev, subset=["Severity"]),
            use_container_width=True,
        )
    else:
        st.success("No open data quality issues.")

    st.divider()

    # ── Series observation counts ─────────────────────────────────────────────
    st.subheader("Macro Series Observation Counts")
    from macro_data.models import DataObservation
    from django.db.models import Count, Max

    stats = list(
        DataObservation.objects.values("provider", "series_id")
        .annotate(count=Count("id"), latest=Max("observation_date"))
        .order_by("provider", "series_id")
    )

    if stats:
        df = pd.DataFrame(stats)
        df["latest"] = pd.to_datetime(df["latest"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True, height=400)
    else:
        st.info("No macro data observations found. Run ingestion tasks.")

    st.divider()

    # ── Recent provider request log ───────────────────────────────────────────
    st.subheader("Recent Provider Requests (last 50)")
    from events.models import ProviderRequestLog
    logs = list(
        ProviderRequestLog.objects.order_by("-request_time_utc")[:50]
    )
    if logs:
        rows = [
            {
                "Provider": l.provider,
                "Endpoint": l.endpoint[:60],
                "Time (UTC)": l.request_time_utc.strftime("%Y-%m-%d %H:%M"),
                "Status": l.http_status,
                "Latency (ms)": l.latency_ms,
                "Success": "✅" if l.success else "❌",
            }
            for l in logs
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No provider request logs found.")
