# How Backtesting Works

This project runs backtests through a Typer CLI command named `backtest`.

For environment setup, local service startup, and live-runtime operations, use:

- [Local Development](./docs/local-development.md)
- [Docker Compose Guide](./docs/docker-compose.md)
- [Live Runtime Guide](./docs/live-runtime.md)

## End-to-end flow

1. You run `backtest run --config <yaml> --output <json>`.
2. The CLI loads YAML and validates it with `BacktestConfig` (Pydantic).
3. Each `run` entry is executed independently in `backtesting.py`.
4. A data feed is built from either:
   - `csv` source (`path` + column mapping), or
   - `yahoo` source (`symbol` + `interval`, with cache support), or
   - `alpaca` source (`symbol` + `interval`, optional `feed`, with cache support).
5. Broker settings are applied (cash, commission, optional slippage).
6. The selected strategy is looked up from the strategy registry and instantiated with `strategy_params`.
7. Built-in analyzers are attached:
   - `SharpeRatio`
   - `DrawDown`
   - `TradeAnalyzer`
   - custom `EquityCurveAnalyzer`
8. After execution, the app builds a per-run result (`summary`, analyzers, optional logs/equity curve).
9. All runs are aggregated into a `BacktestReport` and written to JSON.

The same execution pipeline is also available through `POST /backtests/run`, which accepts inline YAML or JSON text, validates it with `BacktestConfig`, runs the backtest in-process, writes a JSON report to a server-managed temp path, and returns that path plus run status metadata.

## Config shape (high level)

A config YAML contains:

- `global_config` (optional)
  - `default_broker`
  - `data_cache`
- `runs` (required, at least one)
  - `run_id` (must be unique)
  - `start_date`, `end_date`
  - `data` (`csv`, `yahoo`, or `alpaca`)
  - `strategy`
  - optional `strategy_params`, `broker`, `analyzers`

See sample files in `examples/algorithms/`.

Environment and infrastructure setup live outside this guide so the backtesting instructions stay focused on execution and report output.

## CLI commands

### 1) List available strategies

```bash
backtest list-strategies
```

### 2) Run a batch config

```bash
backtest run \
  --config examples/algorithms/batch_demo.yaml \
  --output /tmp/backtest-results.json
```

### 3) Run with custom cache directory

```bash
backtest run \
  --config examples/algorithms/yahoo_substantial.yaml \
  --output /tmp/yahoo-results.json \
  --cache-dir /tmp/backtest-cache
```

### 4) Force refresh Yahoo cache

```bash
backtest run \
  --config examples/algorithms/yahoo_substantial.yaml \
  --output /tmp/yahoo-refresh.json \
  --cache-refresh
```

### 5) Disable cache for this run

```bash
backtest run \
  --config examples/algorithms/yahoo_substantial.yaml \
  --output /tmp/yahoo-no-cache.json \
  --no-cache
```

### 6) Build an HTML report from JSON output

```bash
backtest report-html \
  --input /tmp/backtest-results.json \
  --output /tmp/backtest-report.html \
  --title "Backtest Report"
```

## Exit codes

`backtest run` uses status-based exit codes:

- `0`: all runs succeeded
- `10`: partial failure (some runs failed)
- `20`: all runs failed
- `2`: config/input/validation error

`list-strategies` and `report-html` return `0` on success.

## HTTP endpoint

`POST /backtests/run`

Request body:

```json
{
  "format": "json",
  "config_text": "{\"runs\":[{\"run_id\":\"api_demo\",\"start_date\":\"2024-01-01\",\"end_date\":\"2024-01-19\",\"data\":{\"type\":\"csv\",\"path\":\"examples/data/sample_daily.csv\"},\"strategy\":\"buy_and_hold\",\"strategy_params\":{\"stake\":1}}]}"
}
```

Response body:

```json
{
  "output_path": "/tmp/backtest-api-results/12345678-1234-1234-1234-123456789abc.json",
  "status": "success",
  "total_runs": 1,
  "successful_runs": 1,
  "failed_runs": 0
}
```

Behavior:

- Runs synchronously and returns when the report JSON has been written
- Accepts `format: "json"` or `format: "yaml"`
- Returns `200` even when the report status is `partial_failure` or `failure`
- Returns `422` for parse/validation errors
- Returns `500` if the report cannot be written
