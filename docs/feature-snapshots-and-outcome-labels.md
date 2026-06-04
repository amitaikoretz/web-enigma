# Feature Snapshots and Outcome Labels

This document describes the **Feature Snapshots** and **Outcome Labels** produced by the risk-model dataset pipeline (V1). Each backtest candidate event gets one feature row (point-in-time market context) and one outcome label (simulated forward path).

**Version identifiers:** `features_v1` / `labels_v1` (see `configs/risk_v1.yaml`)

**Primary code:**
- Features: `src/app/risk/features/assemble.py`, `src/app/risk/features/indicators.py`
- Labels: `src/app/risk/labels/path_labels.py`
- Schema: `src/app/output/models.py` (`FeatureSnapshotRecord`, `OutcomeLabelRecord`)
- Dataset assembly: `src/app/risk/dataset/builder.py`
- Backtest sidecars: `*.features.parquet`, `*.labels.parquet`

The repo-wide parquet schema index lives in [docs/parquet-schema-contracts.md](./parquet-schema-contracts.md).

---

## Overview

| Artifact | One row per | Purpose |
|----------|-------------|---------|
| Feature snapshot | Candidate | Market state at decision time, using only bars at or before the candidate timestamp |
| Outcome label | Candidate | Simulated trade outcome over a forward horizon (stop, target, or time exit) |

Both are keyed by `candidate_id` and written as parquet sidecars alongside backtest reports. They can be joined with candidate metadata to build a training dataset for the momentum risk model.

---

## Feature Snapshots (`features_v1`)

### Identity and quality

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | string | Join key to the candidate record |
| `feature_version` | string | Schema version (default: `features_v1`) |
| `feature_timestamp` | string (ISO datetime) | Timestamp of the last bar used for computation |
| `feature_quality_flag` | enum | `OK` or `INSUFFICIENT_HISTORY` |

When history is too short (fewer than `min_history_bars`, default 60) or no bar exists at/before the candidate timestamp, only identity and metadata fields are populated; numeric features are `null` and the quality flag is `INSUFFICIENT_HISTORY`.

Candidate metadata (scalar values only: bool, int, float, str, null) is flattened into `metadata_features` with a `meta_` prefix (e.g. `meta_volume_ok`). These columns are expanded when writing parquet.

### Point-in-time rules

- Features use bars **at or before** the candidate timestamp (`bar_index_at_or_before`).
- No future bars, future index data, or forward-filled bad prices are used.
- Verified by tests: mutating future bars does not change computed features.

### Price and trend features

| Field | Window / method | Definition |
|-------|-----------------|------------|
| `return_5` | 5 bars | `close[-1] / close[-6] - 1` |
| `return_10` | 10 bars | `close[-1] / close[-11] - 1` |
| `return_20` | 20 bars | `close[-1] / close[-21] - 1` |
| `trend_slope_20` | 20 bars | OLS slope of `log(close)` vs bar index |
| `trend_slope_50` | 50 bars | OLS slope of `log(close)` vs bar index |
| `sma_20_distance` | SMA(20) | `close[-1] / sma20[-1] - 1` |
| `sma_50_distance` | SMA(50) | `close[-1] / sma50[-1] - 1` |
| `rsi_14` | 14 bars | Wilder-style RSI on close |
| `return_zscore_20` | 20 bars | Z-score of the latest 1-bar return within a 20-bar window |
| `gap_pct` | 1 bar | `open[-1] / close[-2] - 1` |
| `consecutive_up_bars` | — | Count of consecutive higher closes ending at the decision bar |

> **Note:** Windows are **bar counts**, not calendar days. On 5-minute data, `return_20` spans ~100 minutes.

### Volume and liquidity features

| Field | Window / method | Definition |
|-------|-----------------|------------|
| `volume_zscore_20` | 20 bars | Z-score of latest volume vs 20-bar window |
| `relative_volume_20` | 20 bars | `volume[-1] / mean(volume[-20:])` |
| `dollar_volume_20` | 20 bars | Mean of `close × volume` over last 20 bars |
| `volume_percentile_60` | 60 bars (configurable) | Percentile rank of latest volume within window |

### Volatility features

| Field | Window / method | Definition |
|-------|-----------------|------------|
| `atr_14_pct` | ATR(14) | `ATR(14) / close[-1]` |
| `realized_vol_10` | 10 bars | Std dev of log returns over last 10 bars |
| `realized_vol_20` | 20 bars | Std dev of log returns over last 20 bars |
| `vol_percentile_60` | 60 bars (configurable) | Percentile rank of latest 20-bar realized vol within window |
| `atr_expansion_10_50` | 10 vs 50 bars | Mean true range over 10 bars / mean true range over 50 bars |

### Index / benchmark features

Computed when `include_index_features: true` (default) and a benchmark frame (default: SPY) is available.

| Field | Window / method | Definition |
|-------|-----------------|------------|
| `index_return_20` | 20 bars | Benchmark close return over 20 bars |
| `index_trend_slope_50` | 50 bars | OLS log-slope of benchmark close |
| `correlation_to_index_60` | 60 bars | Pearson correlation of symbol vs index log returns |
| `beta_to_index_60` | 60 bars | Covariance(symbol, index) / variance(index) on log returns |

### Not yet implemented (spec only)

The original spec (`momentum_risk_model_agent_spec.md`) also describes features that are **not** in V1:

- `relative_strength_index`, `relative_strength_sector`
- `sector_return_20`, `sector_trend_slope_50`
- `market_breadth`
- `spread_bps`
- `same_sector_current_exposure`, `portfolio_corr_exposure`

V1 adds `return_zscore_20`, `volume_percentile_60`, and `consecutive_up_bars` (spec had `consecutive_up_days`). Vol percentile uses a 60-bar window (spec had 252).

---

## Outcome Labels (`labels_v1`)

### Identity and plan parameters

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | string | Join key to the candidate record |
| `label_version` | string | Schema version (default: `labels_v1`) |
| `entry_price` | float | Resolved fill price (may differ from planned price for next-bar entry) |
| `horizon_bars` | int | Maximum forward bars to simulate (`planned_horizon_bars`) |
| `stop_pct` | float | Planned stop distance as fraction of entry (e.g. 0.03 = 3%) |
| `target_pct` | float \| null | Planned target distance as fraction of entry; null if no target |

### Path metrics

| Field | Description |
|-------|-------------|
| `mae_pct` | Maximum adverse excursion: worst `low / entry - 1` over the path |
| `mae_abs_pct` | `abs(min(mae_pct, 0))` — magnitude of worst drawdown |
| `mae_atr` | `mae_abs_pct / atr_14_pct` from the feature snapshot (null if ATR unavailable) |
| `mfe_pct` | Maximum favorable excursion: best `high / entry - 1` over the path |
| `final_return_pct` | Return at exit: `exit_price / entry - 1` |
| `realized_R` | `final_return_pct / stop_pct` — outcome in R-multiples |

### Exit flags and timing

| Field | Description |
|-------|-------------|
| `hit_stop` | Stop price was touched |
| `hit_target` | Target price was touched |
| `hit_stop_before_target` | Stop hit, or time exit without hitting target |
| `bars_to_stop` | Bars from entry to stop (null if not hit) |
| `bars_to_target` | Bars from entry to target (null if not hit) |
| `bars_held` | Bars held before exit |
| `exit_reason` | `STOP`, `TARGET`, `TIME`, or `DATA_ERROR` |
| `label_quality_flag` | `OK`, `MISSING_BARS`, `BAD_PRICE`, or `AMBIGUOUS_INTRABAR` |

### Labeling logic

**Entry resolution**

- `entry_type=CLOSE` with `fill_model=close`: enter at the decision bar close (or provided `entry_price`).
- `entry_type=CLOSE` with `fill_model=next_bar`: treated as `NEXT_OPEN` — enter at the next bar's open.
- `entry_type=NEXT_OPEN`: enter at the next bar's open.

**Forward simulation (long only in V1)**

Starting from the bar after entry, each forward bar is checked in order:

1. Update running MAE/MFE from bar low/high.
2. Stop price = `entry × (1 - stop_pct)`.
3. Target price = `entry × (1 + target_pct)` when target is set.
4. If both stop and target are touched on the same bar → `AMBIGUOUS_INTRABAR`; policy resolves exit (default: `assume_stop_first`).
5. If only stop is touched → exit `STOP`.
6. If only target is touched → exit `TARGET`.
7. If horizon expires without stop/target → exit `TIME` at last bar's close.

**Quality flags**

| Flag | When |
|------|------|
| `OK` | Normal path; ambiguous intrabar may still set this with `AMBIGUOUS_INTRABAR` as a secondary signal via the same flag value |
| `MISSING_BARS` | No bar at decision time, no next bar for next-open entry, or no forward bars for simulation |
| `BAD_PRICE` | Invalid OHLC (NaN, inverted high/low, etc.) |
| `AMBIGUOUS_INTRABAR` | Stop and target both touched on the same bar |

**Ambiguous intrabar policy** (config: `assume_stop_first` or `assume_target_first`)

When stop and target are both hit within one bar, the policy chooses which exit to record. Default is stop-first (conservative).

**Scope limits**

- LONG candidates only; SHORT labeling raises `NotImplementedError`.
- `atr_14_pct` for `mae_atr` is taken from the paired feature snapshot when available.

---

## Configuration

From `configs/risk_v1.yaml`:

```yaml
risk_dataset:
  dataset_version: risk_dataset_v1
  label_version: labels_v1
  feature_version: features_v1

labels:
  ambiguous_intrabar_policy: assume_stop_first

features:
  min_history_bars: 60
  lookback_bars: 60
  winsorize_quantiles: [0.01, 0.99]
  vol_percentile_window: 60
  include_index_features: true
  default_benchmark_symbol: SPY
```

`winsorize_quantiles` is defined in config for downstream dataset processing; feature computation itself does not winsorize.

---

## Output and consumption

### Backtest sidecars

During a backtest run, `build_risk_auxiliary_for_run` computes labels and features per candidate. They are persisted as:

- `{run_id}.labels.parquet` — outcome labels
- `{run_id}.features.parquet` — feature snapshots

### Risk dataset builder

`build_risk_dataset` joins candidates + labels + features into a single parquet training file. It reuses existing sidecars when present, otherwise rebuilds from bar data via `BarStore`.

Join key: `candidate_id`.

---

## Example label outcomes

| Scenario | `exit_reason` | Notable fields |
|----------|---------------|----------------|
| Stop hit on bar 2 | `STOP` | `hit_stop=true`, `hit_stop_before_target=true`, `bars_to_stop=2` |
| Target hit on bar 1 | `TARGET` | `hit_target=true`, `hit_stop_before_target=false` |
| Horizon expires | `TIME` | `hit_stop_before_target=true` (no target reached) |
| Stop and target same bar | `STOP` or `TARGET` | `label_quality_flag=AMBIGUOUS_INTRABAR` |
| No forward data | `DATA_ERROR` | `label_quality_flag=MISSING_BARS` |

---

## Related tests

- `tests/test_risk_features.py` — point-in-time safety, insufficient history, metadata flattening
- `tests/test_risk_labels.py` — stop, target, time, ambiguous intrabar, missing bars, next-open entry
- `tests/test_backtest_artifacts.py` — sidecar persistence for labels and features
