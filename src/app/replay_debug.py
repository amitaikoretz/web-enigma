from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
from importlib import import_module


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@dataclass(frozen=True)
class ReplayDebugTarget:
    target_bar_index: int | None = None
    target_bar_time: datetime | None = None
    target_methods: tuple[str, ...] = ()
    break_at: str = "entry"


_ACTIVE_DEBUG_TARGET: ReplayDebugTarget | None = None
_DEBUG_TARGET_TRIGGERED = False


def install_trade_replay_debug_target(target: ReplayDebugTarget) -> None:
    global _ACTIVE_DEBUG_TARGET
    global _DEBUG_TARGET_TRIGGERED
    _ACTIVE_DEBUG_TARGET = target
    _DEBUG_TARGET_TRIGGERED = False


def clear_trade_replay_debug_target() -> None:
    global _ACTIVE_DEBUG_TARGET
    global _DEBUG_TARGET_TRIGGERED
    _ACTIVE_DEBUG_TARGET = None
    _DEBUG_TARGET_TRIGGERED = False


def _trigger_breakpoint() -> None:
    try:
        debugpy = import_module("debugpy")
    except Exception:  # noqa: BLE001
        breakpoint()
        return

    is_connected = getattr(debugpy, "is_client_connected", None)
    if callable(is_connected) and not is_connected():
        breakpoint()
        return

    trigger = getattr(debugpy, "breakpoint", None)
    if callable(trigger):
        trigger()
        return

    breakpoint()


def maybe_break_for_trade_replay(
    method_name: str,
    *,
    bar_index: int | None = None,
    timestamp: str | None = None,
) -> None:
    global _DEBUG_TARGET_TRIGGERED
    if _ACTIVE_DEBUG_TARGET is None or _DEBUG_TARGET_TRIGGERED:
        return
    if method_name not in _ACTIVE_DEBUG_TARGET.target_methods:
        return
    should_break = False
    if _ACTIVE_DEBUG_TARGET.target_bar_index is not None and bar_index is not None:
        should_break = bar_index >= _ACTIVE_DEBUG_TARGET.target_bar_index
    else:
        current_bar_time = _parse_timestamp(timestamp)
        if _ACTIVE_DEBUG_TARGET.target_bar_time is not None and current_bar_time is not None:
            should_break = current_bar_time >= _ACTIVE_DEBUG_TARGET.target_bar_time
    if not should_break:
        return
    _DEBUG_TARGET_TRIGGERED = True
    _trigger_breakpoint()
