from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from app.config.models import BacktestConfig
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.reporting import generate_html_report
from app.strategies.registry import list_strategies

console = Console()
app = typer.Typer(
    name="backtest",
    help="Backtrader backtest CLI",
    add_completion=False,
    no_args_is_help=True,
)



def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("YAML root must be an object")
    return data


def _cmd_run(
    config_path: str,
    output_path: str,
    cache_dir: str | None,
    cache_refresh: bool,
    no_cache: bool,
) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = BacktestConfig.model_validate(raw)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (ValueError, ValidationError) as exc:
        print(f"Config validation failed: {exc}")
        return 2

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        total_backtests = sum(len(r.strategies) if r.strategies else 1 for r in config.runs)
        task_id = progress.add_task("Running backtests", total=total_backtests)

        def on_run_start(run, idx: int, total: int) -> None:
            progress.update(task_id, description=f"Running {run.run_id} ({idx}/{total})")

        def on_run_complete(result, idx: int, total: int) -> None:
            progress.advance(task_id, 1)

        def on_run_error(result, idx: int, total: int) -> None:
            progress.advance(task_id, 1)
            err = result.error.message if result.error else "Unknown error"
            etype = result.error.type if result.error else "Error"
            console.print(f"[red]Run failed immediately[/red] {result.run_id}: {etype}: {err}")

        def on_run_cache_status(run, status: str) -> None:
            console.print(f"[dim]data-cache[/dim] run={run.run_id} source={run.data.type} status={status}")

        report = run_backtests_with_hooks(
            config,
            raw,
            config_path=str(config_file.resolve()),
            on_run_start=on_run_start,
            on_run_complete=on_run_complete,
            on_run_error=on_run_error,
            on_run_cache_status=on_run_cache_status,
            execution_options=RunExecutionOptions(
                cache_enabled=False if no_cache else None,
                cache_dir=cache_dir,
                cache_refresh=cache_refresh,
            ),
        )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        report.model_dump_json(
            indent=2,
            exclude={"results": {"__all__": {"equity_curve"}}},
        ),
        encoding="utf-8",
    )

    console.print(
        f"Completed {report.total_runs} runs: "
        f"{report.successful_runs} success, {report.failed_runs} failed. "
        f"Status={report.status}. Output={output}"
    )

    if report.status == "success":
        return 0
    if report.status == "partial_failure":
        return 10
    return 20


def _cmd_list_strategies() -> int:
    specs = list_strategies()
    for spec in specs:
        console.print(f"{spec.name}: {spec.description}")
    return 0


@app.command("run", help="Run backtests from YAML config")
def run_command(
    config: str = typer.Option(..., "--config", help="YAML config path"),
    output: str = typer.Option(..., "--output", help="JSON output path"),
    cache_dir: str | None = typer.Option(None, "--cache-dir", help="Local parquet cache directory"),
    cache_refresh: bool = typer.Option(False, "--cache-refresh", help="Force refresh cache entries"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable data cache for this run"),
) -> None:
    raise typer.Exit(code=_cmd_run(config, output, cache_dir, cache_refresh, no_cache))


@app.command("list-strategies", help="List available built-in strategies")
def list_strategies_command() -> None:
    raise typer.Exit(code=_cmd_list_strategies())


@app.command("report-html", help="Convert backtest JSON output into a Material Design HTML report")
def report_html_command(
    input_json: str = typer.Option(..., "--input", help="Backtest JSON input path"),
    output_html: str = typer.Option(..., "--output", help="HTML output path"),
    title: str = typer.Option("Backtest Report", "--title", help="Report page title"),
) -> None:
    input_path = Path(input_json)
    output_path = Path(output_html)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        raise typer.Exit(code=2)
    try:
        generate_html_report(input_path, output_path, title=title)
    except ValueError as exc:
        print(f"Invalid backtest JSON: {exc}")
        raise typer.Exit(code=2)
    console.print(f"HTML report created: {output_path}")
    raise typer.Exit(code=0)


def main(argv: list[str] | None = None) -> int:
    try:
        app(args=argv, standalone_mode=False)
        return 0
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.exceptions.Exit as exc:
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
