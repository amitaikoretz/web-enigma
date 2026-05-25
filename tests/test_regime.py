from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategies.core import Bar
from app.strategies.regime import RegimeClassifier, RegimeParams, regime_params_from_strategy


BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[Bar]:
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    return [
        Bar(
            timestamp=BASE_TS + timedelta(days=idx),
            open=close,
            high=highs[idx],
            low=lows[idx],
            close=close,
            volume=1000.0,
        )
        for idx, close in enumerate(closes)
    ]


def _small_params(**overrides: float | int | bool) -> RegimeParams:
    defaults: dict[str, float | int | bool] = {
        "enabled": True,
        "adx_period": 2,
        "adx_min": 20.0,
        "sma_period": 2,
        "atr_period": 2,
        "vol_window": 4,
        "vol_high_mult": 1.5,
        "confirmation_bars": 3,
    }
    defaults.update(overrides)
    return RegimeParams.model_validate(defaults)


def test_regime_disabled_passthrough():
    classifier = RegimeClassifier(_small_params(enabled=False))
    state = classifier.update(_bars([10, 11, 12, 13, 14, 15]))
    assert state.label == "trending"
    assert state.changed is False


def test_regime_warmup_does_not_transition():
    classifier = RegimeClassifier(_small_params())
    state = classifier.update(_bars([10, 11]))
    assert state.changed is False
    assert state.label == "ranging"


def test_regime_detects_high_vol():
    classifier = RegimeClassifier(_small_params(confirmation_bars=1, vol_high_mult=1.1))
    closes = [10.0, 10.2, 10.1, 10.3, 10.2, 12.0]
    highs = [10.5, 10.7, 10.6, 10.8, 10.7, 20.0]
    lows = [9.5, 9.7, 9.6, 9.8, 9.7, 11.5]
    state = classifier.update(_bars(closes, highs=highs, lows=lows))
    assert state.label == "high_vol"
    assert state.changed is True


def test_regime_detects_trending():
    classifier = RegimeClassifier(_small_params(confirmation_bars=1, adx_min=5.0))
    closes = [10, 11, 12, 13, 14, 15, 16]
    highs = [c + 1.5 for c in closes]
    lows = [c - 0.2 for c in closes]
    state = classifier.update(_bars(closes, highs=highs, lows=lows))
    assert state.label == "trending"


def test_regime_detects_ranging():
    classifier = RegimeClassifier(_small_params(confirmation_bars=1, adx_min=50.0))
    closes = [10, 10.1, 10.0, 10.1, 10.0, 10.1, 10.0]
    state = classifier.update(_bars(closes))
    assert state.label == "ranging"


def test_regime_hysteresis_requires_confirmation():
    classifier = RegimeClassifier(_small_params(confirmation_bars=3, vol_high_mult=1.1))
    closes = [10.0, 10.2, 10.1, 10.3, 10.2, 10.1]
    highs = [10.5, 10.7, 10.6, 10.8, 10.7, 10.6]
    lows = [9.5, 9.7, 9.6, 9.8, 9.7, 9.6]

    state = classifier.update(_bars(closes, highs=highs, lows=lows))
    assert state.label == "ranging"

    for step in range(1, 3):
        closes = closes + [12.0]
        highs = highs + [20.0]
        lows = lows + [11.5]
        state = classifier.update(_bars(closes, highs=highs, lows=lows))
        assert state.label == "ranging"
        assert state.changed is False
        assert state.confirmation_count == step
        assert state.candidate_label == "high_vol"

    closes = closes + [12.0]
    highs = highs + [20.0]
    lows = lows + [11.5]
    state = classifier.update(_bars(closes, highs=highs, lows=lows))
    assert state.label == "high_vol"
    assert state.changed is True


def test_regime_changed_flag_only_on_transition_bar():
    classifier = RegimeClassifier(_small_params(confirmation_bars=1, adx_min=5.0))
    bars = _bars([10, 11, 12, 13, 14, 15], highs=[11, 12, 13, 14, 15, 16], lows=[9.5] * 6)
    first = classifier.update(bars)
    second = classifier.update(bars)
    assert first.changed is True
    assert second.changed is False


def test_regime_state_round_trip():
    classifier = RegimeClassifier(_small_params(confirmation_bars=1))
    bars = _bars([10, 11, 12, 13, 14, 15], highs=[11, 12, 13, 14, 15, 16], lows=[9.5] * 6)
    classifier.update(bars)
    saved = classifier.dump_state()

    restored = RegimeClassifier(_small_params(confirmation_bars=1))
    restored.load_state(saved)
    state = restored.update(bars)
    assert state.label == classifier._label


def test_regime_params_from_strategy_legacy_window():
    params = regime_params_from_strategy(
        {
            "volatility_regime_window": 20,
            "volatility_regime_max_mult": 2.5,
            "atr_period": 14,
            "adx_period": 14,
        }
    )
    assert params.enabled is True
    assert params.vol_window == 20
    assert params.vol_high_mult == 2.5


def test_regime_params_from_strategy_explicit_enabled():
    params = regime_params_from_strategy({"regime_enabled": True, "regime_vol_window": 30})
    assert params.enabled is True
    assert params.vol_window == 30


def test_regime_min_bars():
    classifier = RegimeClassifier(_small_params())
    assert classifier.min_bars() == max(4, 4, 2, 2) + 3
