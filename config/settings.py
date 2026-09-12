"""
Django settings for the Red-Folder Macroeconomic Forecasting Platform.

All secrets and environment-specific values are read from environment
variables (never hard-coded).  Copy .env.example to .env and fill in
real values before running.
"""

from __future__ import annotations

import os
from pathlib import Path

import environ

# ── Path helpers ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Environment loading ───────────────────────────────────────────────────────
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DISPLAY_TIMEZONE=(str, "Africa/Nairobi"),
    MIN_SIGNAL_PROBABILITY=(float, 50.0),
    MIN_HISTORICAL_SAMPLE=(int, 25),
    NEAR_CONSENSUS_BAND=(float, 0.05),
    FLAT_REACTION_ATR_MULTIPLIER=(float, 0.25),
    MARKET_DATA_MAX_AGE_MINUTES=(int, 5),
    MACRO_DATA_MAX_AGE_DAYS=(int, 2),
)

environ.Env.read_env(BASE_DIR / ".env")

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ── Application registry ─────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "django_extensions",
]

LOCAL_APPS = [
    "events.apps.EventsConfig",
    "data_sources.apps.DataSourcesConfig",
    "macro_data.apps.MacroDataConfig",
    "forecasting.apps.ForecastingConfig",
    "market_reaction.apps.MarketReactionConfig",
    "backtesting.apps.BacktestingConfig",
    "alerts.apps.AlertsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# ── Templates ────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}
# Ensure Django does not close connections too aggressively on PostgreSQL
DATABASES["default"].setdefault("CONN_MAX_AGE", 60)

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
    }
}

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"          # Always store in UTC
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "DATETIME_FORMAT": "iso-8601",
}

# ── Celery ────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="django-db")
CELERY_RESULT_EXTENDED = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60       # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("SMTP_HOST", default="localhost")
EMAIL_PORT = env.int("SMTP_PORT", default=587)
EMAIL_HOST_USER = env("SMTP_USER", default="")
EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("SMTP_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("ALERT_FROM_EMAIL", default="alerts@localhost")
ALERT_TO_EMAILS = env.list("ALERT_TO_EMAILS", default=[])

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID", default="")

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:8501", "http://localhost:3000"],
)

# ── Data-provider configuration ───────────────────────────────────────────────
TRADING_ECONOMICS_API_KEY = env("TRADING_ECONOMICS_API_KEY", default="")
FRED_API_KEY = env("FRED_API_KEY", default="")
BLS_API_KEY = env("BLS_API_KEY", default="")
MARKET_DATA_PROVIDER = env("MARKET_DATA_PROVIDER", default="twelvedata")
MARKET_DATA_API_KEY = env("MARKET_DATA_API_KEY", default="")
MARKET_DATA_BASE_URL = env("MARKET_DATA_BASE_URL", default="https://api.twelvedata.com")

# ── Application-level thresholds ──────────────────────────────────────────────
DISPLAY_TIMEZONE = env("DISPLAY_TIMEZONE")
MIN_SIGNAL_PROBABILITY = env("MIN_SIGNAL_PROBABILITY")
MIN_HISTORICAL_SAMPLE = env("MIN_HISTORICAL_SAMPLE")
NEAR_CONSENSUS_BAND = env("NEAR_CONSENSUS_BAND")
FLAT_REACTION_ATR_MULTIPLIER = env("FLAT_REACTION_ATR_MULTIPLIER")
MARKET_DATA_MAX_AGE_MINUTES = env("MARKET_DATA_MAX_AGE_MINUTES")
MACRO_DATA_MAX_AGE_DAYS = env("MACRO_DATA_MAX_AGE_DAYS")

# ── Logging ───────────────────────────────────────────────────────────────────
# IMPORTANT: We use importlib to load config/logging.py directly rather than
# importing via the `config` package (i.e. NOT `import config.logging`).
# The `config` package __init__.py imports the Celery app, which itself
# references Django settings — importing it mid-way through settings.py
# would create a circular import.  importlib.util bypasses __init__.py
# and loads only the logging module file.
LOGGING_CONFIG = None  # Tell Django not to apply its default logging config.

import importlib.util as _ilu
import pathlib as _pl

_logging_path = _pl.Path(__file__).parent / "logging.py"
_logging_spec = _ilu.spec_from_file_location("config._logging_setup", _logging_path)
_logging_mod = _ilu.module_from_spec(_logging_spec)
_logging_spec.loader.exec_module(_logging_mod)
_logging_mod.configure_logging(debug=DEBUG, base_dir=BASE_DIR)
del _ilu, _pl, _logging_path, _logging_spec, _logging_mod  # keep namespace clean
