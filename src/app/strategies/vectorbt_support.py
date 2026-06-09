"""Helpers for translating strategy trigger specs into vectorbt-compatible inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from app.strategies.core import Bar


@dataclass
class VectorbtBuildContext:
    """Normalized input data used when a trigger builds a vectorbt simulation."""

    data: pd.DataFrame
    benchmark_data: pd.DataFrame | None = None
    params: dict[str, Any] = field(default_factory=dict)
    shared: dict[str, Any] = field(default_factory=dict)

    @property
    def index(self) -> pd.Index:
        """Shared bar index used to align every derived signal and order series."""
        # The shared index is the contract between trigger logic and portfolio
        # construction, so all arrays/series produced from this context must align
        # to it exactly.
        return self.data.index

    @property
    def close(self) -> pd.Series:
        """Close prices from the primary data frame."""
        return self.data["Close"]

    @property
    def high(self) -> pd.Series:
        """High prices from the primary data frame."""
        return self.data["High"]

    @property
    def low(self) -> pd.Series:
        """Low prices from the primary data frame."""
        return self.data["Low"]

    @property
    def volume(self) -> pd.Series:
        """Volume values from the primary data frame."""
        return self.data["Volume"]

    @property
    def benchmark_close(self) -> pd.Series | None:
        """Benchmark close series, or `None` when no benchmark data was provided."""
        if self.benchmark_data is None:
            return None
        return self.benchmark_data["Close"]


@dataclass(frozen=True)
class VectorbtSpec:
    """A lightweight, vectorbt-friendly description of a trigger's trading intent.

    Each field maps to a distinct part of the event stream that vectorbt can
    consume:
    - `entries` marks bars where a new position should be opened
    - `exits` marks full-position exits
    - `trim_exits` marks partial exits
    - `trim_portion` controls how much of the position to trim
    - `size` sets the default entry size
    - `sl_stop`, `tp_stop`, and `trail_stop` carry stop metadata when supported
    - `warmup_bars` tells callers how much history is needed before signals are valid
    - `metadata` holds extra trigger-specific diagnostics or precomputed arrays
    """

    # Boolean entry mask aligned to the context index.
    entries: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Boolean full-exit mask aligned to the context index.
    exits: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Boolean partial-exit mask aligned to the context index.
    trim_exits: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Fraction of the current position to trim when `trim_exits` fires.
    trim_portion: float | np.ndarray | pd.Series | pd.DataFrame | None = None
    # Default order size used for each entry unless the trigger provides per-bar sizes.
    size: float | np.ndarray | pd.Series | pd.DataFrame | None = None
    # Optional stop-loss distance or mask, depending on the trigger's semantics.
    sl_stop: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Optional take-profit distance or mask, depending on the trigger's semantics.
    tp_stop: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Optional trailing-stop distance or mask, depending on the trigger's semantics.
    trail_stop: np.ndarray | pd.Series | pd.DataFrame | None = None
    # Minimum historical bars required before the spec should be considered active.
    warmup_bars: int = 0
    # Free-form diagnostic payload for downstream auditing, reporting, or custom execution.
    metadata: dict[str, Any] = field(default_factory=dict)


def mask_like(mask: Any, index: pd.Index) -> pd.Series | pd.DataFrame:
    """Coerce an array-like mask into a boolean series aligned to `index`."""
    if isinstance(mask, pd.Series):
        # Reindex first so missing timestamps become explicit `False` values rather
        # than silently shifting the signal.
        return mask.reindex(index=index, fill_value=False).astype(bool)
    if isinstance(mask, pd.DataFrame):
        return mask.reindex(index=index, fill_value=False).astype(bool)
    array = np.asarray(mask, dtype=bool)
    if array.ndim == 0:
        return pd.Series(np.full(len(index), bool(array.item())), index=index)
    if array.shape[0] != len(index):
        raise ValueError("Mask length does not match data length")
    return pd.Series(array, index=index)


def _broadcast_series_to_frame(series: pd.Series, columns: pd.Index) -> pd.DataFrame:
    data = {column: series.to_numpy(copy=True) for column in columns}
    return pd.DataFrame(data, index=series.index)


def _shift_signals(signal: pd.Series | pd.DataFrame, *, fill_model: str) -> pd.Series | pd.DataFrame:
    if fill_model == "close":
        return signal
    shifted = signal.shift(1)
    if isinstance(signal, pd.Series):
        shifted.iloc[-1] = bool(signal.iloc[-1]) if len(signal) > 0 else False
        return shifted.where(shifted.notna(), False).astype(bool)
    if len(signal.index) > 0:
        shifted.iloc[-1] = shifted.iloc[-1] | signal.iloc[-1]
    return shifted.where(shifted.notna(), False).astype(bool)


def _normalize_like(
    value: Any,
    index: pd.Index,
    *,
    columns: pd.Index | None = None,
    fill_value: float | bool = 0.0,
) -> pd.Series | pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.reindex(index=index, fill_value=fill_value)
    if isinstance(value, pd.Series):
        return value.reindex(index=index, fill_value=fill_value)
    array = np.asarray(value)
    if array.ndim == 0:
        if columns is None:
            return pd.Series(np.full(len(index), array.item()), index=index)
        return pd.DataFrame({column: np.full(len(index), array.item()) for column in columns}, index=index)
    if array.ndim == 1:
        if len(array) != len(index):
            raise ValueError("Value length does not match data length")
        if columns is None:
            return pd.Series(array, index=index)
        return pd.DataFrame({column: array for column in columns}, index=index)
    if array.ndim == 2:
        if array.shape[0] != len(index):
            raise ValueError("Value length does not match data length")
        if columns is None:
            columns = pd.RangeIndex(array.shape[1])
        return pd.DataFrame(array, index=index, columns=columns)
    raise ValueError("Unsupported array shape")


def _as_bool_frame(mask: Any, index: pd.Index) -> pd.Series | pd.DataFrame:
    normalized = _normalize_like(mask, index, fill_value=False)
    if isinstance(normalized, pd.DataFrame):
        return normalized.astype(bool)
    return normalized.astype(bool)


def broadcast_grid_from_params(params: dict[str, Any] | None) -> dict[str, list[Any]]:
    """Extract a Cartesian broadcast grid from a parameter payload."""
    raw = (params or {}).get("broadcast", {})
    if not isinstance(raw, dict):
        return {}
    grid: dict[str, list[Any]] = {}
    for name, value in raw.items():
        if isinstance(value, pd.Series):
            values = value.tolist()
        elif isinstance(value, (pd.Index, np.ndarray, list, tuple)):
            values = list(value)
        else:
            continue
        if len(values) > 1:
            grid[name] = values
    return grid


def broadcast_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return [{}]
    names = list(grid.keys())
    return [dict(zip(names, values)) for values in product(*[grid[name] for name in names])]


def broadcast_columns_from_grid(grid: dict[str, list[Any]]) -> pd.Index:
    if not grid:
        return pd.Index([0])
    names = list(grid.keys())
    tuples = [tuple(values) for values in product(*[grid[name] for name in names])]
    return pd.MultiIndex.from_tuples(tuples, names=names)


def _build_order_sizes_1d(
    spec: "VectorbtSpec",
    context: "VectorbtBuildContext",
    *,
    fill_model: str,
) -> pd.Series:
    index = context.index

    if spec.metadata.get("order_sizes") is not None:
        order_sizes = spec.metadata["order_sizes"]
        if isinstance(order_sizes, pd.Series):
            return order_sizes.reindex(index=index, fill_value=0.0).astype(float)
        if isinstance(order_sizes, pd.DataFrame):
            if order_sizes.shape[1] != 1:
                raise ValueError("1D order sizing received a multi-column order_sizes frame")
            return order_sizes.iloc[:, 0].reindex(index=index, fill_value=0.0).astype(float)
        array = np.asarray(order_sizes, dtype=float)
        if array.shape[0] != len(index):
            raise ValueError("Order size length does not match data length")
        return pd.Series(array, index=index, dtype=float)

    entries = mask_like(spec.entries if spec.entries is not None else False, index).to_numpy(dtype=bool)
    exits = mask_like(spec.exits if spec.exits is not None else False, index).to_numpy(dtype=bool)
    trim_exits = mask_like(spec.trim_exits if spec.trim_exits is not None else False, index).to_numpy(dtype=bool)
    if isinstance(spec.size, pd.Series):
        entry_size_series = spec.size.reindex(index=index, fill_value=1.0).astype(float)
        entry_size = None
    elif isinstance(spec.size, pd.DataFrame):
        if spec.size.shape[1] != 1:
            raise ValueError("1D order sizing received a multi-column size frame")
        entry_size_series = spec.size.iloc[:, 0].reindex(index=index, fill_value=1.0).astype(float)
        entry_size = None
    else:
        array = np.asarray(spec.size if spec.size is not None else 1.0, dtype=float)
        if array.ndim == 0:
            entry_size = float(array.item())
            entry_size_series = None
        else:
            if array.shape[0] != len(index):
                raise ValueError("Size length does not match data length")
            entry_size_series = pd.Series(array, index=index, dtype=float)
            entry_size = None
    trim_portion = float(spec.trim_portion if spec.trim_portion is not None else 0.0)

    order_sizes = np.zeros(len(index), dtype=float)
    in_trade = False
    position_size = 0.0
    trimmed = False
    pending_change = 0.0

    for idx in range(len(index)):
        if pending_change != 0.0:
            order_sizes[idx] += pending_change
            position_size += pending_change
            if position_size <= 0.0:
                in_trade = False
                position_size = 0.0
                trimmed = False
            else:
                in_trade = True
            pending_change = 0.0

        if fill_model == "close" and entries[idx] and not in_trade:
            current_entry_size = float(entry_size_series.iloc[idx]) if entry_size_series is not None else float(entry_size)
            order_sizes[idx] += current_entry_size
            in_trade = True
            position_size = current_entry_size
            trimmed = False

        if fill_model == "close" and in_trade:
            if exits[idx]:
                order_sizes[idx] -= position_size
                in_trade = False
                position_size = 0.0
                trimmed = False
            elif trim_exits[idx] and not trimmed and trim_portion > 0.0:
                trim_amount = position_size * trim_portion
                order_sizes[idx] -= trim_amount
                position_size -= trim_amount
                trimmed = True

        if fill_model == "next_bar" and idx < len(index) - 1:
            if entries[idx] and not in_trade:
                current_entry_size = float(entry_size_series.iloc[idx]) if entry_size_series is not None else float(entry_size)
                pending_change += current_entry_size
            elif in_trade:
                if exits[idx]:
                    pending_change -= position_size
                elif trim_exits[idx] and not trimmed and trim_portion > 0.0:
                    trim_amount = position_size * trim_portion
                    pending_change -= trim_amount
                    trimmed = True
        elif fill_model == "next_bar" and idx == len(index) - 1 and in_trade:
            if exits[idx]:
                order_sizes[idx] -= position_size
                in_trade = False
                position_size = 0.0
                trimmed = False
            elif trim_exits[idx] and not trimmed and trim_portion > 0.0:
                trim_amount = position_size * trim_portion
                order_sizes[idx] -= trim_amount
                position_size -= trim_amount
                trimmed = True

    return pd.Series(order_sizes, index=index, dtype=float)


def _build_order_sizes_2d(
    spec: "VectorbtSpec",
    context: "VectorbtBuildContext",
    *,
    fill_model: str,
) -> pd.DataFrame:
    columns: pd.Index | None = None
    for candidate in (spec.entries, spec.exits, spec.trim_exits):
        if isinstance(candidate, pd.DataFrame):
            columns = candidate.columns
            break
    if columns is None:
        raise ValueError("Broadcasted order sizing requires at least one DataFrame signal input")

    size_frame = pd.DataFrame(index=context.index, columns=columns, dtype=float)
    for column in columns:
        column_spec = VectorbtSpec(
            entries=spec.entries[column] if isinstance(spec.entries, pd.DataFrame) else spec.entries,
            exits=spec.exits[column] if isinstance(spec.exits, pd.DataFrame) else spec.exits,
            trim_exits=spec.trim_exits[column] if isinstance(spec.trim_exits, pd.DataFrame) else spec.trim_exits,
            trim_portion=spec.trim_portion[column] if isinstance(spec.trim_portion, pd.DataFrame) else spec.trim_portion,
            size=spec.size[column] if isinstance(spec.size, pd.DataFrame) else spec.size,
            sl_stop=spec.sl_stop[column] if isinstance(spec.sl_stop, pd.DataFrame) else spec.sl_stop,
            tp_stop=spec.tp_stop[column] if isinstance(spec.tp_stop, pd.DataFrame) else spec.tp_stop,
            trail_stop=spec.trail_stop[column] if isinstance(spec.trail_stop, pd.DataFrame) else spec.trail_stop,
            warmup_bars=spec.warmup_bars,
            metadata=spec.metadata,
        )
        size_frame[column] = _build_order_sizes_1d(column_spec, context, fill_model=fill_model)
    return size_frame


def frame_to_bars(frame: pd.DataFrame) -> list[Bar]:
    """Convert an OHLCV frame into the internal `Bar` representation."""
    if frame.empty:
        return []
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Data frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Data frame index must be a DatetimeIndex")
    bars: list[Bar] = []
    for timestamp, row in frame.iterrows():
        # Each row becomes a plain `Bar` object so trigger code can operate on a
        # consistent in-memory model regardless of whether it started from pandas.
        bars.append(
            Bar(
                timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
        )
    return bars


def _extract_price_series(context: VectorbtBuildContext) -> pd.Series:
    """Choose the most appropriate execution price series for portfolio construction."""
    if "Open" in context.data.columns:
        # `next_bar` fills use the open as the execution price proxy because the
        # order is assumed to be placed after the signal bar closes.
        return context.data["Open"].astype(float)
    if "Close" in context.data.columns:
        # Fall back to close when open is unavailable, which keeps the helper usable
        # for simplified datasets or alternate data exports.
        return context.data["Close"].astype(float)
    raise ValueError("Vectorbt context requires at least an Open or Close column")


def build_order_sizes_from_spec(
    spec: VectorbtSpec,
    context: VectorbtBuildContext,
    *,
    fill_model: str = "next_bar",
) -> pd.Series | pd.DataFrame:
    """Turn a trigger spec into signed order sizes aligned with the context index."""
    if fill_model not in {"close", "next_bar"}:
        raise ValueError(f"Unsupported fill model '{fill_model}'")

    index = context.index
    if len(index) == 0:
        return pd.Series(dtype=float, index=index)

    if isinstance(spec.entries, pd.DataFrame) or isinstance(spec.exits, pd.DataFrame) or isinstance(spec.trim_exits, pd.DataFrame):
        return _build_order_sizes_2d(spec, context, fill_model=fill_model)
    return _build_order_sizes_1d(spec, context, fill_model=fill_model)


def _needs_order_path(spec: VectorbtSpec) -> bool:
    return spec.metadata.get("order_sizes") is not None or spec.trim_exits is not None


def _signal_frame_from_spec(
    spec: VectorbtSpec,
    context: VectorbtBuildContext,
    *,
    fill_model: str,
) -> tuple[pd.Series | pd.DataFrame, pd.Series | pd.DataFrame | None]:
    index = context.index
    entries = _shift_signals(_as_bool_frame(spec.entries if spec.entries is not None else False, index), fill_model=fill_model)
    exits = None
    if spec.exits is not None:
        exits = _shift_signals(_as_bool_frame(spec.exits, index), fill_model=fill_model)
    return entries, exits


def build_portfolio_from_spec(
    spec: VectorbtSpec,
    context: VectorbtBuildContext,
    *,
    init_cash: float = 10_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
    fill_model: str = "next_bar",
    freq: str | None = None,
):
    """Build a vectorbt portfolio from a trigger spec and aligned price context."""
    import vectorbt as vbt

    price = context.data["Close"].astype(float) if fill_model == "close" else _extract_price_series(context)
    order_sizes = build_order_sizes_from_spec(spec, context, fill_model=fill_model)

    if not _needs_order_path(spec):
        entries, exits = _signal_frame_from_spec(spec, context, fill_model=fill_model)
        size = spec.size if spec.size is not None else 1.0
        if isinstance(size, pd.DataFrame):
            size = size.reindex(index=context.index)
        return vbt.Portfolio.from_signals(
            price,
            entries=entries,
            exits=exits,
            size=size,
            direction="longonly",
            init_cash=init_cash,
            fees=fees,
            slippage=slippage,
            freq=freq,
        )

    # `from_orders` remains the hybrid fallback for partial trims and other
    # stateful exit rules that require explicit per-bar sizing.
    return vbt.Portfolio.from_orders(
        price,
        size=order_sizes,
        price=price,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        freq=freq,
    )
