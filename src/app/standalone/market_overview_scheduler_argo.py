from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.db.session import get_session_factory
from app.market_overview.persistence import SqlAlchemyMarketOverviewRepository
from app.market_overview.service import MarketOverviewService
from app.settings.service import PlatformSettingsService
from app.script_logging import emit_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Launch a market overview run when the saved cadence says one is due.")
def main(
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="market_overview_scheduler_argo")
    session_factory = get_session_factory()
    results_root = Path(os.environ.get("BACKTEST_RESULTS_DIR", ".cache/backtest-results"))
    settings_service = PlatformSettingsService(results_root / "settings" / "platform-settings.json")
    service = MarketOverviewService(
        session_factory=session_factory,
        repo=SqlAlchemyMarketOverviewRepository(session_factory),
        settings_service=settings_service,
    )
    result = service.launch_if_due()
    if result is None:
        raise typer.Exit(code=0)
    typer.echo(result.snapshot_id)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
