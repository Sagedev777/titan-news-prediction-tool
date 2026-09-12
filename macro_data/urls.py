"""URL stub for macro_data app."""
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

app_name = "macro_data"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def series_status(request):
    """Return summary of available series and observation counts."""
    from .models import DataObservation, MarketObservation
    from django.db.models import Count, Max

    macro_stats = list(
        DataObservation.objects.values("provider", "series_id")
        .annotate(count=Count("id"), latest=Max("observation_date"))
        .order_by("provider", "series_id")
    )
    market_stats = list(
        MarketObservation.objects.values("symbol", "timeframe")
        .annotate(count=Count("id"), latest=Max("timestamp_utc"))
        .order_by("symbol", "timeframe")
    )
    return Response({"macro_series": macro_stats, "market_data": market_stats})


urlpatterns = [
    path("series-status/", series_status, name="series-status"),
]
