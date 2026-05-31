# Kubernetes Trading Agent Design

## Goals

- Build a Kubernetes-based live trading system that retrieves open contracts from the existing REST API.
- Run a stable pool of worker shards during market hours and scale them to zero outside market hours to reduce cost.
- Let each worker shard both evaluate signals and execute trades for the contracts it owns.
- Use Redis for fast shared coordination and PostgreSQL for durable trading state and audit history.
- Design for safe recovery from worker restarts, duplicate assignment attempts, stale data feeds, and broker/API uncertainty.

## Non-Goals

- Ultra-low-latency or high-frequency trading.
- A separate execution microservice in the first stage.
- Per-contract pod creation or pod autoscaling directly from contract count.
- Full multi-broker support in the first stage.

## Existing System Alignment

The current repository already contains pieces this design should reuse:

- `src/app/api.py`
  Exposes `GET /trading-contracts/active` for discovering open contracts.
- `src/app/db/models.py`
  Persists `trading_contracts` in PostgreSQL.
- `src/app/live/executor.py`
  Already has Alpaca bar retrieval, order submission, and local runtime state concepts.

The Kubernetes design extends those components instead of replacing them:

- keep the `trading_contracts` API as the source for desired contract scope
- replace local file runtime state with Postgres + Redis-backed runtime coordination
- evolve the current Alpaca executor into a shard-aware long-running worker

## External Integration Strategy

Initial broker mode:

- start with Alpaca paper trading

Future broker mode:

- add Alpaca live trading next

Implementation guidance:

- define a small broker adapter interface from the start
- keep Alpaca paper as the first concrete implementation
- avoid coupling worker lifecycle and persistence directly to Alpaca-specific response shapes where possible

The same pattern should be used for market data:

- define a market data adapter interface
- support both live and replay-backed implementations

## Runtime Architecture

### Components

#### 1. Contracts Controller

Responsibilities:

- poll `GET /trading-contracts/active`
- determine whether the market is in `pre_open`, `open`, `draining`, or `closed`
- compute the active tradable contract set
- assign contracts to shard ids using deterministic hashing
- publish assignment metadata to Redis
- scale worker shards up before market open and to zero after market close

Deployment:

- Kubernetes `Deployment`
- start with `1` replica

#### 2. Worker Shards

Responsibilities:

- load shard assignment and claim per-contract leases
- subscribe to market data for owned contracts
- maintain in-memory live state for each owned contract
- evaluate strategy logic continuously
- perform local risk checks before order submission
- persist trade intents, orders, fills, and position changes in Postgres
- submit orders directly to the broker with idempotent client order ids
- reconcile owned contracts against broker state on startup and periodically during runtime
- drain cleanly at market close or pod termination

Deployment:

- Kubernetes `Deployment`
- fixed replica count during market hours
- scaled to `0` outside market hours

#### 3. Reconciler

Responsibilities:

- compare broker truth against Postgres truth
- detect missing acknowledgements, orphan open orders, and position drift
- repair internal state and raise alerts

Deployment:

- either Kubernetes `CronJob` every 1-5 minutes during market hours
- or small always-on `Deployment`

For stage 1, a `CronJob` is enough.

#### 4. PostgreSQL

Source of truth for durable state:

- contracts
- trade intents
- orders
- fills
- positions
- reconciliation runs
- operational audit log

#### 5. Redis

Source of truth for coordination and ephemeral hot state:

- per-contract ownership leases
- worker heartbeats
- assignment version
- feed freshness markers
- kill switch and pause flags
- short-lived dedupe keys

## Market Session Model

The controller manages system behavior across these session phases:

- `closed`
  No worker pods running. No trading allowed.
- `pre_open`
  Worker pods are scaled up. Startup reconciliation runs. Feed connections warm up. No opening orders yet unless explicitly supported later.
- `open`
  Workers monitor feeds and may trade.
- `draining`
  Triggered shortly before market close or at close. Workers stop opening new positions, may place exit orders to flatten positions, finish persistence, and prepare for shutdown.

Recommended initial timing:

- scale workers up 10-15 minutes before market open
- begin `draining` at market close
- scale workers to `0` after all workers have drained or after a grace timeout

Initial overnight policy:

- positions must be flat by the end of the session
- workers may submit exit orders during `draining`
- if any position remains open past the target drain window, mark the contract `reconciliation_needed`, alert, and keep the worker set alive long enough to resolve or explicitly fail the session shutdown

An exchange calendar should drive these transitions.

## Assignment and Ownership Model

### Sharding

Each symbol ownership unit is assigned to a logical shard:

`shard_id = hash(symbol_key) % shard_count`

This keeps pod count stable while allowing many contracts per worker.

### Ownership Boundary

Ownership and position tracking should be scoped by broker symbol, not only by `contract_id`, when multiple contracts can target the same tradable instrument.

Reasoning:

- the broker position exists at the symbol level
- separate contract-level ownership can create conflicting orders and unclear aggregate risk
- symbol-level ownership keeps all strategy activity for the same instrument on one worker

Recommended model:

- one worker owns tradable symbol `AAPL`
- multiple contracts may map to that symbol on the same worker
- positions and open broker orders are tracked primarily by symbol
- trade intents still record the originating `contract_id` for attribution and auditability

### Lease Rules

A worker may trade for a contract on a symbol only when all of the following are true:

- the symbol hashes to the worker's shard id
- the worker holds the Redis lease for that symbol
- the assignment version matches the current controller version
- the local feed freshness check is healthy
- the global and contract-level kill switches are not active

### Lease Behavior

- lease TTL: 15-30 seconds
- heartbeat renewal: every 5 seconds
- lease acquisition uses atomic Redis set-if-not-exists semantics
- lease value should include:
  - `worker_id`
  - `shard_id`
  - `assignment_version`
  - `leased_at`

If the worker loses its lease, it must immediately stop creating new orders for that contract.

## State Machines

### Contract Runtime State

Suggested runtime states:

- `discovered`
- `assigned`
- `leasing`
- `warming`
- `tradable`
- `paused`
- `draining`
- `closed`
- `reconciliation_needed`

Interpretation:

- `discovered`: visible from the active contracts API
- `assigned`: mapped to a shard by the controller
- `leasing`: worker is attempting to claim ownership
- `warming`: worker has lease and is loading broker/feed state
- `tradable`: lease held, feed fresh, strategy may trade
- `paused`: blocked by kill switch, feed staleness, or explicit pause
- `draining`: no new entries, exit orders allowed to flatten positions before shutdown
- `closed`: outside active time window
- `reconciliation_needed`: broker truth and local truth diverged

### Order State

Suggested order states:

- `intent_created`
- `submit_pending`
- `submitted`
- `acknowledged`
- `partially_filled`
- `filled`
- `cancel_pending`
- `canceled`
- `rejected`
- `unknown_broker_outcome`
- `reconciled`

Rule:

If broker submission times out or the worker crashes before a durable confirmation write, move the order to `unknown_broker_outcome` and let reconciliation determine the truth before any retry.

## Data Model

### Existing Durable Table

Already present:

- `trading_contracts`

This remains the source for which contracts are eligible to be active.

### Proposed PostgreSQL Tables

#### `trade_intents`

- `id`
- `contract_id`
- `worker_id`
- `shard_id`
- `strategy_name`
- `signal_type`
- `signal_payload` JSONB
- `intended_side`
- `intended_qty`
- `created_at`
- `status`

Purpose:

- durable record that the strategy decided to trade before broker submission

#### `broker_orders`

- `id`
- `contract_id`
- `trade_intent_id`
- `worker_id`
- `client_order_id`
- `broker_order_id`
- `symbol`
- `side`
- `qty`
- `order_type`
- `time_in_force`
- `status`
- `broker_response` JSONB
- `submitted_at`
- `updated_at`

Purpose:

- system of record for order lifecycle

#### `broker_fills`

- `id`
- `broker_order_id`
- `fill_qty`
- `fill_price`
- `fill_timestamp`
- `raw_payload` JSONB

Purpose:

- normalized fill history

#### `positions`

- `id`
- `symbol`
- `symbol_key`
- `net_qty`
- `avg_entry_price`
- `market_value`
- `updated_at`
- `source`

Purpose:

- latest internal position view for each owned symbol

#### `reconciliation_runs`

- `id`
- `worker_id` nullable
- `scope_type`
- `scope_id`
- `started_at`
- `completed_at`
- `status`
- `summary` JSONB

Purpose:

- audit trail for broker-vs-internal consistency checks

#### `worker_events`

- `id`
- `worker_id`
- `contract_id` nullable
- `event_type`
- `payload` JSONB
- `created_at`

Purpose:

- operational debugging and auditability

## Detailed Data Contracts

This section defines the implementation-oriented schema and payload details that should be treated as the contract between controller, workers, reconciliation, and persistence.

### PostgreSQL Conventions

Recommended conventions for new durable tables:

- UUID primary keys
- `created_at` and `updated_at` timestamps in UTC where applicable
- JSONB for broker payloads, signal payloads, and reconciliation summaries
- explicit status columns stored as strings backed by application enums
- foreign keys where relationships are strict, nullable foreign keys where reconciliation may ingest incomplete external data first

### PostgreSQL Table Details

#### `trade_intents`

Primary purpose:

- persist the strategy decision before broker submission

Suggested columns:

- `id UUID PRIMARY KEY`
- `contract_id UUID NOT NULL REFERENCES trading_contracts(id)`
- `symbol VARCHAR(64) NOT NULL`
- `symbol_key VARCHAR(128) NOT NULL`
- `worker_id VARCHAR(128) NOT NULL`
- `shard_id INTEGER NOT NULL`
- `strategy_name VARCHAR(128) NOT NULL`
- `signal_type VARCHAR(64) NOT NULL`
- `signal_hash VARCHAR(128) NOT NULL`
- `signal_payload JSONB NOT NULL DEFAULT '{}'`
- `intended_side VARCHAR(16) NOT NULL`
- `intended_qty NUMERIC(18, 8) NOT NULL`
- `intended_notional NUMERIC(18, 8) NULL`
- `status VARCHAR(32) NOT NULL`
- `decision_reason TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- `(contract_id, created_at DESC)`
- `(symbol_key, created_at DESC)`
- `(worker_id, created_at DESC)`
- unique or near-unique lookup on `(contract_id, signal_hash, created_at bucket)` if dedupe requirements later expand beyond Redis

#### `broker_orders`

Primary purpose:

- record every broker order attempt and its lifecycle

Suggested columns:

- `id UUID PRIMARY KEY`
- `contract_id UUID NULL REFERENCES trading_contracts(id)`
- `trade_intent_id UUID NULL REFERENCES trade_intents(id)`
- `symbol VARCHAR(64) NOT NULL`
- `symbol_key VARCHAR(128) NOT NULL`
- `worker_id VARCHAR(128) NOT NULL`
- `shard_id INTEGER NOT NULL`
- `client_order_id VARCHAR(128) NOT NULL`
- `broker_order_id VARCHAR(128) NULL`
- `broker_name VARCHAR(32) NOT NULL`
- `side VARCHAR(16) NOT NULL`
- `qty NUMERIC(18, 8) NOT NULL`
- `filled_qty NUMERIC(18, 8) NOT NULL DEFAULT 0`
- `remaining_qty NUMERIC(18, 8) NOT NULL DEFAULT 0`
- `order_type VARCHAR(32) NOT NULL`
- `time_in_force VARCHAR(16) NOT NULL`
- `limit_price NUMERIC(18, 8) NULL`
- `stop_price NUMERIC(18, 8) NULL`
- `status VARCHAR(32) NOT NULL`
- `submission_attempts INTEGER NOT NULL DEFAULT 1`
- `last_broker_message TEXT NULL`
- `broker_response JSONB NOT NULL DEFAULT '{}'`
- `submitted_at TIMESTAMPTZ NOT NULL`
- `acknowledged_at TIMESTAMPTZ NULL`
- `last_fill_at TIMESTAMPTZ NULL`
- `closed_at TIMESTAMPTZ NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- unique `(broker_name, client_order_id)`
- unique `(broker_name, broker_order_id)` where `broker_order_id IS NOT NULL`
- `(symbol_key, status, submitted_at DESC)`
- `(contract_id, submitted_at DESC)`

#### `broker_fills`

Primary purpose:

- store normalized fill events independently from order rows

Suggested columns:

- `id UUID PRIMARY KEY`
- `broker_order_row_id UUID NULL REFERENCES broker_orders(id)`
- `broker_order_id VARCHAR(128) NOT NULL`
- `client_order_id VARCHAR(128) NULL`
- `symbol VARCHAR(64) NOT NULL`
- `symbol_key VARCHAR(128) NOT NULL`
- `side VARCHAR(16) NOT NULL`
- `fill_qty NUMERIC(18, 8) NOT NULL`
- `fill_price NUMERIC(18, 8) NOT NULL`
- `fill_notional NUMERIC(18, 8) NULL`
- `fill_timestamp TIMESTAMPTZ NOT NULL`
- `raw_payload JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- `(broker_order_id, fill_timestamp ASC)`
- `(symbol_key, fill_timestamp DESC)`

#### `positions`

Primary purpose:

- persist the latest internal position view per owned symbol

Suggested columns:

- `id UUID PRIMARY KEY`
- `symbol VARCHAR(64) NOT NULL`
- `symbol_key VARCHAR(128) NOT NULL`
- `broker_name VARCHAR(32) NOT NULL`
- `net_qty NUMERIC(18, 8) NOT NULL DEFAULT 0`
- `avg_entry_price NUMERIC(18, 8) NULL`
- `market_value NUMERIC(18, 8) NULL`
- `cost_basis NUMERIC(18, 8) NULL`
- `realized_pnl NUMERIC(18, 8) NULL`
- `unrealized_pnl NUMERIC(18, 8) NULL`
- `last_fill_at TIMESTAMPTZ NULL`
- `last_reconciled_at TIMESTAMPTZ NULL`
- `status VARCHAR(32) NOT NULL`
- `source VARCHAR(32) NOT NULL`
- `source_details JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- unique `(broker_name, symbol_key)`
- `(status, updated_at DESC)`

Note:

- this table should represent the aggregate broker-facing position by symbol, not a per-contract synthetic position

#### `position_contract_allocations`

Primary purpose:

- attribute symbol-level position exposure back to individual contracts when multiple contracts share a symbol

Suggested columns:

- `id UUID PRIMARY KEY`
- `position_id UUID NOT NULL REFERENCES positions(id)`
- `contract_id UUID NOT NULL REFERENCES trading_contracts(id)`
- `allocated_qty NUMERIC(18, 8) NOT NULL`
- `allocation_method VARCHAR(32) NOT NULL`
- `allocation_metadata JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- `(position_id, contract_id)`
- `(contract_id, updated_at DESC)`

This table becomes more valuable if multiple contracts on the same symbol are allowed to coexist.

#### `reconciliation_runs`

Primary purpose:

- capture the scope and result of each reconciliation pass

Suggested columns:

- `id UUID PRIMARY KEY`
- `worker_id VARCHAR(128) NULL`
- `scope_type VARCHAR(32) NOT NULL`
- `scope_id VARCHAR(128) NOT NULL`
- `broker_name VARCHAR(32) NOT NULL`
- `mode VARCHAR(32) NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `completed_at TIMESTAMPTZ NULL`
- `status VARCHAR(32) NOT NULL`
- `mismatch_count INTEGER NOT NULL DEFAULT 0`
- `summary JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- `(scope_type, scope_id, started_at DESC)`
- `(status, started_at DESC)`

#### `worker_events`

Primary purpose:

- append-only operational log with lightweight structured payloads

Suggested columns:

- `id UUID PRIMARY KEY`
- `worker_id VARCHAR(128) NOT NULL`
- `shard_id INTEGER NULL`
- `contract_id UUID NULL REFERENCES trading_contracts(id)`
- `symbol_key VARCHAR(128) NULL`
- `event_type VARCHAR(64) NOT NULL`
- `severity VARCHAR(16) NOT NULL`
- `payload JSONB NOT NULL DEFAULT '{}'`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Suggested indexes:

- `(worker_id, created_at DESC)`
- `(event_type, created_at DESC)`
- `(symbol_key, created_at DESC)`

### Persisted Enum Values

The application should own these enums centrally and keep persisted values stable.

#### `trade_intents.status`

- `created`
- `blocked`
- `submit_requested`
- `submitted`
- `rejected`
- `canceled`
- `reconciled`

#### `broker_orders.status`

- `submit_pending`
- `submitted`
- `acknowledged`
- `partially_filled`
- `filled`
- `cancel_pending`
- `canceled`
- `rejected`
- `expired`
- `unknown_broker_outcome`
- `reconciled`

#### `positions.status`

- `flat`
- `open`
- `closing`
- `closed`
- `reconciliation_needed`

#### `reconciliation_runs.status`

- `running`
- `succeeded`
- `succeeded_with_repairs`
- `failed`

#### `worker_events.severity`

- `debug`
- `info`
- `warning`
- `error`
- `critical`

### Symbol Ownership Key

`symbol_key` should be the canonical ownership identifier used for sharding, leases, and durable position rows.

For the first version:

- for plain equities, `symbol_key = symbol`

Future-safe guidance:

- if routing venue, asset class, or expiry become relevant later, evolve `symbol_key` into a canonical composite string such as `asset_class:venue:symbol`
- the worker and controller should depend on the canonical key generator, not build this key ad hoc

### Redis Data Contract

Redis remains the coordination store, so key names and payload structure should be explicit.

#### `ta:assignments:version`

Type:

- string integer

Meaning:

- global monotonically increasing version for all assignment updates

Example:

```text
1042
```

#### `ta:assignments:shard:{shard_id}`

Type:

- set of `symbol_key`

Meaning:

- the currently desired symbol ownership keys for the shard

Example members:

```text
AAPL
MSFT
NVDA
```

#### `ta:lease:symbol:{symbol_key}`

Type:

- JSON string with TTL

TTL:

- 15-30 seconds

Suggested payload:

```json
{
  "worker_id": "worker-2",
  "pod_name": "worker-shards-5d7f6f8b8f-9abc1",
  "shard_id": 2,
  "symbol_key": "AAPL",
  "assignment_version": 1042,
  "leased_at": "2026-05-24T09:30:03Z",
  "expires_at": "2026-05-24T09:30:23Z"
}
```

Acquisition rule:

- acquire with atomic set-if-not-exists
- renew only if the stored `worker_id` still matches the current worker

#### `ta:worker:{worker_id}:heartbeat`

Type:

- JSON string with TTL

Suggested payload:

```json
{
  "worker_id": "worker-2",
  "pod_name": "worker-shards-5d7f6f8b8f-9abc1",
  "shard_id": 2,
  "status": "tradable",
  "owned_symbol_count": 14,
  "updated_at": "2026-05-24T09:30:05Z"
}
```

TTL guidance:

- roughly `3x` the heartbeat interval

#### `ta:worker:{worker_id}:state`

Type:

- JSON string without strict TTL requirement

Purpose:

- optional diagnostic snapshot for debugging and dashboards

Suggested payload:

```json
{
  "session_phase": "open",
  "assignment_version": 1042,
  "symbols": {
    "AAPL": {"state": "tradable", "feed_lag_ms": 420},
    "MSFT": {"state": "paused", "reason": "stale_feed"}
  }
}
```

#### `ta:feed:{symbol_key}:freshness`

Type:

- JSON string or integer timestamp

Recommended payload:

```json
{
  "last_event_at": "2026-05-24T09:30:05.120Z",
  "lag_ms": 420,
  "state": "fresh"
}
```

Persisting a small JSON payload is preferable to a bare timestamp because it helps local debugging.

#### `ta:control:kill_switch`

Type:

- string boolean or JSON flag

Recommended payload:

```json
{
  "enabled": false,
  "updated_at": "2026-05-24T09:00:00Z",
  "updated_by": "controller"
}
```

#### `ta:control:pause:contract:{contract_id}`

Type:

- JSON flag

Purpose:

- block trading activity originating from a specific contract while preserving broader symbol ownership

#### `ta:control:pause:symbol:{symbol_key}`

Type:

- JSON flag

Purpose:

- block all new trading for the owned symbol across contracts

#### `ta:control:pause:shard:{shard_id}`

Type:

- JSON flag

Purpose:

- emergency control over an entire shard process domain

#### `ta:dedupe:signal:{contract_id}:{signal_hash}`

Type:

- string marker with short TTL

Purpose:

- suppress repeated submissions for the same signal burst

TTL guidance:

- align with strategy cadence, for example 5-60 seconds depending on bar interval and signal semantics

### Repository and Persistence Boundaries

To keep the implementation clean, the application code should not spread raw SQL or raw Redis access everywhere.

Suggested persistence-facing interfaces:

- `TradeIntentRepository`
- `BrokerOrderRepository`
- `PositionRepository`
- `ReconciliationRepository`
- `WorkerEventRepository`
- `AssignmentStore`
- `LeaseStore`
- `ControlFlagStore`

Each interface should encapsulate:

- serialization shape
- optimistic assumptions
- retry semantics
- idempotent upsert behavior where needed

### Mode and Environment Tagging

Durable rows created by workers should carry an environment or run mode tag once implementation begins.

Recommended values:

- `paper_live`
- `paper_replay`
- `simulated`

This can be added as either:

- a dedicated `run_mode` column on selected tables
- or a reusable `execution_context` JSONB field if more flexibility is needed

For v1, a dedicated `run_mode` column is simpler and easier to query.

### Proposed Redis Keys

#### Assignment

- `ta:assignments:version`
  Monotonic integer incremented whenever the controller publishes a new desired assignment set.
- `ta:assignments:shard:{shard_id}`
  Set of symbol ownership keys assigned to the shard.

#### Leases

- `ta:lease:symbol:{symbol_key}`
  JSON value with worker and assignment metadata. TTL-backed.

#### Worker Health

- `ta:worker:{worker_id}:heartbeat`
  Heartbeat timestamp and pod metadata. TTL-backed.
- `ta:worker:{worker_id}:state`
  Optional JSON snapshot with current status, contract count, and feed health summary.

#### Feed Freshness

- `ta:feed:{symbol_key}:freshness`
  Timestamp of last acceptable market data event.

#### Operational Controls

- `ta:control:kill_switch`
  Global stop-trading flag.
- `ta:control:pause:contract:{contract_id}`
  Per-contract pause flag.
- `ta:control:pause:symbol:{symbol_key}`
  Per-symbol pause flag.
- `ta:control:pause:shard:{shard_id}`
  Per-shard pause flag.

#### Dedupe

- `ta:dedupe:signal:{contract_id}:{signal_hash}`
  Short TTL key to avoid rapid duplicate submissions for the same signal.

### Assignment Update Strategy

For the first version, workers should poll Redis keys rather than consume Redis Streams.

Recommended behavior:

- controller writes `ta:assignments:version`
- workers poll every 2-5 seconds
- if the version changes, workers reload the shard assignment set

Why this is preferred for v1:

- simpler implementation
- easier local debugging
- assignment changes are expected to be relatively infrequent
- fewer moving parts during early operational hardening

Redis Streams can be added later if faster or more event-driven reassignment becomes necessary.

## Worker Lifecycle

### Startup

1. Load config and discover `worker_id`, `pod_name`, and `shard_id`.
2. Register heartbeat in Redis.
3. Load current assignment version and assigned contracts.
4. For each assigned symbol:
   - attempt lease acquisition
   - mark runtime state as `warming`
5. Reconcile broker state for leased symbols:
   - open orders
   - positions
   - recent fills if available
6. Load strategy configuration and warm historical bars.
7. Subscribe to live feeds.
8. Mark contract `tradable` only after:
   - lease is valid
   - broker reconciliation completes
   - minimum warmup data is available
   - feed freshness is healthy

### Trading Loop

For each market data event:

1. update local market state
2. evaluate strategy
3. if strategy emits a trade:
   - check kill switches
   - check lease validity
   - check feed freshness
   - check position and trade size limits
   - write `trade_intent`
   - generate deterministic `client_order_id`
   - submit order to broker
   - persist resulting order state
4. consume order updates and fills
5. update positions and runtime state

### Shutdown and Drain

On controller drain signal or Kubernetes termination:

1. stop creating new entry orders
2. continue placing and processing exit orders needed to flatten positions for a bounded grace period
3. persist final runtime state and any unresolved broker outcomes
4. release symbol leases or let them expire
5. unregister heartbeat
6. exit

Kubernetes should use a `preStop` hook and a termination grace period long enough for this sequence.

Shutdown invariant:

- a worker should not exit cleanly while still holding an open position unless the system has already marked the contract for reconciliation and raised an alert

## Controller Lifecycle

### Polling Loop

1. query `GET /trading-contracts/active`
2. group active contracts by tradable symbol ownership key
3. filter to symbol groups allowed by current market session phase
4. compute shard assignments
5. write new assignment version and shard sets to Redis if changed
6. scale worker deployment:
   - to configured replica count during `pre_open` and `open`
   - to `0` during `closed`
7. enter `draining` at market close and wait for worker wind-down

The controller should only scale workers to `0` after one of these is true:

- all tracked positions are flat and all workers report drained
- a configured drain timeout is reached and unresolved positions have been escalated for reconciliation/alerting

### Scaling Policy

Initial approach:

- fixed `shard_count` configured per market/session
- worker deployment replica count equals shard count
- no HPA in the first implementation

This is easier to reason about than mixing HPA with deterministic sharding early on.

## Risk and Safety Controls

Minimum controls for stage 1:

- global kill switch
- per-contract pause
- per-shard pause
- max position size per contract
- max notional per contract
- stale-feed block
- duplicate-signal suppression
- broker timeout -> reconcile-before-retry rule

If a worker cannot confirm fresh feed state or lease validity, it must fail closed and stop opening new trades.

## Failure Handling

### Worker crashes after broker accepts an order

Risk:

- broker has an order, Postgres may not

Mitigation:

- deterministic `client_order_id`
- startup reconciliation loads broker orders by symbol and client order id
- unresolved cases are marked `unknown_broker_outcome`

### Redis unavailable

Risk:

- no safe lease coordination

Behavior:

- workers stop opening new trades
- continue processing already-known broker updates for a bounded period if possible
- move contracts to `paused`

### Postgres unavailable

Risk:

- cannot persist intents/orders/fills safely

Behavior:

- fail closed for new orders
- keep heartbeats alive if helpful for coordination
- pause trading until durable persistence returns

### Feed stale or disconnected

Behavior:

- mark contract `paused`
- block new order creation
- allow reconciliation/order status polling to continue

### Controller unavailable during market hours

Behavior:

- workers continue on current assignment version until leases expire or contracts end
- no reassignment changes are applied
- if controller downtime spans a session boundary, workers should still respect local trading-hour rules and drain

## Observability

### Metrics

- assigned contracts per shard
- lease acquisition failures
- feed freshness lag
- trade intents created
- orders submitted / rejected / timed out
- reconciliation mismatches
- worker drain duration
- startup warmup duration

### Logs and Audit

Every order path should be traceable by:

- `contract_id`
- `worker_id`
- `shard_id`
- `trade_intent_id`
- `client_order_id`
- `broker_order_id`

### Alerts

- no active workers during `open`
- stale feed on tradable contracts
- repeated lease thrashing
- reconciliation mismatch rate above threshold
- global kill switch enabled

## Kubernetes Resources

### `contracts-controller` Deployment

- `replicas: 1`
- owns exchange calendar logic
- owns worker deployment scaling

### `worker-shards` Deployment

- `replicas: 0` outside market hours
- `replicas: shard_count` during pre-open and open
- graceful shutdown hooks required

### `reconciler` CronJob

- runs every 1-5 minutes during market hours
- can also be triggered explicitly after startup if needed

### Supporting Resources

- `ConfigMap` for session, Redis, and broker settings
- `Secret` for broker credentials and API auth
- `PodDisruptionBudget` for controller during market hours
- readiness probes that ensure workers do not become ready before warmup completes

## Testing and Debugging Strategy

The system should be testable without a live Kubernetes cluster and without a live broker session.

### Local Development Stack

Use `docker-compose` for the first operational development environment.

Recommended services:

- `postgres`
- `redis`
- `api`
- `controller`
- `worker-1`
- `worker-2`
- optional `reconciler`
- optional `replay-feed` or `mock-broker`

Why this helps:

- easier debugging than starting directly in Kubernetes
- deterministic reproduction of worker/controller coordination
- direct inspection of Postgres and Redis state during failures
- faster iteration on startup, drain, and reconciliation behavior

### Test Modes

#### Unit Tests

Validate:

- strategy decisions
- broker adapter behavior
- market data adapter behavior
- lease acquisition and renewal logic
- order state transitions
- flat-by-close drain behavior

#### Integration Tests

Run against local Postgres and Redis to validate:

- controller assignment writes
- worker lease behavior
- intent/order/fill persistence
- restart and reconciliation flows

#### Replay Tests

Workers should support a replay mode where historical data is streamed through the live worker loop as if it were live.

Use cases:

- reproduce bugs
- test startup and drain logic
- verify no-overnight-position behavior
- validate order intent and persistence paths without live market risk

### Replay Mode

Add a replay-capable market data adapter that can emit:

- historical bars
- optionally synthetic clock or accelerated wall-clock events

The worker should not need a separate execution path for replay mode. Instead:

- use the same worker lifecycle
- use the same persistence model
- swap in a replay market data adapter
- use a simulated or paper broker adapter depending on the test goal

### Persistence in Replay and Test Environments

Replay mode should keep the same durable schema shape as live mode, but must not share the same operational database.

Recommended isolation options:

- separate database per environment
- or separate schema per environment
- or separate deployment-specific database name in local compose

Each persisted run should include a mode marker such as:

- `paper_live`
- `paper_replay`
- `test_replay`
- `simulated`

This keeps the code path close to production while avoiding contamination of paper/live operational records.

### Operational Debugging

The system should support debugging by:

- inspecting Postgres tables for intents, orders, fills, and positions
- inspecting Redis keys for assignments, leases, heartbeats, and freshness
- replaying a failing market window through replay mode
- running multiple local workers in compose to reproduce lease and shard transitions

## Service Interface Design

This section defines the main Python service boundaries for the first implementation. The goal is to keep orchestration, trading decisions, broker access, and persistence separated enough that we can test them independently and evolve the system without major rewrites.

### Design Principles

- keep external systems behind small adapters
- keep worker lifecycle orchestration separate from strategy logic
- keep Redis and Postgres access behind dedicated repositories or stores
- prefer synchronous first implementations if that matches current code style, but avoid interfaces that block a future async migration
- keep Alpaca-specific behavior inside adapter implementations, not in worker orchestration

### Suggested Module Layout

The current project already has `app.api`, `app.db`, `app.data`, and `app.live`. A good next-step structure would be:

- `src/app/live/controller.py`
- `src/app/live/worker.py`
- `src/app/live/reconciler.py`
- `src/app/live/session.py`
- `src/app/live/models.py`
- `src/app/live/broker.py`
- `src/app/live/market_data.py`
- `src/app/live/assignments.py`
- `src/app/live/leases.py`
- `src/app/live/persistence.py`
- `src/app/live/runtime.py`

This keeps the live trading system grouped under `app.live` while still splitting responsibilities into focused files.

### Domain Models

These models should be Pydantic models or dataclasses shared across services.

Core suggested models:

- `SymbolAssignment`
- `LeaseRecord`
- `WorkerHeartbeat`
- `TradeIntentRecord`
- `BrokerOrderRecord`
- `BrokerFillRecord`
- `PositionRecord`
- `ReconciliationResult`
- `SessionPhase`
- `WorkerContractRuntimeState`
- `ExecutionContext`

`ExecutionContext` should carry values such as:

- `run_mode`
- `broker_name`
- `session_phase`
- `assignment_version`
- `worker_id`
- `shard_id`

### Broker Adapter Interface

Purpose:

- isolate broker-specific order submission, order lookup, position lookup, and optional cancel/close behavior

Suggested interface:

```python
from typing import Protocol

class BrokerAdapter(Protocol):
    broker_name: str

    def submit_order(self, request: SubmitOrderRequest) -> BrokerOrderAck: ...

    def list_open_orders(self, symbol: str) -> list[BrokerOrderSnapshot]: ...

    def get_position(self, symbol: str) -> BrokerPositionSnapshot | None: ...

    def list_recent_fills(self, symbol: str, since: datetime | None = None) -> list[BrokerFillSnapshot]: ...

    def cancel_order(self, broker_order_id: str) -> None: ...

    def healthcheck(self) -> BrokerHealthStatus: ...
```

First implementation:

- `AlpacaPaperBrokerAdapter`

Future implementation:

- `AlpacaLiveBrokerAdapter`

Important design rule:

- client code should operate on normalized request/response models, not raw Alpaca payloads

### Market Data Adapter Interface

Purpose:

- provide a unified source of live or replay market events

Suggested interface:

```python
from typing import Protocol, Iterable

class MarketDataAdapter(Protocol):
    source_name: str

    def warmup_bars(self, symbol: str, interval: str, limit: int) -> list[Bar]: ...

    def subscribe(self, symbol: str, interval: str) -> None: ...

    def unsubscribe(self, symbol: str, interval: str) -> None: ...

    def poll_events(self) -> list[MarketEvent]: ...

    def healthcheck(self) -> MarketDataHealthStatus: ...
```

Implementations:

- `AlpacaPollingMarketDataAdapter`
- `ReplayMarketDataAdapter`

For v1, polling recent bars is acceptable if streaming integration is not ready yet.

### Assignment Store Interface

Purpose:

- encapsulate how the controller publishes desired shard ownership and how workers read it

Suggested interface:

```python
from typing import Protocol

class AssignmentStore(Protocol):
    def get_assignment_version(self) -> int: ...

    def publish_assignments(self, version: int, assignments: dict[int, set[str]]) -> None: ...

    def get_shard_assignments(self, shard_id: int) -> set[str]: ...
```

First implementation:

- `RedisAssignmentStore`

Behavior:

- controller is the only writer
- workers are read-only consumers
- assignment publication should replace the full shard set atomically enough that workers never observe a partially written version for long

### Lease Store Interface

Purpose:

- encapsulate symbol ownership claims and renewals

Suggested interface:

```python
from typing import Protocol

class LeaseStore(Protocol):
    def acquire_symbol_lease(self, request: LeaseAcquireRequest) -> LeaseAcquireResult: ...

    def renew_symbol_lease(self, request: LeaseRenewRequest) -> LeaseRenewResult: ...

    def release_symbol_lease(self, symbol_key: str, worker_id: str) -> None: ...

    def get_symbol_lease(self, symbol_key: str) -> LeaseRecord | None: ...
```

First implementation:

- `RedisLeaseStore`

Critical rule:

- renew and release operations must verify the current lease owner to avoid one worker clobbering another worker's valid lease

### Control Flag Store Interface

Purpose:

- centralize kill switch and pause flag access

Suggested interface:

```python
from typing import Protocol

class ControlFlagStore(Protocol):
    def is_global_kill_switch_enabled(self) -> bool: ...

    def is_contract_paused(self, contract_id: str) -> bool: ...

    def is_symbol_paused(self, symbol_key: str) -> bool: ...

    def is_shard_paused(self, shard_id: int) -> bool: ...
```

First implementation:

- `RedisControlFlagStore`

### Persistence Repository Interfaces

Purpose:

- prevent worker logic from embedding SQLAlchemy queries inline

Suggested repositories:

```python
class TradeIntentRepository(Protocol):
    def create(self, intent: TradeIntentCreate) -> TradeIntentRecord: ...
    def mark_submitted(self, intent_id: UUID, order_id: UUID) -> None: ...
    def mark_blocked(self, intent_id: UUID, reason: str) -> None: ...

class BrokerOrderRepository(Protocol):
    def create(self, order: BrokerOrderCreate) -> BrokerOrderRecord: ...
    def get_by_client_order_id(self, broker_name: str, client_order_id: str) -> BrokerOrderRecord | None: ...
    def update_status(self, order_id: UUID, update: BrokerOrderStatusUpdate) -> BrokerOrderRecord: ...
    def list_open_by_symbol(self, symbol_key: str) -> list[BrokerOrderRecord]: ...

class BrokerFillRepository(Protocol):
    def record_fill(self, fill: BrokerFillCreate) -> BrokerFillRecord: ...
    def list_for_order(self, broker_order_id: str) -> list[BrokerFillRecord]: ...

class PositionRepository(Protocol):
    def get_by_symbol(self, broker_name: str, symbol_key: str) -> PositionRecord | None: ...
    def upsert(self, position: PositionUpsert) -> PositionRecord: ...
    def list_open_positions(self) -> list[PositionRecord]: ...

class ReconciliationRepository(Protocol):
    def start_run(self, request: ReconciliationRunCreate) -> ReconciliationRunRecord: ...
    def complete_run(self, run_id: UUID, result: ReconciliationResult) -> None: ...

class WorkerEventRepository(Protocol):
    def record(self, event: WorkerEventCreate) -> None: ...
```

First implementation:

- SQLAlchemy-backed repositories under `app.live.persistence`

### Session Calendar Interface

Purpose:

- keep market-hour logic out of the controller loop and out of the worker

Suggested interface:

```python
from typing import Protocol

class SessionCalendar(Protocol):
    def get_phase(self, now: datetime) -> SessionPhase: ...

    def next_transition(self, now: datetime) -> datetime | None: ...
```

First implementation:

- `StaticExchangeCalendar` or a wrapper around a market-calendar library

The controller should depend on this interface rather than hardcoding timestamps.

### Strategy Runtime Interface

Purpose:

- adapt existing strategy logic to a long-running worker that evaluates one symbol over time

Suggested interface:

```python
from typing import Protocol

class StrategyRuntime(Protocol):
    def ingest_bar(self, bar: Bar) -> list[StrategySignal]: ...

    def snapshot(self) -> StrategyRuntimeSnapshot: ...

    def restore(self, snapshot: StrategyRuntimeSnapshot) -> None: ...
```

Implementation note:

- the existing strategy core already has runtime and snapshot concepts, so this interface should wrap or extend that code rather than duplicate it

### Risk Guard Interface

Purpose:

- centralize the rules that can block order creation even when a strategy emits a signal

Suggested interface:

```python
from typing import Protocol

class RiskGuard(Protocol):
    def evaluate(self, request: RiskEvaluationRequest) -> RiskDecision: ...
```

Expected checks:

- global kill switch
- symbol pause
- contract pause
- shard pause
- max position size
- max notional
- stale feed
- drain-phase entry block

### Reconciliation Service Interface

Purpose:

- normalize broker-vs-internal comparison logic so it can run on startup, periodically, and during incident handling

Suggested interface:

```python
from typing import Protocol

class ReconciliationService(Protocol):
    def reconcile_symbol(self, request: ReconcileSymbolRequest) -> ReconciliationResult: ...

    def reconcile_worker_scope(self, request: ReconcileWorkerScopeRequest) -> list[ReconciliationResult]: ...
```

Responsibilities:

- load broker open orders and positions
- compare against Postgres records
- create missing durable rows where safe
- mark unresolved mismatches for alerting

### Worker Runtime Coordinator

Purpose:

- orchestrate the full worker lifecycle without embedding all behavior in one function

Suggested interface:

```python
class WorkerRuntimeCoordinator:
    def run_forever(self) -> None: ...
    def refresh_assignments(self) -> None: ...
    def acquire_and_warm_symbols(self) -> None: ...
    def process_market_events(self) -> None: ...
    def drain(self) -> None: ...
```

Internal collaborators:

- `AssignmentStore`
- `LeaseStore`
- `ControlFlagStore`
- `MarketDataAdapter`
- `BrokerAdapter`
- `TradeIntentRepository`
- `BrokerOrderRepository`
- `BrokerFillRepository`
- `PositionRepository`
- `ReconciliationService`
- `RiskGuard`
- `SessionCalendar`

Key rule:

- the coordinator owns lifecycle orchestration, but trading decisions should still emerge from strategy runtimes and risk checks, not from the coordinator itself

### Controller Service Interface

Purpose:

- encapsulate the contracts polling loop and assignment publication logic

Suggested interface:

```python
class ContractsControllerService:
    def sync_once(self) -> ControllerSyncResult: ...
    def run_forever(self) -> None: ...
```

Internal collaborators:

- contracts API client
- `SessionCalendar`
- `AssignmentStore`
- worker scaler
- worker event logger

### Worker Scaler Interface

Purpose:

- abstract how worker deployments are scaled so the controller is not tightly coupled to Kubernetes client details

Suggested interface:

```python
from typing import Protocol

class WorkerScaler(Protocol):
    def scale_to(self, replica_count: int) -> None: ...
    def current_replicas(self) -> int: ...
```

Implementations:

- `KubernetesWorkerScaler`
- `NoopWorkerScaler` for local docker-compose development

### Contracts API Client Interface

Purpose:

- isolate the retrieval of active contracts from the controller

Suggested interface:

```python
from typing import Protocol

class ContractsApiClient(Protocol):
    def get_active_contracts(self, active_at: datetime | None = None) -> list[TradingContractSnapshot]: ...
```

Implementation:

- `HttpContractsApiClient`

### CLI Entry Points

The repo already uses `typer`, and all new operational entry points should follow that rule.

Suggested commands:

- `kalyxctl live-controller --config ...`
- `kalyxctl live-worker --config ... --shard-id ...`
- `kalyxctl live-reconciler --config ...`
- `backtest live-replay --config ...`

These commands should:

- load Pydantic config models
- construct repositories and adapters
- run the selected long-lived service

### Configuration Models

The current config models are a good base, but live orchestration will likely need additional configuration sections.

Suggested new models:

- `LiveTradingConfig`
- `LiveTradingGlobalConfig`
- `ControllerConfig`
- `WorkerConfig`
- `RedisConfig`
- `PostgresRuntimeConfig`
- `ReplayConfig`
- `SessionConfig`

Suggested responsibilities:

- `ControllerConfig`: polling interval, shard count, scale timing, contracts API URL
- `WorkerConfig`: shard id, feed poll interval, warmup bars, drain timeout
- `ReplayConfig`: replay speed, clock mode, historical source, broker mode
- `SessionConfig`: market calendar, pre-open window, drain timeout

### Dependency Assembly

To keep service startup explicit and testable, avoid large hidden globals.

Recommended pattern:

- each CLI command calls a small builder function
- the builder wires config, repositories, adapters, and service objects
- services receive explicit constructor dependencies

For example:

```python
def build_live_worker(config: LiveTradingConfig, shard_id: int) -> WorkerRuntimeCoordinator:
    ...
```

This fits the current style in `src/app/live/executor.py` and keeps unit testing straightforward.

### Interface-Level Testing Plan

Before full end-to-end implementation, test these seams directly:

- broker adapter contract tests
- assignment store and lease store tests against Redis
- repository tests against Postgres
- controller service tests with fake scaler and fake contracts client
- worker coordinator tests with fake broker and replay data adapter

This is the easiest way to keep the implementation reliable while the system is still evolving.

## Rollout Plan

### Milestone 1

- add durable tables for intents, orders, fills, positions, and reconciliation
- keep current REST API contract model as-is

### Milestone 2

- add Redis-backed assignment and leasing
- build a long-running worker process that can own multiple contracts

### Milestone 3

- integrate current Alpaca executor logic into the worker
- replace local file runtime state with Postgres-backed persistence

### Milestone 4

- add controller-driven market session management and worker scale-to-zero

### Milestone 5

- add reconciliation job, kill switches, and alerts

## Open Decisions

These should be resolved before implementation starts:

1. What exact symbol ownership key should be used for non-equity instruments or multi-venue routing?
2. Should replay mode use a simulated broker by default, or Alpaca paper in selected end-to-end tests?
3. Do we need contract-group-level risk rules in addition to symbol-level ownership?

## Recommended First Implementation Defaults

- broker: Alpaca paper
- broker abstraction: define now, implement Alpaca paper first
- session model: pre-open warmup, open trading, close drain, scale-to-zero after drain
- overnight policy: no overnight positions; workers may use drain time to flatten
- assignment model: deterministic shard hash + Redis lease per symbol ownership key
- persistence: Postgres for all durable trading records
- coordination: Redis polling plus ephemeral state and control flags
- strategy ownership: one worker may own many contracts, but only one worker may trade a given symbol ownership key at a time
- local testing: docker-compose with Postgres, Redis, controller, and multiple workers
- replay support: same worker lifecycle with replay-capable market data adapter and isolated persistence
