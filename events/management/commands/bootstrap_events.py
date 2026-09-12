"""
Management command: python manage.py bootstrap_events

Creates EconomicEvent skeleton rows for all allowlisted event codes
so the application has a valid registry even before the first
calendar ingestion.

Run once after initial migration:
    python manage.py migrate
    python manage.py bootstrap_events
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from events.models import ALLOWLISTED_EVENT_CODES, ImpactLevel
from events.services import upsert_economic_event

# ── Static metadata for each allowlisted code ─────────────────────────────────
EVENT_REGISTRY: list[dict] = [
    # United States
    dict(code="US_CPI", name="US CPI (YoY)", country="United States", currency="USD",
         category="Inflation", official_source="https://www.bls.gov/cpi/"),
    dict(code="US_CORE_CPI", name="US Core CPI (YoY)", country="United States", currency="USD",
         category="Inflation", official_source="https://www.bls.gov/cpi/"),
    dict(code="US_NFP", name="US Nonfarm Payrolls", country="United States", currency="USD",
         category="Employment", official_source="https://www.bls.gov/ces/"),
    dict(code="US_UNEMPLOYMENT_RATE", name="US Unemployment Rate", country="United States",
         currency="USD", category="Employment", official_source="https://www.bls.gov/cps/"),
    dict(code="US_AVERAGE_HOURLY_EARNINGS", name="US Average Hourly Earnings",
         country="United States", currency="USD", category="Employment",
         official_source="https://www.bls.gov/ces/"),
    dict(code="US_FOMC_RATE_DECISION", name="FOMC Interest Rate Decision",
         country="United States", currency="USD", category="Central Bank",
         official_source="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    dict(code="US_FOMC_STATEMENT", name="FOMC Statement", country="United States",
         currency="USD", category="Central Bank",
         official_source="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    dict(code="US_GDP", name="US GDP (QoQ)", country="United States", currency="USD",
         category="Growth", official_source="https://www.bea.gov/"),
    dict(code="US_PPI", name="US PPI (YoY)", country="United States", currency="USD",
         category="Inflation", official_source="https://www.bls.gov/ppi/"),
    dict(code="US_CORE_PPI", name="US Core PPI (YoY)", country="United States", currency="USD",
         category="Inflation", official_source="https://www.bls.gov/ppi/"),
    dict(code="US_RETAIL_SALES", name="US Retail Sales (MoM)", country="United States",
         currency="USD", category="Consumption",
         official_source="https://www.census.gov/retail/"),
    # Euro Area
    dict(code="EUROZONE_CPI", name="Eurozone CPI (YoY)", country="Euro Area", currency="EUR",
         category="Inflation", official_source="https://ec.europa.eu/eurostat/"),
    dict(code="EUROZONE_CORE_CPI", name="Eurozone Core CPI (YoY)", country="Euro Area",
         currency="EUR", category="Inflation", official_source="https://ec.europa.eu/eurostat/"),
    dict(code="ECB_RATE_DECISION", name="ECB Rate Decision", country="Euro Area", currency="EUR",
         category="Central Bank", official_source="https://www.ecb.europa.eu/"),
    dict(code="EUROZONE_GDP", name="Eurozone GDP (QoQ)", country="Euro Area", currency="EUR",
         category="Growth", official_source="https://ec.europa.eu/eurostat/"),
    # United Kingdom
    dict(code="UK_CPI", name="UK CPI (YoY)", country="United Kingdom", currency="GBP",
         category="Inflation", official_source="https://www.ons.gov.uk/"),
    dict(code="UK_CORE_CPI", name="UK Core CPI (YoY)", country="United Kingdom", currency="GBP",
         category="Inflation", official_source="https://www.ons.gov.uk/"),
    dict(code="BOE_RATE_DECISION", name="BoE Rate Decision", country="United Kingdom",
         currency="GBP", category="Central Bank", official_source="https://www.bankofengland.co.uk/"),
    dict(code="UK_GDP", name="UK GDP (QoQ)", country="United Kingdom", currency="GBP",
         category="Growth", official_source="https://www.ons.gov.uk/"),
    # Canada
    dict(code="CANADA_CPI", name="Canada CPI (YoY)", country="Canada", currency="CAD",
         category="Inflation", official_source="https://www.statcan.gc.ca/"),
    dict(code="CANADA_EMPLOYMENT_CHANGE", name="Canada Employment Change", country="Canada",
         currency="CAD", category="Employment", official_source="https://www.statcan.gc.ca/"),
    dict(code="CANADA_UNEMPLOYMENT_RATE", name="Canada Unemployment Rate", country="Canada",
         currency="CAD", category="Employment", official_source="https://www.statcan.gc.ca/"),
    dict(code="BOC_RATE_DECISION", name="BoC Rate Decision", country="Canada", currency="CAD",
         category="Central Bank", official_source="https://www.bankofcanada.ca/"),
    # Australia
    dict(code="AUSTRALIA_CPI", name="Australia CPI (YoY)", country="Australia", currency="AUD",
         category="Inflation", official_source="https://www.abs.gov.au/"),
    dict(code="AUSTRALIA_EMPLOYMENT_CHANGE", name="Australia Employment Change",
         country="Australia", currency="AUD", category="Employment",
         official_source="https://www.abs.gov.au/"),
    dict(code="AUSTRALIA_UNEMPLOYMENT_RATE", name="Australia Unemployment Rate",
         country="Australia", currency="AUD", category="Employment",
         official_source="https://www.abs.gov.au/"),
    dict(code="RBA_RATE_DECISION", name="RBA Rate Decision", country="Australia", currency="AUD",
         category="Central Bank", official_source="https://www.rba.gov.au/"),
    # New Zealand
    dict(code="NEW_ZEALAND_CPI", name="New Zealand CPI (YoY)", country="New Zealand",
         currency="NZD", category="Inflation", official_source="https://www.stats.govt.nz/"),
    dict(code="NEW_ZEALAND_EMPLOYMENT_CHANGE", name="New Zealand Employment Change",
         country="New Zealand", currency="NZD", category="Employment",
         official_source="https://www.stats.govt.nz/"),
    dict(code="NEW_ZEALAND_UNEMPLOYMENT_RATE", name="New Zealand Unemployment Rate",
         country="New Zealand", currency="NZD", category="Employment",
         official_source="https://www.stats.govt.nz/"),
    dict(code="RBNZ_RATE_DECISION", name="RBNZ Rate Decision", country="New Zealand",
         currency="NZD", category="Central Bank", official_source="https://www.rbnz.govt.nz/"),
    # Japan
    dict(code="JAPAN_CPI", name="Japan CPI (YoY)", country="Japan", currency="JPY",
         category="Inflation", official_source="https://www.stat.go.jp/"),
    dict(code="BOJ_RATE_DECISION", name="BoJ Rate Decision", country="Japan", currency="JPY",
         category="Central Bank", official_source="https://www.boj.or.jp/"),
]


class Command(BaseCommand):
    help = "Create EconomicEvent skeleton rows for all allowlisted event codes."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for meta in EVENT_REGISTRY:
            _, created = upsert_economic_event(
                code=meta["code"],
                provider_event_id="",          # populated on first calendar ingest
                name=meta["name"],
                country=meta["country"],
                currency=meta["currency"],
                category=meta["category"],
                provider_impact_level="high",  # bootstrap as HIGH by definition
                official_source=meta.get("official_source", ""),
                provider="bootstrap",
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Bootstrap complete. Created: {created_count}, Updated: {updated_count}. "
                f"Total allowlisted: {len(ALLOWLISTED_EVENT_CODES)}."
            )
        )
