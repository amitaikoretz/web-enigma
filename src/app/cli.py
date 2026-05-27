from __future__ import annotations

import base64
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
from app.backtests.argo_payload import build_argo_launch_payload, format_argo_launch_curl
from app.backtests.merge import merge_exit_code, merge_from_manifest
from app.backtests.sharding import plan_shards, resolve_split_by, write_shard_manifest, write_shards_param
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.settings import PlatformSettingsService
from app.live import runtime as live_runtime
from app.output import write_backtest_report_json
from app.reporting import generate_html_report
from app.risk.data.report_loader import CandidateLoadError
from app.risk.dataset.builder import build_risk_dataset
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
    settings_path = Path(".cache/backtest-results/settings/platform-settings.json")
    live_include_candidate_log = None
    if settings_path.exists():
        live_include_candidate_log = PlatformSettingsService(settings_path).load().live_defaults.include_candidate_log
    for run in config.runs:
        try:
            executor = build_alpaca_executor(
                run=run,
                execution=config.global_config.execution,
                include_candidate_log=live_include_candidate_log,
            )
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


def _cmd_plan_shards(
    config_path: str,
    work_dir: str,
    manifest_path: str | None,
    shards_param_path: str | None,
    split_by: str | None,
) -> int:
    config_file = Path(config_path)
    work_path = Path(work_dir)
    try:
        raw = _load_yaml(config_file)
        BacktestConfig.model_validate(raw)
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (ValueError, ValidationError) as exc:
        print(f"Config validation failed: {exc}")
        return 2

    resolved_split = resolve_split_by(
        raw,
        override=split_by if split_by else None,  # type: ignore[arg-type]
    )
    plan = plan_shards(
        raw,
        split_by=resolved_split,
        work_dir=work_path,
        config_path=str(config_file.resolve()),
    )
    manifest = Path(manifest_path) if manifest_path else work_path / "manifest.json"
    write_shard_manifest(plan, manifest)
    shards_param = Path(shards_param_path) if shards_param_path else work_path / "shards-param.json"
    write_shards_param(plan, shards_param)
    console.print(f"Planned {len(plan.shards)} shards split_by={plan.split_by} manifest={manifest}")
    return 0


def _cmd_merge(manifest_path: str, output_path: str, backtest_id: str | None) -> int:
    manifest = Path(manifest_path)
    output = Path(output_path)
    if not manifest.exists():
        print(f"Manifest not found: {manifest}")
        return 2
    try:
        report = merge_from_manifest(manifest)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Merge failed: {exc}")
        return 2
    write_backtest_report_json(report, output)
    if backtest_id:
        from app.backtests.argo_reconciler import update_metadata_from_report

        update_metadata_from_report(backtest_id, report, output_dir=output.parent)
    console.print(
        f"Merged {report.total_runs} runs: "
        f"{report.successful_runs} success, {report.failed_runs} failed. "
        f"Status={report.status}. Output={output}"
    )
    return merge_exit_code(report)


def _cmd_print_argo_payload(
    api_base_url: str,
    config_path: str | None,
    config_text_file: str | None,
    config_b64: str | None,
    split_by: str | None,
    backtest_id: str | None,
) -> int:
    config_text: str | None = None
    resolved_config_path = config_path.strip() if config_path else None
    if config_b64 and config_b64.strip():
        try:
            config_text = base64.b64decode(config_b64).decode()
        except (ValueError, UnicodeDecodeError) as exc:
            print(f"Invalid config-b64: {exc}")
            return 2
    elif config_text_file:
        text_path = Path(config_text_file)
        if not text_path.exists():
            print(f"Config text file not found: {config_text_file}")
            return 2
        config_text = text_path.read_text(encoding="utf-8")

    try:
        if config_text is not None:
            payload = build_argo_launch_payload(
                config_text=config_text,
                split_by=split_by or "",
                backtest_id=backtest_id or "",
            )
        elif resolved_config_path:
            payload = build_argo_launch_payload(
                config_path=resolved_config_path,
                split_by=split_by or "",
                backtest_id=backtest_id or "",
            )
        else:
            print("Provide one of --config-path, --config-text-file, or --config-b64")
            return 2
    except ValueError as exc:
        print(f"Payload build failed: {exc}")
        return 2

    print(format_argo_launch_curl(api_base_url, payload))
    return 0


def _cmd_argo_reconciler(output_dir: str, once: bool) -> int:
    from app.backtests.argo_reconciler import reconcile_backtest_workflows

    reconciled = reconcile_backtest_workflows(Path(output_dir), once=once)
    console.print(f"Reconciled {reconciled} backtest workflow(s)")
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


def _cmd_build_risk_dataset(
    input_paths: list[str],
    output_path: str,
    config_path: str | None,
    cache_dir: str | None,
) -> int:
    paths = [Path(path) for path in input_paths]
    for path in paths:
        if not path.exists():
            print(f"Input file not found: {path}")
            return 2
    try:
        manifest = build_risk_dataset(
            paths,
            output_path=Path(output_path),
            config_path=Path(config_path) if config_path else None,
            cache_dir=cache_dir,
        )
    except CandidateLoadError as exc:
        print(f"Risk dataset build failed: {exc}")
        return 2
    except (ValueError, NotImplementedError, RuntimeError) as exc:
        print(f"Risk dataset build failed: {exc}")
        return 2

    console.print(
        f"Risk dataset created: {manifest.output_path} "
        f"(rows={manifest.joined_rows}, candidates={manifest.total_candidates})"
    )
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


@app.command("plan-shards", help="Split a backtest config into parallel shard YAML files")
def plan_shards_command(
    config: str = typer.Option(..., "--config", help="YAML config path"),
    work_dir: str = typer.Option(..., "--work-dir", help="Directory for shard configs and manifest"),
    manifest: str | None = typer.Option(None, "--manifest", help="Manifest JSON output path"),
    shards_param: str | None = typer.Option(
        None,
        "--shards-param",
        help="Compact JSON array output for Argo withParam",
    ),
    split_by: str | None = typer.Option(
        None,
        "--split-by",
        help="Shard grouping: run, symbol, strategy, or symbol_strategy",
    ),
) -> None:
    raise typer.Exit(code=_cmd_plan_shards(config, work_dir, manifest, shards_param, split_by))


@app.command("merge", help="Merge shard backtest JSON reports into one report")
def merge_command(
    manifest: str = typer.Option(..., "--manifest", help="Shard manifest JSON path"),
    output: str = typer.Option(..., "--output", help="Merged JSON output path"),
    backtest_id: str | None = typer.Option(
        None,
        "--backtest-id",
        help="When set, update job metadata in the output directory parent",
    ),
) -> None:
    raise typer.Exit(code=_cmd_merge(manifest, output, backtest_id))


@app.command("build-risk-dataset", help="Build labeled feature dataset from backtest report JSON(s)")
def build_risk_dataset_command(
    input_json: list[str] = typer.Option(..., "--input", help="Backtest JSON input path (repeatable)"),
    output: str = typer.Option(..., "--output", help="Parquet output path"),
    config: str | None = typer.Option(None, "--config", help="Risk dataset YAML config path"),
    cache_dir: str | None = typer.Option(None, "--cache-dir", help="Override parquet cache directory"),
) -> None:
    raise typer.Exit(code=_cmd_build_risk_dataset(input_json, output, config, cache_dir))


@app.command(
    "print-argo-payload",
    help="Print a curl command that launches this backtest via POST /backtests/argo",
)
def print_argo_payload_command(
    api_base_url: str = typer.Option(
        ...,
        "--api-base-url",
        help="API base URL (e.g. http://localhost:8000)",
    ),
    config_path: str | None = typer.Option(
        None,
        "--config-path",
        help="Config path on the shared backtest-results volume",
    ),
    config_text_file: str | None = typer.Option(
        None,
        "--config-text-file",
        help="Local file whose contents become inline config_text in the payload",
    ),
    config_b64: str | None = typer.Option(
        None,
        "--config-b64",
        help="Base64-encoded config YAML (matches workflow config-b64 parameter)",
    ),
    split_by: str | None = typer.Option(None, "--split-by", help="Argo shard grouping"),
    backtest_id: str | None = typer.Option(None, "--backtest-id", help="Backtest job id"),
) -> None:
    raise typer.Exit(
        code=_cmd_print_argo_payload(
            api_base_url,
            config_path,
            config_text_file,
            config_b64,
            split_by,
            backtest_id,
        )
    )


@app.command("argo-reconciler", help="Reconcile Argo backtest workflow status with job metadata")
def argo_reconciler_command(
    output_dir: str = typer.Option(..., "--output-dir", help="Backtest results directory"),
    once: bool = typer.Option(False, "--once", help="Run one reconciliation pass and exit"),
) -> None:
    raise typer.Exit(code=_cmd_argo_reconciler(output_dir, once))


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
