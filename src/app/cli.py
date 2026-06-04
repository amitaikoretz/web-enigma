from __future__ import annotations

import base64
import json
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import click
import typer
import uvicorn
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from app.api_logging import DEFAULT_LOG_DIR, build_timestamped_log_file, configure_api_logging
from app.strategies.auditor_logging import configure_strategy_logging
from app.config.models import AlpacaTradingConfig, BacktestConfig, LiveTradingConfig
from app.backtests.argo_progress import (
    ARGO_PROGRESS_TOTAL,
    ThrottledProgressWriter,
    pct_from_run_and_bar,
    pct_from_run_index,
    resolve_progress_file,
    write_argo_progress,
)
from app.backtests.merge import merge_exit_code, merge_from_manifest
from app.backtests.sharding import plan_shards, resolve_split_by, write_shard_manifest, write_shards_param
from app.backtests.models import BacktestTradeReplayCapsule
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.settings import PlatformSettingsService
from app.live import runtime as live_runtime
from app.live import build_alpaca_executor
from app.backtests.artifacts import persist_backtest_report
from app.backtests.replay import (
    clear_trade_replay_debug_target,
    resolve_trade_replay_target_bar_index,
    install_trade_replay_debug_target,
)
from app.intraday.cli import app as intraday_app
from app.reporting import generate_html_report
from app.risk.data.report_loader import CandidateLoadError
from app.risk.dataset.builder import build_risk_dataset
from app.strategies.exit_rules import list_exit_rules
from app.strategies.triggers import list_triggers
from app.terminal_command import format_terminal_command
from app.db.session import get_session_factory
from app.universes.service import SymbolUniverseService

console = Console()
app = typer.Typer(
    name="kalyxctl",
    help="Kalyx platform CLI",
    add_completion=False,
    no_args_is_help=True,
)

universes_app = typer.Typer(
    help="Manage symbol universes (DB-backed) and refresh constituents.",
    add_completion=False,
    no_args_is_help=True,
)
app.add_typer(universes_app, name="universes")
app.add_typer(intraday_app, name="intraday")


@app.callback()
def _global_callback(
    terminal_command_out: Path | None = typer.Option(
        None,
        "--terminal-command-out",
        envvar="TERMINAL_COMMAND_OUT",
        help="Write the full CLI command line to this path for Argo output capture.",
    ),
) -> None:
    cmd = format_terminal_command(sys.argv)
    print(f"terminal-command: {cmd}")

    if terminal_command_out is None:
        return

    terminal_command_out.parent.mkdir(parents=True, exist_ok=True)
    terminal_command_out.write_text(f"{cmd}\n", encoding="utf-8")


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
    progress_file: str | None = None,
) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = BacktestConfig.model_validate(raw, context={"config_base_dir": config_file.parent.resolve()})
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return 2
    except (ValueError, ValidationError) as exc:
        print(f"Config validation failed: {exc}")
        return 2

    configure_strategy_logging()

    argo_progress_path = resolve_progress_file(progress_file)
    progress_writer = ThrottledProgressWriter(argo_progress_path) if argo_progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        total_backtests = len(config.runs)
        task_id = progress.add_task("Running backtests", total=total_backtests)

        def on_run_start(run, idx: int, total: int) -> None:
            progress.update(task_id, description=f"Running {run.run_id} ({idx}/{total})")
            if progress_writer is not None:
                progress_writer.write_immediate(pct_from_run_index(idx - 1, total))

        def on_run_bar_progress(run_idx: int, total_runs: int, bar_idx: int, bar_total: int) -> None:
            if progress_writer is not None:
                progress_writer.write(
                    pct_from_run_and_bar(run_idx, total_runs, bar_idx, bar_total),
                )

        def on_run_complete(result, idx: int, total: int) -> None:
            progress.advance(task_id, 1)
            if progress_writer is not None:
                progress_writer.write_immediate(pct_from_run_index(idx, total))

        def on_run_error(result, idx: int, total: int) -> None:
            progress.advance(task_id, 1)
            if progress_writer is not None:
                progress_writer.write_immediate(pct_from_run_index(idx, total))
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
                on_run_bar_progress=on_run_bar_progress if progress_writer is not None else None,
            ),
        )
    output = Path(output_path)
    persist_backtest_report(
        report.report,
        output,
        risk_auxiliary_by_run=report.risk_auxiliary_by_run,
    )
    if progress_writer is not None:
        progress_writer.write_immediate(ARGO_PROGRESS_TOTAL)

    console.print(
        f"Completed {report.report.total_runs} runs: "
        f"{report.report.successful_runs} success, {report.report.failed_runs} failed. "
        f"Status={report.report.status}. Output={output}"
    )

    if report.report.status == "success":
        return 0
    if report.report.status == "partial_failure":
        return 10
    return 20


def _load_trade_replay_capsule(*, capsule_b64: str | None, capsule_path: str | None) -> BacktestTradeReplayCapsule:
    if capsule_b64 and capsule_b64.strip():
        resolved = capsule_b64.strip()
        if resolved.startswith("@"):
            capsule_file = Path(resolved[1:].strip())
            if not capsule_file.exists():
                raise FileNotFoundError(f"Replay capsule file not found: {capsule_file}")
            raw_text = capsule_file.read_text(encoding="utf-8")
        else:
            raw_text = base64.b64decode(resolved, validate=True).decode("utf-8")
    elif capsule_path and capsule_path.strip():
        capsule_file = Path(capsule_path.strip())
        if not capsule_file.exists():
            raise FileNotFoundError(f"Replay capsule file not found: {capsule_file}")
        raw_text = capsule_file.read_text(encoding="utf-8")
    else:
        raise ValueError("Provide --capsule-b64 or --capsule-file")

    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("Replay capsule JSON must be an object")
    return BacktestTradeReplayCapsule.model_validate(payload)


def _cmd_replay_trade(
    capsule_b64: str | None,
    capsule_file: str | None,
    output: str | None,
) -> int:
    try:
        capsule = _load_trade_replay_capsule(capsule_b64=capsule_b64, capsule_path=capsule_file)
    except (FileNotFoundError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        console.print(f"[red]Replay capsule load failed[/red]: {exc}")
        return 2

    config_text = capsule.config_text
    try:
        raw = yaml.safe_load(config_text)
        if not isinstance(raw, dict):
            raise ValueError("Replay config must parse to a mapping")
        config = BacktestConfig.model_validate(raw)
    except (ValueError, ValidationError, yaml.YAMLError) as exc:
        console.print(f"[red]Replay config validation failed[/red]: {exc}")
        return 2

    replay_output = Path(output) if output else Path(tempfile.gettempdir()) / (
        f"replay-{capsule.backtest_id}-{capsule.run_id.replace(':', '_')}-{uuid.uuid4().hex}.json"
    )

    try:
        resolved_target_bar_index = resolve_trade_replay_target_bar_index(config, capsule)
        if resolved_target_bar_index is not None:
            capsule = capsule.model_copy(
                update={
                    "trade": capsule.trade.model_copy(
                        update={
                            "entry_bar_index": resolved_target_bar_index
                            if capsule.break_at == "entry"
                            else capsule.trade.entry_bar_index,
                            "exit_bar_index": resolved_target_bar_index
                            if capsule.break_at == "exit"
                            else capsule.trade.exit_bar_index,
                        }
                    )
                }
            )
        install_trade_replay_debug_target(capsule)
        report = run_backtests_with_hooks(config, raw)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Replay run failed[/red]: {exc}")
        return 20
    finally:
        clear_trade_replay_debug_target()

    persist_backtest_report(report.report, replay_output, risk_auxiliary_by_run=report.risk_auxiliary_by_run)
    console.print(
        f"Replayed trade {capsule.backtest_id} / {capsule.run_id} trade={capsule.trade_index + 1} "
        f"status={report.report.status} output={replay_output}"
    )
    if report.report.status == "success":
        return 0
    if report.report.status == "partial_failure":
        return 10
    return 20


def _cmd_alpaca_run(config_path: str) -> int:
    config_file = Path(config_path)
    try:
        raw = _load_yaml(config_file)
        config = AlpacaTradingConfig.model_validate(raw, context={"config_base_dir": config_file.parent.resolve()})
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
    console.print("Triggers:")
    for spec in list_triggers():
        console.print(f"  {spec.name}: {spec.description}")
    console.print("Exit rules:")
    for spec in list_exit_rules():
        console.print(f"  {spec.name}: {spec.description}")
    return 0


def _cmd_serve(host: str, port: int, log_dir: Path) -> int:
    from app.api import app as fastapi_app

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
    written_paths = persist_backtest_report(report, output, manifest_path=manifest)
    if backtest_id:
        from app.backtests.argo_reconciler import update_metadata_from_report
        from app.backtests.artifacts import resolve_results_root

        update_metadata_from_report(
            backtest_id,
            report,
            output_dir=resolve_results_root(output, backtest_id),
            write_artifacts=False,
            artifact_paths=written_paths,
        )
    console.print(
        f"Merged {report.total_runs} runs: "
        f"{report.successful_runs} success, {report.failed_runs} failed. "
        f"Status={report.status}. Output={output}"
    )
    return merge_exit_code(report)


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
    progress_file: str | None = typer.Option(
        None,
        "--progress-file",
        help="Write Argo-style N/100 progress (defaults to ARGO_PROGRESS_FILE when set)",
    ),
) -> int:
    return _cmd_run(config, output, cache_dir, cache_refresh, no_cache, progress_file)


@app.command("replay-trade", help="Replay a specific backtest trade under the debugger")
def replay_trade_command(
    capsule_b64: str | None = typer.Option(
        None,
        "--capsule-b64",
        envvar="KALYX_REPLAY_CAPSULE_B64",
        help="Base64-encoded replay capsule JSON.",
    ),
    capsule_file: str | None = typer.Option(
        None,
        "--capsule-file",
        help="Path to a replay capsule JSON file.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        help="Optional JSON output path for the replay run.",
    ),
) -> int:
    return _cmd_replay_trade(capsule_b64, capsule_file, output)


@app.command("alpaca-run", help="Evaluate latest completed Alpaca bars and submit paper/live orders")
def alpaca_run_command(
    config: str = typer.Option(..., "--config", help="Alpaca trading YAML config path"),
) -> int:
    return _cmd_alpaca_run(config)


@app.command("list-strategies", help="List available built-in strategies")
def list_strategies_command() -> int:
    return _cmd_list_strategies()


@app.command("report-html", help="Convert backtest JSON output into a Material Design HTML report")
def report_html_command(
    input_json: str = typer.Option(..., "--input", help="Backtest JSON input path"),
    output_html: str = typer.Option(..., "--output", help="HTML output path"),
    title: str = typer.Option("Backtest Report", "--title", help="Report page title"),
) -> int:
    input_path = Path(input_json)
    output_path = Path(output_html)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return 2
    try:
        generate_html_report(input_path, output_path, title=title)
    except ValueError as exc:
        print(f"Invalid backtest JSON: {exc}")
        return 2
    console.print(f"HTML report created: {output_path}")
    return 0


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
        help="Shard grouping: run, symbol, trigger, symbol_trigger (aliases: strategy, symbol_strategy)",
    ),
) -> int:
    return _cmd_plan_shards(config, work_dir, manifest, shards_param, split_by)


@app.command("merge", help="Merge shard backtest JSON reports into one report")
def merge_command(
    manifest: str = typer.Option(..., "--manifest", help="Shard manifest JSON path"),
    output: str = typer.Option(..., "--output", help="Merged JSON output path"),
    backtest_id: str | None = typer.Option(
        None,
        "--backtest-id",
        help="When set, update job metadata in the output directory parent",
    ),
) -> int:
    return _cmd_merge(manifest, output, backtest_id)


@app.command("build-risk-dataset", help="Build labeled feature dataset from backtest report JSON(s)")
def build_risk_dataset_command(
    input_json: list[str] = typer.Option(..., "--input", help="Backtest JSON input path (repeatable)"),
    output: str = typer.Option(..., "--output", help="Parquet output path"),
    config: str | None = typer.Option(None, "--config", help="Risk dataset YAML config path"),
    cache_dir: str | None = typer.Option(None, "--cache-dir", help="Override parquet cache directory"),
) -> int:
    return _cmd_build_risk_dataset(input_json, output, config, cache_dir)


@app.command("argo-reconciler", help="Reconcile Argo backtest workflow status with job metadata")
def argo_reconciler_command(
    output_dir: str = typer.Option(..., "--output-dir", help="Backtest results directory"),
    once: bool = typer.Option(False, "--once", help="Run one reconciliation pass and exit"),
) -> int:
    return _cmd_argo_reconciler(output_dir, once)


def _cmd_import_metadata(output_dir: str) -> int:
    import json

    from app.backtests.artifacts import default_artifact_paths
    from app.backtests.models import BacktestListItem
    from app.backtests.persistence import SqlAlchemyBacktestJobRepository
    from app.db.session import get_session_factory

    results_dir = Path(output_dir).resolve()
    if not results_dir.is_dir():
        print(f"Results directory not found: {results_dir}")
        return 2

    job_repository = SqlAlchemyBacktestJobRepository(get_session_factory())
    imported = 0
    for meta_path in sorted(results_dir.glob("*.meta.json")):
        backtest_id = meta_path.name[: -len(".meta.json")]
        if job_repository.get(backtest_id) is not None:
            continue
        try:
            metadata = BacktestListItem.model_validate_json(meta_path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"Skipping {meta_path.name}: {exc}")
            continue
        paths = default_artifact_paths(results_dir, backtest_id)
        job_repository.create(metadata, paths=paths)
        imported += 1

    console.print(f"Imported {imported} legacy metadata file(s) into backtest_jobs")
    return 0


@app.command("import-metadata", help="Import legacy .meta.json files into the backtest_jobs table")
def import_metadata_command(
    output_dir: str = typer.Option(..., "--output-dir", help="Backtest results directory"),
) -> int:
    return _cmd_import_metadata(output_dir)


@universes_app.command("refresh", help="Refresh symbol universe constituents in the DB")
def universes_refresh_command(
    key: str | None = typer.Option(None, "--key", help="Universe key to refresh"),
    all_universes: bool = typer.Option(False, "--all", help="Refresh all active universes"),
    as_of: str = typer.Option(..., "--as-of", help="As-of date (YYYY-MM-DD)"),
) -> int:
    from datetime import date as date_type

    try:
        resolved_as_of = date_type.fromisoformat(as_of)
    except ValueError:
        console.print(f"[red]Invalid --as-of date:[/red] {as_of!r} (expected YYYY-MM-DD)")
        return 2

    if (key is None and not all_universes) or (key is not None and all_universes):
        console.print("[red]Provide either --key or --all.[/red]")
        return 2

    session_factory = get_session_factory()
    universe_service = SymbolUniverseService()

    with session_factory() as session:
        if all_universes:
            items = universe_service.list_universes(session, active_only=True)
            keys = [item["key"] for item in items]
        else:
            keys = [key.strip().lower()] if key is not None else []

        for universe_key in keys:
            record = universe_service.get_universe(session, key=universe_key)
            if record is None:
                console.print(f"[yellow]Universe not found:[/yellow] {universe_key}")
                continue
            if not bool(record.is_active):
                console.print(f"[yellow]Universe inactive, skipping:[/yellow] {universe_key}")
                continue
            run = universe_service.create_refresh_run(
                session,
                universe_id=record.id,
                as_of=resolved_as_of,
                status="running",
            )
            console.print(f"Refreshing [bold]{record.key}[/bold] as_of={resolved_as_of.isoformat()} provider={record.provider}")
            try:
                stats = universe_service.refresh_universe_in_db(session, universe=record, as_of=resolved_as_of)
            except Exception as exc:
                universe_service.finish_refresh_run(
                    session,
                    run_id=run.id,
                    status="failed",
                    error=str(exc),
                )
                console.print(f"[red]Refresh failed for {record.key}:[/red] {exc}")
                return 1
            universe_service.finish_refresh_run(
                session,
                run_id=run.id,
                status="succeeded",
                stats=stats.as_dict(),
            )
            console.print(f"OK {record.key}: added={stats.added} closed={stats.closed} unchanged={stats.unchanged}")

    return 0


@universes_app.command("sync-registry", help="Sync the local universe registry into the DB (registry wins)")
def universes_sync_registry_command() -> int:
    session_factory = get_session_factory()
    universe_service = SymbolUniverseService()

    with session_factory() as session:
        stats = universe_service.sync_registry(session)

    console.print(
        f"Universe registry sync complete: created={stats['created']} updated={stats['updated']} disabled={stats['disabled']}"
    )
    return 0


@app.command("serve", help="Run the FastAPI market data service")
def serve_command(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", min=1, max=65535, help="Bind port"),
    log_dir: Path = typer.Option(DEFAULT_LOG_DIR, "--log-dir", help="Directory for timestamped API log files"),
) -> int:
    return _cmd_serve(host, port, log_dir)


@app.command("live-controller", help="Run the live trading contracts controller")
def live_controller_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    once: bool = typer.Option(False, "--once", help="Run one sync iteration and exit"),
) -> int:
    return _cmd_live_controller(config, once)


@app.command("live-worker", help="Run a live trading worker shard")
def live_worker_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    shard_id: int = typer.Option(..., "--shard-id", min=0, help="Shard id for this worker"),
    once: bool = typer.Option(False, "--once", help="Run one worker iteration and exit"),
) -> int:
    return _cmd_live_worker(config, shard_id, once)


@app.command("live-reconciler", help="Run the live trading reconciler")
def live_reconciler_command(
    config: str = typer.Option(..., "--config", help="Live trading YAML config path"),
    once: bool = typer.Option(False, "--once", help="Run one reconciliation pass and exit"),
) -> int:
    return _cmd_live_reconciler(config, once)


def main(argv: list[str] | None = None) -> int:
    prev_argv = None
    if argv is not None:
        prev_argv = sys.argv
        sys.argv = ["kalyxctl", *argv]
    try:
        code = app(args=argv, standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.exceptions.Exit as exc:
        return exc.exit_code
    finally:
        if prev_argv is not None:
            sys.argv = prev_argv
    return 0 if code is None else int(code)


if __name__ == "__main__":
    main()
