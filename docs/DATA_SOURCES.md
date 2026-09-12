# Data Sources

This document describes every real data provider used by the platform,
what data is fetched, how it is stored, and its limitations.

---

## 1. Trading Economics (Economic Calendar)

**Purpose:** Primary economic calendar — event names, schedules, consensus, actuals.

**API:** https://tradingeconomics.com/api/docs/

**Configuration:** `TRADING_ECONOMICS_API_KEY` in `.env`

**Data fetched:**
- Event name, country, currency, category
- Impact level (1=low, 2=medium, 3=high)
- Scheduled release time
- Consensus, previous, actual, revised previous
- Historical releases

**Red-folder enforcement:**
Events with `Importance != 3` (not HIGH) are written to the excluded/diagnostics
store and never passed to the forecasting pipeline.

**Limitations:**
- Point-in-time consensus history requires a premium subscription.
  Without it, the stored consensus is the current value, not the historical one.
  Backtests note this limitation.
- Release times can be adjusted by the provider before the event.

---

## 2. Bureau of Labor Statistics (BLS)

**Purpose:** Official US CPI and employment data.

**API:** https://www.bls.gov/developers/api_signature_v2.htm

**Configuration:** `BLS_API_KEY` in `.env`

**Key series:**

| Series ID | Description |
|-----------|-------------|
| CUSR0000SA0 | CPI All Items SA |
| CUSR0000SA0L1E | CPI Core (ex food & energy) SA |
| CUSR0000SAF | CPI Food SA |
| CUSR0000SA0E | CPI Energy SA |
| CUSR0000SETB01 | CPI Gasoline SA |
| CUSR0000SAH1 | CPI Shelter SA |
| CUSR0000SEHA | CPI Rent SA |
| CUSR0000SEHC | Owners' Equivalent Rent SA |
| CES0000000001 | Nonfarm Payrolls |
| LNS14000000 | Unemployment Rate |
| CES0000000008 | Average Hourly Earnings |
| WPUFD49104 | PPI Final Demand |

**Revision policy:**
BLS revises prior-month data at each release.
The platform stores each vintage separately using `vintage_date`.
Backtests use only the vintage available at the simulated forecast time.

---

## 3. Federal Reserve Economic Data (FRED)

**Purpose:** Treasury yields, oil prices, financial conditions, survey expectations.

**API:** https://fred.stlouisfed.org/docs/api/fred/

**Configuration:** `FRED_API_KEY` in `.env`

**Key series:**

| Series ID | Description |
|-----------|-------------|
| DGS2 | 2-Year Treasury Yield |
| DGS10 | 10-Year Treasury Yield |
| DCOILWTICO | WTI Crude Oil |
| GASREGCOVW | US Retail Gasoline |
| MICH | Michigan Inflation Expectations |
| ADPWNUSNERSA | ADP Employment |
| JTSJOL | JOLTS Job Openings |

**Vintage support:**
FRED provides `realtime_start` and `realtime_end` parameters for point-in-time
data retrieval. This is used in backtesting to ensure historical simulations
do not use revised values.

---

## 4. Cleveland Fed Inflation Nowcast

**Purpose:** External CPI model estimate (used as one feature, not the answer).

**Source:** https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting

**Configuration:** None required (public data).

**Important:** The Cleveland Fed nowcast is treated as one input feature in the
CPI model. It is NOT treated as the ground truth or the forecast answer.
All forecasts note the distinction clearly.

**Limitations:**
- Published as a CSV file. If the URL or format changes, ingestion will fail
  and the feature will be marked as missing (not silently substituted).
- Publication frequency is daily but may lag by 1–2 days.

---

## 5. Market Data (Twelve Data)

**Purpose:** OHLCV price data for forex pairs, gold, dollar index, and treasuries.

**API:** https://twelvedata.com/docs

**Configuration:** `MARKET_DATA_API_KEY`, `MARKET_DATA_BASE_URL` in `.env`

**Supported instruments:**
EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, XAUUSD, DXY, US02Y, US10Y

**Supported timeframes:** 1min, 5min, 15min, 1h, 4h, 1day

**Delayed data:**
All market observations store an `is_delayed` flag.
Delayed data is never represented as real-time.

---

## General Principles

- **No mock data.** If a provider is unavailable, the application shows an error.
- **Permanent raw storage.** Every API response is hashed and the hash stored.
- **Point-in-time.** All features accessed for forecasting or backtesting are
  filtered by `publication_time_utc <= forecast_time`.
- **Revision tracking.** Revised values are stored with a new `vintage_date`.
  Original values are never overwritten.
