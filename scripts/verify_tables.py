"""
Verify database tables exist after migration.
Prints table names and spot-checks application tables.
Does NOT insert any data.
Run: $env:ENV_FILE=".env.sqlite" ; python -c "exec(open('scripts/verify_tables.py').read())"
"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    tables = connection.introspection.table_names(cursor)

print(f"Total tables in database: {len(tables)}")
print()

# Application tables we expect
expected = [
    "events_economicevent",
    "events_economicrelease",
    "events_dataqualityissue",
    "events_providerrequestlog",
    "macro_data_dataobservation",
    "macro_data_marketobservation",
    "forecasting_forecastrun",
    "forecasting_forecastfeature",
    "market_reaction_instrumentforecast",
    "backtesting_backtestrun",
    "backtesting_backtestresult",
]

print("=== Application table verification ===")
all_present = True
for t in expected:
    present = t in tables
    status = "OK" if present else "MISSING"
    print(f"  {t:<45}: {status}")
    if not present:
        all_present = False

print()
if all_present:
    print("All expected application tables: PRESENT")
else:
    print("WARNING: Some tables are MISSING")

# Spot-check Phase 1 columns via introspection
print()
print("=== Phase 1 column verification ===")
with connection.cursor() as cursor:
    bt_run_cols = [
        col.name for col in
        connection.introspection.get_table_description(cursor, "backtesting_backtestrun")
    ]
    bt_res_cols = [
        col.name for col in
        connection.introspection.get_table_description(cursor, "backtesting_backtestresult")
    ]

lim = "limitations" in bt_run_cols
approx = "consensus_is_approximate" in bt_res_cols
print(f"  backtesting_backtestrun.limitations            : {'PRESENT' if lim else 'MISSING'}")
print(f"  backtesting_backtestresult.consensus_is_approximate : {'PRESENT' if approx else 'MISSING'}")

# Spot-check FK indexes on key tables
print()
print("=== All tables in database ===")
for t in sorted(tables):
    print(f"  {t}")
