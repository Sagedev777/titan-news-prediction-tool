# API Reference

## Authentication

All API endpoints require a token.

```
Authorization: Token <your_token>
```

Obtain a token:
```
POST /api/auth/token/
{"username": "user", "password": "pass"}
```

---

## Endpoints

### Events

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/events/economic-events/` | GET | All red-folder events |
| `/api/events/economic-events/forecastable/` | GET | Pipeline-ready events |
| `/api/events/economic-events/excluded/` | GET | Excluded non-red events (diagnostics) |
| `/api/events/releases/` | GET | Historical releases |
| `/api/events/releases/upcoming/` | GET | Next 48h unreleased releases |
| `/api/events/releases/recent/` | GET | 20 most recent released prints |
| `/api/events/data-quality/` | GET | Open data quality issues |
| `/api/events/provider-logs/` | GET | Provider request audit log |

### Forecasting

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/forecast/runs/` | GET | All forecast runs |
| `/api/forecast/runs/latest/` | GET | Most recent run per event |
| `/api/forecast/runs/trigger/` | POST | Trigger forecast for upcoming events |

### Market Reaction

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/market/signals/` | GET | All instrument forecasts |

### Backtesting

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/backtest/runs/` | GET | Completed backtest runs |
| `/api/backtest/runs/{id}/` | GET | Detailed backtest report |
| `/api/backtest/runs/run/` | POST | Trigger new backtest |

### Data Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health/` | GET | Provider health + staleness check |

### Macro Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/macro/series-status/` | GET | Series observation counts |

---

## Response Format

All responses return JSON.

Error response:
```json
{"detail": "Authentication credentials were not provided."}
```

Paginated response:
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/events/releases/?page=2",
  "previous": null,
  "results": [...]
}
```
