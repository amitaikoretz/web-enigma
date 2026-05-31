# volume_rally A/B validation

Compare the failed 1m baseline against the tuned 5m configuration on AAPL and AMD
(2026-04-25 through 2026-05-25).

Requires Alpaca credentials in the environment.

## Run

```bash
kalyxctl run \
  --config experiments/volume_rally_baseline_1m.yaml \
  --output /tmp/volume-rally-baseline.json

kalyxctl run \
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

## Gross edge (2026-05-25)

Config: [`experiments/volume_rally_gross_edge_5m.yaml`](volume_rally_gross_edge_5m.yaml) — zero commission, wider trail/target.

| | AAPL | AMD |
|---|---|---|
| Return | -0.10% | -0.15% |
| Trades | 3 | 4 |
| Net PnL | -$10.05 | -$15.15 |
| Max loss | -$9.15 | **-$152.50** |

Gross PnL still negative — confirms fees were not the only problem. AMD hit two `atr_target` wins but one large `trailing_exit` loss dominated.

## V2 (2026-05-25)

Config: [`experiments/volume_rally_v2_5m.yaml`](volume_rally_v2_5m.yaml) — session window, close strength, 1 trade/session, breakeven, stale exit, tighter initial stop.

```bash
kalyxctl run \
  --config experiments/volume_rally_v2_5m.yaml \
  --output /tmp/volume-rally-v2-5m.json
```

| | AAPL | AMD |
|---|---|---|
| Return | 0.00% | 0.00% |
| Trades | **0** | **0** |

V2 filters blocked every entry on this window (Apr–May 2026). That eliminates the May 6 AMD -$152 loss but also removes the two target hits. Next tuning step: relax one lever at a time (e.g. `min_close_strength: 0.55`, or `session_start_minutes: 15`) and re-run against gross-edge.

## V2 relaxed (2026-05-25)

Config: [`experiments/volume_rally_v2_relaxed_5m.yaml`](volume_rally_v2_relaxed_5m.yaml) — vs strict v2:

- `volume_spike_mult`: 3.5 → **3.0**
- `session_start_minutes`: 30 → **15** (9:45 ET)
- `min_close_strength`: 0.65 → **0.55**

```bash
kalyxctl run \
  --config experiments/volume_rally_v2_relaxed_5m.yaml \
  --output /tmp/volume-rally-v2-relaxed-5m.json
```

| | AAPL | AMD | Total |
|---|---|---|---|
| Return | **+0.03%** | 0.00% | — |
| Trades | 1 | 0 | 1 |
| Net PnL | **+$2.60** | $0 | **+$2.60** |
| Max loss | — | — | (none) |

Single trade: AAPL May 6 14:45, `trailing_exit`, +$2.60. AMD still flat — May 6 -$152 and May 8/11 winners all remain filtered out. Relaxed v2 beats gross-edge on this window (+$2.60 vs -$25.20) but sample size is one trade.

## V2 tuned — 8 symbols (2026-05-25)

Config: [`experiments/volume_rally_v2_tuned_5m.yaml`](volume_rally_v2_tuned_5m.yaml)

Changes vs relaxed:
- `session_start_minutes`: 15 → **5** (9:35 ET; blocks 9:30 open bar only)
- `min_close_strength`: 0.55 → **0.50**
- `volume_spike_mult`: 3.0 → **2.8**
- Symbols: **AAPL, AMD, NVDA, MSFT, META, TSLA, GOOGL, AMZN**

```bash
kalyxctl run \
  --config experiments/volume_rally_v2_tuned_5m.yaml \
  --output /tmp/volume-rally-v2-tuned-5m.json
```

| Symbol | Return | Trades | Net PnL | Notes |
|--------|--------|--------|---------|-------|
| **AMD** | **+0.64%** | 2 | **+$63.65** | May 8 `atr_target` +$128.55; May 19 `atr_stop` -$64.90 |
| AAPL | -0.09% | 2 | -$9.00 | +$2.60 win, -$11.60 stop |
| MSFT | -0.28% | 2 | -$27.70 | both `atr_stop` |
| GOOGL | -0.36% | 2 | -$36.05 | both `trailing_exit` |
| NVDA | -0.47% | 5 | -$47.05 | 0 wins — most churn |
| TSLA | -0.61% | 2 | -$61.20 | both `atr_stop` -$30.60 |
| META | 0.00% | 0 | $0 | no signals |
| AMZN | 0.00% | 0 | $0 | no signals |
| **Total** | — | **15** | **-$117.35** | 2/15 wins |

Auditor rejections (20): `session_window` 17, `weak_close` 2, `cooldown` 1. Loosening session to 5 min recovered AMD May 8 target without reopening May 6 open-bar disaster.

**Tuned B** ([`volume_rally_v2_tuned_b_5m.yaml`](volume_rally_v2_tuned_b_5m.yaml) — tighter ADX/spike, wider initial SL) cut trades to 7 but **removed AMD winner**; total PnL -$113.40. **Tuned A is better** on this window.

Next levers: symbol-specific params (NVDA/TSLA need stricter filters), longer date range, or drop chronic losers from universe.

## V2 core universe (2026-05-25)

Config: [`experiments/volume_rally_v2_core_5m.yaml`](volume_rally_v2_core_5m.yaml) — AAPL, AMD, MSFT only, tuned A params.

```bash
kalyxctl run \
  --config experiments/volume_rally_v2_core_5m.yaml \
  --output /tmp/volume-rally-v2-core-5m.json
```

| Symbol | Return | Trades | Net PnL |
|--------|--------|--------|---------|
| **AMD** | **+0.64%** | 2 | **+$63.65** |
| AAPL | -0.09% | 2 | -$9.00 |
| MSFT | -0.28% | 2 | -$27.70 |
| **Total** | — | **6** | **+$26.95** |

First **positive** portfolio result on this window — AMD target hit dominates; dropping NVDA/TSLA/GOOGL removes drag.

## V2 per-symbol volume spikes (2026-05-25)

Config: [`experiments/volume_rally_v2_symbol_spikes_5m.yaml`](volume_rally_v2_symbol_spikes_5m.yaml)

Spike tiers: AAPL/AMD **2.8**, MSFT/GOOGL/META/AMZN **3.0**, NVDA **3.5**, TSLA **4.0**.

```bash
kalyxctl run \
  --config experiments/volume_rally_v2_symbol_spikes_5m.yaml \
  --output /tmp/volume-rally-v2-symbol-spikes-5m.json
```

| Symbol | Spike | Trades | Net PnL | vs uniform |
|--------|-------|--------|---------|------------|
| AMD | 2.8 | 2 | **+$63.65** | same |
| NVDA | 3.5 | **0** | $0 | **+$47.05** (was -$47) |
| TSLA | 4.0 | 1 | -$30.60 | **+$30.60** (was -$61) |
| GOOGL | 3.0 | 2 | -$36.05 | same |
| MSFT | 3.0 | 2 | -$27.70 | same |
| AAPL | 2.8 | 2 | -$9.00 | same |
| **Total** | — | **9** | **-$39.70** | **+$77.65** vs uniform 8-sym |

Per-symbol spikes eliminate NVDA churn entirely and halve TSLA losses while preserving the AMD winner. Full 8-symbol still net negative; **core 3-symbol is the only profitable basket** on Apr–May 2026.
