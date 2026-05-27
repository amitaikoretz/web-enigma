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

- `DATABASE_URL` is required for database-backed API endpoints, async backtest job APIs (`POST /backtests`, status polling, Argo launch), and live runtime services.
- `BACKTEST_RESULTS_DIR` optionally overrides where the API reads and writes backtest artifacts (JSON, YAML, Parquet). Job metadata and artifact path pointers live in PostgreSQL (`backtest_jobs` table); the API loads reports using those DB paths.
- With **`make k3s-deploy`**, results and cache use hostPath PVCs at **`data/backtest-results`** and **`data/backtest-cache`** in the repo (override with `HOST_BACKTEST_RESULTS` / `HOST_BACKTEST_CACHE`). You can browse merged JSON and parquet on your Mac while cluster pods use the same files at `/data/backtest-results`.
- Argo workflow pods write merged reports under `BACKTEST_WORKFLOW_RESULTS_MOUNT` (default `/data/backtest-results`). The merge step calls `update_metadata_from_report` directly (shared library code, no HTTP) to update Postgres with artifact paths. The API and workflow pods must read/write the **same** files at that path — with `make k3s-deploy`, the API runs in `backtest` and workflows in `backtest-workflows`, both bound to the same host directories via hostPath PVs. For hybrid dev (host API + cluster Argo), point `BACKTEST_RESULTS_DIR` at the same host directory (the default when using `make api-serve` after `make k3s-deploy`).
- Set `ARGO_REQUIRE_SHARED_RESULTS=1` to reject Argo launches when the API results directory does not match the workflow mount (instead of only logging a warning).
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are required for Alpaca-backed market data and Alpaca trading commands.
- `BACKTEST_CACHE_DIR` optionally overrides the default parquet cache directory (`.cache/backtest-data`). In Kubernetes this is typically `/data/cache`.

## Database Setup

Initialize the database schema:

```bash
alembic upgrade head
```

This creates the API, backtest job, and live runtime tables managed by Alembic.

If you have legacy `{backtest_id}.meta.json` files from before the database migration, import them once:

```bash
backtest import-metadata --output-dir "${BACKTEST_RESULTS_DIR:-/tmp/backtest-api-results}"
```

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

Submit a batch Alpaca download job (async). Parquet files are written under `output_folder` using the standard cache layout (`alpaca/{SYMBOL}/{resolution}/...`). The job returns immediately with a job ID; poll status until `completed`:

```bash
curl -X POST http://localhost:8000/market-data/downloads \
  -H 'Content-Type: application/json' \
  -d '{
    "output_folder": ".cache/backtest-data",
    "records": [
      {
        "symbol": "AAPL",
        "start_date": "2024-01-01",
        "stop_date": "2024-01-31",
        "resolution": "1d",
        "feed": "iex"
      }
    ]
  }'
```

Poll progress (replace `{job_id}` with the value from the create response):

```bash
curl http://localhost:8000/market-data/downloads/{job_id}/status
```

Fetch the full manifest with per-record parquet paths and errors:

```bash
curl http://localhost:8000/market-data/downloads/{job_id}
```

`output_folder` must be under the API cache root (`BACKTEST_CACHE_DIR` or `.cache/backtest-data` by default).

In the web UI, open **Data** in the top navigation to create download jobs, track progress, and jump to the backtest wizard with the same symbol universe.

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

### Backtest execution backend

Platform settings control where wizard backtests run:

- **Local (in-process)** — default for compose and bare-metal dev; jobs run in the API process thread pool.
- **Argo Workflows** — when Argo is configured (in-cluster Kubernetes API or `ARGO_SERVER_URL` for a remote Argo server); wizard jobs submit an inline backtest workflow (plan → run shards → merge). Use **Settings → Platform Behavior** to switch backends and choose the Argo shard strategy (`run`, `symbol`, `strategy`, or `symbol + strategy`).

For local API development against a remote Argo server:

```bash
export BACKTEST_ARGO_ENABLED=true
export ARGO_SERVER_URL=http://localhost:2746          # use https:// only when Argo has TLS enabled
export ARGO_SERVER_INSECURE_SKIP_VERIFY=true          # HTTPS with self-signed certs only
export ARGO_TOKEN="$(argo auth token)"         # when auth is enabled
export ARGO_NAMESPACE=backtest-workflows
export ARGO_WORKFLOW_SERVICE_ACCOUNT=backtest-workflow
export BACKTEST_RESULTS_DIR="${BACKTEST_RESULTS_DIR:-$(pwd)/data/backtest-results}"
backtest serve --port 8000
```

To launch Argo explicitly (regardless of the platform default):

```bash
curl -X POST http://localhost:8000/backtests/argo \
  -H 'Content-Type: application/json' \
  -d '{
    "config_path": "/data/backtest-results/experiment.yaml",
    "split_by": "symbol_strategy"
  }'
```

Parallel shard planning and report merge are also available via CLI:

```bash
backtest plan-shards --config experiments/volume_rally_v2_core_5m.yaml --work-dir /tmp/shards --split-by symbol
backtest merge --manifest /tmp/shards/manifest.json --output /tmp/merged.json
```

See [`deploy/k8s/README.md`](../deploy/k8s/README.md) for cluster setup.

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

Candidate logging for live Alpaca runs is controlled from **Settings → Live trading → Log live entry candidates**, or via `execution.include_candidate_log` in the Alpaca YAML. When enabled, events append to `{state_directory}/{run_id}/candidates.jsonl`.

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
