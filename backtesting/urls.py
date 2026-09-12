from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import BacktestRunViewSet

app_name = "backtesting"

router = DefaultRouter()
router.register(r"runs", BacktestRunViewSet, basename="backtest-run")

urlpatterns = [path("", include(router.urls))]
