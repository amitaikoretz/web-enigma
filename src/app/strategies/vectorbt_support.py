"""Helpers for translating strategy trigger specs into vectorbt-compatible inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    entries: np.ndarray | pd.Series | None = None
    # Boolean full-exit mask aligned to the context index.
    exits: np.ndarray | pd.Series | None = None
    # Boolean partial-exit mask aligned to the context index.
    trim_exits: np.ndarray | pd.Series | None = None
    # Fraction of the current position to trim when `trim_exits` fires.
    trim_portion: float | np.ndarray | pd.Series | None = None
    # Default order size used for each entry unless the trigger provides per-bar sizes.
    size: float | np.ndarray | pd.Series | None = None
    # Optional stop-loss distance or mask, depending on the trigger's semantics.
    sl_stop: np.ndarray | pd.Series | None = None
    # Optional take-profit distance or mask, depending on the trigger's semantics.
    tp_stop: np.ndarray | pd.Series | None = None
    # Optional trailing-stop distance or mask, depending on the trigger's semantics.
    trail_stop: np.ndarray | pd.Series | None = None
    # Minimum historical bars required before the spec should be considered active.
    warmup_bars: int = 0
    # Free-form diagnostic payload for downstream auditing, reporting, or custom execution.
    metadata: dict[str, Any] = field(default_factory=dict)


def mask_like(mask: Any, index: pd.Index) -> pd.Series:
    """Coerce an array-like mask into a boolean series aligned to `index`."""
    if isinstance(mask, pd.Series):
        # Reindex first so missing timestamps become explicit `False` values rather
        # than silently shifting the signal.
        return mask.reindex(index=index, fill_value=False).astype(bool)
    array = np.asarray(mask, dtype=bool)
    if array.shape[0] != len(index):
        raise ValueError("Mask length does not match data length")
    return pd.Series(array, index=index)


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
) -> pd.Series:
    """Turn a trigger spec into signed order sizes aligned with the context index."""
    if fill_model not in {"close", "next_bar"}:
        raise ValueError(f"Unsupported fill model '{fill_model}'")

    index = context.index
    if len(index) == 0:
        return pd.Series(dtype=float, index=index)

    # Some triggers precompute exact order sizes in metadata. When present, honor
    # that directly instead of deriving sizes from entry/exit booleans.
    if spec.metadata.get("order_sizes") is not None:
        order_sizes = spec.metadata["order_sizes"]
        if isinstance(order_sizes, pd.Series):
            return order_sizes.reindex(index=index, fill_value=0.0).astype(float)
        array = np.asarray(order_sizes, dtype=float)
        if array.shape[0] != len(index):
            raise ValueError("Order size length does not match data length")
        return pd.Series(array, index=index, dtype=float)

    entries = mask_like(spec.entries if spec.entries is not None else False, index).to_numpy(dtype=bool)
    exits = mask_like(spec.exits if spec.exits is not None else False, index).to_numpy(dtype=bool)
    trim_exits = mask_like(spec.trim_exits if spec.trim_exits is not None else False, index).to_numpy(dtype=bool)
    entry_size = float(spec.size if spec.size is not None else 1.0)
    trim_portion = float(spec.trim_portion if spec.trim_portion is not None else 0.0)

    # The loop below emulates a minimal position ledger:
    # - `in_trade` tracks whether a position is currently open
    # - `position_size` stores the live size of that position
    # - `trimmed` prevents repeated partial exits from firing multiple times
    # - `pending_change` defers fills for `next_bar` execution until the following bar
    order_sizes = np.zeros(len(index), dtype=float)
    in_trade = False
    position_size = 0.0
    trimmed = False
    pending_change = 0.0

    for idx in range(len(index)):
        if pending_change != 0.0:
            # Apply deferred fills before processing the current bar so the new
            # position state is visible to any exit logic on this bar.
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
            order_sizes[idx] += entry_size
            in_trade = True
            position_size = entry_size
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
            # For next-bar execution, signals generated on this bar are converted
            # into orders on the following bar rather than immediately.
            if entries[idx] and not in_trade:
                pending_change += entry_size
            elif in_trade:
                if exits[idx]:
                    pending_change -= position_size
                elif trim_exits[idx] and not trimmed and trim_portion > 0.0:
                    trim_amount = position_size * trim_portion
                    pending_change -= trim_amount
                    trimmed = True
        elif fill_model == "next_bar" and idx == len(index) - 1 and in_trade:
            # The final bar has no "next" bar, so any terminal exit signal is
            # executed in-place to avoid leaving stale open exposure in the result.
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

    price = _extract_price_series(context)
    order_sizes = build_order_sizes_from_spec(spec, context, fill_model=fill_model)
    # `from_orders` is the lowest-friction way to feed a custom event stream into
    # vectorbt while preserving the exact signed order schedule we computed above.
    return vbt.Portfolio.from_orders(
        price,
        size=order_sizes,
        price=price,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        freq=freq,
    )
