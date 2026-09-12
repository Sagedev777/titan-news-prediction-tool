"""API views for market_reaction app."""
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from .models import InstrumentForecast
from .serializers import InstrumentForecastSerializer


class InstrumentForecastViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InstrumentForecastSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-ranking_score"]

    def get_queryset(self):
        return InstrumentForecast.objects.select_related(
            "forecast_run__event"
        ).filter(
            forecast_run__event__normalized_impact_level="HIGH",
            forecast_run__event__is_allowlisted=True,
        ).order_by("-ranking_score")
