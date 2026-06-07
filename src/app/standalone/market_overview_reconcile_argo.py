from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.db.session import get_session_factory
from app.market_overview.persistence import SqlAlchemyMarketOverviewRepository
from app.market_overview.service import MarketOverviewService

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Reconcile a market overview snapshot artifact into the database.")
def main(
    snapshot_id: str = typer.Option(..., "--snapshot-id"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    session_factory = get_session_factory()
    service = MarketOverviewService(
        session_factory=session_factory,
        repo=SqlAlchemyMarketOverviewRepository(session_factory),
    )
    snapshot = service.refresh_from_artifact(snapshot_id)
    if snapshot is None:
        raise typer.Exit(code=2)
    typer.echo(snapshot.snapshot_id)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
