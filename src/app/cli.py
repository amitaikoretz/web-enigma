from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import typer
import uvicorn
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from app.api import app as fastapi_app
from app.api_logging import DEFAULT_LOG_DIR, build_timestamped_log_file, configure_api_logging
from app.strategies.auditor_logging import configure_strategy_logging
from app.config.models import AlpacaTradingConfig, BacktestConfig, LiveTradingConfig
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.live.executor import build_alpaca_executor
from app.live import runtime as live_runtime
from app.output import write_backtest_report_json
from app.reporting import generate_html_report
from app.strategies.registry import list_strategies

console = Console()
app = typer.Typer(
    name="backtest",
    help="backtesting.py backtest CLI",
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

    configure_strategy_logging()

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
    write_backtest_report_json(report, output)

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


def _cmd_alpaca_run(config_path: str) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = AlpacaTradingConfig.model_validate(raw)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (ValueError, ValidationError) as exc:
        print(f"Config validation failed: {exc}")
        return 2

    failures = 0
    for run in config.runs:
        try:
            executor = build_alpaca_executor(run=run, execution=config.global_config.execution)
            events = executor.process_latest_bar()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            console.print(f"[red]Alpaca run failed[/red] {run.run_id}: {exc}")
            continue

        if events:
            for event in events:
                console.print(
                    f"run={run.run_id} status={event.status} type={event.event_type} "
                    f"is_buy={event.is_buy} size={event.size} reason={event.reason}"
                )
        else:
            console.print(f"run={run.run_id} processed latest completed bar with no new events")

    return 0 if failures == 0 else 20


def _cmd_list_strategies() -> int:
    specs = list_strategies()
    for spec in specs:
        console.print(f"{spec.name}: {spec.description}")
    return 0


def _cmd_serve(host: str, port: int, log_dir: Path) -> int:
    log_file = build_timestamped_log_file(log_dir)
    logger = configure_api_logging(log_file, force=True)
    logger.info("API started on %s:%s", host, port)
    console.print(f"API logs: {log_file.resolve()}")
    uvicorn.run(fastapi_app, host=host, port=port)
    return 0


def _cmd_live_controller(config_path: str, once: bool) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = LiveTradingConfig.model_validate(raw)
        service = live_runtime.build_live_controller(config)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (RuntimeError, ValueError, ValidationError) as exc:
        print(f"Live controller startup failed: {exc}")
        return 2

    console.print(f"Starting live controller once={once} shard_count={config.global_config.controller.shard_count}")
    if once:
        result = service.sync_once()
        console.print(
            f"phase={result.session_phase.value} assignments={result.assignment_version} "
            f"symbols={result.active_symbol_count} replicas={result.desired_replicas}"
        )
    else:
        service.run_forever()
    return 0


def _cmd_live_worker(config_path: str, shard_id: int, once: bool) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = LiveTradingConfig.model_validate(raw)
        service = live_runtime.build_live_worker(config, shard_id=shard_id)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (RuntimeError, ValueError, ValidationError) as exc:
        print(f"Live worker startup failed: {exc}")
        return 2

    console.print(f"Starting live worker shard={shard_id} once={once}")
    if once:
        service.run_forever(max_iterations=1)
        service.drain()
    else:
        service.run_forever()
    return 0


def _cmd_live_reconciler(config_path: str, once: bool) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = LiveTradingConfig.model_validate(raw)
        service = live_runtime.build_live_reconciler(config)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (RuntimeError, ValueError, ValidationError) as exc:
        print(f"Live reconciler startup failed: {exc}")
        return 2

    console.print(f"Starting live reconciler once={once}")
    results = service.run_once()
    if once and results:
        console.print(f"reconciliations={len(results)} status={results[0].status.value}")
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


@app.command("alpaca-run", help="Evaluate latest completed Alpaca bars and submit paper/live orders")
def alpaca_run_command(
    config: str = typer.Option(..., "--config", help="Alpaca trading YAML config path"),
) -> None:
    raise typer.Exit(code=_cmd_alpaca_run(config))


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


@app.command("serve", help="Run the FastAPI market data service")
def serve_command(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535, help="Bind port"),
    log_dir: Path = typer.Option(DEFAULT_LOG_DIR, "--log-dir", help="Directory for timestamped API log files"),
) -> None:
    raise typer.Exit(code=_cmd_serve(host, port, log_dir))


@app.command("live-controller", help="Run the live trading contracts controller")
def live_controller_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    once: bool = typer.Option(False, "--once", help="Run one sync iteration and exit"),
) -> None:
    raise typer.Exit(code=_cmd_live_controller(config, once))


@app.command("live-worker", help="Run a live trading worker shard")
def live_worker_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    shard_id: int = typer.Option(..., "--shard-id", min=0, help="Shard id for this worker"),
    once: bool = typer.Option(False, "--once", help="Run one worker iteration and exit"),
) -> None:
    raise typer.Exit(code=_cmd_live_worker(config, shard_id, once))


@app.command("live-reconciler", help="Run the live trading reconciler")
def live_reconciler_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    once: bool = typer.Option(False, "--once", help="Run one reconciliation pass and exit"),
) -> None:
    raise typer.Exit(code=_cmd_live_reconciler(config, once))


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
