import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pandas as pd
import yaml

from app.cli import main
from app.config.models import BacktestConfig
from app.engine.runner import _extract_trade_counts, run_backtests


def _make_vwap_pullback_feed(
    *,
    start_price: float,
    close_step: float,
    volume_base: float,
    entry_index: int | None = None,
    trim_index: int | None = None,
    total_bars: int = 78,
) -> pd.DataFrame:
    tz = ZoneInfo("America/New_York")
    start = datetime(2024, 1, 2, 9, 30, tzinfo=tz)
    rows: list[dict[str, object]] = []
    for idx in range(total_bars):
        close = start_price + idx * close_step
        if entry_index is not None and idx == entry_index:
            close = 102.4
        if trim_index is not None and idx == trim_index:
            close = 104.0
        if rows and idx > (trim_index if trim_index is not None else -1):
            close = max(close, float(rows[-1]["Close"]) + 0.03)
        open_price = close - 0.04
        high = close + 0.05
        low = close - 0.08
        volume = volume_base + idx * 15
        if entry_index is not None and idx == entry_index:
            open_price = float(rows[-1]["Close"]) + 0.01 if rows else close - 0.04
            high = close + 0.04
            low = 100.95
            volume = volume_base * 3
        if trim_index is not None and idx == trim_index:
            open_price = float(rows[-1]["Close"]) + 0.02 if rows else close - 0.04
            high = close + 0.18
            low = close - 0.15
            volume = volume_base * 2.5
        rows.append(
            {
                "datetime": start + timedelta(minutes=5 * idx),
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        )
    frame = pd.DataFrame(rows).set_index("datetime")
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def test_csv_single_run_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_ok",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 1
    assert report.successful_runs == 1
    assert report.results[0].status == "success"
    assert report.results[0].summary is not None
    assert report.results[0].summary.total_trades >= 1
    closed_trades = report.results[0].trades
    assert closed_trades
    assert all(hasattr(trade, "reason") for trade in closed_trades)
    summary = report.results[0].summary
    assert summary is not None
    assert summary.trade_diagnostics is not None
    assert summary.risk_metrics is not None
    assert summary.filter_diagnostics is not None
    assert report.results[0].rejections == []
    assert "trade_diagnostics" in report.results[0].analyzers


def test_extract_trade_counts_uses_total_not_closed():
    trade_data = {
        "total": {"total": 1, "open": 1, "closed": 0},
        "won": {"total": 0},
        "lost": {"total": 0},
    }
    total_trades, won_trades, lost_trades = _extract_trade_counts(trade_data)
    assert total_trades == 1
    assert won_trades == 0
    assert lost_trades == 0


def test_csv_oco_atr_tp_sl_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_oco_sl_tp",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_oco_atr", "params": {"stake": 1, "atr_period": 5, "entry_sma": 2}},
                "exit_rules": {
                    "rules": [
                        {"name": "atr_oco", "params": {"atr_period": 5, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}
                    ]
                },
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 1
    assert report.successful_runs == 1
    assert report.results[0].status == "success"


def test_csv_oco_atr_tp_trailing_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_oco_trailing_tp",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_oco_atr", "params": {"stake": 1, "atr_period": 5, "entry_sma": 2}},
                "exit_rules": {
                    "rules": [
                        {"name": "atr_trailing", "params": {"atr_period": 5, "trail_atr_mult": 1.2, "tp_atr_mult": 3.0}}
                    ]
                },
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 1
    assert report.successful_runs == 1
    assert report.results[0].status == "success"


def test_vwap_pullback_backtest_trims_and_flattens_before_overnight(monkeypatch):
    main_feed = _make_vwap_pullback_feed(
        start_price=100.0,
        close_step=0.1,
        volume_base=1000.0,
        entry_index=23,
        trim_index=24,
        total_bars=78,
    )
    benchmark_feed = _make_vwap_pullback_feed(
        start_price=200.0,
        close_step=0.1,
        volume_base=2000.0,
        total_bars=78,
    )

    def fake_yahoo_data_feed_with_cache(data, start_date, end_date, cache_config, force_refresh):
        symbol = str(getattr(data, "symbol", "")).upper()
        if symbol == "TQQQ":
            return main_feed.copy(), "mock"
        if symbol == "QQQ":
            return benchmark_feed.copy(), "mock"
        raise AssertionError(f"unexpected symbol {symbol!r}")

    monkeypatch.setattr("app.engine.runner.build_yahoo_data_feed_with_cache", fake_yahoo_data_feed_with_cache)

    raw = {
        "runs": [
            {
                "run_id": "vwap_pullback_e2e",
                "start_date": "2024-01-02",
                "end_date": "2024-01-02",
                "data": {"type": "yahoo", "symbol": "TQQQ", "interval": "5m"},
                "execution": {"fill_model": "next_bar"},
                    "trigger": {
                        "name": "vwap_pullback",
                        "params": {
                            "stake": 10,
                        "benchmark_symbol": "QQQ",
                        "trend_ema_fast": 2,
                        "trend_ema_mid": 3,
                        "trend_ema_slow": 4,
                        "benchmark_ema_fast": 2,
                        "benchmark_ema_slow": 3,
                        "volume_window": 3,
                        "volume_spike_mult": 1.1,
                        "pullback_distance_pct": 0.01,
                        "min_closes_above_vwap": 1,
                        "recent_close_window": 3,
                        "max_entry_gap_pct": 0.01,
                        "stop_buffer_pct": 0.001,
                        "max_stop_distance_pct": 0.05,
                        "max_stop_atr_mult": 10.0,
                        "session_morning_start_minutes": 0,
                        "session_morning_end_minutes": 390,
                        "session_afternoon_start_minutes": 0,
                        "session_afternoon_end_minutes": 390,
                    },
                },
                "exit_rules": {
                    "rules": [
                        {
                            "name": "vwap_pullback_manage",
                            "params": {
                                "stop_buffer_pct": 0.001,
                                "breakeven_buffer_pct": 0.0,
                                "partial_trim_portion": 0.5,
                                "time_stop_bars": 1000,
                                "eod_flatten_minutes": 385,
                            },
                        }
                    ]
                },
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)

    assert report.total_runs == 1
    assert report.successful_runs == 1
    result = report.results[0]
    assert result.status == "success"
    assert result.summary is not None
    assert result.summary.total_trades == 2
    assert len(result.orders) == 3
    assert result.orders[0].is_buy is True and result.orders[0].size == 10.0
    assert result.orders[1].is_buy is True and result.orders[1].size == 5.0
    assert result.orders[2].is_buy is False and result.orders[2].size == 5.0
    assert len(result.trades) == 1
    assert result.trades[0].reason == "exit:vwap_pullback_manage:one_r_trim"
    assert result.trades[0].datetime.endswith("11:35:00-05:00")


def test_csv_multiple_runs_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_multi_buy_hold",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            },
            {
                "run_id": "csv_multi_sma_cross",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "sma_cross", "params": {"fast": 3, "slow": 8, "stake": 1}},
                "exit_rules": {
                    "rules": [
                        {"name": "sma_cross_down", "params": {"fast": 3, "slow": 8}},
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                        {"name": "max_hold_bars", "params": {"max_hold_bars": 24}},
                    ]
                },
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 2
    assert report.successful_runs == 2
    assert {r.run_id for r in report.results} == {"csv_multi_buy_hold", "csv_multi_sma_cross"}


def test_mixed_batch_partial_failure():
    raw = {
        "runs": [
            {
                "run_id": "ok",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            },
            {
                "run_id": "bad_file",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/missing.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            },
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.status == "partial_failure"
    assert report.successful_runs == 1
    assert report.failed_runs == 1


def test_yahoo_path_mocked(monkeypatch):
    def fake_yahoo_feed(*args, **kwargs):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [101.0, 102.0, 103.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.5, 101.5, 102.5],
                "Volume": [1000, 1100, 1200],
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        )
        return (frame, "hit")

    monkeypatch.setattr("app.engine.runner.build_yahoo_data_feed_with_cache", fake_yahoo_feed)

    raw = {
        "runs": [
            {
                "run_id": "yahoo_mock",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "yahoo", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.status == "success"


def test_alpaca_path_mocked(monkeypatch):
    def fake_alpaca_feed(*args, **kwargs):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [101.0, 102.0, 103.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.5, 101.5, 102.5],
                "Volume": [1000, 1100, 1200],
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        )
        return (frame, "hit")

    monkeypatch.setattr("app.engine.runner.build_alpaca_data_feed_with_cache", fake_alpaca_feed)

    raw = {
        "runs": [
            {
                "run_id": "alpaca_mock",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "alpaca", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.status == "success"


def test_cli_list_strategies(capsys):
    code = main(["list-strategies"])
    out = capsys.readouterr().out
    assert code == 0
    assert "sma_cross" in out


def test_cli_run_exits_nonzero_on_run_failure(tmp_path: Path):
    config_payload = {
        "runs": [
            {
                "run_id": "cli_fail",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/missing.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    code = main(["run", "--config", str(cfg_path), "--output", str(out_path)])

    assert code == 20
    assert out_path.exists()


def test_cli_run_writes_output(tmp_path: Path):
    config_payload = {
        "runs": [
            {
                "run_id": "cli_run",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    code = main(["run", "--config", str(cfg_path), "--output", str(out_path)])
    assert code == 0
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["status"] == "success"
    result = data["results"][0]
    assert "equity_curve" not in result
    assert "orders" not in result
    assert "trades" not in result
    assert "rejections" not in result
    assert (tmp_path / "result" / "result.orders.parquet").exists()
    assert (tmp_path / "result" / "result.trades.parquet").exists()


def test_cli_report_html_from_json(tmp_path: Path):
    payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "app_version": "0.1.0",
        "config_sha256": "abc123",
        "total_runs": 1,
        "successful_runs": 1,
        "failed_runs": 0,
        "status": "success",
        "results": [
            {
                "run_id": "demo_run",
                "name": "Demo Run",
                "status": "success",
                "strategy": "buy_and_hold",
                "data_source": "csv",
                "summary": {
                    "start_value": 10000,
                    "end_value": 10500,
                    "return_pct": 5.0,
                    "max_drawdown_pct": 2.2,
                    "sharpe_ratio": 1.3,
                    "total_trades": 2,
                    "won_trades": 1,
                    "lost_trades": 1,
                },
                "orders": [
                    {
                        "datetime": "2026-01-02T00:00:00",
                        "status": "Completed",
                        "is_buy": True,
                        "size": 1.0,
                        "price": 100.0,
                        "value": 100.0,
                        "commission": 0.1,
                    }
                ],
                "trades": [
                    {
                        "datetime": "2026-01-03T00:00:00",
                        "size": 1.0,
                        "price": 105.0,
                        "value": 105.0,
                        "pnl": 5.0,
                        "pnlcomm": 4.9,
                    }
                ],
                "equity_curve": [
                    {"datetime": "2026-01-02", "value": 10000.0},
                    {"datetime": "2026-01-03", "value": 10500.0},
                ],
            }
        ],
    }
    json_path = tmp_path / "result.json"
    html_path = tmp_path / "report.html"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    code = main(["report-html", "--input", str(json_path), "--output", str(html_path)])
    assert code == 0
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Backtest Report" in html
    assert "Equity Curve" in html
    assert "Trade Open/Close Examples" in html
    assert "demo_run" in html


def test_cli_run_cache_flags_with_yahoo(capsys, monkeypatch, tmp_path: Path):
    def fake_yahoo_feed(*args, **kwargs):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [101.0, 102.0],
                "Low": [99.0, 100.0],
                "Close": [100.5, 101.5],
                "Volume": [1000, 1100],
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )
        return (frame, "force_refresh")

    monkeypatch.setattr("app.engine.runner.build_yahoo_data_feed_with_cache", fake_yahoo_feed)

    config_payload = {
        "runs": [
            {
                "run_id": "cli_yahoo",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "yahoo", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    code = main(
        [
            "run",
            "--config",
            str(cfg_path),
            "--output",
            str(out_path),
            "--cache-refresh",
            "--cache-dir",
            str(tmp_path / ".cache"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "data-cache" in out
    assert "force_refresh" in out


def test_cli_run_cache_flags_with_alpaca(capsys, monkeypatch, tmp_path: Path):
    def fake_alpaca_feed(*args, **kwargs):
        import pandas as pd

        frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [101.0, 102.0],
                "Low": [99.0, 100.0],
                "Close": [100.5, 101.5],
                "Volume": [1000, 1100],
            },
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )
        return (frame, "force_refresh")

    monkeypatch.setattr("app.engine.runner.build_alpaca_data_feed_with_cache", fake_alpaca_feed)

    config_payload = {
        "runs": [
            {
                "run_id": "cli_alpaca",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "alpaca", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    code = main(
        [
            "run",
            "--config",
            str(cfg_path),
            "--output",
            str(out_path),
            "--cache-refresh",
            "--cache-dir",
            str(tmp_path / ".cache"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "data-cache" in out
    assert "source=alpaca" in out
    assert "force_refresh" in out


def test_backtest_fill_model_next_bar_changes_fill_timing():
    close_raw = {
        "runs": [
            {
                "run_id": "close_fill",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                "execution": {"fill_model": "close"},
            }
        ]
    }
    next_bar_raw = {
        "runs": [
            {
                "run_id": "next_bar_fill",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                "execution": {"fill_model": "next_bar"},
            }
        ]
    }

    close_report = run_backtests(BacktestConfig.model_validate(close_raw), close_raw)
    next_bar_report = run_backtests(BacktestConfig.model_validate(next_bar_raw), next_bar_raw)

    assert close_report.results[0].orders[0].datetime == "2024-01-02T00:00:00"
    assert next_bar_report.results[0].orders[0].datetime == "2024-01-03T00:00:00"


def test_backtest_closes_positions_before_overnight(tmp_path: Path):
    csv_path = tmp_path / "intraday_two_sessions.csv"
    csv_path.write_text(
        "datetime,open,high,low,close,volume,openinterest\n"
        "2024-01-02T09:30:00,100,101,99,100.5,1000,0\n"
        "2024-01-02T10:30:00,100.5,101.5,100,101.0,1100,0\n"
        "2024-01-02T15:59:00,101.0,102,100.5,101.5,1200,0\n"
        "2024-01-03T09:30:00,101.5,103,101,102.5,1100,0\n",
        encoding="utf-8",
    )
    raw = {
        "runs": [
            {
                "run_id": "no_overnight",
                "start_date": "2024-01-02",
                "end_date": "2024-01-03",
                "data": {
                    "type": "csv",
                    "path": str(csv_path),
                    "date_format": "%Y-%m-%dT%H:%M:%S",
                },
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.successful_runs == 1
    trades = report.results[0].trades
    assert trades
    assert trades[0].reason == "session_close"
    assert trades[0].datetime.startswith("2024-01-02")


def test_cli_alpaca_run_uses_separate_config(monkeypatch, tmp_path: Path, capsys):
    config_payload = {
        "global_config": {"execution": {"mode": "paper", "state_directory": str(tmp_path / '.state')}},
        "runs": [
            {
                "run_id": "alpaca_cli",
                "symbol": "AAPL",
                "interval": "1m",
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}]},
            }
        ],
    }
    cfg_path = tmp_path / "alpaca.yaml"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    class FakeExecutor:
        def process_latest_bar(self):
            return []

    monkeypatch.setattr("app.cli.build_alpaca_executor", lambda **kwargs: FakeExecutor())

    code = main(["alpaca-run", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "alpaca_cli" in out
