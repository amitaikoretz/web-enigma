from __future__ import annotations

import math
from statistics import median
from typing import Any

import pandas as pd

from app.output.models import (
    CandidateDiagnostics,
    CandidateRecord,
    FilterDiagnostics,
    HistogramBin,
    OrderRecord,
    RejectionRecord,
    RiskMetrics,
    TradeDiagnostics,
    TradeDistribution,
    TradeRecord,
)

HOLD_TIME_MINUTE_BINS: list[tuple[float, float, str]] = [
    (0.0, 5.0, "0–5 min"),
    (5.0, 15.0, "5–15 min"),
    (15.0, 30.0, "15–30 min"),
    (30.0, 60.0, "30–60 min"),
    (60.0, math.inf, "60+ min"),
]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def duration_to_minutes(duration: Any) -> float | None:
    if duration is None:
        return None
    try:
        if pd.isna(duration):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(duration, pd.Timedelta):
        return duration.total_seconds() / 60.0
    try:
        return pd.Timedelta(duration).total_seconds() / 60.0
    except (TypeError, ValueError):
        return None


def _count_values_in_bins(values: list[float], edges: list[tuple[float, float, str]]) -> list[HistogramBin]:
    bins: list[HistogramBin] = []
    for start, end, label in edges:
        count = sum(1 for value in values if start <= value < end)
        bins.append(HistogramBin(start=start, end=end if math.isfinite(end) else start, count=count, label=label))
    return bins


def _size_bin_edges(values: list[float], *, max_bins: int = 6) -> list[tuple[float, float, str]]:
    if not values:
        return []
    unique_values = sorted(set(values))
    if len(unique_values) == 1:
        value = unique_values[0]
        label = f"{value:g}"
        return [(value, value, label)]

    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        label = f"{minimum:g}"
        return [(minimum, maximum, label)]

    span = maximum - minimum
    bin_count = min(max_bins, max(2, len(unique_values)))
    width = span / bin_count
    edges: list[tuple[float, float, str]] = []
    for index in range(bin_count):
        start = minimum + index * width
        end = maximum if index == bin_count - 1 else minimum + (index + 1) * width
        if index == bin_count - 1:
            label = f"{start:.2f}+"
        else:
            label = f"{start:.2f}–{end:.2f}"
        edges.append((start, end if index < bin_count - 1 else math.inf, label))
    return edges


def _count_values_in_dynamic_bins(values: list[float]) -> list[HistogramBin]:
    edges = _size_bin_edges(values)
    bins: list[HistogramBin] = []
    for start, end, label in edges:
        if math.isfinite(end):
            if start == end:
                count = sum(1 for value in values if value == start)
            else:
                count = sum(1 for value in values if start <= value < end or (end == start and value == start))
        else:
            count = sum(1 for value in values if value >= start)
        bins.append(HistogramBin(start=start, end=end if math.isfinite(end) else start, count=count, label=label))
    return bins


def build_trade_distribution(trades: list[TradeRecord]) -> TradeDistribution:
    hold_minutes = [trade.hold_minutes for trade in trades if trade.hold_minutes is not None]
    sizes = [abs(trade.size) for trade in trades]
    notionals = [abs(trade.value) for trade in trades]
    return TradeDistribution(
        hold_time_bins=_count_values_in_bins(hold_minutes, HOLD_TIME_MINUTE_BINS),
        hold_time_unit="minutes",
        size_bins=_count_values_in_dynamic_bins(sizes),
        size_value_bins=_count_values_in_dynamic_bins(notionals) if notionals else None,
    )


def enrich_trade_records(
    trade_log: list[dict[str, Any]],
    closed_trades: pd.DataFrame,
) -> list[TradeRecord]:
    records: list[TradeRecord] = []
    for index, raw in enumerate(trade_log):
        row = closed_trades.iloc[index] if index < len(closed_trades) else None
        hold_minutes = None
        hold_bars = None
        entry_datetime = None
        if row is not None:
            hold_minutes = duration_to_minutes(row.get("Duration"))
            entry_bar = row.get("EntryBar")
            exit_bar = row.get("ExitBar")
            if entry_bar is not None and exit_bar is not None and not pd.isna(entry_bar) and not pd.isna(exit_bar):
                hold_bars = max(0, int(exit_bar) - int(entry_bar))
            entry_datetime = _iso_timestamp(row.get("EntryTime"))
        records.append(
            TradeRecord(
                datetime=raw.get("datetime"),
                size=float(raw.get("size", 0.0)),
                price=float(raw.get("price", 0.0)),
                value=float(raw.get("value", 0.0)),
                pnl=float(raw.get("pnl", 0.0)),
                pnlcomm=float(raw.get("pnlcomm", 0.0)),
                reason=raw.get("reason"),
                entry_datetime=entry_datetime,
                hold_minutes=hold_minutes,
                hold_bars=hold_bars,
                regime_label=raw.get("regime_label"),
            )
        )
    return records


def build_order_records(order_log: list[dict[str, Any]]) -> list[OrderRecord]:
    return [
        OrderRecord(
            datetime=raw.get("datetime"),
            status=str(raw.get("status", "")),
            is_buy=bool(raw.get("is_buy")),
            size=float(raw.get("size", 0.0)),
            price=float(raw.get("price", 0.0)),
            value=float(raw.get("value", 0.0)),
            commission=float(raw.get("commission", 0.0)),
        )
        for raw in order_log
    ]


def build_rejection_records(rejection_log: list[dict[str, Any]]) -> list[RejectionRecord]:
    return [
        RejectionRecord(
            datetime=raw.get("datetime"),
            symbol=raw.get("symbol"),
            reason=raw.get("reason"),
        )
        for raw in rejection_log
    ]


def build_candidate_records(candidate_log: list[Any]) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    for raw in candidate_log:
        if hasattr(raw, "model_dump"):
            records.append(CandidateRecord.model_validate(raw.model_dump()))
        elif isinstance(raw, dict):
            records.append(CandidateRecord.model_validate(raw))
    return records


def compute_candidate_diagnostics(candidates: list[CandidateRecord]) -> CandidateDiagnostics:
    traded = sum(1 for candidate in candidates if candidate.was_traded)
    return CandidateDiagnostics(
        total_candidates=len(candidates),
        traded_candidates=traded,
        rejected_candidates=len(candidates) - traded,
    )


def compute_trade_diagnostics(
    trades: list[TradeRecord],
    orders: list[OrderRecord],
    *,
    start_value: float,
    end_value: float,
) -> TradeDiagnostics:
    net_pnls = [trade.pnlcomm for trade in trades]
    gross_pnls = [trade.pnl for trade in trades]
    net_pnl = end_value - start_value
    gross_pnl = sum(gross_pnls)
    total_commission = sum(order.commission for order in orders)

    wins = [value for value in net_pnls if value > 0]
    losses = [value for value in net_pnls if value <= 0]
    total_trades = len(trades)

    profit_factor = None
    loss_total = abs(sum(losses))
    if loss_total > 0:
        profit_factor = sum(wins) / loss_total

    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    payoff_ratio = None
    if avg_win is not None and avg_loss is not None and avg_loss != 0:
        payoff_ratio = avg_win / abs(avg_loss)

    hold_minutes = [trade.hold_minutes for trade in trades if trade.hold_minutes is not None]
    exit_reason_counts: dict[str, int] = {}
    exit_reason_pnl: dict[str, float] = {}
    for trade in trades:
        reason = trade.reason or "unknown"
        exit_reason_counts[reason] = exit_reason_counts.get(reason, 0) + 1
        exit_reason_pnl[reason] = exit_reason_pnl.get(reason, 0.0) + trade.pnlcomm

    dominant_exit_reason = None
    if exit_reason_counts:
        dominant_exit_reason = max(exit_reason_counts, key=exit_reason_counts.get)

    commission_pct_of_gross = None
    if gross_pnl > 0:
        commission_pct_of_gross = total_commission / gross_pnl * 100.0

    diagnostics = TradeDiagnostics(
        net_pnl=net_pnl,
        gross_pnl=gross_pnl,
        total_commission=total_commission,
        commission_pct_of_gross=commission_pct_of_gross,
        profit_factor=profit_factor,
        expectancy=(sum(net_pnls) / total_trades) if total_trades else None,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff_ratio,
        win_rate_pct=(len(wins) / total_trades * 100.0) if total_trades else None,
        median_hold_minutes=median(hold_minutes) if hold_minutes else None,
        mean_hold_minutes=(sum(hold_minutes) / len(hold_minutes)) if hold_minutes else None,
        best_trade_pnl=max(net_pnls) if net_pnls else None,
        worst_trade_pnl=min(net_pnls) if net_pnls else None,
        exit_reason_counts=exit_reason_counts,
        exit_reason_pnl=exit_reason_pnl,
        dominant_exit_reason=dominant_exit_reason,
        distributions=build_trade_distribution(trades) if trades else None,
    )
    return diagnostics


def compute_filter_diagnostics(
    rejections: list[RejectionRecord],
    *,
    total_trades: int,
) -> FilterDiagnostics:
    rejection_counts: dict[str, int] = {}
    for rejection in rejections:
        reason = rejection.reason or "unknown"
        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
    total_rejections = len(rejections)
    signal_to_trade_pct = None
    opportunities = total_trades + total_rejections
    if opportunities > 0:
        signal_to_trade_pct = total_trades / opportunities * 100.0
    return FilterDiagnostics(
        rejection_counts=rejection_counts,
        total_rejections=total_rejections,
        signal_to_trade_pct=signal_to_trade_pct,
    )


def _format_duration(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timedelta):
        return str(value)
    return str(value)


def compute_risk_metrics(stats: Any, *, return_pct: float) -> RiskMetrics:
    buy_hold_return_pct = _as_float(stats.get("Buy & Hold Return [%]"))
    alpha_vs_buy_hold_pct = None
    if buy_hold_return_pct is not None:
        alpha_vs_buy_hold_pct = return_pct - buy_hold_return_pct
    return RiskMetrics(
        sortino_ratio=_as_float(stats.get("Sortino Ratio")),
        calmar_ratio=_as_float(stats.get("Calmar Ratio")),
        buy_hold_return_pct=buy_hold_return_pct,
        alpha_vs_buy_hold_pct=alpha_vs_buy_hold_pct,
        exposure_time_pct=_as_float(stats.get("Exposure Time [%]")),
        avg_drawdown_pct=_as_float(stats.get("Avg. Drawdown [%]")),
        max_drawdown_duration=_format_duration(stats.get("Max. Drawdown Duration")),
    )
