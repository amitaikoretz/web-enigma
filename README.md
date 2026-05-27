# Backtest App

A simple `backtesting.py` CLI app with:
- YAML input validated by Pydantic
- Batch run support
- Demo strategy registry
- Comprehensive JSON output validated by Pydantic

Built-in strategies include:
- `sma_cross`
- `rsi_reversion`
- `buy_and_hold`
- `breakout_channel`
- `buy_oco_atr_tp_sl`
- `buy_oco_atr_tp_trailing`
- `volume_rally` for confirmed breakout/rally detection using volume, VWAP, MACD, ADX, and ATR exits

## Quick Start

```bash
pip install -e .
```

Run a sample backtest:

backtest list-strategies
backtest run --config examples/algorithms/batch_demo.yaml --output /tmp/results.json
```

Start the API:

```bash
backtest serve --port 8000
```

## Docs

Start here for local setup and operations:

- [Local Development](./docs/local-development.md)
- [Docker Compose Guide](./docs/docker-compose.md)
- [Live Runtime Guide](./docs/live-runtime.md)
- [Backtesting Guide](./BACKTEST.md)
- [Kubernetes Design Notes](./docs/k8s-trading-agent-design.md)

## What Each Guide Covers

Backtesting:

- [BACKTEST.md](./BACKTEST.md) explains the backtest execution flow, CLI commands, report generation, and the `POST /backtests/run` API.

Local setup:

- [docs/local-development.md](./docs/local-development.md) covers install, env vars, migrations, API startup, web UI startup, troubleshooting, and the current CLI command surface.

Docker Compose:

- [docs/docker-compose.md](./docs/docker-compose.md) documents the checked-in Compose stack for local orchestration.

Live runtime:

- [docs/live-runtime.md](./docs/live-runtime.md) covers the current `live-controller`, `live-worker`, and `live-reconciler` commands, their dependencies, and the recommended local startup order.

## API Snapshot

Run a backtest synchronously over HTTP with inline YAML:

```bash
curl -X POST http://localhost:8000/backtests/run \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "yaml",
    "config_text": "runs:\n  - run_id: api_demo\n    start_date: 2024-01-01\n    end_date: 2024-01-19\n    data:\n      type: csv\n      path: examples/data/sample_daily.csv\n    strategy: buy_and_hold\n    strategy_params:\n      stake: 1\n"
  }'
```

See [docs/local-development.md](./docs/local-development.md) for setup details and [BACKTEST.md](./BACKTEST.md) for the full API contract.
