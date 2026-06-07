from __future__ import annotations

import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Generate a market-overview snapshot artifact for Argo.")
def main(
    snapshot_id: str = typer.Option(..., "--snapshot-id"),
    output_path: str = typer.Option(..., "--output-path"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    now = datetime.now(UTC)
    payload = {
        "snapshot_id": snapshot_id,
        "status": "completed",
        "top_regime": "Narrow risk-on / fragile bull",
        "probabilities": {
            "Narrow risk-on / fragile bull": 0.71,
            "Goldilocks risk-on": 0.12,
            "Late-cycle risk-on": 0.09,
            "Range / neutral": 0.08,
        },
        "confidence": 71.0,
        "fragility": 64.0,
        "contradiction_score": 18.0,
        "pillar_scores": {
            "trend": 1.0,
            "breadth": -1.0,
            "volatility": 0.5,
            "credit": 1.0,
            "rates": -1.0,
            "macro": 0.0,
            "earnings": 0.5,
        },
        "developments": [
            {
                "category": "policy repricing",
                "title": "Rates moved higher",
                "importance_score": 0.82,
                "market_reaction": {"rates": "up", "growth": "mixed"},
            },
            {
                "category": "breadth divergence",
                "title": "Participation weakened",
                "importance_score": 0.76,
                "market_reaction": {"breadth": "down", "equities": "stable"},
            },
        ],
        "freshness": {"market": now.isoformat(), "news": now.isoformat()},
        "summary_text": (
            "Equities remain in an uptrend and credit is calm, but participation is narrowing "
            "and higher yields are increasing vulnerability to a negative macro or policy surprise."
        ),
        "evidence": {
            "trend": ["S&P 500 above 50D/200D"],
            "breadth": ["equal-weight lagging cap-weight"],
        },
        "params": {},
        "error_message": None,
        "name": None,
        "argo_namespace": None,
        "argo_workflow_name": None,
        "as_of": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(json.dumps(payload))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
