"""
Management command: python manage.py set_forecastable_events

Sets is_forecastable=True on every EconomicEvent whose code appears
in forecasting.event_models.EVENT_MODEL_REGISTRY, and sets it to
False for all others.

Rules
-----
- Only event codes explicitly registered in EVENT_MODEL_REGISTRY are
  marked forecastable.  The registry is the single source of truth.
- An event that is allowlisted but has no implemented model stays
  is_forecastable=False and will appear in the admin with status
  "pipeline not ready".
- An event that is NOT in ALLOWLISTED_EVENT_CODES can never be
  forecastable, even if accidentally added to the registry.
- The command is idempotent: running it multiple times is safe.
- Run this after `bootstrap_events` and after adding a new event model.

Output
------
Prints a table of every event touched: code, was_forecastable,
is_now_forecastable, reason.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from events.models import ALLOWLISTED_EVENT_CODES, EconomicEvent, ImpactLevel


class Command(BaseCommand):
    help = (
        "Mark EconomicEvent.is_forecastable based on the forecasting "
        "event-model registry.  Only HIGH-impact allowlisted events with "
        "an implemented model are marked True."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]

        # Import the registry here (not at module level) to avoid loading
        # the full Django ORM before it is ready.
        from forecasting.event_models import EVENT_MODEL_REGISTRY

        implemented_codes: frozenset[str] = frozenset(EVENT_MODEL_REGISTRY.keys())

        self.stdout.write(
            self.style.HTTP_INFO(
                f"Implemented model codes ({len(implemented_codes)}): "
                + ", ".join(sorted(implemented_codes))
            )
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no database changes."))

        set_true: list[str] = []
        set_false: list[str] = []
        skipped_not_allowlisted: list[str] = []
        skipped_not_high: list[str] = []
        already_correct: list[str] = []

        all_events = list(EconomicEvent.objects.all().order_by("code"))

        for event in all_events:
            should_be_forecastable = (
                event.code in implemented_codes
                and event.code in ALLOWLISTED_EVENT_CODES
                and event.normalized_impact_level == ImpactLevel.HIGH
            )

            if event.code in implemented_codes:
                # Extra validation: warn if a modelled code is blocked
                if event.code not in ALLOWLISTED_EVENT_CODES:
                    skipped_not_allowlisted.append(event.code)
                    self.stdout.write(
                        self.style.WARNING(
                            f"  SKIP  {event.code}: has a model but is NOT in "
                            "ALLOWLISTED_EVENT_CODES — will not be marked forecastable."
                        )
                    )
                    should_be_forecastable = False

                elif event.normalized_impact_level != ImpactLevel.HIGH:
                    skipped_not_high.append(event.code)
                    self.stdout.write(
                        self.style.WARNING(
                            f"  SKIP  {event.code}: has a model but impact="
                            f"{event.normalized_impact_level!r} (not HIGH) — "
                            "will not be marked forecastable."
                        )
                    )
                    should_be_forecastable = False

            if event.is_forecastable == should_be_forecastable:
                already_correct.append(event.code)
                continue

            if should_be_forecastable:
                set_true.append(event.code)
                self.stdout.write(
                    f"  SET TRUE   {event.code}"
                    + (" (dry run)" if dry_run else "")
                )
            else:
                set_false.append(event.code)
                self.stdout.write(
                    f"  SET FALSE  {event.code}"
                    + (" (dry run)" if dry_run else "")
                )

            if not dry_run:
                event.is_forecastable = should_be_forecastable
                event.save(update_fields=["is_forecastable", "updated_at"])

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN complete. No changes written. "
                    "Re-run without --dry-run to apply."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. "
                    f"Marked forecastable: {len(set_true)}  "
                    f"Marked not-forecastable: {len(set_false)}  "
                    f"Already correct: {len(already_correct)}  "
                    f"Skipped (not allowlisted): {len(skipped_not_allowlisted)}  "
                    f"Skipped (not HIGH): {len(skipped_not_high)}"
                )
            )

        if not all_events:
            self.stdout.write(
                self.style.WARNING(
                    "No EconomicEvent rows found in the database. "
                    "Run 'python manage.py bootstrap_events' first."
                )
            )
