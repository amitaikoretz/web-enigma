from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.backtests.models import VectorbtWorkflowRequest
from app.script_logging import emit_info, emit_terminal_command
from app.terminal_command import format_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)

_DEFAULT_SCRIPT_PATH = str(Path(__file__).with_name("backtest_risk_gated_ma.py"))


def _decode_request(raw: str) -> VectorbtWorkflowRequest:
    decoded = base64.b64decode(raw.encode("utf-8")).decode("utf-8")
    payload = json.loads(decoded)
    return VectorbtWorkflowRequest.model_validate(payload)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _script_path() -> Path:
    configured = os.environ.get("VECTORBT_RISK_GATED_MA_SCRIPT_PATH", _DEFAULT_SCRIPT_PATH)
    return Path(configured)


def _build_command(request: VectorbtWorkflowRequest, artifact_dir: Path) -> list[str]:
    script_path = _script_path()
    if not script_path.is_file():
        raise FileNotFoundError(
            f"Vectorbt script not found: {script_path}. Set VECTORBT_RISK_GATED_MA_SCRIPT_PATH to a valid path."
        )

    output_csv = artifact_dir / "vectorbt-summary.csv"
    trades_csv = artifact_dir / "vectorbt-trades.csv"
    regime_csv = artifact_dir / "vectorbt-regime-summary.csv"
    report_html = artifact_dir / "vectorbt-report.html"

    command = [
        sys.executable,
        str(script_path),
        "--data-path",
        request.dataset_path,
        "--volume-window",
        str(request.volume_window),
        "--min-volume-ratio",
        str(request.min_volume_ratio),
        "--entry-cutoff-minutes",
        str(request.entry_cutoff_minutes),
        "--risk-threshold",
        str(request.risk_threshold),
        "--exit-style",
        request.exit_style,
        "--min-hold-minutes",
        str(request.min_hold_minutes),
        "--atr-window",
        str(request.atr_window),
        "--atr-stop-mult",
        str(request.atr_stop_mult),
        "--output",
        str(output_csv),
        "--trades-output",
        str(trades_csv),
        "--regime-summary-output",
        str(regime_csv),
        "--histograms-html-output",
        str(report_html),
    ]
    if request.risk_model_artifact_path:
        command.extend(["--model-path", request.risk_model_artifact_path])
    if request.from_date is not None:
        command.extend(["--from-date", request.from_date.isoformat()])
    if request.max_symbols is not None:
        command.extend(["--max-symbols", str(request.max_symbols)])
    return command


@app.command(help="Run the vectorbt workflow payload inside Argo.")
def main(
    backtest_id: str = typer.Option(..., "--backtest-id"),
    request_json_b64: str = typer.Option(..., "--request-json-b64"),
    artifact_dir: str = typer.Option(..., "--artifact-dir"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
) -> None:
    emit_terminal_command(
        sys.argv,
        terminal_command_out=terminal_command_out,
        script="run_vectorbt_backtest_argo",
    )

    request = _decode_request(request_json_b64)
    output_dir = Path(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _write_json(output_dir / "vectorbt-request.json", request.model_dump(mode="json"))

    command = _build_command(request, output_dir)
    emit_info(
        "vectorbt-command",
        format_terminal_command(command),
        script="run_vectorbt_backtest_argo",
    )

    subprocess.run(command, check=True)

    _write_json(
        output_dir / "vectorbt-artifacts.json",
        {
            "backtest_id": backtest_id,
            "artifact_dir": str(output_dir),
            "artifacts": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
        },
    )


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
