# volume_rally A/B validation

Compare the failed 1m baseline against the tuned 5m configuration on AAPL and AMD
(2026-04-25 through 2026-05-25).

Requires Alpaca credentials in the environment.

## Run

```bash
backtest run \
  --config experiments/volume_rally_baseline_1m.yaml \
  --output /tmp/volume-rally-baseline.json

backtest run \
  --config experiments/volume_rally_tuned_5m.yaml \
  --output /tmp/volume-rally-tuned.json
```

## What to compare

| Metric | Baseline (1m) | Tuned (5m) |
|--------|---------------|------------|
| Total trades | Higher (~27–28 per symbol) | Lower (fewer false breakouts) |
| Net win rate | ~15% | Should improve or losses shrink |
| Median hold time | ~4 minutes | Longer (wider trail + 5m bars) |
| Commission drag | Dominates at stake=1 | Reduced at stake=10 |
| Exit reasons | Many `trailing_exit` within 5 bars | Fewer immediate trailing exits |

## Baseline reference (failed run 629cfd7007…)

- AAPL: -0.16% return, 4/27 wins, median hold 4 min
- AMD: -0.37% return, 4/28 wins, median hold 4 min

## Results (2026-05-25 validation run)

| | Baseline 1m AAPL | Tuned 5m AAPL | Baseline 1m AMD | Tuned 5m AMD |
|---|---|---|---|---|
| Return | -0.16% | -0.19% | -0.37% | -0.23% |
| Trades | 27 | 3 | 28 | 5 |
| Wins | 4 | 1 | 4 | 2 |
| Net PnL | -$16.48 | -$18.81 | -$36.73 | -$23.07 |
| Median hold | 4 min | 50 min | 4 min | 45 min |
| Dominant exit | trailing_exit (19) | trailing_exit (3) | trailing_exit (23) | trailing_exit (3) |

Tuned config materially reduced churn and lengthened holds. AMD loss shrank; AAPL still lost at stake 10
with commission but with far fewer trades. Neither config is profitable on this window — the goal was
lower noise and clearer diagnostics, not guaranteed edge.
