from __future__ import annotations

import json
import math
import shlex
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.backtests.model_policy import LoadedModelArtifact
from app.backtests.models import VectorbtWorkflowRequest
from app.output.models import FeatureSnapshotRecord
from app.risk.features.assemble import build_feature_snapshot
from app.risk.models import EnrichedCandidate, RiskDatasetConfig
from app.script_logging import emit_info, emit_terminal_command, emit_warning
from app.strategies.regime import RegimeClassifier, RegimeParams
from app.strategies.vectorbt_indicators import run_atr, run_session_vwap, run_sma
from app.strategies.vectorbt_support import VectorbtBuildContext, VectorbtSpec, build_portfolio_from_spec, frame_to_bars

app = typer.Typer(add_completion=False, no_args_is_help=True)

_SCRIPT_NAME = "backtest_risk_gated_ma"
_DEFAULT_INIT_CASH = 100_000.0
US_EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SymbolRunResult:
    symbol: str
    summary: dict[str, Any]
    trades: pd.DataFrame
    regime_summary: pd.DataFrame
    signal_rows: pd.DataFrame
    portfolio: Any


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _write_json(path: str | None, payload: object) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _as_utc_index(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.DatetimeIndex):
        index = frame.index
    else:
        datetime_columns = ("timestamp", "datetime", "date_time", "bar_time")
        index = None
        for column in datetime_columns:
            if column in frame.columns:
                index = pd.DatetimeIndex(pd.to_datetime(frame[column], utc=True, errors="coerce"))
                frame = frame.drop(columns=[column])
                break
        if index is None:
            raise ValueError("Dataset must have a DatetimeIndex or a timestamp/datetime column")

    normalized = frame.copy()
    if index.tz is None:
        normalized.index = index.tz_localize("UTC")
    else:
        normalized.index = index.tz_convert("UTC")
    normalized = normalized.sort_index(kind="mergesort")
    return normalized


def _normalize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = _as_utc_index(frame)
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(normalized.columns))
    if missing:
        raise ValueError(f"Dataset is missing required OHLCV columns: {missing}")
    ordered_columns = ["Open", "High", "Low", "Close", "Volume"]
    ordered_columns.extend(column for column in normalized.columns if column not in required)
    return normalized.loc[:, ordered_columns]


def _split_symbol_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "symbol" not in frame.columns:
        return {"__all__": _normalize_ohlcv_frame(frame)}

    symbol_frames: dict[str, pd.DataFrame] = {}
    for symbol, group in frame.groupby(frame["symbol"].astype(str).str.upper(), sort=True):
        symbol_frames[symbol] = _normalize_ohlcv_frame(group.drop(columns=["symbol"]))
    return symbol_frames


def _load_dataset_frame(dataset_path: str) -> pd.DataFrame:
    return pd.read_parquet(dataset_path)


def _filter_from_date(frame: pd.DataFrame, from_date: str | None) -> pd.DataFrame:
    if from_date is None:
        return frame
    start = pd.Timestamp(from_date, tz="UTC")
    return frame.loc[frame.index >= start]


def _bar_interval_minutes(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 1.0
    deltas = index.to_series().diff().dropna().dt.total_seconds() / 60.0
    if deltas.empty:
        return 1.0
    value = float(deltas.median())
    return value if value > 0 else 1.0


def _session_minutes_since_open(index: pd.DatetimeIndex) -> pd.Series:
    if len(index) == 0:
        return pd.Series(dtype=float, index=index)
    minutes: list[float] = []
    current_session: str | None = None
    session_start: pd.Timestamp | None = None
    for timestamp in index:
        local_timestamp = timestamp.tz_convert(US_EASTERN) if timestamp.tzinfo is not None else timestamp.tz_localize(US_EASTERN)
        session_key = local_timestamp.date().isoformat()
        if current_session != session_key:
            current_session = session_key
            session_start = local_timestamp.normalize() + pd.Timedelta(hours=9, minutes=30)
        if session_start is None:
            minutes.append(float("nan"))
        else:
            minutes.append((local_timestamp - session_start).total_seconds() / 60.0)
    return pd.Series(minutes, index=index, dtype=float)


def _flatten_snapshot(snapshot: FeatureSnapshotRecord) -> dict[str, Any]:
    payload = snapshot.model_dump(mode="python")
    metadata_features = payload.pop("metadata_features", {})
    if isinstance(metadata_features, dict):
        payload.update(metadata_features)
    return payload


def _risk_score_for_signal(
    *,
    frame: pd.DataFrame,
    idx: int,
    symbol: str,
    signal_score: float | None,
    signal_reason: str,
    atr_value: float,
    atr_stop_mult: float,
    model: LoadedModelArtifact | None,
    risk_config: RiskDatasetConfig,
    bar_minutes: float,
    min_hold_minutes: float,
) -> tuple[float, FeatureSnapshotRecord | None]:
    entry_price = float(frame["Close"].iloc[idx])
    planned_stop_pct = max(1e-6, (atr_value * atr_stop_mult) / max(entry_price, 1e-9))
    planned_horizon_bars = max(1, int(round(min_hold_minutes / max(bar_minutes, 1e-9)))) if min_hold_minutes > 0 else max(
        1, int(round(atr_stop_mult * 4.0))
    )
    candidate = EnrichedCandidate(
        candidate_id=f"{symbol}:{frame.index[idx].isoformat()}",
        strategy_id="risk_gated_ma",
        symbol=symbol,
        timestamp=frame.index[idx].isoformat(),
        side="LONG",
        entry_price=entry_price,
        entry_type="CLOSE",
        planned_stop_pct=planned_stop_pct,
        planned_target_pct=None,
        planned_horizon_bars=planned_horizon_bars,
        signal_score=signal_score,
        signal_reason=signal_reason,
        metadata={
            "atr_value": atr_value,
            "atr_stop_mult": atr_stop_mult,
        },
        was_traded=False,
        reject_reason=None,
        run_id="vectorbt",
        resolution=f"{int(round(bar_minutes))}m" if bar_minutes > 0 else None,
        feed=None,
        data_source="parquet",
        fill_model="close",
        start_date=None,
        end_date=None,
        benchmark_symbol=None,
        source_report_path="",
        csv_path=None,
    )
    snapshot = build_feature_snapshot(candidate, frame=frame.iloc[: idx + 1], config=risk_config)
    if snapshot.feature_quality_flag != "OK":
        return 1.0, snapshot
    if model is None:
        return 0.0, snapshot
    return float(model.score(_flatten_snapshot(snapshot))), snapshot


def _max_drawdown_pct(equity: pd.Series) -> float | None:
    if equity.empty:
        return None
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min() * 100.0)


def _symbol_summary(symbol: str, portfolio: Any, trades: pd.DataFrame) -> dict[str, Any]:
    equity = portfolio.value()
    start_value = float(equity.iloc[0]) if len(equity) else _DEFAULT_INIT_CASH
    end_value = float(equity.iloc[-1]) if len(equity) else _DEFAULT_INIT_CASH
    returns_pct = ((end_value / start_value) - 1.0) * 100.0 if start_value else 0.0
    pnl = trades["pnl"] if "pnl" in trades.columns else pd.Series(dtype=float)
    won = int((pnl > 0).sum()) if not pnl.empty else 0
    lost = int((pnl < 0).sum()) if not pnl.empty else 0
    return {
        "symbol": symbol,
        "start_value": start_value,
        "end_value": end_value,
        "return_pct": returns_pct,
        "max_drawdown_pct": _max_drawdown_pct(equity),
        "sharpe_ratio": None,
        "total_trades": int(len(trades)),
        "won_trades": won,
        "lost_trades": lost,
    }


def _build_regime_summary(frame: pd.DataFrame) -> pd.DataFrame:
    bars = frame_to_bars(frame)
    classifier = RegimeClassifier(RegimeParams())
    rows: list[dict[str, Any]] = []
    for idx, bar in enumerate(bars):
        state = classifier.update(bars[: idx + 1])
        rows.append(
            {
                "timestamp": bar.iso_timestamp,
                "label": state.label,
                "candidate_label": state.candidate_label,
                "bars_in_regime": state.bars_in_regime,
                "changed": state.changed,
            }
        )
    regime_df = pd.DataFrame(rows)
    if regime_df.empty:
        return regime_df
    summary = (
        regime_df.groupby("label", as_index=False)
        .agg(
            bars=("label", "size"),
            first_timestamp=("timestamp", "min"),
            last_timestamp=("timestamp", "max"),
            changes=("changed", "sum"),
        )
        .sort_values("label", kind="mergesort")
    )
    return summary


def _render_html_report(
    *,
    summaries: list[dict[str, Any]],
    trades: pd.DataFrame,
    signal_rows: pd.DataFrame,
    regime_summaries: pd.DataFrame,
) -> str:
    trade_table = trades.head(200).to_html(index=False, escape=True) if not trades.empty else "<p>No trades.</p>"
    signal_table = signal_rows.head(200).to_html(index=False, escape=True) if not signal_rows.empty else "<p>No signals.</p>"
    summary_table = pd.DataFrame(summaries).to_html(index=False, escape=True) if summaries else "<p>No summary.</p>"
    regime_table = regime_summaries.to_html(index=False, escape=True) if not regime_summaries.empty else "<p>No regime data.</p>"
    return (
        "<html><head><meta charset='utf-8'><title>Vectorbt Risk-Gated MA</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;margin:24px;line-height:1.4}"
        "table{border-collapse:collapse;margin:16px 0;width:100%}th,td{border:1px solid #ddd;padding:6px 8px;text-align:left}"
        "th{background:#f4f4f4}h1,h2{margin-top:24px}</style></head><body>"
        "<h1>Vectorbt Risk-Gated MA</h1>"
        "<h2>Summary</h2>"
        f"{summary_table}"
        "<h2>Trades</h2>"
        f"{trade_table}"
        "<h2>Signals</h2>"
        f"{signal_table}"
        "<h2>Regime Summary</h2>"
        f"{regime_table}"
        "</body></html>"
    )


def _run_symbol(
    symbol: str,
    frame: pd.DataFrame,
    *,
    volume_window: int,
    min_volume_ratio: float,
    entry_cutoff_minutes: int,
    risk_threshold: float,
    exit_style: str,
    min_hold_minutes: float,
    atr_window: int,
    atr_stop_mult: float,
    model: LoadedModelArtifact | None,
    risk_config: RiskDatasetConfig,
) -> SymbolRunResult:
    frame = _normalize_ohlcv_frame(frame)
    frame = frame.sort_index(kind="mergesort")
    bar_minutes = _bar_interval_minutes(frame.index)
    min_hold_bars = max(0, int(math.ceil(min_hold_minutes / max(bar_minutes, 1e-9))))

    close = frame["Close"].astype(float)
    high = frame["High"].astype(float)
    low = frame["Low"].astype(float)
    volume = frame["Volume"].astype(float)
    fast_window = max(5, min(20, volume_window))
    slow_window = max(fast_window + 10, volume_window * 2)
    fast_ma = run_sma(close, fast_window)
    slow_ma = run_sma(close, slow_window)
    vwap = run_session_vwap(high, low, close, volume, frame.index)
    atr = run_atr(high, low, close, atr_window)
    volume_sma = run_sma(volume, volume_window)
    minutes_since_open = _session_minutes_since_open(frame.index)

    regime_rows = _build_regime_summary(frame)
    regime_labels = pd.Series(index=frame.index, dtype="object")
    if not regime_rows.empty:
        # Best-effort per-bar regime labels for trade annotations.
        classifier = RegimeClassifier(RegimeParams())
        bars = frame_to_bars(frame)
        labels: list[str] = []
        for idx, _bar in enumerate(bars):
            labels.append(classifier.update(bars[: idx + 1]).label)
        regime_labels = pd.Series(labels, index=frame.index, dtype="object")

    entries = pd.Series(False, index=frame.index, dtype=bool)
    exits = pd.Series(False, index=frame.index, dtype=bool)
    signal_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    in_position = False
    entry_idx = -1
    entry_price = 0.0
    entry_atr = 0.0
    highest_close = -np.inf
    risk_config = risk_config.model_copy(update={"min_history_bars": max(risk_config.min_history_bars, atr_window, slow_window)})

    for idx in range(len(frame)):
        signal_components = {
            "close": float(close.iloc[idx]),
            "fast_ma": float(fast_ma.iloc[idx]) if not pd.isna(fast_ma.iloc[idx]) else None,
            "slow_ma": float(slow_ma.iloc[idx]) if not pd.isna(slow_ma.iloc[idx]) else None,
            "vwap": float(vwap.iloc[idx]) if not pd.isna(vwap.iloc[idx]) else None,
            "atr": float(atr.iloc[idx]) if not pd.isna(atr.iloc[idx]) else None,
            "volume_ratio": None,
            "minutes_since_open": float(minutes_since_open.iloc[idx]) if not pd.isna(minutes_since_open.iloc[idx]) else None,
        }
        if not pd.isna(volume_sma.iloc[idx]) and float(volume_sma.iloc[idx]) > 0:
            signal_components["volume_ratio"] = float(volume.iloc[idx] / volume_sma.iloc[idx])

        risk_score: float | None = None
        snapshot: FeatureSnapshotRecord | None = None
        entry_signal = False
        if (
            idx > 0
            and not in_position
            and not pd.isna(fast_ma.iloc[idx])
            and not pd.isna(fast_ma.iloc[idx - 1])
            and not pd.isna(slow_ma.iloc[idx])
            and not pd.isna(slow_ma.iloc[idx - 1])
            and not pd.isna(vwap.iloc[idx])
            and not pd.isna(atr.iloc[idx])
            and not pd.isna(volume_sma.iloc[idx])
        ):
            cross_up = float(close.iloc[idx]) > float(fast_ma.iloc[idx]) and float(close.iloc[idx - 1]) <= float(fast_ma.iloc[idx - 1])
            trend_ok = float(fast_ma.iloc[idx]) > float(slow_ma.iloc[idx]) and float(close.iloc[idx]) > float(slow_ma.iloc[idx])
            vwap_ok = float(close.iloc[idx]) > float(vwap.iloc[idx])
            volume_ok = float(volume.iloc[idx]) >= float(volume_sma.iloc[idx]) * float(min_volume_ratio)
            cutoff_ok = entry_cutoff_minutes <= 0 or float(minutes_since_open.iloc[idx]) <= float(entry_cutoff_minutes)
            entry_signal = cross_up and trend_ok and vwap_ok and volume_ok and cutoff_ok
            if entry_signal:
                signal_score = min(1.0, max(0.0, (float(close.iloc[idx]) - float(fast_ma.iloc[idx])) / max(float(fast_ma.iloc[idx]), 1e-9)))
                risk_score, snapshot = _risk_score_for_signal(
                    frame=frame,
                    idx=idx,
                    symbol=symbol,
                    signal_score=signal_score,
                    signal_reason="ma_cross_vwap_volume",
                    atr_value=float(atr.iloc[idx]),
                    atr_stop_mult=atr_stop_mult,
                    model=model,
                    risk_config=risk_config,
                    bar_minutes=bar_minutes,
                    min_hold_minutes=min_hold_minutes,
                )
                if risk_score is not None and risk_score <= risk_threshold:
                    entries.iloc[idx] = True
                    in_position = True
                    entry_idx = idx
                    entry_price = float(close.iloc[idx])
                    entry_atr = float(atr.iloc[idx])
                    highest_close = entry_price
                else:
                    entry_signal = False

        signal_rows.append(
            {
                "symbol": symbol,
                "timestamp": frame.index[idx].isoformat(),
                "entry_signal": bool(entry_signal),
                "risk_score": risk_score,
                "risk_threshold": risk_threshold,
                "accepted": bool(entries.iloc[idx]),
                "fast_ma": signal_components["fast_ma"],
                "slow_ma": signal_components["slow_ma"],
                "vwap": signal_components["vwap"],
                "atr": signal_components["atr"],
                "volume_ratio": signal_components["volume_ratio"],
                "minutes_since_open": signal_components["minutes_since_open"],
                "feature_timestamp": snapshot.feature_timestamp if snapshot is not None else None,
                "feature_quality_flag": snapshot.feature_quality_flag if snapshot is not None else None,
            }
        )

        if not in_position:
            continue

        highest_close = max(highest_close, float(close.iloc[idx]))
        stop_price = entry_price - entry_atr * float(atr_stop_mult)
        trailing_stop = highest_close - entry_atr * float(atr_stop_mult)
        held_bars = idx - entry_idx
        can_exit = held_bars >= min_hold_bars
        exit_reason: str | None = None

        if float(low.iloc[idx]) <= stop_price:
            exit_reason = "stop_loss"
        elif exit_style == "trailing" and float(close.iloc[idx]) <= trailing_stop and can_exit:
            exit_reason = "trailing_stop"
        elif exit_style == "vwap" and can_exit and (float(close.iloc[idx]) < float(vwap.iloc[idx]) or float(close.iloc[idx]) < float(slow_ma.iloc[idx])):
            exit_reason = "vwap_exit"
        elif idx == len(frame) - 1:
            exit_reason = "eod"

        if exit_reason is None:
            continue

        exits.iloc[idx] = True
        exit_price = float(close.iloc[idx])
        pnl = exit_price - entry_price
        trade_rows.append(
            {
                "symbol": symbol,
                "entry_timestamp": frame.index[entry_idx].isoformat(),
                "exit_timestamp": frame.index[idx].isoformat(),
                "entry_bar_index": int(entry_idx),
                "exit_bar_index": int(idx),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": (pnl / entry_price) * 100.0 if entry_price else None,
                "hold_bars": int(held_bars),
                "hold_minutes": float((frame.index[idx] - frame.index[entry_idx]).total_seconds() / 60.0),
                "reason": exit_reason,
                "regime_label": str(regime_labels.iloc[idx]) if idx < len(regime_labels) and pd.notna(regime_labels.iloc[idx]) else None,
            }
        )
        in_position = False
        entry_idx = -1
        entry_price = 0.0
        entry_atr = 0.0
        highest_close = -np.inf

    if in_position and entry_idx >= 0:
        idx = len(frame) - 1
        exits.iloc[idx] = True
        exit_price = float(close.iloc[idx])
        pnl = exit_price - entry_price
        trade_rows.append(
            {
                "symbol": symbol,
                "entry_timestamp": frame.index[entry_idx].isoformat(),
                "exit_timestamp": frame.index[idx].isoformat(),
                "entry_bar_index": int(entry_idx),
                "exit_bar_index": int(idx),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": (pnl / entry_price) * 100.0 if entry_price else None,
                "hold_bars": int(idx - entry_idx),
                "hold_minutes": float((frame.index[idx] - frame.index[entry_idx]).total_seconds() / 60.0),
                "reason": "forced_exit",
                "regime_label": str(regime_labels.iloc[idx]) if idx < len(regime_labels) and pd.notna(regime_labels.iloc[idx]) else None,
            }
        )

    context = VectorbtBuildContext(data=frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]], params={}, shared={})
    spec = VectorbtSpec(entries=entries, exits=exits, size=1.0, warmup_bars=max(slow_window, atr_window, volume_window))
    portfolio = build_portfolio_from_spec(spec, context, init_cash=_DEFAULT_INIT_CASH, fill_model="close", freq=None)

    trades_df = pd.DataFrame(trade_rows)
    summary = _symbol_summary(symbol, portfolio, trades_df)
    signal_df = pd.DataFrame(signal_rows)
    return SymbolRunResult(
        symbol=symbol,
        summary=summary,
        trades=trades_df,
        regime_summary=regime_rows,
        signal_rows=signal_df,
        portfolio=portfolio,
    )


@app.command(help="Run the risk-gated MA vectorbt workflow and write artifacts for Argo collection.")
def main(
    data_path: str = typer.Option(..., "--data-path"),
    volume_window: int = typer.Option(20, "--volume-window"),
    min_volume_ratio: float = typer.Option(1.25, "--min-volume-ratio"),
    entry_cutoff_minutes: int = typer.Option(0, "--entry-cutoff-minutes"),
    risk_threshold: float = typer.Option(0.5, "--risk-threshold"),
    exit_style: str = typer.Option("vwap", "--exit-style"),
    min_hold_minutes: float = typer.Option(0.0, "--min-hold-minutes"),
    atr_window: int = typer.Option(14, "--atr-window"),
    atr_stop_mult: float = typer.Option(1.5, "--atr-stop-mult"),
    output: str = typer.Option(..., "--output"),
    trades_output: str = typer.Option(..., "--trades-output"),
    regime_summary_output: str = typer.Option(..., "--regime-summary-output"),
    histograms_html_output: str = typer.Option(..., "--histograms-html-output"),
    model_path: str | None = typer.Option(None, "--model-path"),
    from_date: str | None = typer.Option(None, "--from-date"),
    max_symbols: int | None = typer.Option(None, "--max-symbols"),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script=_SCRIPT_NAME)

    for path in [output, trades_output, regime_summary_output, histograms_html_output]:
        _write_text(path, "")

    if exit_style not in {"vwap", "trailing"}:
        raise ValueError("--exit-style must be either 'vwap' or 'trailing'")

    emit_info("vectorbt-input", f"data_path={data_path}", script=_SCRIPT_NAME)
    emit_info(
        "vectorbt-params",
        json.dumps(
            {
                "volume_window": volume_window,
                "min_volume_ratio": min_volume_ratio,
                "entry_cutoff_minutes": entry_cutoff_minutes,
                "risk_threshold": risk_threshold,
                "exit_style": exit_style,
                "min_hold_minutes": min_hold_minutes,
                "atr_window": atr_window,
                "atr_stop_mult": atr_stop_mult,
                "max_symbols": max_symbols,
            },
            sort_keys=True,
        ),
        script=_SCRIPT_NAME,
    )

    model = LoadedModelArtifact.from_path(model_path, family="risk") if model_path else None
    if model_path:
        emit_info("vectorbt-model", model_path, script=_SCRIPT_NAME)

    frame = _load_dataset_frame(data_path)
    frame = _filter_from_date(frame, from_date)
    if frame.empty:
        raise ValueError("Dataset is empty after applying the requested date filter")

    symbol_frames = _split_symbol_frames(frame)
    symbols = sorted(symbol_frames.keys())
    if max_symbols is not None:
        symbols = symbols[:max_symbols]
    if not symbols:
        raise ValueError("No symbols were available in the dataset")

    results: list[SymbolRunResult] = []
    risk_config = RiskDatasetConfig()
    for symbol in symbols:
        emit_info("vectorbt-symbol", symbol, script=_SCRIPT_NAME)
        results.append(
            _run_symbol(
                symbol,
                symbol_frames[symbol],
                volume_window=volume_window,
                min_volume_ratio=min_volume_ratio,
                entry_cutoff_minutes=entry_cutoff_minutes,
                risk_threshold=risk_threshold,
                exit_style=exit_style,
                min_hold_minutes=min_hold_minutes,
                atr_window=atr_window,
                atr_stop_mult=atr_stop_mult,
                model=model,
                risk_config=risk_config,
            )
        )

    all_trades = pd.concat([result.trades for result in results], ignore_index=True) if results else pd.DataFrame()
    all_signals = pd.concat([result.signal_rows for result in results], ignore_index=True) if results else pd.DataFrame()
    regime_summary = pd.concat([result.regime_summary.assign(symbol=result.symbol) for result in results], ignore_index=True)
    if not regime_summary.empty and "symbol" in regime_summary.columns:
        regime_summary = regime_summary.loc[:, ["symbol", *[column for column in regime_summary.columns if column != "symbol"]]]

    summaries = [result.summary for result in results]
    if len(results) > 1:
        combined_start = float(sum(result.summary["start_value"] for result in results))
        combined_end = float(sum(result.summary["end_value"] for result in results))
        combined_trades = int(sum(result.summary["total_trades"] for result in results))
        combined_won = int(sum(result.summary["won_trades"] for result in results))
        combined_lost = int(sum(result.summary["lost_trades"] for result in results))
        summaries.append(
            {
                "symbol": "combined",
                "start_value": combined_start,
                "end_value": combined_end,
                "return_pct": ((combined_end / combined_start) - 1.0) * 100.0 if combined_start else 0.0,
                "max_drawdown_pct": None,
                "sharpe_ratio": None,
                "total_trades": combined_trades,
                "won_trades": combined_won,
                "lost_trades": combined_lost,
            }
        )

    summary_df = pd.DataFrame(summaries)
    summary_df.to_csv(output, index=False)
    all_trades.to_csv(trades_output, index=False)
    regime_summary.to_csv(regime_summary_output, index=False)
    _write_text(
        histograms_html_output,
        _render_html_report(
            summaries=summaries,
            trades=all_trades,
            signal_rows=all_signals,
            regime_summaries=regime_summary,
        ),
    )

    _write_json(
        str(Path(output).with_suffix(".json")),
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "data_path": data_path,
            "model_path": model_path,
            "symbol_count": len(results),
            "symbols": [result.symbol for result in results],
            "summaries": summaries,
            "trade_count": int(len(all_trades)),
            "signal_count": int(len(all_signals)),
        },
    )

    emit_warning(
        "vectorbt-output",
        f"wrote {len(summaries)} summary row(s), {len(all_trades)} trade row(s), and {len(all_signals)} signal row(s)",
        script=_SCRIPT_NAME,
    )


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
