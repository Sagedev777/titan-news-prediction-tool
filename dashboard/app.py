"""
Red-Folder Macroeconomic Forecasting Dashboard.

Streamlit multi-page application.  All data is read from the Django
database via direct Django ORM calls (Django is initialised below).

Pages:
  1. Overview    — upcoming red-folder events
  2. Event Detail — full research card for one event
  3. Pair Rankings — all instrument signals ranked
  4. Backtesting — historical performance
  5. Data Health — provider status
  6. Excluded Events — diagnostics (non-red events)
"""

from __future__ import annotations

import os
import sys

# ── Bootstrap Django ──────────────────────────────────────────────────────────
# This allows Streamlit to use Django models directly.
# The Streamlit process runs in the same Docker container as the Django app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

# ── Streamlit app ─────────────────────────────────────────────────────────────
import streamlit as st

st.set_page_config(
    page_title="Red Folder Forecast",
    page_icon="🔴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import pages
from dashboard.pages import (
    overview,
    event_detail,
    pair_rankings,
    backtesting,
    data_health,
    excluded_events,
)

# ── Sidebar navigation ────────────────────────────────────────────────────────
PAGES = {
    "🔴 Red Folder Overview": overview,
    "📋 Event Detail": event_detail,
    "📊 Pair Rankings": pair_rankings,
    "🔬 Backtesting": backtesting,
    "🩺 Data Health": data_health,
    "🗑️ Excluded Events (Diagnostics)": excluded_events,
}

st.sidebar.title("🔴 Red Folder Forecast")
st.sidebar.markdown("---")
selection = st.sidebar.radio("Navigate", list(PAGES.keys()))
st.sidebar.markdown("---")
st.sidebar.caption(
    "All signals are probabilistic estimates. "
    "Not financial advice. Use with professional analysis."
)

# Render selected page
PAGES[selection].render()
