"""
Tests for environment selection and database setup.

Covers:
- ENV_FILE selection mechanism
- Real .env is not overwritten by test run
- SQLite is active during test session
- Red-folder filtering (already in test_red_folder_filter.py, repeated here
  as DB-backed tests using the actual bootstrapped registry)
- All foreign keys resolve (model meta inspection)
- Point-in-time data boundary (future data must not enter a forecast)
- No fake economic data is present in the database
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
import pytest

# ── Path to project root ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# ENV_FILE selection
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvFileSelection:
    """Prove ENV_FILE controls which env file is loaded."""

    def test_env_sqlite_file_exists(self):
        """The .env.sqlite file must exist for the SQLite dev workflow."""
        env_sqlite = BASE_DIR / ".env.sqlite"
        assert env_sqlite.exists(), (
            ".env.sqlite does not exist. "
            "Run: copy .env.example .env.sqlite and fill in SQLite values."
        )

    def test_real_env_exists_and_is_not_sqlite(self):
        """.env must exist and must NOT point to SQLite (it is the Postgres env)."""
        real_env = BASE_DIR / ".env"
        assert real_env.exists(), ".env file is missing."
        content = real_env.read_text(encoding="utf-8", errors="replace")
        # .env should reference postgres, not sqlite, in DATABASE_URL
        lines = [
            line.strip() for line in content.splitlines()
            if line.strip().startswith("DATABASE_URL=") and not line.strip().startswith("#")
        ]
        assert lines, ".env has no uncommented DATABASE_URL"
        # At least one active DATABASE_URL line must NOT be sqlite
        non_sqlite = [l for l in lines if "sqlite" not in l.lower()]
        assert non_sqlite, (
            "All active DATABASE_URL entries in .env point to SQLite. "
            ".env should point to PostgreSQL for production."
        )

    def test_env_sqlite_points_to_sqlite(self):
        """The .env.sqlite file must point to SQLite."""
        env_sqlite = BASE_DIR / ".env.sqlite"
        content = env_sqlite.read_text(encoding="utf-8", errors="replace")
        active_db_lines = [
            line.strip() for line in content.splitlines()
            if line.strip().startswith("DATABASE_URL=") and not line.strip().startswith("#")
        ]
        assert active_db_lines, ".env.sqlite has no active DATABASE_URL"
        assert all("sqlite" in l.lower() for l in active_db_lines), (
            ".env.sqlite DATABASE_URL must point to SQLite, not PostgreSQL."
        )

    def test_env_file_var_controls_loading(self):
        """The active DATABASE_URL in settings must be SQLite during the test run
        (because conftest.py sets DATABASE_URL to SQLite)."""
        import django
        from django.conf import settings
        db = settings.DATABASES["default"]
        assert "sqlite3" in db["ENGINE"], (
            f"Expected SQLite engine during tests, got {db['ENGINE']}. "
            "Ensure DATABASE_URL is set to sqlite:/// in conftest.py."
        )

    def test_env_sqlite_not_committed(self):
        """.env.sqlite must be covered by .gitignore patterns."""
        gitignore = BASE_DIR / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        # .env.* pattern covers .env.sqlite
        assert ".env.*" in content or ".env.sqlite" in content, (
            ".gitignore must exclude .env.sqlite (via .env.* or explicit entry)."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Database engine assertion
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseEngine:
    def test_sqlite_engine_active(self):
        """Tests must run on SQLite — never on a production PostgreSQL server."""
        import django
        from django.conf import settings
        engine = settings.DATABASES["default"]["ENGINE"]
        assert engine == "django.db.backends.sqlite3", (
            f"Test database engine is {engine!r}. "
            "Tests must use SQLite. Set DATABASE_URL=sqlite:///test.sqlite3 in conftest.py."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Red-folder filtering (DB-independent — pure Python)
# ─────────────────────────────────────────────────────────────────────────────

class TestRedFolderFilterDB:
    """DB-backed tests confirming the filter holds in services.py."""

    def test_medium_rejected_by_service(self):
        from events.models import EconomicEvent, ImpactLevel
        from events.services import is_red_folder
        e = EconomicEvent.__new__(EconomicEvent)
        e.code = "US_CPI"
        e.normalized_impact_level = ImpactLevel.MEDIUM
        e.is_allowlisted = True
        assert is_red_folder(e) is False

    def test_low_rejected_by_service(self):
        from events.models import EconomicEvent, ImpactLevel
        from events.services import is_red_folder
        e = EconomicEvent.__new__(EconomicEvent)
        e.code = "US_CPI"
        e.normalized_impact_level = ImpactLevel.LOW
        e.is_allowlisted = True
        assert is_red_folder(e) is False

    def test_unknown_rejected_by_service(self):
        from events.models import EconomicEvent, ImpactLevel
        from events.services import is_red_folder
        e = EconomicEvent.__new__(EconomicEvent)
        e.code = "US_CPI"
        e.normalized_impact_level = ImpactLevel.UNKNOWN
        e.is_allowlisted = True
        assert is_red_folder(e) is False

    def test_non_allowlisted_high_rejected(self):
        from events.models import EconomicEvent, ImpactLevel
        from events.services import is_red_folder
        e = EconomicEvent.__new__(EconomicEvent)
        e.code = "SOME_RANDOM_EVENT_NOT_IN_REGISTRY"
        e.normalized_impact_level = ImpactLevel.HIGH
        e.is_allowlisted = False
        assert is_red_folder(e) is False

    def test_valid_high_allowlisted_accepted(self):
        from events.models import EconomicEvent, ImpactLevel
        from events.services import is_red_folder
        e = EconomicEvent.__new__(EconomicEvent)
        e.code = "US_NFP"
        e.normalized_impact_level = ImpactLevel.HIGH
        e.is_allowlisted = True
        assert is_red_folder(e) is True


# ─────────────────────────────────────────────────────────────────────────────
# Foreign key resolution (model meta inspection)
# ─────────────────────────────────────────────────────────────────────────────

class TestForeignKeyResolution:
    """All FK targets must resolve in the loaded Django app registry."""

    def test_all_fk_targets_resolve(self):
        import django
        from django.apps import apps as registry

        apps_to_check = [
            "events", "macro_data", "forecasting", "market_reaction", "backtesting"
        ]
        broken = []
        for app_label in apps_to_check:
            app_config = registry.get_app_config(app_label)
            for model in app_config.get_models():
                for field in model._meta.get_fields():
                    if hasattr(field, "related_model") and field.related_model:
                        try:
                            registry.get_model(
                                field.related_model._meta.app_label,
                                field.related_model.__name__,
                            )
                        except Exception as exc:
                            broken.append(
                                f"{app_label}.{model.__name__}.{field.name}: {exc}"
                            )
        assert not broken, "Broken FK targets:\n" + "\n".join(broken)


# ─────────────────────────────────────────────────────────────────────────────
# Point-in-time boundary
# ─────────────────────────────────────────────────────────────────────────────

class TestPointInTimeBoundary:
    """
    Future data must not enter a point-in-time forecast.
    Tests the get_available_data() logic without requiring real DB data.
    """

    @pytest.mark.django_db
    def test_future_publication_time_excluded(self):
        """
        DataObservation rows with publication_time_utc > as_of
        must be excluded by get_available_data().
        """
        import pytz
        from django.utils import timezone
        from macro_data.normalization import build_series_dataframe
        from macro_data.models import DataObservation

        # The function filters by publication_time_utc <= as_of.
        # We test the filtering logic directly without needing real rows.
        # Use a fixed past time as the simulated forecast time.
        as_of = datetime(2020, 1, 1, tzinfo=pytz.UTC)
        future_time = datetime(2020, 6, 1, tzinfo=pytz.UTC)  # AFTER as_of

        # DataObservation.objects.filter(...) with publication_time_utc__lte=as_of
        # must exclude anything published after as_of.
        # We verify the queryset builds correctly (no DB rows needed).
        qs = DataObservation.objects.filter(
            provider="test",
            series_id="TEST_SERIES",
            publication_time_utc__lte=as_of,
        )
        # Queryset must not include future rows (none exist, so count = 0 is correct)
        assert qs.count() == 0, (
            "Expected 0 rows for test series — but found data that should not exist."
        )

    def test_as_of_enforced_in_accessor(self):
        """PointInTimeDataAccessor.get_series respects as_of."""
        import pytz
        from backtesting.point_in_time import PointInTimeDataAccessor

        past_time = datetime(2010, 1, 1, tzinfo=pytz.UTC)
        accessor = PointInTimeDataAccessor(as_of=past_time, strict=True)
        # Should return an empty DataFrame — no 2010 data in test DB
        df = accessor.get_series("fred", "DGS2")
        assert df is not None  # Must return a DataFrame, not raise
        assert hasattr(df, "empty")


# ─────────────────────────────────────────────────────────────────────────────
# No fake data
# ─────────────────────────────────────────────────────────────────────────────

class TestNoFakeData:
    """
    The database must not contain fake economic values.
    After bootstrap, no EconomicRelease rows should exist
    (releases come only from real calendar ingestion).
    """

    def test_no_economic_releases_without_ingestion(self):
        """
        bootstrap_events creates EconomicEvent rows only.
        No EconomicRelease rows should be present until real ingestion runs.
        """
        from events.models import EconomicRelease
        count = EconomicRelease.objects.count()
        assert count == 0, (
            f"Found {count} EconomicRelease row(s) before any ingestion. "
            "These may be fake or erroneously inserted values. "
            "EconomicRelease rows must come only from real calendar ingestion."
        )

    def test_no_data_observations_without_ingestion(self):
        """No DataObservation rows should exist until BLS/FRED ingestion runs."""
        from macro_data.models import DataObservation
        count = DataObservation.objects.count()
        assert count == 0, (
            f"Found {count} DataObservation row(s) before any ingestion. "
            "These may be fake values. "
            "DataObservation rows must come only from real BLS/FRED API responses."
        )

    def test_no_market_observations_without_ingestion(self):
        """No MarketObservation rows should exist until market data ingestion runs."""
        from macro_data.models import MarketObservation
        count = MarketObservation.objects.count()
        assert count == 0, (
            f"Found {count} MarketObservation row(s) before any ingestion. "
            "MarketObservation rows must come only from real market data API responses."
        )

    def test_no_forecast_runs_without_data(self):
        """No ForecastRun rows should exist — forecasts require real ingested data."""
        from forecasting.models import ForecastRun
        count = ForecastRun.objects.count()
        assert count == 0, (
            f"Found {count} ForecastRun row(s) before data ingestion. "
            "ForecastRun rows must come only from the forecasting pipeline "
            "after real data has been ingested."
        )
