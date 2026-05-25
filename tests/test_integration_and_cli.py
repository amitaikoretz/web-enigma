import json
from pathlib import Path

import pytest
import yaml

from app.cli import main
from app.config.models import BacktestConfig
from app.engine.runner import _extract_trade_counts, run_backtests


def test_csv_single_run_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_ok",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_oco_atr_tp_sl",
                "strategy_params": {"stake": 1, "atr_period": 5, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0},
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
                "strategy": "buy_oco_atr_tp_trailing",
                "strategy_params": {"stake": 1, "atr_period": 5, "trail_atr_mult": 1.2, "tp_atr_mult": 3.0},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 1
    assert report.successful_runs == 1
    assert report.results[0].status == "success"


def test_csv_single_run_multiple_strategies_integration():
    raw = {
        "runs": [
            {
                "run_id": "csv_multi",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategies": [
                    {"name": "buy_and_hold", "params": {"stake": 1}},
                    {"name": "sma_cross", "params": {"fast": 3, "slow": 8, "stake": 1}},
                ],
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.total_runs == 2
    assert report.successful_runs == 2
    assert report.results[0].run_id in {"csv_multi:buy_and_hold", "csv_multi:sma_cross"}
    assert report.results[1].run_id in {"csv_multi:buy_and_hold", "csv_multi:sma_cross"}
    assert report.results[0].run_id != report.results[1].run_id


def test_mixed_batch_partial_failure():
    raw = {
        "runs": [
            {
                "run_id": "ok",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            },
            {
                "run_id": "bad_file",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/missing.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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


def test_cli_run_writes_output(tmp_path: Path):
    config_payload = {
        "runs": [
            {
                "run_id": "cli_run",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
    assert "equity_curve" not in data["results"][0]


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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
                "execution": {"fill_model": "next_bar"},
            }
        ]
    }

    close_report = run_backtests(BacktestConfig.model_validate(close_raw), close_raw)
    next_bar_report = run_backtests(BacktestConfig.model_validate(next_bar_raw), next_bar_raw)

    assert close_report.results[0].orders[0].datetime == "2024-01-02T00:00:00"
    assert next_bar_report.results[0].orders[0].datetime == "2024-01-03T00:00:00"


def test_cli_alpaca_run_uses_separate_config(monkeypatch, tmp_path: Path, capsys):
    config_payload = {
        "global_config": {"execution": {"mode": "paper", "state_directory": str(tmp_path / '.state')}},
        "runs": [
            {
                "run_id": "alpaca_cli",
                "symbol": "AAPL",
                "interval": "1m",
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
