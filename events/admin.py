"""
Django admin configuration for the events app.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    DataQualityIssue,
    EconomicEvent,
    EconomicRelease,
    ProviderRequestLog,
)


@admin.register(EconomicEvent)
class EconomicEventAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "country",
        "currency",
        "normalized_impact_level",
        "is_allowlisted",
        "is_forecastable",
        "red_folder_badge",
        "updated_at",
    ]
    list_filter = [
        "normalized_impact_level",
        "is_allowlisted",
        "is_forecastable",
        "country",
        "provider",
    ]
    search_fields = ["code", "name", "country", "currency"]
    readonly_fields = ["created_at", "updated_at", "is_allowlisted"]
    ordering = ["country", "code"]

    @admin.display(description="Red Folder", boolean=False)
    def red_folder_badge(self, obj):
        if obj.is_red_folder:
            return format_html('<span style="color:red;font-weight:bold;">🔴 RED</span>')
        return format_html('<span style="color:gray;">—</span>')


@admin.register(EconomicRelease)
class EconomicReleaseAdmin(admin.ModelAdmin):
    list_display = [
        "event",
        "period",
        "release_time_utc",
        "consensus",
        "actual",
        "surprise_display",
        "is_revised",
        "retrieved_at",
    ]
    list_filter = [
        "event__normalized_impact_level",
        "event__country",
        "is_revised",
    ]
    search_fields = ["event__code", "event__name", "period"]
    readonly_fields = ["retrieved_at", "raw_payload_hash"]
    date_hierarchy = "release_time_utc"
    ordering = ["-release_time_utc"]

    @admin.display(description="Surprise")
    def surprise_display(self, obj):
        s = obj.surprise
        if s is None:
            return "—"
        color = "green" if s > 0 else ("red" if s < 0 else "gray")
        sign = "+" if s > 0 else ""
        return format_html('<span style="color:{};">{}{:.4f}</span>', color, sign, s)


@admin.register(DataQualityIssue)
class DataQualityIssueAdmin(admin.ModelAdmin):
    list_display = [
        "provider",
        "series_id",
        "issue_type",
        "severity",
        "message_short",
        "detected_at",
        "resolved",
    ]
    list_filter = ["severity", "issue_type", "provider", "resolved"]
    search_fields = ["provider", "series_id", "message"]
    readonly_fields = ["detected_at"]
    ordering = ["-detected_at"]
    actions = ["mark_resolved"]

    @admin.display(description="Message")
    def message_short(self, obj):
        return obj.message[:80] + ("…" if len(obj.message) > 80 else "")

    @admin.action(description="Mark selected issues as resolved")
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        queryset.update(resolved=True, resolved_at=timezone.now())
        self.message_user(request, f"{queryset.count()} issue(s) marked resolved.")


@admin.register(ProviderRequestLog)
class ProviderRequestLogAdmin(admin.ModelAdmin):
    list_display = [
        "provider",
        "endpoint_short",
        "request_time_utc",
        "http_status",
        "latency_ms",
        "success",
    ]
    list_filter = ["provider", "success"]
    search_fields = ["provider", "endpoint"]
    readonly_fields = [f.name for f in ProviderRequestLog._meta.get_fields()]
    ordering = ["-request_time_utc"]

    @admin.display(description="Endpoint")
    def endpoint_short(self, obj):
        return obj.endpoint[:80] + ("…" if len(obj.endpoint) > 80 else "")
