"""URLs for the data_sources health endpoints."""
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

app_name = "data_sources"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health_view(request):
    """Run provider health checks and return status."""
    from .health import run_all_health_checks, check_data_staleness
    health = run_all_health_checks()
    staleness = check_data_staleness()
    return Response({"health": health, "staleness": staleness})


urlpatterns = [
    path("", health_view, name="health"),
]
