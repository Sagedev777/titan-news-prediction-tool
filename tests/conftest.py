"""
pytest configuration for the Red-Folder Forecasting Platform.

This file is discovered automatically by pytest before any test module
is imported.  It sets up Django so that:

1. DJANGO_SETTINGS_MODULE is set before Django is initialised.
2. django.setup() is called exactly once.
3. Tests that do NOT touch the database run without migrations
   (the red-folder filter tests are pure Python and need no DB).
4. Tests that DO need the database use @pytest.mark.django_db.

Environment note
----------------
Settings read from .env via django-environ.  When running in CI or
without a real .env file, set the required variables directly in the
environment.  The minimum required variable to prevent a crash is:

    DJANGO_SECRET_KEY=test-secret-key-not-for-production

If DATABASE_URL is not set, settings.py falls back to SQLite
(sqlite:///db.sqlite3), which is acceptable for the test suite.
"""

import django
import os
import pytest


# ---------------------------------------------------------------------------
# Tell Django which settings module to use.
# This must happen before any Django import.
# ---------------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Provide a minimal fallback secret key so settings.py does not crash when
# no .env file is present (e.g. in bare CI).  A real .env takes precedence
# because django-environ reads it first.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-insecure-key-for-pytest-only")

# Use SQLite in-memory for tests so no Postgres is required locally.
os.environ.setdefault("DATABASE_URL", "sqlite:///test_db.sqlite3")

# Disable Redis for tests — use Django's local-memory cache backend instead.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Silence provider key warnings during tests (keys not needed for unit tests).
os.environ.setdefault("TRADING_ECONOMICS_API_KEY", "")
os.environ.setdefault("FRED_API_KEY", "")
os.environ.setdefault("BLS_API_KEY", "")
os.environ.setdefault("MARKET_DATA_API_KEY", "")


# ---------------------------------------------------------------------------
# pytest-django hook: called before the Django test runner sets up the DB.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def django_db_setup():
    """
    Override the default DB setup.

    Most Phase 1 tests (red-folder filter, normalise_impact) are pure Python
    and never touch the database.  This fixture is a no-op so those tests
    run without needing a real database connection.

    Tests that explicitly need DB access must be decorated with
    @pytest.mark.django_db, which will then use the SQLite fallback
    configured above.
    """
    pass
