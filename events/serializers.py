"""
DRF serializers for the events app.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    DataQualityIssue,
    EconomicEvent,
    EconomicRelease,
    ProviderRequestLog,
)


class EconomicEventSerializer(serializers.ModelSerializer):
    is_red_folder = serializers.ReadOnlyField()
    is_pipeline_ready = serializers.ReadOnlyField()

    class Meta:
        model = EconomicEvent
        fields = [
            "id",
            "code",
            "provider_event_id",
            "name",
            "country",
            "currency",
            "category",
            "provider_impact_level",
            "normalized_impact_level",
            "is_allowlisted",
            "is_forecastable",
            "is_red_folder",
            "is_pipeline_ready",
            "official_source",
            "provider",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "is_allowlisted"]


class EconomicReleaseSerializer(serializers.ModelSerializer):
    event_code = serializers.CharField(source="event.code", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    currency = serializers.CharField(source="event.currency", read_only=True)
    country = serializers.CharField(source="event.country", read_only=True)
    surprise = serializers.ReadOnlyField()
    is_released = serializers.ReadOnlyField()
    is_red_folder = serializers.BooleanField(source="event.is_red_folder", read_only=True)

    class Meta:
        model = EconomicRelease
        fields = [
            "id",
            "event",
            "event_code",
            "event_name",
            "currency",
            "country",
            "is_red_folder",
            "period",
            "forecast",
            "consensus",
            "previous",
            "actual",
            "revised_previous",
            "unit",
            "surprise",
            "is_released",
            "release_time_utc",
            "retrieved_at",
            "is_revised",
            "raw_payload_hash",
        ]
        read_only_fields = ["id", "retrieved_at", "raw_payload_hash"]


class DataQualityIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataQualityIssue
        fields = [
            "id",
            "provider",
            "series_id",
            "issue_type",
            "severity",
            "message",
            "detected_at",
            "resolved",
            "resolved_at",
        ]
        read_only_fields = ["id", "detected_at"]


class ProviderRequestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderRequestLog
        fields = [
            "id",
            "provider",
            "endpoint",
            "request_time_utc",
            "response_time_utc",
            "http_status",
            "latency_ms",
            "success",
            "error_message",
        ]
        read_only_fields = fields
