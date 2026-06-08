from __future__ import annotations

import json
from datetime import UTC, datetime

from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.market_overview.models import MarketOverviewSnapshot
from app.market_overview.persistence import SqlAlchemyMarketOverviewRepository
import app.standalone.market_overview_argo as market_overview_argo


def _build_repository() -> SqlAlchemyMarketOverviewRepository:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return SqlAlchemyMarketOverviewRepository(session_factory)


def _sample_snapshot() -> MarketOverviewSnapshot:
    now = datetime.now(UTC)
    return MarketOverviewSnapshot(
        snapshot_id="snap-123",
        status="completed",
        argo_namespace="backtest-workflows",
        argo_workflow_name="market-overview-snap-123",
        as_of=now,
        top_regime="Narrow risk-on / fragile bull",
        probabilities={"Narrow risk-on / fragile bull": 0.71, "Range / neutral": 0.12},
        confidence=71.0,
        fragility=64.0,
        contradiction_score=18.0,
        market_indicators=[
            {
                "key": "spx",
                "label": "S&P 500",
                "value": "+0.8%",
                "tone": "positive",
                "explanation": {
                    "summary": "Headline equity trend gauge.",
                    "inputs": ["S&P 500 close", "50-day moving average", "200-day moving average"],
                    "calculation_steps": ["Compare spot against the trend filters."],
                    "interpretation": "Positive when the benchmark is above trend filters and rising.",
                    "freshness": "Uses the latest close.",
                    "caveats": ["A strong index can still hide weak breadth."],
                },
            }
        ],
        pillar_scores={"trend": 1.0, "breadth": -1.0},
        developments=[{"title": "Breadth weakened"}],
        freshness={"market": now.isoformat()},
        summary_text="Equities remain supported but breadth is narrowing.",
        watch_next=["Watch breadth confirmation"],
        methodology={
            "summary": "Cross-asset signals are blended into a weighted regime read.",
            "inputs": ["Equities", "Rates"],
            "scoring": ["Aggregate pillar scores", "Adjust for freshness"],
            "freshness": "Older inputs lower confidence.",
            "caveats": ["Probabilistic, not deterministic."],
        },
        evidence={"trend": ["S&P 500 above 50D/200D"]},
        params={},
        created_at=now,
        updated_at=now,
    )


def test_market_overview_repository_round_trip_preserves_structured_fields() -> None:
    repo = _build_repository()
    snapshot = _sample_snapshot()

    repo.upsert(snapshot)
    stored = repo.get_latest()

    assert stored is not None
    assert stored.market_indicators[0].label == "S&P 500"
    assert stored.market_indicators[0].explanation is not None
    assert stored.market_indicators[0].explanation.summary == "Headline equity trend gauge."
    assert stored.watch_next == ["Watch breadth confirmation"]
    assert stored.methodology is not None
    assert stored.methodology.summary == "Cross-asset signals are blended into a weighted regime read."


def test_market_overview_argo_payload_includes_indicator_tape_and_methodology(
    tmp_path,
    monkeypatch,
) -> None:
    runner = CliRunner()
    output_path = tmp_path / "snapshot.json"
    terminal_path = tmp_path / "terminal-command.txt"
    monkeypatch.setattr(
        market_overview_argo.sys,
        "argv",
        [
            "python",
            "-m",
            "app.standalone.market_overview_argo",
            "--snapshot-id",
            "snap-123",
            "--output-path",
            str(output_path),
            "--terminal-command-out",
            str(terminal_path),
        ],
    )

    result = runner.invoke(
        market_overview_argo.app,
        [
            "--snapshot-id",
            "snap-123",
            "--output-path",
            str(output_path),
            "--terminal-command-out",
            str(terminal_path),
        ],
    )

    assert result.exit_code == 0, result.output

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["market_indicators"]
    assert payload["market_indicators"][0]["label"] == "S&P 500"
    assert all("explanation" in indicator and indicator["explanation"] for indicator in payload["market_indicators"])
    assert payload["watch_next"]
    assert payload["methodology"]["summary"].startswith("The overview blends")
    assert terminal_path.read_text(encoding="utf-8") == "python -m app.standalone.market_overview_argo --snapshot-id snap-123 --output-path " + str(output_path) + " --terminal-command-out " + str(terminal_path)
