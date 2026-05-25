# Docker Compose Guide

This repo does not currently include a checked-in `docker-compose.yml` or Compose-managed local stack.

The current state is:

- manual local startup is supported today
- Docker Compose is the intended first operational local environment
- the intended stack shape is described in `docs/k8s-trading-agent-design.md`

This guide explains how Compose should be used for local orchestration once the stack artifacts are added, and what services/env wiring that stack needs to include.

## Current Status

What exists now:

- `backtest serve` for the API
- `backtest live-controller`
- `backtest live-worker`
- `backtest live-reconciler`
- Alembic migrations for PostgreSQL-backed tables

What does not exist yet:

- a checked-in `docker-compose.yml`
- checked-in Dockerfiles for these services
- a validated one-command local stack launch flow

## Intended Local Stack

The design docs and current runtime code point to this local Compose topology:

- `postgres`
- `redis`
- `api`
- optional `web`
- `controller`
- one or more `worker` services
- optional `reconciler`

## Expected Service Responsibilities

`postgres`

- stores trading contracts and live runtime persistence tables
- must be reachable through `DATABASE_URL`

`redis`

- stores assignments, leases, heartbeats, and control flags for live runtime coordination

`api`

- runs `backtest serve --host 0.0.0.0 --port 8000`
- serves backtest endpoints and trading-contract endpoints
- should run after migrations are applied or in an environment where migrations are applied at startup

`web` (optional)

- runs the React UI from `web/`
- should point at the API service

`controller`

- runs `backtest live-controller --config /app/path/to/live.yaml`
- reads active contracts from the API using `contracts_api_base_url`
- writes assignment state to Redis

`worker`

- runs `backtest live-worker --config /app/path/to/live.yaml --shard-id <n>`
- consumes assignments and leases through Redis
- writes durable state to PostgreSQL

`reconciler` (optional)

- runs `backtest live-reconciler --config /app/path/to/live.yaml`

## Environment Wiring

Any future Compose stack should wire these values consistently:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/<db-name>
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

The live config should align with the container network:

- `global_config.redis.url`: should point at the `redis` service, for example `redis://redis:6379/0`
- `global_config.controller.contracts_api_base_url`: should point at the `api` service, for example `http://api:8000`

## Startup Order

When Compose support is added, the local runbook should follow this order:

1. Start `postgres` and `redis`.
2. Apply Alembic migrations against `postgres`.
3. Start the `api`.
4. Seed or create active trading contracts if testing live runtime behavior.
5. Start `controller`.
6. Start one or more `worker` services.
7. Optionally start `reconciler`.

## What To Document When Compose Artifacts Are Added

When the repo adds actual Compose files, extend this guide with:

- the exact Compose file path
- exact `docker compose up` commands
- migration commands for the stack
- any volume mappings for report output, logs, or runtime state
- example `live.yaml` mounting and container paths
- a minimal “stack is healthy” verification checklist

## Related Docs

- [Local Development](./local-development.md)
- [Live Runtime Guide](./live-runtime.md)
- [Kubernetes Design Notes](./k8s-trading-agent-design.md)
