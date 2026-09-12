"""
Root URL configuration for the Red-Folder Forecasting Platform.
"""

from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    # ── Admin ─────────────────────────────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ── Auth ──────────────────────────────────────────────────────────────────
    path("api/auth/token/", obtain_auth_token, name="api-token-auth"),

    # ── Application APIs ──────────────────────────────────────────────────────
    path("api/events/", include("events.urls", namespace="events")),
    path("api/macro/", include("macro_data.urls", namespace="macro_data")),
    path("api/forecast/", include("forecasting.urls", namespace="forecasting")),
    path("api/market/", include("market_reaction.urls", namespace="market_reaction")),
    path("api/backtest/", include("backtesting.urls", namespace="backtesting")),
    path("api/health/", include("data_sources.urls", namespace="data_sources")),
]
