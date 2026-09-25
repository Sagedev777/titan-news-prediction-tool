"""
Safe settings verification — prints NO secret values.
Run with: python scripts/verify_settings.py
Set ENV_FILE first: $env:ENV_FILE = ".env.sqlite"
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings

db = settings.DATABASES["default"]
print("=== Effective Settings (safe view — no secret values) ===")
print(f"  Active ENV_FILE      : {os.environ.get('ENV_FILE', '(not set — using .env)')}")
print(f"  Database engine      : {db['ENGINE']}")
print(f"  Database name/path   : {db.get('NAME', '(not set)')}")
print(f"  TIME_ZONE            : {settings.TIME_ZONE}")
print(f"  DISPLAY_TIMEZONE     : {settings.DISPLAY_TIMEZONE}")
print(f"  DEBUG                : {settings.DEBUG}")
print(f"  NEAR_CONSENSUS_BAND  : {settings.NEAR_CONSENSUS_BAND}")
print(f"  MIN_SIGNAL_PROB      : {settings.MIN_SIGNAL_PROBABILITY}")
print()
print("=== API Key presence (True = configured, False = empty) ===")
key_names = [
    ("TRADING_ECONOMICS_API_KEY", settings.TRADING_ECONOMICS_API_KEY),
    ("FRED_API_KEY",              settings.FRED_API_KEY),
    ("BLS_API_KEY",               settings.BLS_API_KEY),
    ("MARKET_DATA_API_KEY",       settings.MARKET_DATA_API_KEY),
    ("TELEGRAM_BOT_TOKEN",        getattr(settings, "TELEGRAM_BOT_TOKEN", "")),
    ("SMTP_USER",                 getattr(settings, "EMAIL_HOST_USER", "")),
]
for name, val in key_names:
    present = bool(val and str(val).strip())
    print(f"  {name:<35}: {present}")
print()
print("=== Celery ===")
print(f"  CELERY_BROKER_URL    : {settings.CELERY_BROKER_URL}")
print(f"  CELERY_RESULT_BACKEND: {settings.CELERY_RESULT_BACKEND}")
print()
print("VERIFY COMPLETE — no secret values printed.")
