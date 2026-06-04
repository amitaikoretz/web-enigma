# Market-Data Sentiment Features and Pipeline

This document defines a market-data-only feature set for approximating short-horizon
market or sector sentiment in the past hours or day. The goal is to infer a latent
`risk-on / risk-off` state from OHLCV and benchmark data, without using news, social,
or other text sources.

**Primary code context in this repo**
- Existing indicator helpers: `src/app/risk/features/indicators.py`
- Existing feature assembly: `src/app/risk/features/assemble.py`
- Dataset wiring: `src/app/risk/dataset/builder.py`
- Feature column selection: `src/app/risk/dataset/feature_columns.py`

**Design assumptions**
- Windows are expressed in bars, not calendar time.
- The same formulas can be applied to intraday or daily data.
- All features must be computed point-in-time using bars at or before the decision bar.
- When benchmark or sector frames are available, we compare local market state against them
  to build relative-strength and breadth signals.

---

## Feature Spec

### 1. Return and trend features

| Feature | Description | Formula |
|---|---|---|
| `ret_1` | Latest 1-bar return | `close[t] / close[t-1] - 1` |
| `ret_4` | Short-horizon momentum | `close[t] / close[t-4] - 1` |
| `ret_12` | Intraday/day momentum | `close[t] / close[t-12] - 1` |
| `ret_24` | Multi-hour / 1-day momentum | `close[t] / close[t-24] - 1` |
| `ret_accel_4_24` | Short-term momentum minus medium-term momentum | `ret_4 - ret_24` |
| `log_trend_12` | Trend slope over recent bars | OLS slope of `log(close)` on bar index over last 12 bars |
| `log_trend_24` | Trend slope over recent bars | OLS slope of `log(close)` on bar index over last 24 bars |
| `distance_sma_12` | Distance from short moving average | `close[t] / sma(close, 12)[t] - 1` |
| `distance_sma_24` | Distance from medium moving average | `close[t] / sma(close, 24)[t] - 1` |
| `momentum_z_24` | Return surprise vs recent history | Z-score of latest 1-bar return in trailing 24-bar window |

**Interpretation**
- Positive values suggest risk appetite or bullish pressure.
- Strong acceleration indicates improving sentiment, while a negative spread between short and medium horizons often signals fading enthusiasm.

### 2. Volatility and stress features

| Feature | Description | Formula |
|---|---|---|
| `rv_12` | Short realized volatility | `std(log(close[t-i] / close[t-i-1])) for i in 1..12` |
| `rv_24` | Medium realized volatility | `std(log(close[t-i] / close[t-i-1])) for i in 1..24` |
| `rv_ratio_12_24` | Volatility expansion / contraction | `rv_12 / rv_24` |
| `true_range_pct_1` | Latest bar range normalized by close | `(high[t] - low[t]) / close[t]` |
| `atr_pct_14` | Volatility scaled to price | `atr(high, low, close, 14)[t] / close[t]` |
| `downside_rv_24` | Downside volatility | `std(min(r_i, 0))` over trailing 24 returns |
| `tail_move_count_24` | Extreme move frequency | Count of bars where `abs(r_i) > k * rolling_std(r)` |
| `vol_of_vol_24` | Volatility instability | `std(rv_window)` over trailing 24 bars |

**Interpretation**
- Rising volatility with weak returns usually aligns with stress or de-risking.
- A fast rise in realized vol is often more informative than the level alone.

### 3. Liquidity and participation features

| Feature | Description | Formula |
|---|---|---|
| `volume_z_24` | Relative volume surprise | Z-score of latest volume vs trailing 24-bar window |
| `rel_volume_24` | Latest volume vs recent average | `volume[t] / mean(volume[t-23..t])` |
| `dollar_volume_24` | Trading activity in dollars | `mean(close * volume)` over trailing 24 bars |
| `turnover_z_24` | Turnover surprise | Z-score of `volume / shares_outstanding` if available |
| `amihud_illiquidity_24` | Price impact proxy | `mean(abs(r_i) / dollar_volume_i)` over trailing 24 bars |
| `range_volume_imbalance_24` | Range vs volume tension | `mean((high - low) / volume)` over trailing 24 bars |
| `gap_pct` | Overnight or bar-to-bar gap | `open[t] / close[t-1] - 1` |

**Interpretation**
- Strong sentiment often comes with higher participation, not just higher prices.
- Illiquidity spikes can indicate panic, forced selling, or crowded positioning.

### 4. Breadth and cross-sectional sentiment proxies

These require a universe frame at the same timestamp, such as all names in a market basket or sector basket.

| Feature | Description | Formula |
|---|---|---|
| `advancer_frac` | Share of names with positive return | `count(r_i > 0) / N` |
| `decliner_frac` | Share of names with negative return | `count(r_i < 0) / N` |
| `adv_dec_spread` | Breadth balance | `advancer_frac - decliner_frac` |
| `median_cross_sectional_ret` | Typical name performance | `median(r_i)` across universe |
| `return_dispersion` | Cross-sectional disagreement | `std(r_i)` across universe |
| `correlation_breadth` | Co-movement stress | Average pairwise correlation of recent returns across names |
| `new_high_low_spread` | Regime confirmation | `count(new_highs) - count(new_lows)` over trailing window |

**Interpretation**
- Broad positive breadth is a cleaner bullish signal than a single large-cap move.
- High dispersion can mean disagreement, uncertainty, or selective rotation.

### 5. Relative-strength features

These compare a market, sector, or symbol to a benchmark or broader basket.

| Feature | Description | Formula |
|---|---|---|
| `market_vs_benchmark_ret_24` | Relative momentum vs benchmark | `ret_24(market) - ret_24(benchmark)` |
| `market_vs_benchmark_trend_24` | Relative trend slope | `log_trend_24(market) - log_trend_24(benchmark)` |
| `sector_vs_market_ret_24` | Sector sentiment vs market | `ret_24(sector) - ret_24(market)` |
| `sector_vs_market_rv_24` | Sector stress relative to market | `rv_24(sector) - rv_24(market)` |
| `sector_rank_ret_24` | Relative rank among sectors | Rank of `ret_24(sector)` within all sectors |
| `sector_rank_breadth_24` | Breadth rank among sectors | Rank of `adv_dec_spread(sector)` within all sectors |
| `relative_strength_24` | Normalized relative performance | `zscore(ret_24(symbol) - ret_24(benchmark))` |

**Interpretation**
- Relative-strength features are often more stable than raw market features.
- For sector sentiment, the key signal is usually "sector outperforms the market" rather than absolute sector return.

### 6. Regime and regime-change features

| Feature | Description | Formula |
|---|---|---|
| `risk_on_score` | Composite latent bullishness score | Weighted sum of returns, breadth, liquidity, and volatility normalization |
| `risk_off_score` | Composite latent stress score | Weighted sum of negative returns, breadth weakness, vol expansion, and illiquidity |
| `sentiment_change_4_24` | Fast change in regime | `risk_on_score_4 - risk_on_score_24` |
| `sentiment_surprise_24` | Deviation from trailing baseline | `risk_on_score - rolling_mean(risk_on_score, 24 or 60)` |
| `sentiment_reversal` | Short-term reversal condition | `ret_1 - ret_12` or `risk_on_score_4 - risk_on_score_24` |

**Suggested composite construction**

```text
risk_on_score =
  z(ret_24)
  + z(adv_dec_spread)
  + z(rel_volume_24)
  + z(market_vs_benchmark_ret_24)
  - z(rv_24)
  - z(amihud_illiquidity_24)

risk_off_score =
  z(-ret_24)
  + z(rv_24)
  + z(return_dispersion)
  + z(amihud_illiquidity_24)
  - z(adv_dec_spread)
```

The exact weights can start equal and later be learned or tuned.

---

## Recommended Pipeline Plan

This section turns the feature spec into a Python pipeline that fits the existing risk-model architecture.

### Pipeline goals

1. Produce point-in-time market features for each candidate timestamp.
2. Support both market-wide and sector-relative sentiment proxies.
3. Keep the feature set modular so new windows and new universes can be added without rewriting the dataset builder.
4. Preserve compatibility with the existing `FeatureSnapshotRecord` and dataset join logic.

### Proposed stages

#### Stage 1: Input normalization

Create a normalized OHLCV frame per symbol, benchmark, and sector basket.

Responsibilities:
- Sort by timestamp
- Enforce numeric dtypes for `Open`, `High`, `Low`, `Close`, `Volume`
- Drop or flag invalid rows
- Align timestamps across symbols when building cross-sectional features

Suggested location:
- `src/app/risk/features/market_sentiment.py`

#### Stage 2: Single-series feature helpers

Implement reusable helpers for:
- returns
- rolling z-scores
- realized volatility
- ATR and true range
- moving averages and trend slopes
- illiquidity and volume ratios

These helpers should mirror the style of `src/app/risk/features/indicators.py`.

#### Stage 3: Cross-sectional feature helpers

Add functions that take a synchronized universe frame and compute:
- advance/decline statistics
- dispersion
- correlation breadth
- sector rank features
- sector-vs-market relative features

This stage should accept a mapping like:

```text
{symbol -> bar frame at timestamp}
```

or a pre-joined panel frame if the data source already provides one.

#### Stage 4: Composite sentiment scores

Build a small set of composite factors:
- `risk_on_score`
- `risk_off_score`
- `sentiment_change`
- `sentiment_surprise`

Keep the composites deterministic and explainable so they can be audited during model review.

#### Stage 5: Snapshot assembly

Extend the existing feature snapshot builder so that each candidate gets:
- market-only sentiment proxies
- optional benchmark-relative values
- optional sector-relative values when a sector universe is available

Recommended behavior:
- compute all features at the candidate's decision bar
- return `None` or `NaN` when the required lookback is unavailable
- set a quality flag when the history is insufficient

#### Stage 6: Dataset join and column selection

Once the snapshot is written into the dataset parquet, update the feature column selector so the new numeric columns are included automatically.

The existing selection pattern in `src/app/risk/dataset/feature_columns.py` already supports:
- snapshot fields
- candidate numeric metadata
- prefixed metadata columns

That means the new feature set should be mostly additive if the snapshot schema is expanded consistently.

---

## Suggested Python Module Layout

If implemented in code, the pipeline could be organized like this:

```text
src/app/risk/features/
  indicators.py                # low-level math helpers
  market_sentiment.py          # market-only sentiment feature helpers
  assemble.py                  # per-candidate snapshot assembly

src/app/risk/dataset/
  builder.py                   # dataset join + parquet writing
  feature_columns.py           # final model column selection
```

### Planned function groups

- `compute_return_features(frame, windows)`
- `compute_volatility_features(frame, windows)`
- `compute_liquidity_features(frame, windows)`
- `compute_cross_sectional_features(panel, universe)`
- `compute_relative_strength_features(symbol_frame, benchmark_frame, sector_frame)`
- `compute_sentiment_scores(feature_row)`
- `build_market_sentiment_snapshot(candidate, frame, benchmark_frame, sector_frame, config)`

---

## Implementation Order

1. Add single-series market sentiment helpers.
2. Add benchmark-relative features.
3. Add sector-relative and breadth features.
4. Add composite risk-on / risk-off scores.
5. Wire the new snapshot fields into `assemble.py`.
6. Update tests to verify point-in-time safety and window correctness.
7. Add dataset-level checks to confirm the new columns are selected and persisted.

---

## Validation Checklist

- Features must not read future bars.
- All rolling windows should be explicit in bars.
- Cross-sectional features must use synchronized timestamps.
- Composite scores should remain interpretable from their components.
- Missing benchmark or sector data should degrade gracefully rather than fail the entire snapshot.

---

## Initial Feature Set Recommendation

If you want a compact first version, start with:

- `ret_1`
- `ret_12`
- `ret_24`
- `ret_accel_4_24`
- `log_trend_12`
- `rv_12`
- `rv_24`
- `rv_ratio_12_24`
- `volume_z_24`
- `rel_volume_24`
- `amihud_illiquidity_24`
- `adv_dec_spread`
- `return_dispersion`
- `market_vs_benchmark_ret_24`
- `sector_vs_market_ret_24`
- `risk_on_score`
- `risk_off_score`

That set is small enough to reason about, but still captures level, change, breadth, liquidity, and relative strength.
