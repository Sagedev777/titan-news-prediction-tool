from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import InstrumentForecastViewSet

app_name = "market_reaction"

router = DefaultRouter()
router.register(r"signals", InstrumentForecastViewSet, basename="signal")

urlpatterns = [path("", include(router.urls))]
