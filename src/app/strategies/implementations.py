from __future__ import annotations

import backtrader as bt


class BaseTrackedStrategy(bt.Strategy):
    def __init__(self) -> None:
        self.order_log: list[dict] = []
        self.trade_log: list[dict] = []
        self.pending_order: bt.Order | None = None
        self.entry_price: float | None = None
        self.entry_bar: int | None = None

    def notify_order(self, order: bt.Order) -> None:
        if order.status not in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            return

        dt = bt.num2date(order.executed.dt).isoformat() if order.executed.dt else None
        self.order_log.append(
            {
                "datetime": dt,
                "status": order.getstatusname(),
                "is_buy": bool(order.isbuy()),
                "size": float(order.executed.size),
                "price": float(order.executed.price),
                "value": float(order.executed.value),
                "commission": float(order.executed.comm),
            }
        )

        if order is self.pending_order:
            self.pending_order = None

        if order.status == order.Completed and order.isbuy():
            self.entry_price = float(order.executed.price)
            self.entry_bar = len(self)

        if order.status == order.Completed and order.issell() and not self.position:
            self.entry_price = None
            self.entry_bar = None

    def notify_trade(self, trade: bt.Trade) -> None:
        if not trade.isclosed:
            return
        dt = bt.num2date(trade.dtclose).isoformat() if trade.dtclose else None
        self.trade_log.append(
            {
                "datetime": dt,
                "size": float(trade.size),
                "price": float(trade.price),
                "value": float(trade.value),
                "pnl": float(trade.pnl),
                "pnlcomm": float(trade.pnlcomm),
            }
        )

    def _in_position_bars(self) -> int:
        if self.entry_bar is None:
            return 0
        return max(0, len(self) - self.entry_bar)

    def _should_exit_by_risk(self, stop_loss_pct: float, take_profit_pct: float) -> bool:
        if not self.position or self.entry_price is None:
            return False
        close = float(self.data.close[0])
        stop_price = self.entry_price * (1.0 - stop_loss_pct)
        take_profit_price = self.entry_price * (1.0 + take_profit_pct)
        return close <= stop_price or close >= take_profit_price


class SmaCrossStrategy(BaseTrackedStrategy):
    params = (
        ("fast", 8),
        ("slow", 21),
        ("stake", 1.0),
        ("stop_loss_pct", 0.01),
        ("take_profit_pct", 0.02),
        ("max_hold_bars", 24),
    )

    def __init__(self) -> None:
        super().__init__()
        fast = bt.indicators.SMA(period=self.params.fast)
        slow = bt.indicators.SMA(period=self.params.slow)
        self.cross = bt.indicators.CrossOver(fast, slow)

    def next(self) -> None:
        if self.pending_order:
            return

        if self.position:
            time_exit = self._in_position_bars() >= int(self.params.max_hold_bars)
            signal_exit = self.cross < 0
            risk_exit = self._should_exit_by_risk(
                stop_loss_pct=float(self.params.stop_loss_pct),
                take_profit_pct=float(self.params.take_profit_pct),
            )
            if signal_exit or risk_exit or time_exit:
                self.pending_order = self.close()
            return

        if self.cross > 0:
            self.pending_order = self.buy(size=float(self.params.stake))


class RsiReversionStrategy(BaseTrackedStrategy):
    params = (
        ("period", 14),
        ("oversold", 30),
        ("overbought", 60),
        ("stake", 1.0),
        ("stop_loss_pct", 0.008),
        ("take_profit_pct", 0.015),
        ("max_hold_bars", 18),
    )

    def __init__(self) -> None:
        super().__init__()
        self.rsi = bt.indicators.RSI_Safe(period=self.params.period)

    def next(self) -> None:
        if self.pending_order:
            return

        if self.position:
            time_exit = self._in_position_bars() >= int(self.params.max_hold_bars)
            signal_exit = float(self.rsi[0]) >= float(self.params.overbought)
            risk_exit = self._should_exit_by_risk(
                stop_loss_pct=float(self.params.stop_loss_pct),
                take_profit_pct=float(self.params.take_profit_pct),
            )
            if signal_exit or risk_exit or time_exit:
                self.pending_order = self.close()
            return

        if float(self.rsi[0]) <= float(self.params.oversold):
            self.pending_order = self.buy(size=float(self.params.stake))


class BuyAndHoldStrategy(BaseTrackedStrategy):
    params = (("stake", 1.0), ("stop_loss_pct", 0.02), ("take_profit_pct", 0.04))

    def __init__(self) -> None:
        super().__init__()
        self.has_entered = False

    def next(self) -> None:
        if self.pending_order:
            return

        if self.position:
            if self._should_exit_by_risk(
                stop_loss_pct=float(self.params.stop_loss_pct),
                take_profit_pct=float(self.params.take_profit_pct),
            ):
                self.pending_order = self.close()
            return

        if not self.has_entered:
            self.pending_order = self.buy(size=float(self.params.stake))
            self.has_entered = True


class BuyOcoAtrTpSlStrategy(BaseTrackedStrategy):
    params = (
        ("stake", 1.0),
        ("atr_period", 14),
        ("entry_sma", 20),
        ("sl_atr_mult", 1.5),
        ("tp_atr_mult", 3.0),
        ("max_hold_bars", 24),
    )

    def __init__(self) -> None:
        super().__init__()
        self.atr = bt.indicators.ATR(period=self.params.atr_period)
        self.sma = bt.indicators.SMA(period=self.params.entry_sma)
        self.cross = bt.indicators.CrossOver(self.data.close, self.sma)

    def _should_exit_by_atr(self) -> bool:
        if not self.position or self.entry_price is None:
            return False
        atr_value = float(self.atr[0])
        if atr_value <= 0:
            return False
        stop_price = self.entry_price - atr_value * float(self.params.sl_atr_mult)
        take_profit_price = self.entry_price + atr_value * float(self.params.tp_atr_mult)
        close = float(self.data.close[0])
        return close <= stop_price or close >= take_profit_price

    def next(self) -> None:
        if self.pending_order:
            return

        if self.position:
            time_exit = self._in_position_bars() >= int(self.params.max_hold_bars)
            signal_exit = self.cross < 0
            atr_exit = self._should_exit_by_atr()
            if signal_exit or atr_exit or time_exit:
                self.pending_order = self.close()
            return

        if len(self.data) < max(int(self.params.atr_period), int(self.params.entry_sma)):
            return
        if float(self.atr[0]) <= 0:
            return
        if self.cross > 0:
            self.pending_order = self.buy(size=float(self.params.stake))


class BuyOcoAtrTpTrailingStrategy(BaseTrackedStrategy):
    params = (
        ("stake", 1.0),
        ("atr_period", 14),
        ("entry_sma", 20),
        ("trail_atr_mult", 1.0),
        ("tp_atr_mult", 2.5),
        ("max_hold_bars", 30),
    )

    def __init__(self) -> None:
        super().__init__()
        self.atr = bt.indicators.ATR(period=self.params.atr_period)
        self.sma = bt.indicators.SMA(period=self.params.entry_sma)
        self.cross = bt.indicators.CrossOver(self.data.close, self.sma)
        self.peak_price: float | None = None

    def notify_order(self, order: bt.Order) -> None:
        super().notify_order(order)
        if order.status == order.Completed and order.isbuy():
            self.peak_price = float(order.executed.price)
        if order.status == order.Completed and order.issell() and not self.position:
            self.peak_price = None

    def _should_exit_with_trailing_atr(self) -> bool:
        if not self.position or self.entry_price is None:
            return False
        atr_value = float(self.atr[0])
        if atr_value <= 0:
            return False
        close = float(self.data.close[0])
        self.peak_price = close if self.peak_price is None else max(self.peak_price, close)
        trailing_stop = self.peak_price - atr_value * float(self.params.trail_atr_mult)
        take_profit_price = self.entry_price + atr_value * float(self.params.tp_atr_mult)
        return close <= trailing_stop or close >= take_profit_price

    def next(self) -> None:
        if self.pending_order:
            return

        if self.position:
            time_exit = self._in_position_bars() >= int(self.params.max_hold_bars)
            signal_exit = self.cross < 0
            trailing_exit = self._should_exit_with_trailing_atr()
            if signal_exit or trailing_exit or time_exit:
                self.pending_order = self.close()
            return

        if len(self.data) < max(int(self.params.atr_period), int(self.params.entry_sma)):
            return
        if float(self.atr[0]) <= 0:
            return
        if self.cross > 0:
            self.pending_order = self.buy(size=float(self.params.stake))


class BreakoutChannelStrategy(BaseTrackedStrategy):
    params = (
        ("lookback", 20),
        ("stake", 1.0),
        ("stop_loss_pct", 0.01),
        ("take_profit_pct", 0.02),
        ("max_hold_bars", 20),
    )

    def __init__(self) -> None:
        super().__init__()
        self.highest = bt.indicators.Highest(self.data.high, period=self.params.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.params.lookback)

    def next(self) -> None:
        if self.pending_order:
            return

        if len(self.data) < int(self.params.lookback) + 1:
            return

        if self.position:
            channel_break = float(self.data.close[0]) < float(self.lowest[-1])
            time_exit = self._in_position_bars() >= int(self.params.max_hold_bars)
            risk_exit = self._should_exit_by_risk(
                stop_loss_pct=float(self.params.stop_loss_pct),
                take_profit_pct=float(self.params.take_profit_pct),
            )
            if channel_break or time_exit or risk_exit:
                self.pending_order = self.close()
            return

        if float(self.data.close[0]) > float(self.highest[-1]):
            self.pending_order = self.buy(size=float(self.params.stake))
