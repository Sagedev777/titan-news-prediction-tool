from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DataQualityIssueViewSet,
    EconomicEventViewSet,
    EconomicReleaseViewSet,
    ProviderRequestLogViewSet,
)

app_name = "events"

router = DefaultRouter()
router.register(r"economic-events", EconomicEventViewSet, basename="economic-event")
router.register(r"releases", EconomicReleaseViewSet, basename="release")
router.register(r"data-quality", DataQualityIssueViewSet, basename="data-quality")
router.register(r"provider-logs", ProviderRequestLogViewSet, basename="provider-log")

urlpatterns = [
    path("", include(router.urls)),
]
