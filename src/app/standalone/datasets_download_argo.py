from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.config.models import AlpacaDataSource, AlpacaOptionsDataSource, DataCacheConfig, YahooDataSource
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_alpaca_options_data_feed_with_cache,
    build_yahoo_data_feed_with_cache,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _log(message: str) -> None:
    typer.echo(message, err=True)


@app.command(help="Argo-safe dataset downloader that writes parquet artifacts to shared storage.")
def main(
    symbol: str = typer.Option(..., "--symbol"),
    provider: str = typer.Option(..., "--provider"),
    resolution: str = typer.Option(..., "--resolution"),
    start_date: str = typer.Option(..., "--start-date"),
    end_date: str = typer.Option(..., "--end-date"),
    options_enabled: bool = typer.Option(False, "--options-enabled/--no-options-enabled"),
    options_feed: str = typer.Option("indicative", "--options-feed"),
    output_dir: str = typer.Option(..., "--output-dir"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
    dataset_path_out: str | None = typer.Option(None, "--dataset-path-out"),
    manifest_path_out: str | None = typer.Option(None, "--manifest-path-out"),
    options_dataset_path_out: str | None = typer.Option(None, "--options-dataset-path-out"),
    options_manifest_path_out: str | None = typer.Option(None, "--options-manifest-path-out"),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    _write_text(dataset_path_out, "")
    _write_text(manifest_path_out, "")
    _write_text(options_dataset_path_out, "")
    _write_text(options_manifest_path_out, "")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from datetime import date

    symbol_normalized = symbol.strip().upper()
    provider_normalized = provider.strip().lower()
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    cache_config = DataCacheConfig(directory=str(out_dir / ".cache"))

    _log(
        "Starting dataset download: "
        f"symbol={symbol_normalized} provider={provider_normalized} "
        f"resolution={resolution} start_date={start.isoformat()} end_date={end.isoformat()}"
    )
    _log(f"Writing artifacts to {out_dir}")
    _log(f"Using cache directory {cache_config.directory}")

    if provider_normalized == "alpaca":
        _log("Loading Alpaca data feed")
        frame, _ = build_alpaca_data_feed_with_cache(
            AlpacaDataSource(type="alpaca", symbol=symbol_normalized, interval=resolution, feed="iex"),
            start,
            end,
            cache_config,
        )
    elif provider_normalized == "yahoo":
        _log("Loading Yahoo data feed")
        frame, _ = build_yahoo_data_feed_with_cache(
            YahooDataSource(type="yahoo", symbol=symbol_normalized, interval=resolution),
            start,
            end,
            cache_config,
        )
    else:
        raise ValueError("provider must be alpaca or yahoo")

    options_parquet_path: Path | None = None
    options_manifest: Path | None = None
    if options_enabled:
        _log("Loading Alpaca options data feed")
        options_frame, _ = build_alpaca_options_data_feed_with_cache(
            AlpacaOptionsDataSource(
                type="alpaca-options",
                symbol=symbol_normalized,
                interval=resolution,
                feed=options_feed,  # type: ignore[arg-type]
            ),
            start,
            end,
            cache_config,
        )
        options_parquet_path = out_dir / f"{symbol_normalized}-alpaca-options-{resolution}.parquet"
        options_manifest = out_dir / f"{symbol_normalized}-alpaca-options-{resolution}.manifest.json"
        _log(f"Saving options parquet to {options_parquet_path}")
        options_frame.to_parquet(options_parquet_path, index=False)
        _log(f"Saving options manifest to {options_manifest}")
        options_manifest.write_text(
            json.dumps(
                {
                    "symbol": symbol_normalized,
                    "provider": "alpaca-options",
                    "resolution": resolution,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "row_count": int(len(options_frame)),
                    "dataset_path": str(options_parquet_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    row_count = int(len(frame))
    _log(f"Downloaded frame with {row_count} rows")

    parquet_path = out_dir / f"{symbol_normalized}-{provider_normalized}-{resolution}.parquet"
    manifest_path = out_dir / f"{symbol_normalized}-{provider_normalized}-{resolution}.manifest.json"
    _log(f"Saving parquet to {parquet_path}")
    frame.to_parquet(parquet_path, index=False)
    _log(f"Saving manifest to {manifest_path}")
    manifest_path.write_text(
        json.dumps(
            {
                "symbol": symbol_normalized,
                "provider": provider_normalized,
                "resolution": resolution,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "row_count": row_count,
                "dataset_path": str(parquet_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    _write_text(dataset_path_out, str(parquet_path))
    _write_text(manifest_path_out, str(manifest_path))
    _write_text(options_dataset_path_out, str(options_parquet_path) if options_parquet_path else "")
    _write_text(options_manifest_path_out, str(options_manifest) if options_manifest else "")
    _log("Dataset download complete")
    _log(f"Dataset path: {parquet_path}")
    _log(f"Manifest path: {manifest_path}")
    if options_parquet_path and options_manifest:
        _log(f"Options dataset path: {options_parquet_path}")
        _log(f"Options manifest path: {options_manifest}")


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
