from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence

from app.replay_debug import maybe_break_for_trade_replay
from app.strategies.core import StrategyContext, StrategyCore, StrategyDecision


class TriggerCore(ABC):
    def load_state(self, state: dict[str, Any] | None) -> None:
        return None

    def dump_state(self) -> dict[str, Any]:
        return {}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        return None

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
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
    def __init__(self, *, trigger_name: str, trigger: TriggerCore, exit_rules: Sequence[tuple[str, ExitRuleCore]]):
        self._trigger_name = trigger_name
        self._trigger = trigger
        self._exit_rules = list(exit_rules)

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
            return StrategyDecision.hold()

        decision = _ensure_trigger_decision(self._trigger.on_bar(context), trigger_name=self._trigger_name)
        if decision.action == "buy":
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
