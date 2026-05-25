from __future__ import annotations

from pathlib import Path

from app.output.models import BacktestReport


def write_backtest_report_json(report: BacktestReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        report.model_dump_json(
            indent=2,
            exclude={"results": {"__all__": {"equity_curve"}}},
        ),
        encoding="utf-8",
    )
