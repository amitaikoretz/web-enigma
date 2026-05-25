from __future__ import annotations

import os

from app.config.models import LiveTradingConfig
from app.db.session import get_session_factory
from app.live.assignments import RedisAssignmentStore, get_shared_redis_backend
from app.live.broker import AlpacaPaperBrokerAdapter
from app.live.control_flags import RedisControlFlagStore
from app.live.controller import ContractsControllerService, HttpContractsApiClient, NoopWorkerScaler
from app.live.leases import RedisLeaseStore
from app.live.market_data import NoopMarketDataAdapter
from app.live.revocation import RedisContractRevocationStore
from app.live.persistence import (
    SqlAlchemyBrokerFillRepository,
    SqlAlchemyBrokerOrderRepository,
    SqlAlchemyPositionRepository,
    SqlAlchemyReconciliationRepository,
    SqlAlchemyTradeIntentRepository,
    SqlAlchemyWorkerEventRepository,
)
from app.live.reconciler import PlaceholderReconciliationService
from app.live.session import WallClockSessionCalendar
from app.live.worker import WorkerRuntimeCoordinator


def build_live_controller(config: LiveTradingConfig) -> ContractsControllerService:
    backend = get_shared_redis_backend(config.global_config.redis.url)
    assignment_store = RedisAssignmentStore(backend=backend, key_prefix=config.global_config.redis.key_prefix)
    session_factory = get_session_factory()
    return ContractsControllerService(
        contracts_api_client=HttpContractsApiClient(base_url=config.global_config.controller.contracts_api_base_url),
        assignment_store=assignment_store,
        session_calendar=WallClockSessionCalendar(config=config.global_config.session),
        worker_scaler=NoopWorkerScaler(),
        shard_count=config.global_config.controller.shard_count,
        scale_up_replicas=config.global_config.controller.scale_up_replicas or config.global_config.controller.shard_count,
        poll_interval_seconds=config.global_config.controller.poll_interval_seconds,
        worker_event_repository=SqlAlchemyWorkerEventRepository(session_factory),
    )


def build_live_worker(config: LiveTradingConfig, shard_id: int) -> WorkerRuntimeCoordinator:
    backend = get_shared_redis_backend(config.global_config.redis.url)
    assignment_store = RedisAssignmentStore(backend=backend, key_prefix=config.global_config.redis.key_prefix)
    lease_store = RedisLeaseStore(backend=backend, key_prefix=config.global_config.redis.key_prefix)
    control_flag_store = RedisControlFlagStore(backend=backend, key_prefix=config.global_config.redis.key_prefix)
    session_factory = get_session_factory()
    worker_id = config.global_config.worker.worker_id or f"worker-{shard_id}"
    pod_name = os.environ.get("HOSTNAME", worker_id)
    return WorkerRuntimeCoordinator(
        worker_id=worker_id,
        pod_name=pod_name,
        shard_id=shard_id,
        assignment_store=assignment_store,
        lease_store=lease_store,
        control_flag_store=control_flag_store,
        contracts_api_client=HttpContractsApiClient(
            base_url=config.global_config.controller.contracts_api_base_url,
        ),
        revocation_store=RedisContractRevocationStore(
            backend=backend,
            key_prefix=config.global_config.redis.key_prefix,
        ),
        worker_event_repository=SqlAlchemyWorkerEventRepository(session_factory),
        heartbeat_interval_seconds=config.global_config.redis.heartbeat_interval_seconds,
        lease_ttl_seconds=config.global_config.redis.lease_ttl_seconds,
    )


def build_live_reconciler(config: LiveTradingConfig) -> PlaceholderReconciliationService:
    session_factory = get_session_factory()
    return PlaceholderReconciliationService(
        reconciliation_repository=SqlAlchemyReconciliationRepository(session_factory),
        worker_event_repository=SqlAlchemyWorkerEventRepository(session_factory),
        broker_adapter=AlpacaPaperBrokerAdapter(),
        market_data_adapter=NoopMarketDataAdapter(),
        broker_order_repository=SqlAlchemyBrokerOrderRepository(session_factory),
        broker_fill_repository=SqlAlchemyBrokerFillRepository(session_factory),
        position_repository=SqlAlchemyPositionRepository(session_factory),
        trade_intent_repository=SqlAlchemyTradeIntentRepository(session_factory),
        run_mode=config.global_config.runtime.run_mode,
    )
