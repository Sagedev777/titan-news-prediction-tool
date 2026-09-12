"""DRF serializers for market_reaction app."""
from rest_framework import serializers
from .models import InstrumentForecast


class InstrumentForecastSerializer(serializers.ModelSerializer):
    probability_edge = serializers.ReadOnlyField()
    display_probability = serializers.ReadOnlyField()
    event_code = serializers.CharField(source="forecast_run.event.code", read_only=True)

    class Meta:
        model = InstrumentForecast
        fields = [
            "id", "event_code", "symbol", "horizon", "signal",
            "probability_up", "probability_down", "probability_flat",
            "probability_edge", "display_probability",
            "expected_return", "lower_return_bound", "upper_return_bound",
            "historical_accuracy", "sample_size", "ranking_score",
            "evidence_quality", "explanation", "warnings", "created_at",
        ]
        read_only_fields = fields
