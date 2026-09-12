from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ForecastRunViewSet

app_name = "forecasting"

router = DefaultRouter()
router.register(r"runs", ForecastRunViewSet, basename="forecast-run")

urlpatterns = [path("", include(router.urls))]
