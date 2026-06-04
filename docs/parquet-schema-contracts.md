# Parquet Schema Contracts

This page is the canonical schema contract index for every parquet-producing artifact in the repo.

Rules:

- If a file ends in `.parquet`, it must be covered here.
- Backtest shard sidecars use the same schema as their non-sharded counterparts.
- String timestamps are stored as ISO-8601 text unless a contract says otherwise.
- Parquet writes are atomic temp-file replacements.
- If a contract changes, the docs and tests must change with it.

## Contract Index

| Artifact family | Typical path pattern | Producer | Row grain | Contract section |
|---|---|---|---|---|
| Backtest report summary | `*.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per backtest run | [Backtest Report Summary Parquet](#backtest-report-summary-parquet) |
| Backtest candidates | `*.candidates.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per candidate | [Backtest Candidates Parquet](#backtest-candidates-parquet) |
| Backtest orders | `*.orders.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per order | [Backtest Orders Parquet](#backtest-orders-parquet) |
| Backtest trades | `*.trades.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per trade | [Backtest Trades Parquet](#backtest-trades-parquet) |
| Backtest rejections | `*.rejections.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per rejection | [Backtest Rejections Parquet](#backtest-rejections-parquet) |
| Backtest equity | `*.equity.parquet` | `app.backtests.artifacts.write_report_artifacts` | One row per equity point | [Backtest Equity Parquet](#backtest-equity-parquet) |
| Risk labels | `*.labels.parquet` | `app.backtests.artifacts.persist_backtest_report` and risk auxiliary writers | One row per candidate label | [Risk Labels Parquet](#risk-labels-parquet) |
| Risk features | `*.features.parquet` | `app.backtests.artifacts.persist_backtest_report` and risk auxiliary writers | One row per candidate snapshot | [Risk Features Parquet](#risk-features-parquet) |
| Joined risk dataset | `risk_dataset.parquet` or configured output path | `app.risk.dataset.builder.build_risk_dataset` | One row per joined candidate | [Joined Risk Dataset Parquet](#joined-risk-dataset-parquet) |
| Intraday dataset | `dataset.parquet` | `app.intraday.pipeline.write_intraday_artifacts` | One row per symbol-timestamp sample | [Intraday Dataset Parquet](#intraday-dataset-parquet) |
| Intraday predictions | `predictions.parquet` | `app.intraday.pipeline.write_intraday_artifacts` | One row per scored sample | [Intraday Predictions Parquet](#intraday-predictions-parquet) |
| Intraday positions | `positions.parquet` | `app.intraday.pipeline.write_intraday_artifacts` | One row per sizing decision | [Intraday Positions Parquet](#intraday-positions-parquet) |
| Parquet cache | `*.parquet` under the data cache root | `app.data.cache.ParquetDataCache.put` | Same as the source frame | [Parquet Cache Files](#parquet-cache-files) |

## Shared Backtest Rules

- All backtest parquet sidecars carry `run_id` so rows can be grouped back to a specific run.
- `metadata_json` and `metadata_features_json` are parquet-only fields used to preserve nested metadata.
- The loader side of the contract is Pydantic validation. Missing required fields should fail fast.
- Shard sidecars and merged sidecars share the same schema contract.

## Backtest Report Summary Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** `app.backtests.artifacts.hydrate_report_from_artifacts`, UI artifact inventory, report summaries  
**Row grain:** one row per backtest run  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `name` | string | nullable | Optional display name |
| `status` | string | required | `success` or `failed` |
| `strategy` | string | required | Strategy name |
| `symbol` | string | nullable | Primary symbol, if any |
| `data_source` | string | required | Resolved data source |
| `start_value` | float | nullable | Starting equity |
| `end_value` | float | nullable | Ending equity |
| `return_pct` | float | nullable | Run return in percent |
| `max_drawdown_pct` | float | nullable | Maximum drawdown in percent |
| `sharpe_ratio` | float | nullable | Sharpe ratio |
| `total_trades` | int | required | Total trades |
| `won_trades` | int | required | Winning trades |
| `lost_trades` | int | required | Losing trades |

**Ordering:** rows follow `report.results` order.  
**Failure behavior:** if the summary row cannot be built, no parquet is written. Missing summary values are written as null or zero, not inferred.

## Backtest Candidates Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** backtest hydration, risk dataset loading, replay tooling  
**Row grain:** one row per candidate  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `candidate_id` | string | required | Stable candidate key |
| `strategy_id` | string | required | Strategy that produced the candidate |
| `symbol` | string | required | Symbol under consideration |
| `timestamp` | string | required | ISO timestamp |
| `side` | string | required | `LONG` or `SHORT` |
| `entry_price` | float | required | Planned/recorded entry |
| `entry_type` | string | required | Entry type |
| `planned_stop_pct` | float | required | Planned stop distance |
| `planned_target_pct` | float | nullable | Planned target distance |
| `planned_horizon_bars` | int | required | Max forward bars |
| `signal_score` | float | nullable | Strategy signal score |
| `signal_reason` | string | nullable | Human/machine readable reason |
| `was_traded` | bool | required | Whether the candidate became a trade |
| `reject_reason` | string | nullable | Why the candidate was rejected |
| `metadata_json` | string | nullable | JSON encoded candidate metadata |

**Ordering:** rows follow the emitted candidate order within each run.  
**Failure behavior:** if `metadata` is absent, `metadata_json` is null. Candidate rows must still validate against `CandidateRecord`.

## Backtest Orders Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** report hydration and UI artifact downloads  
**Row grain:** one row per order  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `datetime` | string | nullable | Order timestamp |
| `status` | string | required | Broker/order status |
| `is_buy` | bool | required | Buy/sell flag |
| `size` | float | required | Order size |
| `price` | float | required | Order price |
| `value` | float | required | Notional value |
| `commission` | float | required | Commission paid |

**Ordering:** rows follow the original order sequence.  
**Failure behavior:** missing required fields fail Pydantic validation on load.

## Backtest Trades Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** report hydration, trade diagnostics, replay tooling  
**Row grain:** one row per closed trade  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `datetime` | string | nullable | Close timestamp |
| `entry_bar_index` | int | nullable | Entry bar index |
| `exit_bar_index` | int | nullable | Exit bar index |
| `size` | float | required | Signed size |
| `price` | float | required | Close price |
| `value` | float | required | Notional value |
| `pnl` | float | required | Gross PnL |
| `pnlcomm` | float | required | Net PnL after commission |
| `reason` | string | nullable | Exit reason |
| `entry_datetime` | string | nullable | Entry timestamp |
| `hold_minutes` | float | nullable | Hold duration in minutes |
| `hold_bars` | int | nullable | Hold duration in bars |
| `regime_label` | string | nullable | Exit regime label |

**Ordering:** rows follow the original trade order.  
**Failure behavior:** missing required fields fail Pydantic validation on load.

## Backtest Rejections Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** report hydration and filter diagnostics  
**Row grain:** one row per rejection  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `datetime` | string | nullable | Rejection timestamp |
| `symbol` | string | nullable | Symbol, if available |
| `reason` | string | nullable | Rejection reason |

**Ordering:** rows follow the original rejection order.  
**Failure behavior:** missing required fields fail Pydantic validation on load.

## Backtest Equity Parquet

**Producer:** `app.backtests.artifacts.write_report_artifacts`  
**Consumer:** charting, hydration, equity diagnostics  
**Row grain:** one row per equity point  
**Versioning:** no embedded schema version; the column set is the contract

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `datetime` | string | required | ISO timestamp |
| `value` | float | required | Portfolio value |

**Ordering:** rows follow the original equity curve order.  
**Failure behavior:** missing required fields fail Pydantic validation on load.

## Risk Labels Parquet

**Producer:** `app.backtests.artifacts.persist_backtest_report` and risk auxiliary shard writers  
**Consumer:** `app.risk.dataset.builder`, training jobs, model analysis  
**Row grain:** one row per candidate label  
**Versioning:** `label_version`

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `candidate_id` | string | required | Join key |
| `label_version` | string | required | Schema version |
| `entry_price` | float | required | Resolved entry price |
| `horizon_bars` | int | required | Planned horizon |
| `stop_pct` | float | required | Planned stop distance |
| `target_pct` | float | nullable | Planned target distance |
| `mae_pct` | float | required | Max adverse excursion |
| `mae_abs_pct` | float | required | Absolute MAE |
| `mae_atr` | float | nullable | MAE normalized by ATR |
| `mfe_pct` | float | required | Max favorable excursion |
| `final_return_pct` | float | required | Final return |
| `realized_R` | float | required | Return expressed in R |
| `hit_stop` | bool | required | Stop was touched |
| `hit_target` | bool | required | Target was touched |
| `hit_stop_before_target` | bool | required | Stop-before-target flag |
| `bars_to_stop` | int | nullable | Bars to stop |
| `bars_to_target` | int | nullable | Bars to target |
| `bars_held` | int | required | Bars held |
| `exit_reason` | string | required | `STOP`, `TARGET`, `TIME`, `DATA_ERROR` |
| `label_quality_flag` | string | required | Label quality flag |

**Ordering:** rows follow the candidate order inside each run.  
**Failure behavior:** long-only V1. Missing bars or bad OHLCs are encoded with `label_quality_flag`, not hidden.

## Risk Features Parquet

**Producer:** `app.backtests.artifacts.persist_backtest_report` and risk auxiliary shard writers  
**Consumer:** `app.risk.dataset.builder`, feature analysis, training jobs  
**Row grain:** one row per candidate snapshot  
**Versioning:** `feature_version`

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `run_id` | string | required | Run identifier |
| `candidate_id` | string | required | Join key |
| `feature_version` | string | required | Schema version |
| `feature_timestamp` | string | required | Timestamp of the last bar used |
| `feature_quality_flag` | string | required | `OK` or `INSUFFICIENT_HISTORY` |
| `return_5` | float | nullable | 5-bar return |
| `return_10` | float | nullable | 10-bar return |
| `return_20` | float | nullable | 20-bar return |
| `trend_slope_20` | float | nullable | 20-bar slope |
| `trend_slope_50` | float | nullable | 50-bar slope |
| `sma_20_distance` | float | nullable | SMA distance |
| `sma_50_distance` | float | nullable | SMA distance |
| `rsi_14` | float | nullable | RSI |
| `return_zscore_20` | float | nullable | Return z-score |
| `gap_pct` | float | nullable | Open gap |
| `consecutive_up_bars` | int | nullable | Consecutive up closes |
| `volume_zscore_20` | float | nullable | Volume z-score |
| `relative_volume_20` | float | nullable | Relative volume |
| `atr_14_pct` | float | nullable | ATR divided by close |
| `realized_vol_10` | float | nullable | Realized vol |
| `realized_vol_20` | float | nullable | Realized vol |
| `vol_percentile_60` | float | nullable | Volume percentile |
| `atr_expansion_10_50` | float | nullable | ATR expansion |
| `dollar_volume_20` | float | nullable | Dollar volume |
| `volume_percentile_60` | float | nullable | Volume percentile |
| `index_return_20` | float | nullable | Benchmark return |
| `index_trend_slope_50` | float | nullable | Benchmark slope |
| `correlation_to_index_60` | float | nullable | Symbol/index correlation |
| `beta_to_index_60` | float | nullable | Symbol/index beta |
| `metadata_features_json` | string | nullable | JSON encoded metadata map |

**Ordering:** rows follow the candidate order inside each run.  
**Failure behavior:** insufficient history keeps the row but nulls numeric fields and sets `feature_quality_flag=INSUFFICIENT_HISTORY`.

## Joined Risk Dataset Parquet

**Producer:** `app.risk.dataset.builder.build_risk_dataset`  
**Consumer:** training, validation, model registry, analysis notebooks  
**Row grain:** one row per joined candidate  
**Versioning:** `dataset_version`, `label_version`, `feature_version`

This parquet is a joined superset of the candidate, label, and feature contracts, with these rules:

- `dataset_version`, `label_version`, and `feature_version` are inserted as the leading columns.
- Candidate metadata is flattened to `meta_...` columns.
- Feature metadata is flattened to `meta_...` columns when the builder reconstructs the dataset from bars.
- When candidate logs are missing from the report JSON, the builder may synthesize a reduced candidate frame from the label and feature sidecars. That fallback is documented, but the preferred source of truth is still the candidate log in the report.

Minimum columns that every joined dataset must have:

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `dataset_version` | string | required | Dataset schema version |
| `label_version` | string | required | Label schema version |
| `feature_version` | string | required | Feature schema version |
| `candidate_id` | string | required | Join key |
| `entry_price` | float | required | Candidate entry price |
| `planned_stop_pct` | float | required | Candidate stop distance |
| `planned_horizon_bars` | int | required | Candidate horizon |
| `stop_pct` | float | required | Label stop distance |
| `feature_quality_flag` | string | required | Feature quality flag |

**Ordering:** rows are concatenated in input-report order; within a report, the candidate order is preserved as much as possible.  
**Failure behavior:** inner joins drop candidates that do not have both labels and features. That is intentional and should be reflected in `RiskDatasetManifest`.

## Intraday Dataset Parquet

**Producer:** `app.intraday.pipeline.write_intraday_artifacts`  
**Consumer:** intraday model training, walk-forward validation, model selection  
**Row grain:** one row per symbol-timestamp sample  
**Versioning:** `dataset_version`, `feature_version`, `label_version`, `model_version`

Required base columns:

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `symbol` | string | required | Traded symbol |
| `timestamp` | string | required | UTC timestamp |
| `entry_price` | float | required | Entry price |
| `target_return_pct` | float | required | Forward return target |
| `target_return_bps` | float | required | Forward return target in bps |
| `feature_quality_flag` | string | required | Feature quality flag |

Feature columns required by the contract:

`ret_1`, `ret_5`, `ret_20`, `ret_z_20`, `range_pct_1`, `close_to_high_pct`, `close_to_low_pct`, `sma_20_dist`, `ema_9_dist`, `trend_slope_20`, `rsi_14`, `consecutive_up_bars`, `volume_1`, `volume_z_20`, `relative_volume_20`, `realized_vol_10`, `realized_vol_20`, `atr_pct_14`, `vol_expansion_20_60`, `time_of_day_sin`, `time_of_day_cos`, `minute_of_session`, `day_of_week`, `benchmark_ret_5`, `benchmark_ret_20`, `benchmark_trend_slope_20`, `benchmark_realized_vol_20`, `relative_ret_20`, `correlation_to_benchmark_20`, `beta_to_benchmark_20`

**Ordering:** dataset rows are sorted by `timestamp` then `symbol`.  
**Failure behavior:** rows with insufficient history or invalid forward horizons are dropped before write.

## Intraday Predictions Parquet

**Producer:** `app.intraday.pipeline.write_intraday_artifacts`  
**Consumer:** scoring analysis, validation metrics, position sizing review  
**Row grain:** one row per scored sample  
**Versioning:** inherits the dataset version fields and adds scoring columns

This parquet contains the intraday dataset columns plus the scoring outputs below.

Scoring columns:

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `fold_id` | int | required | Walk-forward fold |
| `subset` | string | required | `validation` or `test` |
| `pred_return_pct` | float | required | Predicted return |
| `pred_return_bps` | float | required | Predicted return in bps |
| `pred_vol_bps` | float | required | Predicted residual vol |
| `pred_quantile_10_pct` | float | required | 10th percentile prediction |
| `pred_quantile_50_pct` | float | required | Median prediction |
| `pred_quantile_90_pct` | float | required | 90th percentile prediction |
| `expected_edge_bps` | float | required | Edge after round-trip cost |
| `forecast_risk_bps` | float | required | Risk estimate used for sizing |
| `direction` | string | required | `LONG`, `SHORT`, or `FLAT` |
| `final_shares` | float | required | Final position size |
| `final_notional` | float | required | Final notional |
| `stop_distance_bps` | float | required | Stop distance used for sizing |
| `quality_scale` | float | required | Quality scalar used for sizing |
| `vol_scale` | float | required | Volatility scalar used for sizing |
| `liquidity_cap_shares` | float | required | Liquidity cap |
| `gross_pnl` | float | required | Gross PnL |
| `roundtrip_cost` | float | required | Round-trip cost |
| `net_pnl` | float | required | Net PnL |
| `realized_gross_pnl` | float | required | Realized gross PnL |
| `realized_net_pnl` | float | required | Realized net PnL |
| `hit_direction` | bool | required | Direction hit flag |

**Ordering:** rows follow the scored dataset order produced by the pipeline.  
**Failure behavior:** this parquet is derived from the dataset, so any model-selection failure should fail before write.

## Intraday Positions Parquet

**Producer:** `app.intraday.pipeline.write_intraday_artifacts`  
**Consumer:** trade sizing review, audit logs, model outputs  
**Row grain:** one row per sizing decision  
**Versioning:** no separate version; the row shape matches `PositionSizingDecision`

| Column | Type | Nullability | Notes |
|---|---|---|---|
| `symbol` | string | required | Symbol |
| `timestamp` | string | required | UTC timestamp |
| `direction` | string | required | `LONG`, `SHORT`, or `FLAT` |
| `expected_edge_bps` | float | required | Expected edge |
| `forecast_risk_bps` | float | required | Forecast risk |
| `threshold_bps` | float | required | Signal threshold |
| `quality_scale` | float | required | Quality scale |
| `vol_scale` | float | required | Volatility scale |
| `risk_based_shares` | float | required | Risk-constrained shares |
| `liquidity_cap_shares` | float | required | Liquidity cap |
| `final_shares` | float | required | Final shares |
| `final_notional` | float | required | Final notional |
| `entry_price` | float | required | Entry price |
| `stop_distance_bps` | float | required | Stop distance |
| `roundtrip_cost_bps` | float | required | Round-trip cost |
| `fold_id` | int | nullable | Fold identifier |
| `reason` | string | nullable | Sizing decision reason |

**Ordering:** rows follow the scored dataset order.  
**Failure behavior:** `FLAT` rows are valid and expected when signals do not clear the threshold.

## Parquet Cache Files

**Producer:** `app.data.cache.ParquetDataCache.put`  
**Consumer:** `app.data.cache.ParquetDataCache.get` and source-specific data loaders  
**Row grain:** whatever the source frame represents  
**Versioning:** the cache key encodes `source`, `symbol`, `interval`, date range, optional `feed`, and `normalization_version`

This cache is not a normalized schema. Its contract is:

- the parquet content is a round-trip of the source DataFrame
- the index is preserved
- the file path is stable for a given `CacheKey`
- schema compatibility is the responsibility of the source-specific loader

**Ordering:** preserves the source frame order unless the source loader sorts before caching.  
**Failure behavior:** cache miss and stale data return status codes instead of schema errors; schema mismatches must be validated by the consumer after load.
