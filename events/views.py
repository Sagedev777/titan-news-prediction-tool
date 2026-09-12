"""
API views for the events app.

All list endpoints that return EconomicEvent or EconomicRelease
enforce the red-folder filter unless they explicitly serve the
diagnostics / excluded-events endpoint.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    DataQualityIssue,
    EconomicEvent,
    EconomicRelease,
    ImpactLevel,
    ProviderRequestLog,
)
from .serializers import (
    DataQualityIssueSerializer,
    EconomicEventSerializer,
    EconomicReleaseSerializer,
    ProviderRequestLogSerializer,
)
from .services import get_upcoming_red_folder_releases

logger = logging.getLogger("events")


class EconomicEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view of EconomicEvent records.

    The default queryset returns ONLY red-folder events (HIGH + allowlisted).
    Use the /excluded/ action to see non-red events for diagnostics.
    """

    serializer_class = EconomicEventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "country", "currency"]
    ordering_fields = ["country", "code", "normalized_impact_level"]
    ordering = ["country", "code"]

    def get_queryset(self):
        # DEFAULT: only red-folder events
        return EconomicEvent.objects.filter(
            normalized_impact_level=ImpactLevel.HIGH,
            is_allowlisted=True,
        )

    @action(detail=False, methods=["get"], url_path="excluded")
    def excluded(self, request):
        """
        Return excluded non-red events for diagnostics only.

        Clearly labelled — not used by the forecasting system.
        """
        qs = EconomicEvent.objects.exclude(
            normalized_impact_level=ImpactLevel.HIGH,
            is_allowlisted=True,
        ).order_by("normalized_impact_level", "code")

        serializer = self.get_serializer(qs, many=True)
        return Response(
            {
                "label": "Excluded non-red events — not used by the forecasting system.",
                "count": qs.count(),
                "results": serializer.data,
            }
        )

    @action(detail=False, methods=["get"], url_path="forecastable")
    def forecastable(self, request):
        """Return only events that are fully pipeline-ready."""
        qs = EconomicEvent.objects.filter(
            normalized_impact_level=ImpactLevel.HIGH,
            is_allowlisted=True,
            is_forecastable=True,
        ).order_by("country", "code")
        serializer = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class EconomicReleaseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view of EconomicRelease records.

    Always filtered to red-folder events only.
    """

    serializer_class = EconomicReleaseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["release_time_utc", "event__code"]
    ordering = ["-release_time_utc"]

    def get_queryset(self):
        return EconomicRelease.objects.select_related("event").filter(
            event__normalized_impact_level=ImpactLevel.HIGH,
            event__is_allowlisted=True,
        )

    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request):
        """Return upcoming unreleased red-folder releases (next 48 h)."""
        releases = get_upcoming_red_folder_releases(hours_ahead=48)
        serializer = self.get_serializer(releases, many=True)
        return Response(
            {
                "as_of": timezone.now().isoformat(),
                "count": len(releases),
                "results": serializer.data,
            }
        )

    @action(detail=False, methods=["get"], url_path="recent")
    def recent(self, request):
        """Return the 20 most-recent released prints."""
        qs = (
            self.get_queryset()
            .filter(actual__isnull=False)
            .order_by("-release_time_utc")[:20]
        )
        serializer = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class DataQualityIssueViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DataQualityIssueSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-detected_at"]

    def get_queryset(self):
        return DataQualityIssue.objects.filter(resolved=False)

    @action(detail=False, methods=["get"], url_path="all")
    def all_issues(self, request):
        qs = DataQualityIssue.objects.all().order_by("-detected_at")[:200]
        serializer = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class ProviderRequestLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProviderRequestLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-request_time_utc"]

    def get_queryset(self):
        return ProviderRequestLog.objects.order_by("-request_time_utc")[:500]
