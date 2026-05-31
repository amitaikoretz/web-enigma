from __future__ import annotations

import base64
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_payload import build_argo_launch_payload, format_argo_launch_curl
from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _maybe_read_at_file(value: str) -> str:
    value = value.strip()
    if not value.startswith("@"):
        return value
    at_path = value[1:].strip()
    if not at_path:
        raise ValueError("empty @file reference")
    return Path(at_path).read_text(encoding="utf-8").strip()


def _decode_config_b64(value: str) -> str:
    resolved = _maybe_read_at_file(value)
    raw = base64.b64decode(resolved, validate=True)
    return raw.decode("utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Print a curl command that launches this backtest via POST /backtests/argo")
def main(
    api_base_url: str = typer.Option(..., "--api-base-url", help="API base URL (e.g. http://localhost:8000)"),
    config_path: str | None = typer.Option(
        None, "--config-path", help="Config path on the shared backtest-results volume"
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
    launch_curl_out: str | None = typer.Option(
        None,
        "--launch-curl-out",
        help="Write the curl command to this path (for Argo output parameters)",
    ),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    config_text: str | None = None
    resolved_config_path = config_path.strip() if config_path else None

    # Write this early so Argo output parameters always include the invoked command line,
    # even if we exit with an error while parsing inputs.
    _write_text(terminal_command_out, _terminal_command(sys.argv))

    if config_b64 and config_b64.strip():
        try:
            config_text = _decode_config_b64(config_b64)
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            typer.echo(f"Invalid --config-b64: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    elif config_text_file:
        text_path = Path(config_text_file)
        if not text_path.exists():
            typer.echo(f"Config text file not found: {config_text_file}", err=True)
            raise typer.Exit(code=2)
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
            typer.echo("Provide one of --config-path, --config-text-file, or --config-b64", err=True)
            raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(f"Payload build failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    curl = format_argo_launch_curl(api_base_url, payload)
    typer.echo(curl)

    _write_text(launch_curl_out, curl)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
