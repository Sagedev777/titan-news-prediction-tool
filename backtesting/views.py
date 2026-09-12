"""API views for backtesting app."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import BacktestRun
from .reports import generate_backtest_report


class BacktestRunViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    ordering = ["-created_at"]

    def get_queryset(self):
        return BacktestRun.objects.filter(status="completed").order_by("-created_at")

    def list(self, request):
        qs = self.get_queryset()
        data = [
            {
                "id": r.id, "name": r.name, "event_code": r.event_code,
                "start_date": str(r.start_date), "end_date": str(r.end_date),
                "model_version": r.model_version, "status": r.status,
                "created_at": r.created_at.isoformat(),
                "summary": r.summary,
            }
            for r in qs
        ]
        return Response({"count": len(data), "results": data})

    def retrieve(self, request, pk=None):
        run = self.get_object()
        report = generate_backtest_report(run)
        return Response(report)

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        """Trigger a new backtest run."""
        event_code = request.data.get("event_code")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")

        if not all([event_code, start_date, end_date]):
            return Response({"error": "event_code, start_date, end_date required."}, status=400)

        from .runner import run_backtest
        from datetime import date
        result = run_backtest(
            event_code=event_code,
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
        )
        return Response(result)
