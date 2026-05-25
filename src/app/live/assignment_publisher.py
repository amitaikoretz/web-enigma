from __future__ import annotations

import hashlib
from collections import defaultdict

from app.live.assignments import AssignmentStore
from app.live.models import TradingContractSnapshot


def group_contracts_by_symbol(contracts: list[TradingContractSnapshot]) -> dict[str, list[TradingContractSnapshot]]:
    grouped: dict[str, list[TradingContractSnapshot]] = defaultdict(list)
    for contract in contracts:
        grouped[contract.symbol_key].append(contract)
    return grouped


def compute_shard_id(symbol_key: str, shard_count: int) -> int:
    digest = hashlib.sha256(symbol_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count


def compute_assignments(symbol_keys: object, shard_count: int) -> dict[int, set[str]]:
    assignments = {shard_id: set() for shard_id in range(shard_count)}
    for symbol_key in sorted(symbol_keys):
        assignments[compute_shard_id(str(symbol_key), shard_count)].add(str(symbol_key))
    return assignments


def publish_assignments_for_contracts(
    assignment_store: AssignmentStore,
    contracts: list[TradingContractSnapshot],
    shard_count: int,
) -> int:
    grouped = group_contracts_by_symbol(contracts)
    assignments = compute_assignments(grouped.keys(), shard_count)
    next_version = assignment_store.get_assignment_version() + 1
    assignment_store.publish_assignments(next_version, assignments)
    return next_version


def contracts_to_snapshots(contracts) -> list[TradingContractSnapshot]:
    from app.db.models import TradingContract

    snapshots: list[TradingContractSnapshot] = []
    for contract in contracts:
        if not isinstance(contract, TradingContract):
            continue
        snapshots.append(
            TradingContractSnapshot(
                contract_id=contract.id,
                symbol=contract.symbol,
                strategy=contract.strategy,
                strategy_params=contract.strategy_params or {},
                start_datetime=contract.start_datetime,
                end_datetime=contract.end_datetime,
                maximum_trade_size=float(contract.maximum_trade_size),
                total_invested=float(contract.total_invested),
            )
        )
    return snapshots
