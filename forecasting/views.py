"""API views for the forecasting app."""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone

from .models import ForecastRun
from .serializers import ForecastRunSerializer


class ForecastRunViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ForecastRunSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-run_time_utc"]

    def get_queryset(self):
        return (
            ForecastRun.objects.select_related("event", "economic_release")
            .prefetch_related("features")
            .filter(
                event__normalized_impact_level="HIGH",
                event__is_allowlisted=True,
            )
            .order_by("-run_time_utc")
        )

    @action(detail=False, methods=["get"], url_path="latest")
    def latest(self, request):
        """Return the most recent forecast run for each event."""
        from django.db.models import Max
        event_ids = (
            ForecastRun.objects.filter(
                event__normalized_impact_level="HIGH",
                event__is_allowlisted=True,
            )
            .values("event_id")
            .annotate(max_run=Max("run_time_utc"))
        )

        runs = []
        for entry in event_ids:
            run = (
                ForecastRun.objects.filter(
                    event_id=entry["event_id"],
                    run_time_utc=entry["max_run"],
                )
                .select_related("event", "economic_release")
                .prefetch_related("features")
                .first()
            )
            if run:
                runs.append(run)

        serializer = self.get_serializer(runs, many=True)
        return Response({
            "as_of": timezone.now().isoformat(),
            "count": len(runs),
            "results": serializer.data,
        })

    @action(detail=False, methods=["post"], url_path="trigger")
    def trigger(self, request):
        """Manually trigger a forecast run for all upcoming red-folder events."""
        from forecasting.tasks import run_upcoming_event_forecasts
        task = run_upcoming_event_forecasts.delay()
        return Response({"task_id": task.id, "status": "queued"})
