"""
Management command: python manage.py ingest_calendar

Pulls economic calendar data from the configured provider and
populates EconomicEvent + EconomicRelease tables.

Only HIGH-impact allowlisted events enter the forecasting database.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("events")


class Command(BaseCommand):
    help = (
        "Ingest economic calendar events from Trading Economics. "
        "Only HIGH-impact allowlisted events are stored in the forecasting tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=14,
            help="Number of days ahead to fetch (default: 14).",
        )
        parser.add_argument(
            "--provider",
            type=str,
            default="trading_economics",
            choices=["trading_economics"],
            help="Calendar provider to use.",
        )

    def handle(self, *args, **options):
        days_ahead = options["days_ahead"]
        provider_name = options["provider"]

        self.stdout.write(
            f"Ingesting economic calendar from {provider_name!r} "
            f"({days_ahead} days ahead)…"
        )

        try:
            from data_sources.trading_economics import TradingEconomicsProvider
            provider = TradingEconomicsProvider()
            result = provider.ingest_calendar(days_ahead=days_ahead)

        except Exception as exc:
            raise CommandError(f"Calendar ingestion failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Ingested: {result.get('ingested', 0)}, "
                f"Excluded (non-red): {result.get('excluded', 0)}, "
                f"Errors: {result.get('errors', 0)}"
            )
        )


