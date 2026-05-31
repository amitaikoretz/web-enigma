# Live Runtime Guide

This guide explains the current local operating model for the live runtime commands exposed by the CLI.

## Current Commands

The current CLI includes:

```bash
kalyxctl live-controller --config /path/to/live.yaml
kalyxctl live-worker --config /path/to/live.yaml --shard-id 0
kalyxctl live-reconciler --config /path/to/live.yaml
```

For local debugging, each command also supports `--once`.

## What `LiveTradingConfig` Needs

At a high level, the live runtime configuration includes:

- Redis connection settings
- runtime database mode settings
- session timing settings
- replay settings
- controller settings
- worker settings
- execution settings
- a list of contracts to manage

The model lives in `src/app/config/models.py` under `LiveTradingConfig`.

Important fields to understand before local startup:

- `global_config.redis.url`
- `global_config.redis.key_prefix`
- `global_config.runtime.database_url_env`
- `global_config.runtime.run_mode`
- `global_config.controller.contracts_api_base_url`
- `global_config.controller.shard_count`
- `global_config.worker.shard_id`
- `global_config.execution.mode`
- `contracts`

## External Dependencies

The current local live runtime depends on:

- PostgreSQL through `DATABASE_URL`
- Redis for assignments, leases, and control flags
- the API for active trading contract reads
- Alpaca credentials for Alpaca-backed execution and market data paths

Set the shared environment first:

```bash
export DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5442/survey_platform'
export ALPACA_API_KEY='your-key'
export ALPACA_SECRET_KEY='your-secret'
```

Apply migrations:

```bash
alembic upgrade head
```

## Recommended Local Startup Order

### 1. Start infrastructure

Start PostgreSQL and Redis using your preferred local tooling.

### 2. Start the API

```bash
kalyxctl serve --host 0.0.0.0 --port 8000
```

The controller expects the contracts API base URL to be reachable.

### 3. Ensure active contracts exist

The controller syncs against the API’s trading-contract data. Make sure your test database contains the contracts you want it to manage.

### 4. Start the controller

```bash
kalyxctl live-controller --config /path/to/live.yaml
```

For one iteration only:

```bash
kalyxctl live-controller --config /path/to/live.yaml --once
```

### 5. Start one or more workers

```bash
kalyxctl live-worker --config /path/to/live.yaml --shard-id 0
kalyxctl live-worker --config /path/to/live.yaml --shard-id 1
```

For a one-iteration smoke test:

```bash
kalyxctl live-worker --config /path/to/live.yaml --shard-id 0 --once
```

### 6. Optionally start the reconciler

```bash
kalyxctl live-reconciler --config /path/to/live.yaml
```

Or run a one-shot pass:

```bash
kalyxctl live-reconciler --config /path/to/live.yaml --once
```

## Suggested Local Wiring

For a local non-container setup, the common defaults are:

- API base URL: `http://localhost:8000`
- Redis URL: `redis://localhost:6379/0`

If you move to containers later, these usually become service-to-service URLs instead.

## Current Status and Limitations

Be explicit about the maturity level of this stack:

- the CLI commands exist and are tested at the command-entry level
- the configuration models and runtime builders exist
- the repo includes design guidance for a Compose-based and Kubernetes-based operational model
- there is not yet a checked-in Compose stack or a production deployment runbook in this repo

That means the current local workflow is best treated as an engineer runbook for iterative development, not a finalized operator platform.

## Related Docs

- [Local Development](./local-development.md)
- [Docker Compose Guide](./docker-compose.md)
- [Kubernetes Design Notes](./k8s-trading-agent-design.md)
