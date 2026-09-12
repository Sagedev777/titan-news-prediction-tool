# Model Methodology

## Overview

The platform uses event-specific models. One universal model is never used
for all economic events. Each event family has its own dedicated model.

---

## Model Development Stages

### Stage 1 — Baselines (always run)

1. **Seasonal Naive** — same period one year ago
2. **Previous Value** — last released value
3. **Rolling Average** — rolling mean of recent N prints
4. **Consensus** — use analyst consensus
5. **External Nowcast** — Cleveland Fed or other published nowcast

All Stage 2+ models must beat the best baseline on out-of-sample data.
If they do not, the baseline is used and the result is reported.

### Stage 2 — Linear Models

- OLS
- Ridge regression (preferred — handles multicollinearity)
- Elastic Net

Selected via walk-forward cross-validation (no random shuffling of time series).

### Stage 3 — Non-linear Models

- Random Forest
- Gradient Boosting

Used only when Stage 2 models are insufficient AND sufficient data exists.
Economic release datasets are small. Complex models overfit easily.

### Stage 4 — Advanced (future)

- Dynamic Factor Model
- State-space model

---

## Model Selection

Models are selected by out-of-sample MAE from walk-forward cross-validation.
If a complex model does not achieve at least 5% better MAE than the best
baseline, the baseline is used. This is reported explicitly.

---

## US CPI Model

**Target:** Headline CPI MoM (SA)

**Features (at forecast time):**
- CPI component lags (headline, core, food, energy, shelter, rent, OER, vehicles)
- Oil price and gasoline price changes
- PPI (goods and services)
- Import price index
- Consumer inflation expectations (Michigan, NY Fed)
- Cleveland Fed nowcast (external estimate — one feature only)
- Consensus forecast
- Seasonal factors (implicit via lagged series)

**Method:**
1. Run all baselines.
2. Run Ridge regression with walk-forward CV.
3. If Ridge beats best baseline (MAE < 0.95 × baseline MAE), use Ridge.
4. Otherwise use rolling average baseline.
5. Report which model was selected and why.

---

## US NFP Model

**Target:** Nonfarm Payrolls monthly change (K)

**Features:**
- ADP employment (leading indicator — NOT treated as NFP proxy)
- JOLTS job openings, hires, quits, layoffs
- Initial and continuing jobless claims
- Average weekly hours
- National Financial Conditions Index
- Consensus forecast

**Important:** ADP is a feature, not a proxy for NFP. The model does not
simply output ADP as the NFP estimate. The relationship between ADP and NFP
changes over time and across economic cycles.

---

## Surprise Probabilities

Defined:
- **Above consensus:** actual > consensus + `near_band`
- **Near consensus:** |actual − consensus| ≤ `near_band`
- **Below consensus:** actual < consensus − `near_band`

Default `near_band` = 0.05 percentage points (configurable per event).
NFP near_band = 25K.

Probabilities are computed from a Gaussian distribution centred on the model
estimate with standard deviation equal to the historical residual standard deviation.

**Calibration:** Applied using isotonic regression where sample size ≥ 25.
Below 25 observations, the message "Probability not calibrated — insufficient
historical sample" is displayed.

---

## Market Reaction Model

Separate from the economic release model.

**Question 1:** What number will be released?
**Question 2:** How will the market react?

These are distinct questions with different features and different models.

For each (event, symbol, horizon) combination:
- Historical reactions are labelled as UP / DOWN / FLAT
- Flat threshold: `abs(return) < 0.25 × ATR` (configurable)
- Walk-forward logistic regression classifies P(UP)
- Minimum 25 comparable events required for any signal

**Signal classification:**
- P(UP) or P(DOWN) ≥ 50%: display signal
- < 50%: NO SIGNAL
- < 25 events: NO SIGNAL with warning

---

## Calibration Requirements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Brier Score | < 0.25 | Walk-forward CV |
| ECE | < 0.10 | Calibration curve |
| PI Coverage (90%) | 85–95% | Out-of-sample |

---

## What the Model Does Not Do

- Does not claim certainty
- Does not guarantee a direction
- Does not use future data in historical simulations
- Does not use revised data where original-release data should be used
- Does not produce a signal when data is missing or insufficient
- Does not hide warnings from the user
