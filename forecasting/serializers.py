"""DRF serializers for the forecasting app."""
from rest_framework import serializers
from .models import ForecastRun, ForecastFeature


class ForecastFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForecastFeature
        fields = [
            "feature_name", "value", "source", "publication_time_utc",
            "lag_days", "contribution", "missing_flag", "revised_flag",
        ]


class ForecastRunSerializer(serializers.ModelSerializer):
    event_code = serializers.CharField(source="event.code", read_only=True)
    event_name = serializers.CharField(source="event.name", read_only=True)
    currency = serializers.CharField(source="event.currency", read_only=True)
    features = ForecastFeatureSerializer(many=True, read_only=True)
    estimated_surprise = serializers.ReadOnlyField()
    is_valid = serializers.ReadOnlyField()

    class Meta:
        model = ForecastRun
        fields = [
            "id", "event_code", "event_name", "currency",
            "model_name", "model_version", "run_time_utc", "data_cutoff_time_utc",
            "estimate", "lower_bound", "upper_bound",
            "probability_below_consensus", "probability_near_consensus", "probability_above_consensus",
            "near_consensus_band", "estimated_surprise",
            "event_bias", "data_quality_status", "calibration_status",
            "comparable_releases_count", "warnings", "data_sources_used",
            "is_valid", "features",
        ]
        read_only_fields = fields
