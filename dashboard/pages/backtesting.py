"""
Page 4: Backtesting

Historical performance of the forecasting models.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def render():
    st.title("🔬 Backtesting")
    st.caption(
        "All backtests use strict point-in-time data rules. "
        "No future data, no revised values in historical simulations."
    )

    from backtesting.models import BacktestRun
    from backtesting.reports import generate_backtest_report
    from forecasting.event_models import EVENT_MODEL_REGISTRY

    # ── Run new backtest ──────────────────────────────────────────────────────
    with st.expander("▶️ Run New Backtest"):
        col1, col2, col3 = st.columns(3)
        with col1:
            event_code = st.selectbox(
                "Event code",
                list(EVENT_MODEL_REGISTRY.keys()),
            )
        with col2:
            start_date = st.date_input("Start date", value=None)
        with col3:
            end_date = st.date_input("End date", value=None)

        strict_pit = st.checkbox("Strict point-in-time (recommended)", value=True)

        if st.button("Run Backtest"):
            if not start_date or not end_date:
                st.error("Please select start and end dates.")
            else:
                with st.spinner("Running backtest (this may take a few minutes)…"):
                    from backtesting.runner import run_backtest
                    result = run_backtest(
                        event_code=event_code,
                        start_date=start_date,
                        end_date=end_date,
                        strict_pit=strict_pit,
                    )
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(
                        f"Backtest complete. "
                        f"MAE: {result['summary'].get('mae', 'N/A')}"
                    )

    st.divider()

    # ── Existing backtest runs ────────────────────────────────────────────────
    runs = list(BacktestRun.objects.filter(status="completed").order_by("-created_at"))

    if not runs:
        st.info("No completed backtest runs found. Run a backtest above.")
        return

    run_labels = {f"{r.name} ({r.event_code}, {r.start_date}–{r.end_date})": r for r in runs}
    selected_label = st.selectbox("Select backtest run", list(run_labels.keys()))
    selected_run = run_labels[selected_label]

    # ── Display report ────────────────────────────────────────────────────────
    report = generate_backtest_report(selected_run)

    st.subheader(f"Results: {selected_run.name}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"**Event:** {selected_run.event_code}")
        st.info(f"**Model:** {selected_run.model_version}")
    with col2:
        st.info(f"**Date range:** {selected_run.start_date} → {selected_run.end_date}")
        st.info(f"**Data policy:** {selected_run.data_vintage_policy}")
    with col3:
        st.info(f"**Releases:** {report.get('n_results', 0)}")
        st.info(f"**Status:** {selected_run.status}")

    # Summary metrics
    metrics = report.get("summary_metrics", {})
    st.subheader("Performance Metrics")

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("MAE", f"{metrics.get('mae', 'N/A'):.4f}" if isinstance(metrics.get('mae'), float) else "N/A")
    with m2:
        st.metric("RMSE", f"{metrics.get('rmse', 'N/A'):.4f}" if isinstance(metrics.get('rmse'), float) else "N/A")
    with m3:
        st.metric("Bias", f"{metrics.get('bias', 'N/A'):+.4f}" if isinstance(metrics.get('bias'), float) else "N/A")
    with m4:
        cov = metrics.get("interval_coverage_90pct")
        st.metric("90% PI Coverage", f"{cov:.0%}" if isinstance(cov, float) else "N/A",
                  help="Expected ~90% if intervals are properly calibrated.")
    with m5:
        acc = metrics.get("class_accuracy_above_near_below")
        st.metric("Direction Accuracy", f"{acc:.0%}" if isinstance(acc, float) else "N/A")

    # Calibration
    cal = report.get("calibration", {})
    st.subheader("Calibration")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        st.metric("Brier Score", f"{cal.get('brier_score', 'N/A'):.4f}" if isinstance(cal.get("brier_score"), float) else "N/A",
                  help="0 = perfect, 0.25 = random, lower is better.")
    with cc2:
        st.metric("Status", cal.get("status", "N/A"))
    with cc3:
        st.metric("ECE", f"{cal.get('ece', 'N/A'):.4f}" if isinstance(cal.get("ece"), float) else "N/A",
                  help="Expected Calibration Error. Lower = better calibrated.")

    if cal.get("warnings"):
        for w in cal["warnings"]:
            st.warning(w)

    # By year
    by_year = report.get("by_year", {})
    if by_year:
        st.subheader("Results by Year")
        year_rows = []
        for year, ym in sorted(by_year.items()):
            year_rows.append({
                "Year": year,
                "N": ym.get("n", 0),
                "MAE": f"{ym['mae']:.4f}" if isinstance(ym.get("mae"), float) else "N/A",
                "RMSE": f"{ym['rmse']:.4f}" if isinstance(ym.get("rmse"), float) else "N/A",
                "Bias": f"{ym['bias']:+.4f}" if isinstance(ym.get("bias"), float) else "N/A",
                "PI Coverage": f"{ym['interval_coverage_90pct']:.0%}" if isinstance(ym.get("interval_coverage_90pct"), float) else "N/A",
            })
        if year_rows:
            st.dataframe(pd.DataFrame(year_rows), use_container_width=True)
