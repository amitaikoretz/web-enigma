from __future__ import annotations

from typing import Any

from app.config.models import BacktestModelPolicyConfig
from app.strategies.components import ComposableStrategyCore
from app.strategies.exit_rules import EXIT_RULE_REGISTRY, ExitRulesSelection, resolve_exit_rule_warmup_bars
from app.strategies.triggers import TRIGGER_REGISTRY, TriggerSelection, resolve_trigger_warmup_bars


def build_strategy_core(
    *,
    trigger: TriggerSelection,
    exit_rules: ExitRulesSelection,
    entry_policy: Any | None = None,
) -> ComposableStrategyCore:
    trigger_spec = TRIGGER_REGISTRY[trigger.name]
    trigger_core = trigger_spec.factory(dict(trigger.params))
    rules: list[tuple[str, Any]] = []
    for rule in exit_rules.rules:
        spec = EXIT_RULE_REGISTRY[rule.name]
        rules.append((rule.name, spec.factory(dict(rule.params))))
    return ComposableStrategyCore(
        trigger_name=trigger.name,
        trigger=trigger_core,
        exit_rules=rules,
        entry_policy=entry_policy,
    )


def resolve_warmup_bars(*, trigger: TriggerSelection, exit_rules: ExitRulesSelection) -> int:
    trigger_warmup = resolve_trigger_warmup_bars(trigger.name, trigger.params)
    rule_warmups = [resolve_exit_rule_warmup_bars(rule.name, rule.params) for rule in exit_rules.rules]
    return max([trigger_warmup, *rule_warmups, 1])


def composed_strategy_id(
    *,
    trigger: TriggerSelection,
    exit_rules: ExitRulesSelection,
    model_policy: BacktestModelPolicyConfig | None = None,
) -> str:
    # Used as "strategy name" for reporting/candidate logs.
    parts = [trigger.name]
    if model_policy is not None and (model_policy.forecast_model is not None or model_policy.risk_model is not None):
        parts.append(f"models:{model_policy.stable_id()}")
    parts.append(f"exits:{exit_rules.stable_id()}")
    return "|".join(parts)
