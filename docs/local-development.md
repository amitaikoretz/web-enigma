# Local Development

This guide is the fastest path for engineers who need to run this repo locally.

## Prerequisites

- Python 3.11+
- Node.js 20+ if you want to run the web UI in `web/`
- PostgreSQL for database-backed API and live runtime flows
- Redis for live controller/worker/reconciler flows

## Install

From the repo root:

```bash
pip install -e .
```

## Environment Variables

The current code references these environment variables:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5442/survey_platform'
export ALPACA_API_KEY='your-key'
export ALPACA_SECRET_KEY='your-secret'
```

Notes:

- `DATABASE_URL` is required for database-backed API endpoints and live runtime services.
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are required for Alpaca-backed market data and Alpaca trading commands.

## Database Setup

Initialize the database schema:

```bash
alembic upgrade head
```

This creates the API and live runtime tables managed by Alembic.

## First Successful Backtest

### CLI

Run a sample config and write the JSON report:

```bash
backtest run \
  --config examples/algorithms/batch_demo.yaml \
  --output /tmp/backtest-results.json
```

Generate an HTML report from the JSON output:

```bash
backtest report-html \
  --input /tmp/backtest-results.json \
  --output /tmp/backtest-report.html \
  --title "Batch Backtest Dashboard"
```

### HTTP API

Start the API:

```bash
backtest serve --host 0.0.0.0 --port 8000
```

In another terminal, run a backtest synchronously over HTTP:

```bash
curl -X POST http://localhost:8000/backtests/run \
  -H 'Content-Type: application/json' \
  -d '{
    "format": "yaml",
    "config_text": "runs:\n  - run_id: api_demo\n    start_date: 2024-01-01\n    end_date: 2024-01-19\n    data:\n      type: csv\n      path: examples/data/sample_daily.csv\n    strategy: buy_and_hold\n    strategy_params:\n      stake: 1\n"
  }'
```

## API and Web UI

Start the API:

```bash
backtest serve --port 8000
```

Start the frontend:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173`.

## Live Runtime Commands

The CLI currently exposes these long-running service commands:

```bash
backtest live-controller --config /path/to/live.yaml
backtest live-worker --config /path/to/live.yaml --shard-id 0
backtest live-reconciler --config /path/to/live.yaml
```

Useful one-shot variants for local debugging:

```bash
backtest live-controller --config /path/to/live.yaml --once
backtest live-worker --config /path/to/live.yaml --shard-id 0 --once
backtest live-reconciler --config /path/to/live.yaml --once
```

The live runtime needs:

- PostgreSQL via `DATABASE_URL`
- Redis
- the API running so the controller can read active trading contracts
- Alpaca credentials for paper/live broker and Alpaca market data paths

See [live-runtime.md](./live-runtime.md) for the startup order and wiring model.

## Docker Compose

For a one-command local stack (Postgres, Redis, API, controller, workers):

```bash
cp .env.example .env   # add Alpaca credentials
docker compose up --build
```

See [docs/docker-compose.md](./docs/docker-compose.md) for profiles, seeding contracts, and health checks.

## Other Useful Commands

List built-in strategies:

```bash
backtest list-strategies
```

Evaluate the latest completed Alpaca bar and submit paper/live orders for an Alpaca trading config:

```bash
backtest alpaca-run --config /path/to/alpaca.yaml
```

## Troubleshooting

`DATABASE_URL is required for database-backed API usage`

- Export `DATABASE_URL` before starting the API if you use trading-contract endpoints or live runtime flows.
- Re-run `alembic upgrade head` after pointing at a new database.

`Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY`

- Export both Alpaca variables before running Alpaca-backed API requests or trading commands.

Tables are missing or API/database-backed flows fail at startup

- Confirm `alembic upgrade head` ran against the same database named in `DATABASE_URL`.

API is reachable but live services do not do useful work

- Confirm PostgreSQL and Redis are both running.
- Confirm the API is running before the controller starts.
- Confirm active contracts exist for the controller to fetch.
- Confirm the live config points at the right API base URL and Redis URL.

## Related Docs

- [Backtesting Guide](../BACKTEST.md)
- [Docker Compose Guide](./docker-compose.md)
- [Live Runtime Guide](./live-runtime.md)
- [Kubernetes Design Notes](./k8s-trading-agent-design.md)
