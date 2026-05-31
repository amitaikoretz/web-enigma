# Docker Compose Guide

This repo ships a checked-in Compose stack for local orchestration of the API and live runtime services.

## Stack Overview

Services in [`docker-compose.yml`](../docker-compose.yml):

| Service | Required | Description |
|---------|----------|-------------|
| `postgres` | yes | Trading contracts and live runtime persistence |
| `redis` | yes | Assignments, leases, heartbeats, and control flags |
| `migrate` | yes | One-shot Alembic migration bootstrap |
| `api` | yes | FastAPI backtest and trading-contract endpoints |
| `controller` | yes | Polls active contracts and publishes assignments |
| `worker-0`, `worker-1` | yes | Live worker shards (count matches `shard_count` in live config) |
| `reconciler` | optional | Reconciliation loop (`full` profile) |
| `web` | optional | React UI (`web` profile) |

Live runtime wiring is defined in [`examples/live/compose.yaml`](../examples/live/compose.yaml):

- `global_config.redis.url`: `redis://redis:6379/0`
- `global_config.controller.contracts_api_base_url`: `http://api:8000`
- `global_config.controller.shard_count`: `2`

## Prerequisites

- Docker with Compose v2
- Alpaca API credentials for paper/live broker and market data paths

Copy the environment template and fill in credentials:

```bash
cp .env.example .env
```

## Quick Start

From the repo root:

```bash
docker compose up --build
```

This starts infrastructure, runs migrations, and launches the API, controller, and two worker shards.

### Optional services

Include the reconciler:

```bash
docker compose --profile full up --build
```

Include the web UI (Vite dev server on port 8080):

```bash
docker compose --profile web up --build
```

Both optional profiles together:

```bash
docker compose --profile full --profile web up --build
```

## Startup Order

Compose enforces this order through health checks and `depends_on`:

1. `postgres` and `redis` become healthy
2. `migrate` runs `alembic upgrade head`
3. `api` starts after migrations complete
4. `controller` starts after the API is healthy
5. `worker-0` and `worker-1` start after the controller
6. `reconciler` (optional) starts after the API is healthy

## Migrations

Migrations run automatically via the `migrate` service on every `docker compose up`.

To rerun migrations manually:

```bash
docker compose run --rm migrate alembic upgrade head
```

## Seed Trading Contracts

The controller reads active contracts from the API. Seed a sample contract after the stack is up:

```bash
chmod +x examples/live/seed_contracts.sh
./examples/live/seed_contracts.sh
```

Override the API base URL if needed:

```bash
API_BASE_URL=http://localhost:8000 ./examples/live/seed_contracts.sh
```

## Environment Variables

Compose services share these values (see [`.env.example`](../.env.example)):

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/backtest
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

## Volume Mappings

Source mounts keep Python and React services on the latest repo code without rebuilding images.

| Path | Service | Purpose |
|------|---------|---------|
| `postgres_data` (named volume) | `postgres` | Database files |
| `./src:/app/src` | Python services | Application source (editable install) |
| `./alembic:/app/alembic` | Python services | Migration scripts |
| `./alembic.ini:/app/alembic.ini:ro` | Python services | Alembic config |
| `./pyproject.toml:/app/pyproject.toml:ro` | Python services | Package metadata |
| `./examples/live/compose.yaml:/app/config/live.yaml:ro` | `controller`, `worker-*`, `reconciler` | Live runtime config |
| `./web:/app` | `web` | React source (Vite dev server with HMR) |
| `web_node_modules` (named volume) | `web` | Installed frontend dependencies |

Rebuild images when dependencies change (`pyproject.toml` or `web/package.json`). Python code and frontend changes are picked up automatically from the mounted paths.

Report and log output still use in-container paths today. Mount host directories here when you need durable artifacts outside the stack.

## Health Checklist

After `docker compose up --build`:

1. API health: `curl http://localhost:8000/health` returns `{"status":"ok"}`
2. Redis: `docker compose exec redis redis-cli ping` returns `PONG`
3. Postgres: `docker compose exec postgres pg_isready -U postgres -d backtest`
4. Migrations: `docker compose run --rm migrate alembic current` shows head revision
5. Seed a contract: `./examples/live/seed_contracts.sh`
6. Controller one-shot: `docker compose run --rm controller kalyxctl live-controller --config /app/config/live.yaml --once`
7. Worker one-shot: `docker compose run --rm worker-0 kalyxctl live-worker --config /app/config/live.yaml --shard-id 0 --once`
8. Web (optional): open `http://localhost:8080`

## Local Redis Backend Notes

- Production and Compose paths use real Redis via `redis://` URLs.
- Unit tests use in-memory backends with `memory://` URLs so they do not require a running Redis instance.

## Related Docs

- [Local Development](./local-development.md)
- [Live Runtime Guide](./live-runtime.md)
- [Kubernetes Design Notes](./k8s-trading-agent-design.md)
