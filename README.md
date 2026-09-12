# Red-Folder Macroeconomic Forecasting Platform

A real-data, research-grade economic news forecasting platform that:

- Detects upcoming **red-folder only** (HIGH-impact) economic events
- Estimates the likely release outcome using real macro data
- Compares estimates with analyst consensus
- Produces calibrated surprise probabilities
- Forecasts likely forex, gold, and yield reactions
- Ranks instruments by evidence strength (BUY / SELL / NO SIGNAL)
- Backtests with strict point-in-time data rules
- Alerts via email and Telegram before each release

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your real API keys
```

Required keys:
- `TRADING_ECONOMICS_API_KEY`
- `FRED_API_KEY`
- `BLS_API_KEY`
- `MARKET_DATA_API_KEY`
- `DJANGO_SECRET_KEY`
- `DATABASE_URL`

### 2. Start services

```bash
docker-compose up -d
```

### 3. Initialise database

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py bootstrap_events
docker-compose exec web python manage.py createsuperuser
```

### 4. Ingest initial data

```bash
docker-compose exec web python manage.py ingest_calendar --days-ahead 30
```

Celery beat will handle ongoing ingestion automatically.

### 5. Open dashboard

```
http://localhost:8501
```

API (Django):
```
http://localhost:8000/api/
```

Admin:
```
http://localhost:8000/admin/
```

---

## Architecture

```
config/         Django settings, Celery, logging
events/         Event registry, release records, data quality
data_sources/   Provider clients: Trading Economics, BLS, FRED, Cleveland Fed, Market Data
macro_data/     Time-series storage, feature retrieval (PIT-correct)
forecasting/    Event-specific models, calibration, scenarios
market_reaction/ Per-instrument signal generation and ranking
backtesting/    Walk-forward historical performance evaluation
alerts/         Email, Telegram, webhook notifications
dashboard/      Streamlit 6-page UI
tests/          Red-folder filter and normalisation tests
docs/           DATA_SOURCES, MODEL_METHODOLOGY, BACKTESTING, API
```

---

## Red-Folder Policy

**Only HIGH-impact allowlisted events enter the forecasting pipeline.**

The filter is enforced in:
- API ingestion (TradingEconomicsProvider)
- Database queries (normalized_impact_level == HIGH AND is_allowlisted == True)
- All forecasting services (assert_red_folder gate)
- Dashboard queries
- Alert dispatch
- Backtesting queries

Excluded events are visible on the Diagnostics page only, clearly labelled
"Excluded non-red events — not used by the forecasting system."

---

## Honest Forecast Policy

Every forecast shows:
- Model estimate and prediction interval
- Probability definition and calibration status
- Historical sample size
- Data sources and quality warnings
- Model version and data cutoff time

The platform never displays:
- Guaranteed predictions
- 100% confidence
- Signals based on missing data
- Results based on future or revised data in backtests

---

## Supported Events

See `events/models.py` → `ALLOWLISTED_EVENT_CODES` for the full list.
Modelled events: US_CPI, US_CORE_CPI, US_NFP, US_UNEMPLOYMENT_RATE,
US_AVERAGE_HOURLY_EARNINGS.

More event models are added in `forecasting/event_models.py`.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Documentation

- [Data Sources](docs/DATA_SOURCES.md)
- [Model Methodology](docs/MODEL_METHODOLOGY.md)
- [Backtesting](docs/BACKTESTING.md)
- [API Reference](docs/API.md)

---

## Disclaimer

This platform produces probabilistic model estimates. It is not financial
advice. No prediction is guaranteed. Always use with professional analysis
and risk management.
