from __future__ import annotations

from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import create_app
from app.config.models import DataCacheConfig
from app.db.base import Base
from app.db.session import get_db_session
from app.db.models import SymbolUniverse, SymbolUniverseConstituent
from datetime import UTC, datetime
from app.universes.service import SymbolUniverseService
from app.universes.registry import UNIVERSE_REGISTRY


def _build_client(tmp_path) -> tuple[TestClient, sessionmaker[Session]]:
    app = create_app(
        DataCacheConfig(directory=str(tmp_path)),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_db_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    return TestClient(app), test_session_factory


def test_list_universes_empty(tmp_path):
    client, _session_factory = _build_client(tmp_path)
    response = client.get("/universes")
    assert response.status_code == 200
    assert response.json() == []


def test_admin_create_and_patch_universe(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ADMIN_SECRET", "secret")
    client, _session_factory = _build_client(tmp_path)

    payload = {
        "key": "sp500",
        "name": "S&P 500",
        "description": "Large cap US equities",
        "provider": "static",
        "provider_ref": {"symbols": ["AAPL", "MSFT"]},
        "is_active": True,
    }
    response = client.post("/universes", json=payload, headers={"x-admin-secret": "secret"})
    assert response.status_code == 201
    body = response.json()
    assert body["key"] == "sp500"
    assert body["provider"] == "static"
    assert body["is_active"] is True

    patch = {"description": "Updated", "is_active": False}
    response = client.patch("/universes/sp500", json=patch, headers={"x-admin-secret": "secret"})
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Updated"
    assert body["is_active"] is False


def test_admin_rejects_deprecated_fmp_provider_on_create_and_patch(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ADMIN_SECRET", "secret")
    client, _session_factory = _build_client(tmp_path)

    response = client.post(
        "/universes",
        json={
            "key": "legacy",
            "name": "Legacy",
            "description": None,
            "provider": " fMp ",
            "provider_ref": {},
            "is_active": True,
        },
        headers={"x-admin-secret": "secret"},
    )
    assert response.status_code == 422

    response = client.post(
        "/universes",
        json={
            "key": "demo",
            "name": "Demo",
            "description": None,
            "provider": "static",
            "provider_ref": {"symbols": ["AAPL"]},
            "is_active": True,
        },
        headers={"x-admin-secret": "secret"},
    )
    assert response.status_code == 201

    response = client.patch(
        "/universes/demo",
        json={"provider": "fmp"},
        headers={"x-admin-secret": "secret"},
    )
    assert response.status_code == 422


def test_list_universes_auto_migrates_deprecated_fmp_provider(tmp_path):
    client, session_factory = _build_client(tmp_path)

    with session_factory() as session:
        session.add(
            SymbolUniverse(
                key="dow30",
                kind="registry",
                name="Dow 30",
                description=None,
                provider="fmp",
                provider_ref={},
                is_active=1,
            )
        )
        session.commit()

    response = client.get("/universes?active_only=false")
    assert response.status_code == 200
    items = response.json()
    assert any(item["key"] == "dow30" and item["provider"] == "wikipedia" for item in items)

    with session_factory() as session:
        record = session.query(SymbolUniverse).filter(SymbolUniverse.key == "dow30").one()
        assert record.provider == "wikipedia"
        assert record.provider_ref.get("kind") == "dow30"


def test_get_constituents_as_of(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ADMIN_SECRET", "secret")
    client, session_factory = _build_client(tmp_path)

    response = client.post(
        "/universes",
        json={
            "key": "demo",
            "name": "Demo",
            "description": None,
            "provider": "static",
            "provider_ref": {"symbols": ["AAPL", "MSFT"]},
            "is_active": True,
        },
        headers={"x-admin-secret": "secret"},
    )
    assert response.status_code == 201

    with session_factory() as session:
        universe = session.query(SymbolUniverse).filter(SymbolUniverse.key == "demo").one()
        session.add_all(
            [
                SymbolUniverseConstituent(
                    universe_id=universe.id,
                    symbol="AAPL",
                    effective_from=datetime(2026, 5, 28, tzinfo=UTC),
                    effective_to=None,
                ),
                SymbolUniverseConstituent(
                    universe_id=universe.id,
                    symbol="MSFT",
                    effective_from=datetime(2026, 5, 28, tzinfo=UTC),
                    effective_to=None,
                ),
            ]
        )
        session.commit()

    response = client.get(f"/universes/demo/constituents?as_of={date(2026, 5, 28).isoformat()}")
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "demo"
    assert sorted(body["symbols"]) == ["AAPL", "MSFT"]


def test_sync_registry_upserts_and_disables(tmp_path):
    _client, session_factory = _build_client(tmp_path)
    service = SymbolUniverseService()

    with session_factory() as session:
        session.add(
            SymbolUniverse(
                key="custom",
                name="Custom",
                description=None,
                provider="static",
                provider_ref={"keep": True},
                is_active=1,
            )
        )
        session.commit()

        stats = service.sync_registry(session)
        assert stats["created"] == len(UNIVERSE_REGISTRY)
        assert stats["disabled"] == 1

        sp500 = session.query(SymbolUniverse).filter(SymbolUniverse.key == "sp500").one()
        assert sp500.provider == "wikipedia"
        assert sp500.is_active == 1
        assert sp500.provider_ref == {"kind": "sp500"}

        custom = session.query(SymbolUniverse).filter(SymbolUniverse.key == "custom").one()
        assert custom.is_active == 0
        assert custom.provider_ref == {"keep": True}


def test_sync_registry_does_not_disable_user_universes(tmp_path):
    _client, session_factory = _build_client(tmp_path)
    service = SymbolUniverseService()

    with session_factory() as session:
        session.add(
            SymbolUniverse(
                key="user-demo-1",
                kind="user",
                name="User demo",
                description=None,
                provider=None,
                provider_ref={},
                is_active=1,
            )
        )
        session.commit()

        stats = service.sync_registry(session)
        assert stats["disabled"] == 0
        user_demo = session.query(SymbolUniverse).filter(SymbolUniverse.key == "user-demo-1").one()
        assert user_demo.is_active == 1
        assert user_demo.kind == "user"


def test_sync_registry_migrates_fmp_registry_provider_and_backfills_kind(tmp_path):
    _client, session_factory = _build_client(tmp_path)
    service = SymbolUniverseService()

    with session_factory() as session:
        session.add(
            SymbolUniverse(
                key="dow30",
                kind="registry",
                name="Dow 30",
                description=None,
                provider="fmp",
                provider_ref={},
                is_active=1,
            )
        )
        session.commit()

        stats = service.sync_registry(session)
        assert stats["created"] == len(UNIVERSE_REGISTRY) - 1
        assert stats["updated"] >= 1

        dow30 = session.query(SymbolUniverse).filter(SymbolUniverse.key == "dow30").one()
        assert dow30.provider == "wikipedia"
        assert dow30.provider_ref.get("kind") == "dow30"


def test_sync_registry_reactivates_registry_universe(tmp_path):
    _client, session_factory = _build_client(tmp_path)
    service = SymbolUniverseService()

    with session_factory() as session:
        session.add(
            SymbolUniverse(
                key="sp500",
                kind="registry",
                name="S&P 500 (old)",
                description=None,
                provider="wikipedia",
                provider_ref={"kind": "sp500"},
                is_active=0,
            )
        )
        session.commit()

        stats = service.sync_registry(session)
        assert stats["created"] == len(UNIVERSE_REGISTRY) - 1
        assert stats["updated"] >= 1

        sp500 = session.query(SymbolUniverse).filter(SymbolUniverse.key == "sp500").one()
        assert sp500.is_active == 1


def test_create_user_universe_and_replace_symbols_versions(tmp_path):
    _client, session_factory = _build_client(tmp_path)
    service = SymbolUniverseService()

    with session_factory() as session:
        universe = service.create_user_universe(
            session,
            name="My Basket",
            symbols=["AAPL", "msft", "  "],
            description="test",
            is_active=True,
            created_on=date(2026, 5, 28),
        )
        assert universe.kind == "user"
        symbols = service.constituents_as_of(session, universe=universe, as_of=date(2026, 5, 28))
        assert symbols == ["AAPL", "MSFT"]

        stats = service.replace_user_universe_symbols(
            session,
            universe=universe,
            symbols=["AAPL", "NVDA"],
            effective_on=date(2026, 5, 29),
        )
        assert stats["added"] == 1
        assert stats["closed"] == 1

        day1 = service.constituents_as_of(session, universe=universe, as_of=date(2026, 5, 28))
        assert day1 == ["AAPL", "MSFT"]
        day2 = service.constituents_as_of(session, universe=universe, as_of=date(2026, 5, 29))
        assert day2 == ["AAPL", "NVDA"]


def test_delete_user_universe_removes_constituents(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_ADMIN_SECRET", "secret")
    client, session_factory = _build_client(tmp_path)

    response = client.post(
        "/universes/user",
        json={
            "name": "My Basket",
            "description": None,
            "symbols": ["AAPL", "MSFT"],
            "is_active": True,
        },
    )
    assert response.status_code == 201
    key = response.json()["key"]

    response = client.get(f"/universes/{key}/constituents?as_of={date(2026, 5, 28).isoformat()}")
    assert response.status_code == 200
    assert sorted(response.json()["symbols"]) == ["AAPL", "MSFT"]

    response = client.delete(f"/universes/user/{key}")
    assert response.status_code == 204

    response = client.get("/universes?active_only=false")
    assert response.status_code == 200
    assert not any(item["key"] == key for item in response.json())

    with session_factory() as session:
        assert session.query(SymbolUniverse).filter(SymbolUniverse.key == key).count() == 0
        assert session.query(SymbolUniverseConstituent).count() == 0
