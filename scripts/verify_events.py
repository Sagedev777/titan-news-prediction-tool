"""
Verify bootstrapped events and forecastable flags.
No fake data is inserted or printed.
"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from events.models import EconomicEvent, ImpactLevel

all_events = EconomicEvent.objects.values(
    "code", "normalized_impact_level", "is_allowlisted", "is_forecastable"
).order_by("normalized_impact_level", "code")

print(f"{'CODE':<40} {'IMPACT':<10} {'ALLOWLISTED':<12} {'FORECASTABLE'}")
print("-" * 80)
for row in all_events:
    print(
        f"{row['code']:<40} "
        f"{row['normalized_impact_level']:<10} "
        f"{str(row['is_allowlisted']):<12} "
        f"{row['is_forecastable']}"
    )

print()
total = all_events.count()
forecastable = EconomicEvent.objects.filter(is_forecastable=True).count()
high_allowlisted = EconomicEvent.objects.filter(
    normalized_impact_level=ImpactLevel.HIGH, is_allowlisted=True
).count()

print(f"Total events     : {total}")
print(f"HIGH + allowlisted: {high_allowlisted}")
print(f"Forecastable (model implemented): {forecastable}")
print()

# Reject check — no MEDIUM/LOW/UNKNOWN should be forecastable
bad = EconomicEvent.objects.filter(is_forecastable=True).exclude(
    normalized_impact_level=ImpactLevel.HIGH, is_allowlisted=True
).count()
if bad:
    print(f"WARNING: {bad} non-red event(s) marked forecastable — this is wrong!")
else:
    print("Red-folder gate: VERIFIED — no non-red events marked forecastable.")
