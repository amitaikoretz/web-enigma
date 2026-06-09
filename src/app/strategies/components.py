from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

import pandas as pd

from app.replay_debug import maybe_break_for_trade_replay
from app.strategies.core import StrategyContext, StrategyCore, StrategyDecision
from app.strategies.vectorbt_support import VectorbtSpec
from app.strategies.vectorbt_support import _broadcast_series_to_frame


class TriggerCore(ABC):
    def load_state(self, state: dict[str, Any] | None) -> None:
        return None

    def dump_state(self) -> dict[str, Any]:
        return {}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def on_trade_trimmed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def vectorbt_supported(self) -> bool:
        return False

    def vectorbt_spec(self, context: Any) -> Any | None:
        return None

    @abstractmethod
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        raise NotImplementedError


class ExitRuleCore(ABC):
    def load_state(self, state: dict[str, Any] | None) -> None:
        return None

    def dump_state(self) -> dict[str, Any]:
        return {}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def on_trade_trimmed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def vectorbt_supported(self) -> bool:
        return False

    def vectorbt_spec(self, context: Any) -> Any | None:
        return None

    @abstractmethod
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        raise NotImplementedError


def _ensure_trigger_decision(
    decision: StrategyDecision, *, trigger_name: str
) -> StrategyDecision:
    if decision.action == "close":
        raise ValueError(f"Trigger '{trigger_name}' returned close() which is not allowed")
    return decision


def _ensure_exit_rule_decision(
    decision: StrategyDecision, *, rule_name: str
) -> StrategyDecision:
    if decision.action == "buy":
        raise ValueError(f"Exit rule '{rule_name}' returned buy() which is not allowed")
    return decision


class ComposableStrategyCore(StrategyCore):
    def __init__(
        self,
        *,
        trigger_name: str,
        trigger: TriggerCore,
        exit_rules: Sequence[tuple[str, ExitRuleCore]],
        entry_policy: Any | None = None,
    ):
        self._trigger_name = trigger_name
        self._trigger = trigger
        self._exit_rules = list(exit_rules)
        self._entry_policy = entry_policy

    def entry_regime_label(self) -> str | None:
        label_fn = getattr(self._trigger, "entry_regime_label", None)
        if callable(label_fn):
            return label_fn()
        return None

    def load_state(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self._trigger.load_state(state.get("trigger"))
        exits_state = state.get("exit_rules")
        if not isinstance(exits_state, dict):
            exits_state = {}
        for name, rule in self._exit_rules:
            rule.load_state(exits_state.get(name))

    def dump_state(self) -> dict[str, Any]:
        return {
            "trigger": self._trigger.dump_state(),
            "exit_rules": {name: rule.dump_state() for name, rule in self._exit_rules},
        }

    def vectorbt_supported(self) -> bool:
        if self._entry_policy is not None:
            return False
        if not self._trigger.vectorbt_supported():
            return False
        return all(rule.vectorbt_supported() for _, rule in self._exit_rules)

    def vectorbt_spec(self, context: Any) -> Any | None:
        if not self.vectorbt_supported():
            return None

        trigger_spec = self._trigger.vectorbt_spec(context)
        if trigger_spec is None:
            return None
        entries = getattr(trigger_spec, "entries", None)
        if entries is None:
            return None

        shared = getattr(context, "shared", None)
        if isinstance(shared, dict):
            shared["entries"] = entries
            shared["size"] = getattr(trigger_spec, "size", None)

        exit_specs: list[Any] = []
        for _, rule in self._exit_rules:
            rule_spec = rule.vectorbt_spec(context)
            if rule_spec is None:
                return None
            exit_specs.append(rule_spec)

        combined_exits = None
        combined_trim_exits = None
        combined_trim_portion = None
        for rule_spec in exit_specs:
            exits = getattr(rule_spec, "exits", None)
            combined_exits = _merge_masks(combined_exits, exits)
            trim_exits = getattr(rule_spec, "trim_exits", None)
            combined_trim_exits = _merge_masks(combined_trim_exits, trim_exits)
            trim_portion = getattr(rule_spec, "trim_portion", None)
            if trim_portion is not None:
                combined_trim_portion = trim_portion

        merged_metadata: dict[str, Any] = {}
        merged_metadata.update(getattr(trigger_spec, "metadata", {}) or {})
        for rule_spec in exit_specs:
            merged_metadata.update(getattr(rule_spec, "metadata", {}) or {})

        warmup_bars = max(
            [int(getattr(trigger_spec, "warmup_bars", 0) or 0)]
            + [int(getattr(rule_spec, "warmup_bars", 0) or 0) for rule_spec in exit_specs]
        )

        return VectorbtSpec(
            entries=entries,
            exits=combined_exits,
            trim_exits=combined_trim_exits,
            trim_portion=combined_trim_portion,
            size=getattr(trigger_spec, "size", None),
            sl_stop=getattr(trigger_spec, "sl_stop", None),
            tp_stop=getattr(trigger_spec, "tp_stop", None),
            trail_stop=getattr(trigger_spec, "trail_stop", None),
            warmup_bars=warmup_bars,
            metadata=merged_metadata,
        )

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        maybe_break_for_trade_replay(
            "app.strategies.components.ComposableStrategyCore.on_bar",
            bar_index=len(context.bars) - 1,
            timestamp=context.bar.iso_timestamp,
        )
        if context.position.is_open:
            for rule_name, rule in self._exit_rules:
                decision = _ensure_exit_rule_decision(rule.on_bar(context), rule_name=rule_name)
                if decision.action == "close":
                    reason = decision.reason or "exit"
                    wrapped = StrategyDecision.close(f"exit:{rule_name}:{reason}")
                    self._trigger.on_trade_closed(context, wrapped)
                    for _, other in self._exit_rules:
                        other.on_trade_closed(context, wrapped)
                    return wrapped
                if decision.action == "trim":
                    reason = decision.reason or "trim"
                    wrapped = StrategyDecision.trim(
                        float(decision.portion or 0.0),
                        f"exit:{rule_name}:{reason}",
                    )
                    self._trigger.on_trade_trimmed(context, wrapped)
                    for _, other in self._exit_rules:
                        other.on_trade_trimmed(context, wrapped)
                    return wrapped
            return StrategyDecision.hold()

        decision = _ensure_trigger_decision(self._trigger.on_bar(context), trigger_name=self._trigger_name)
        if decision.action == "buy":
            if self._entry_policy is not None:
                decision = self._entry_policy.apply(context, decision)
                if decision.action != "buy":
                    return StrategyDecision.hold(
                        reason=decision.reason,
                        auditor_rejection=decision.auditor_rejection,
                        entry_intent=decision.entry_intent,
                    )
            reason = decision.reason or "entry"
            wrapped = StrategyDecision.buy(
                float(decision.size or 0.0),
                f"trigger:{self._trigger_name}:{reason}",
                entry_intent=decision.entry_intent,
            )
            self._trigger.on_trade_opened(context, wrapped)
            for _, rule in self._exit_rules:
                rule.on_trade_opened(context, wrapped)
            return wrapped
        return StrategyDecision.hold(
            reason=decision.reason,
            auditor_rejection=decision.auditor_rejection,
            entry_intent=decision.entry_intent,
        )


def _merge_masks(left: Any | None, right: Any | None) -> Any | None:
    if right is None:
        return left
    if left is None:
        return right
    if isinstance(left, pd.DataFrame) and isinstance(right, pd.Series):
        right = _broadcast_series_to_frame(right, left.columns)
    elif isinstance(left, pd.Series) and isinstance(right, pd.DataFrame):
        left = _broadcast_series_to_frame(left, right.columns)
    elif isinstance(left, pd.DataFrame) and isinstance(right, pd.DataFrame):
        columns = left.columns.union(right.columns)
        left = left.reindex(columns=columns, fill_value=False)
        right = right.reindex(columns=columns, fill_value=False)
    return left | right
