# Backtesting

## Point-in-Time Rules

All backtests enforce strict point-in-time data access.

**Rule:** For a simulated forecast at time T, only data with
`publication_time_utc ≤ T` may be used.

This means:
- No revised values used where original values should be
- No future market candles
- No updated consensus values not available at T
- No model versions trained after T

Violations of this rule produce look-ahead bias and will overstate accuracy.

---

## Walk-Forward Simulation

For each historical release:
1. Simulate the forecast timestamp as `release_time − 1 hour`
2. Fetch all features available at that timestamp
3. Run the event-specific model
4. Record the prediction
5. After all predictions are made, compare to actuals

Training data at each step uses only releases prior to the current one.

---

## Data Vintage Policy

| Policy | Description |
|--------|-------------|
| `strict_pit` | Only uses observations with `publication_approximate=False`. Excludes records where publication time is estimated. |
| `lenient` | Includes records with approximate publication times. May slightly overstate accuracy. |

`strict_pit` is the default and recommended policy.

---

## Metrics

| Metric | Description |
|--------|-------------|
| MAE | Mean Absolute Error of point estimates |
| RMSE | Root Mean Square Error |
| Bias | Mean forecast error (positive = systematically above) |
| 90% PI Coverage | Fraction of actuals inside the 90% prediction interval |
| Direction Accuracy | Correct above/near/below classification rate |
| Brier Score | Probability calibration (lower = better) |
| Log Loss | Log probability score (lower = better) |
| ECE | Expected Calibration Error |

---

## Known Limitations

1. **Consensus point-in-time:** The Trading Economics free tier does not provide
   historical consensus snapshots. The stored consensus at backtest time may differ
   from the consensus that was available when the original forecast was made.
   This is noted in the backtest metadata.

2. **Market data gaps:** Some historical 1-minute market candles may be missing.
   Releases with missing market windows are excluded from reaction-model backtests.

3. **Sample size:** Most supported events have 10–50 historical observations.
   This limits the statistical power of calibration and model selection.
