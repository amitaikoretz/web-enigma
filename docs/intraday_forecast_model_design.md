# Intraday Forecast Model Design

This document defines a practical first version of an **intraday expected return forecast model** for liquid US equities or ETFs.

The goal is not to predict large moves. The goal is to estimate a small, tradable edge over a short horizon, then convert that edge into a disciplined position size after costs.

## 1. Scope and Assumptions

### Scope

- Asset class: liquid US equities or ETFs
- Bar size: 1, 5, or 15 minutes
- Default forecast horizon: 5 minutes
- Trading style: long-only or long/short depending on downstream execution support
- Target: forecast **midquote return** or **midprice return** over the next horizon

### Default assumptions

- Use only point-in-time data available at decision time
- Measure all forecasts net of spread, fees, and slippage
- Refit on a rolling schedule
- Trade only when expected edge exceeds a minimum execution threshold

### Design principle

Intraday models should be judged on **net tradability**, not raw prediction quality. A model that predicts well but loses after execution costs is not useful.

---

## 2. Forecast Target

### Primary label

Let:

```text
y_t = log(mid_{t+h}) - log(mid_t)
```

Where:

- `mid_t` is the midpoint of best bid and best ask at decision time
- `h` is the forecast horizon in bars
- `y_t` is the forward log return

### Optional trading label

For execution-aware training, define:

```text
y_t_net = y_t - estimated_cost_t
```

Where estimated cost includes:

- half-spread or spread crossing
- commission / fees
- slippage
- an optional conservative impact allowance

### Recommended horizons

- 1 bar: very noisy, only if execution is extremely strong
- 5 bars: default starting point
- 15 bars: useful if the signal is slower and turnover needs to drop

---

## 3. Feature Schema

This schema is designed for **intraday microstructure forecasting**. It intentionally avoids fundamentals and long-horizon valuation inputs.

### 3.1 Record identity

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker or instrument ID |
| `timestamp` | datetime | Decision timestamp in exchange timezone or UTC |
| `bar_interval` | string | Bar size used for the sample, e.g. `1m`, `5m`, `15m` |
| `horizon_bars` | int | Forecast horizon in bars |
| `session_date` | date | Trading session date |
| `session_minute_index` | int | Minutes or bars since market open |
| `market_regime_id` | string | Optional regime label if available |

### 3.2 Lean v1 feature set

The v1 model should start small. Use these as the core features only:

#### Price and return

| Field | Type | Window | Definition |
|-------|------|--------|------------|
| `ret_1` | float | 1 bar | Latest log return |
| `ret_5` | float | 5 bars | Log return over last 5 bars |
| `ret_20` | float | 20 bars | Log return over last 20 bars |
| `ret_z_20` | float | 20 bars | Z-score of latest 1-bar return |
| `range_pct_1` | float | 1 bar | `(high - low) / close` |
| `close_to_high_pct` | float | 1 bar | `(high - close) / range` |
| `close_to_low_pct` | float | 1 bar | `(close - low) / range` |

#### Trend

| Field | Type | Window | Definition |
|-------|------|--------|------------|
| `sma_20_dist` | float | 20 bars | `close / sma_20 - 1` |
| `ema_9_dist` | float | 9 bars | `close / ema_9 - 1` |
| `trend_slope_20` | float | 20 bars | OLS slope of `log(close)` over bar index |
| `rsi_14` | float | 14 bars | Wilder RSI on close |
| `consecutive_up_bars` | int | n/a | Count of consecutive higher closes |

#### Volume, flow, and liquidity

| Field | Type | Window | Definition |
|-------|------|--------|------------|
| `volume_1` | float | 1 bar | Latest bar volume |
| `volume_z_20` | float | 20 bars | Z-score of latest volume |
| `relative_volume_20` | float | 20 bars | Latest volume / mean volume |
| `order_imbalance` | float | 1 bar | `(bid_size - ask_size) / (bid_size + ask_size)` or equivalent |
| `spread_bps` | float | 1 bar | `(ask - bid) / mid * 10000` |
| `depth_imbalance` | float | 1 bar | `(bid_depth - ask_depth) / (bid_depth + ask_depth)` |
| `dollar_volume_20` | float | 20 bars | Mean `close * volume` |

#### Volatility

| Field | Type | Window | Definition |
|-------|------|--------|------------|
| `realized_vol_10` | float | 10 bars | Std dev of log returns |
| `realized_vol_20` | float | 20 bars | Std dev of log returns |
| `atr_pct_14` | float | 14 bars | ATR / close |
| `vol_expansion_20_60` | float | 20 vs 60 bars | Short vol / long vol |

#### Market context

| Field | Type | Window | Definition |
|-------|------|--------|------------|
| `time_of_day_sin` | float | n/a | Cyclical time encoding |
| `time_of_day_cos` | float | n/a | Cyclical time encoding |
| `minute_of_session` | int | n/a | Bars or minutes since open |
| `day_of_week` | int | n/a | Monday to Friday |

### 3.3 Feature quality and missingness

| Field | Type | Description |
|-------|------|-------------|
| `feature_version` | string | Version tag for the schema |
| `feature_quality_flag` | enum | `OK`, `INSUFFICIENT_HISTORY`, `BAD_DATA` |
| `missing_feature_count` | int | Count of unavailable numeric features |
| `stale_data_flag` | bool | True if feed latency or stale bar issues exist |

### 3.4 Exclusions

Do not include these in the first version:

- forward-looking or post-trade features
- non-point-in-time fundamentals
- post-close information
- future index values
- any feature that would not be available at decision time

### 3.5 Challenger features for later

These are reasonable candidates for v2 or later if v1 is stable:

- `ret_3`
- `ret_10`
- `gap_pct`
- `sma_5_dist`
- `ema_21_dist`
- `trend_slope_50`
- `consecutive_down_bars`
- `signed_volume_1`
- `signed_volume_5`
- `trade_imbalance`
- `spread_z_20`
- `bid_depth`
- `ask_depth`
- `dollar_depth`
- `illiquidity_proxy`
- `range_mean_20`
- `vol_percentile_60`
- `index_ret_5`
- `index_ret_20`
- `index_trend_slope_50`
- `index_vol_20`
- `beta_to_index_60`
- `corr_to_index_60`
- `vix_level`
- `vix_change_1d`

---

## 4. Model Output Schema

The forecast model should emit more than a point estimate.

| Field | Type | Description |
|-------|------|-------------|
| `pred_return` | float | Forecast log return over the horizon |
| `pred_return_net` | float | Forecast return after estimated execution cost |
| `pred_vol` | float | Forecast short-horizon volatility |
| `pred_quantile_10` | float | Lower-tail return estimate |
| `pred_quantile_50` | float | Median return estimate |
| `pred_quantile_90` | float | Upper-tail return estimate |
| `confidence` | float | Model confidence or forecast strength score |
| `expected_edge_bps` | float | `pred_return_net` expressed in basis points |
| `model_version` | string | Model artifact version |
| `feature_version` | string | Feature schema version |

---

## 5. Walk-Forward Backtest Design

The backtest must simulate how the model would be trained and used in production.

### 5.1 Backtest unit

Each decision point is one row:

- symbol
- timestamp
- features available at that time
- forecast produced by a model trained only on past data
- realized future return over the horizon
- realized trading PnL after costs

### 5.2 Data split protocol

Use chronological splits only.

Recommended structure:

1. **Training window**: past `N` days or weeks
2. **Validation window**: the next contiguous block
3. **Test window**: the following contiguous block
4. Roll forward and repeat

Examples:

- Train on the last 60 trading days, validate on the next 5, test on the next 5
- Train on the last 90 trading days, then re-estimate daily and trade the next session

### 5.3 Walk-forward schedule

Recommended default:

- retrain daily after the session close, or
- retrain every `k` bars if the signal drifts quickly

For each test period:

1. Fit preprocessing on training data only
2. Fit the model on training data only
3. Tune thresholds on validation data only
4. Freeze parameters
5. Generate predictions on the next out-of-sample block
6. Apply trading rules
7. Record realized PnL and diagnostics

### 5.4 Leakage controls

The backtest must explicitly prevent:

- future bars leaking into feature windows
- training on data from the test period
- selecting thresholds on the final test period
- using close prices from bars that would not have been known yet
- using survivor-biased universes

### 5.5 Execution model

Backtest execution should include:

- spread crossing or half-spread cost
- slippage model
- commissions or fees
- optional market impact
- order delay if the live system does not execute instantly

Minimum recommendation:

```text
net_pnl = gross_pnl - spread_cost - slippage_cost - commission_cost - impact_cost
```

### 5.6 Evaluation metrics

Report all of the following:

- mean forecast error
- correlation between forecast and realized return
- directional hit rate
- average gross and net return per trade
- profit factor
- Sharpe ratio after costs
- max drawdown
- turnover
- average holding period
- hit rate by time of day
- performance by forecast decile
- performance by volatility regime
- performance by spread regime

### 5.7 Required baselines

Compare against:

- zero forecast
- lagged return only
- simple momentum rule
- simple mean-reversion rule
- random entry with identical exits and costs

If the model does not beat these baselines out of sample after costs, do not promote it.

---

## 6. Trading Rule and Position Sizing

This section converts the forecast into a tradeable position.

### 6.1 Core idea

Position size should depend on:

- expected edge
- forecast uncertainty
- execution cost
- available risk budget
- current volatility
- liquidity constraints

Do not size directly from raw forecast alone.

### 6.2 Basic decision rule

Trade only when the forecasted net edge exceeds a minimum threshold:

```text
if expected_edge_bps <= threshold_bps:
    size = 0
```

Recommended threshold inputs:

- spread cost
- slippage estimate
- minimum required alpha cushion

### 6.3 Signal normalization

Define a normalized signal:

```text
signal = expected_edge_bps / forecast_risk_bps
```

Where `forecast_risk_bps` can be derived from predicted short-horizon volatility or a rolling historical volatility estimate.

### 6.4 Risk-budgeted sizing

For long-only:

```text
desired_risk_dollars = account_equity * max_risk_fraction
unit_risk_dollars = entry_price * stop_distance_pct
raw_size = desired_risk_dollars / unit_risk_dollars
```

Then scale by forecast quality:

```text
quality_scale = clamp(signal / target_signal, 0, 1)
final_size = raw_size * quality_scale
```

Where:

- `target_signal` is the minimum signal strength required for full size
- `clamp(x, 0, 1)` limits the scale to `[0, 1]`

### 6.5 Volatility adjustment

Use a volatility scaler to reduce size in noisy regimes:

```text
vol_scale = target_vol / max(pred_vol, floor_vol)
```

Then:

```text
final_size = raw_size * quality_scale * vol_scale
```

Cap `vol_scale` to avoid over-levering extremely quiet conditions.

### 6.6 Liquidity cap

Position size must also satisfy liquidity constraints:

```text
final_size <= max_participation_rate * expected_bar_volume
final_size <= max_notional_by_depth / entry_price
```

Suggested participation caps:

- conservative: 1% to 2% of bar volume
- moderate: 3% to 5%

### 6.7 Portfolio cap

Apply portfolio-level constraints after instrument sizing:

- max gross exposure
- max single-name exposure
- max sector exposure
- max correlated cluster exposure

If portfolio caps bind, reduce position size proportionally rather than overriding the signal.

### 6.8 Long/short symmetry

For a short signal, mirror the same logic with sign flipped:

```text
signed_edge = sign * expected_edge_bps
```

Where `sign = +1` for long and `-1` for short.

Only take the trade if the signed edge clears the threshold.

### 6.9 Practical sizing formula

A simple first version:

```text
if expected_edge_bps <= threshold_bps:
    final_size = 0
else:
    final_size = min(
        risk_based_size,
        liquidity_cap_size,
        portfolio_cap_size
    ) * quality_scale * vol_scale
```

This keeps the system conservative and easier to debug.

---

## 7. Suggested First Version Parameters

These are starting values, not permanent defaults.

| Parameter | Suggested start |
|-----------|------------------|
| Horizon | 5 minutes |
| Bar size | 1m or 5m |
| Retrain frequency | Daily |
| Training window | 60 to 90 trading days |
| Validation window | 5 trading days |
| Feature windows | 5, 10, 20, 60 bars |
| Minimum edge threshold | spread + slippage + safety buffer |
| Max risk per trade | 10 to 50 bps of equity, depending on strategy |
| Participation cap | 1% to 5% of bar volume |

---

## 8. Implementation Notes

- Use midprice-based returns for the label whenever possible
- Keep feature computation strictly point-in-time safe
- Store the feature version and model version with every prediction
- Log rejected trades as well as executed trades
- Track both gross and net performance
- If the model only works with unrealistically low costs, do not ship it

---

## 9. Minimal Acceptance Criteria

A first version should satisfy all of the following:

1. Walk-forward backtests run without leakage
2. Feature schema is reproducible and point-in-time safe
3. Forecasts beat the zero baseline after costs on at least one liquid test universe
4. Position sizing is deterministic and bounded by risk and liquidity
5. Results remain stable across multiple contiguous out-of-sample windows

If any of these fail, iterate on the model before promoting it.
