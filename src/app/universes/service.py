from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, and_, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import SymbolUniverse, SymbolUniverseConstituent, SymbolUniverseRefreshRun
from app.universes.registry import UNIVERSE_REGISTRY
from app.universes.providers import provider_for_universe


class InvalidUniverseError(RuntimeError):
    pass


class SymbolUniverseProviderError(RuntimeError):
    pass


def _as_of_start(as_of: date) -> datetime:
    return datetime.combine(as_of, time.min, tzinfo=UTC)


def _as_of_end(as_of: date) -> datetime:
    return datetime.combine(as_of, time.max, tzinfo=UTC)


def _normalize_symbol(value: str) -> str:
    return value.strip().upper()


@dataclass(frozen=True)
class UniverseRefreshStats:
    added: int
    closed: int
    unchanged: int

    def as_dict(self) -> dict[str, int]:
        return {"added": self.added, "closed": self.closed, "unchanged": self.unchanged}


class SymbolUniverseService:
    def list_universes(self, session: Session, *, active_only: bool) -> list[dict]:
        # Auto-migrate legacy universes stored with the deprecated "fmp" provider to "wikipedia"
        # so the UI/API never surface "fmp" again.
        migrated = False
        legacy = (
            session.execute(
                select(SymbolUniverse).where(func.lower(func.trim(SymbolUniverse.provider)) == "fmp")
            )
            .scalars()
            .all()
        )
        for record in legacy:
            record.provider = "wikipedia"
            if record.kind == "registry":
                provider_ref = record.provider_ref or {}
                kind = provider_ref.get("kind")
                if not isinstance(kind, str) or not kind.strip():
                    record.provider_ref = {**provider_ref, "kind": record.key}
            migrated = True
        if migrated:
            session.commit()

        base = select(SymbolUniverse)
        if active_only:
            base = base.where(SymbolUniverse.is_active == 1)
        universes = session.execute(base.order_by(SymbolUniverse.key.asc())).scalars().all()

        latest = (
            select(
                SymbolUniverseRefreshRun.universe_id,
                SymbolUniverseRefreshRun.status,
                SymbolUniverseRefreshRun.started_at,
                SymbolUniverseRefreshRun.as_of,
            )
            .where(SymbolUniverseRefreshRun.universe_id.is_not(None))
            .order_by(SymbolUniverseRefreshRun.universe_id, desc(SymbolUniverseRefreshRun.started_at))
        )
        rows = session.execute(latest).all()
        latest_by_universe: dict = {}
        for universe_id, status, started_at, as_of in rows:
            if universe_id in latest_by_universe:
                continue
            latest_by_universe[universe_id] = (status, started_at, as_of)

        payload: list[dict] = []
        for item in universes:
            refresh = latest_by_universe.get(item.id)
            payload.append(
                {
                    "key": item.key,
                    "kind": getattr(item, "kind", None),
                    "name": item.name,
                    "description": item.description,
                    "provider": item.provider,
                    "provider_ref": item.provider_ref or {},
                    "is_active": bool(item.is_active),
                    "latest_refresh_status": refresh[0] if refresh else None,
                    "latest_refresh_started_at": refresh[1].isoformat() if refresh else None,
                    "latest_refresh_as_of": refresh[2].date().isoformat() if refresh else None,
                }
            )
        return payload

    def sync_registry(self, session: Session) -> dict[str, int]:
        created = 0
        updated = 0
        disabled = 0

        desired_keys = set(UNIVERSE_REGISTRY.keys())
        for key, spec in UNIVERSE_REGISTRY.items():
            record = self.get_universe(session, key=key)
            if record is None:
                provider_ref: dict = {}
                if spec.provider.strip().lower() == "wikipedia":
                    provider_ref = {"kind": spec.key}
                record = SymbolUniverse(
                    key=spec.key,
                    kind="registry",
                    name=spec.name,
                    description=spec.description,
                    provider=spec.provider,
                    provider_ref=provider_ref,
                    is_active=1,
                )
                session.add(record)
                created += 1
                continue

            changed = False
            if getattr(record, "kind", "registry") != "registry":
                record.kind = "registry"
                changed = True
            if record.is_active != 1:
                record.is_active = 1
                changed = True
            if record.name != spec.name:
                record.name = spec.name
                changed = True
            if record.description != spec.description:
                record.description = spec.description
                changed = True
            if record.provider != spec.provider:
                record.provider = spec.provider
                changed = True
            if spec.provider.strip().lower() == "wikipedia":
                provider_ref = record.provider_ref or {}
                kind = provider_ref.get("kind")
                if not isinstance(kind, str) or not kind.strip():
                    record.provider_ref = {**provider_ref, "kind": spec.key}
                    changed = True
            # Migrate legacy FMP registry universes to Wikipedia without requiring an Alembic migration.
            if (record.provider or "").strip().lower() == "fmp":
                record.provider = "wikipedia"
                provider_ref = record.provider_ref or {}
                if not isinstance(provider_ref.get("kind"), str) or not str(provider_ref.get("kind") or "").strip():
                    record.provider_ref = {**provider_ref, "kind": spec.key}
                changed = True
            if changed:
                updated += 1

        if desired_keys:
            deactivate_stmt = (
                update(SymbolUniverse)
                .where(SymbolUniverse.key.not_in(sorted(desired_keys)))
                .where(SymbolUniverse.kind == "registry")
                .where(SymbolUniverse.is_active == 1)
                .values(is_active=0)
            )
            result = session.execute(deactivate_stmt)
            try:
                disabled = int(result.rowcount or 0)
            except Exception:  # noqa: BLE001
                disabled = 0

        session.commit()
        return {"created": created, "updated": updated, "disabled": disabled}

    def get_universe(self, session: Session, *, key: str) -> SymbolUniverse | None:
        normalized = key.strip().lower()
        return session.execute(select(SymbolUniverse).where(SymbolUniverse.key == normalized)).scalar_one_or_none()

    def create_universe(self, session: Session, *, payload: dict) -> SymbolUniverse:
        record = SymbolUniverse(
            key=payload["key"].strip().lower(),
            kind=payload.get("kind") or "registry",
            name=payload["name"].strip(),
            description=payload.get("description"),
            provider=(payload["provider"].strip() if payload.get("provider") else None),
            provider_ref=payload.get("provider_ref") or {},
            is_active=1 if payload.get("is_active", True) else 0,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def patch_universe(self, session: Session, *, key: str, patch: dict) -> SymbolUniverse:
        record = self.get_universe(session, key=key)
        if record is None:
            raise InvalidUniverseError("Universe not found")
        if "name" in patch and patch["name"] is not None:
            record.name = str(patch["name"]).strip()
        if "description" in patch:
            record.description = patch["description"]
        if "provider" in patch and patch["provider"] is not None:
            record.provider = str(patch["provider"]).strip()
        if "provider_ref" in patch and patch["provider_ref"] is not None:
            record.provider_ref = patch["provider_ref"]
        if "is_active" in patch and patch["is_active"] is not None:
            record.is_active = 1 if bool(patch["is_active"]) else 0
        session.commit()
        session.refresh(record)
        return record

    def _generate_user_key(self, session: Session, *, name: str) -> str:
        import re
        import secrets

        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "universe"
        for _ in range(10):
            candidate = f"user-{base}-{secrets.token_hex(3)}"
            exists = session.execute(select(SymbolUniverse.id).where(SymbolUniverse.key == candidate)).first()
            if not exists:
                return candidate
        raise RuntimeError("Failed to generate unique universe key")

    def create_user_universe(
        self,
        session: Session,
        *,
        name: str,
        symbols: list[str],
        description: str | None,
        is_active: bool,
        created_on: date,
    ) -> SymbolUniverse:
        key = self._generate_user_key(session, name=name)
        record = SymbolUniverse(
            key=key,
            kind="user",
            name=name.strip(),
            description=description,
            provider=None,
            provider_ref={},
            is_active=1 if is_active else 0,
        )
        session.add(record)
        session.commit()
        session.refresh(record)

        self.replace_user_universe_symbols(session, universe=record, symbols=symbols, effective_on=created_on)
        session.refresh(record)
        return record

    def patch_user_universe(
        self,
        session: Session,
        *,
        key: str,
        name: str | None,
        description: str | None,
        is_active: bool | None,
    ) -> SymbolUniverse:
        record = self.get_universe(session, key=key)
        if record is None or record.kind != "user":
            raise InvalidUniverseError("User universe not found")
        if name is not None:
            record.name = name.strip()
        if description is not None:
            record.description = description
        if is_active is not None:
            record.is_active = 1 if is_active else 0
        session.commit()
        session.refresh(record)
        return record

    def replace_user_universe_symbols(
        self,
        session: Session,
        *,
        universe: SymbolUniverse,
        symbols: list[str],
        effective_on: date,
    ) -> dict[str, int]:
        if universe.kind != "user":
            raise InvalidUniverseError("Universe is not user-defined")
        as_of_dt = _as_of_start(effective_on)
        close_dt = as_of_dt - timedelta(microseconds=1)

        normalized = sorted({_normalize_symbol(item) for item in symbols if _normalize_symbol(item)})

        current_open = session.execute(
            select(SymbolUniverseConstituent.symbol)
            .where(SymbolUniverseConstituent.universe_id == universe.id)
            .where(SymbolUniverseConstituent.effective_to.is_(None))
        ).scalars().all()
        current_set = set(current_open)
        next_set = set(normalized)

        to_add = sorted(next_set - current_set)
        to_close = sorted(current_set - next_set)
        unchanged = len(next_set & current_set)

        if to_close:
            session.execute(
                update(SymbolUniverseConstituent)
                .where(SymbolUniverseConstituent.universe_id == universe.id)
                .where(SymbolUniverseConstituent.symbol.in_(to_close))
                .where(SymbolUniverseConstituent.effective_to.is_(None))
                .values(effective_to=close_dt)
            )

        # Close unchanged constituents too so changes are versioned at effective_on.
        session.execute(
            update(SymbolUniverseConstituent)
            .where(SymbolUniverseConstituent.universe_id == universe.id)
            .where(SymbolUniverseConstituent.effective_to.is_(None))
            .values(effective_to=close_dt)
        )

        for symbol in normalized:
            session.add(
                SymbolUniverseConstituent(
                    universe_id=universe.id,
                    symbol=symbol,
                    effective_from=as_of_dt,
                    effective_to=None,
                )
            )

        session.commit()
        return {"added": len(to_add), "closed": len(to_close), "unchanged": unchanged}

    def delete_user_universe(self, session: Session, *, key: str) -> None:
        record = self.get_universe(session, key=key)
        if record is None or record.kind != "user":
            raise InvalidUniverseError("User universe not found")

        session.execute(
            update(SymbolUniverseRefreshRun)
            .where(SymbolUniverseRefreshRun.universe_id == record.id)
            .values(universe_id=None)
        )
        session.query(SymbolUniverseConstituent).filter(SymbolUniverseConstituent.universe_id == record.id).delete()
        session.query(SymbolUniverse).filter(SymbolUniverse.id == record.id).delete()
        session.commit()

    def constituents_as_of(self, session: Session, *, universe: SymbolUniverse, as_of: date) -> list[str]:
        as_of_dt = _as_of_start(as_of)
        query = (
            select(SymbolUniverseConstituent.symbol)
            .where(SymbolUniverseConstituent.universe_id == universe.id)
            .where(SymbolUniverseConstituent.effective_from <= as_of_dt)
            .where(
                or_(
                    SymbolUniverseConstituent.effective_to.is_(None),
                    SymbolUniverseConstituent.effective_to >= as_of_dt,
                )
            )
            .order_by(SymbolUniverseConstituent.symbol.asc())
        )
        return [row[0] for row in session.execute(query).all()]

    def refresh_universe_in_db(self, session: Session, *, universe: SymbolUniverse, as_of: date) -> UniverseRefreshStats:
        provider = provider_for_universe(universe)
        as_of_dt = _as_of_start(as_of)

        try:
            target_membership = { _normalize_symbol(s) for s in provider.fetch_membership(universe, as_of=as_of) }
            target_membership = {s for s in target_membership if s}
        except Exception as exc:  # noqa: BLE001 - provider exceptions should surface as runtime errors
            raise SymbolUniverseProviderError(str(exc)) from exc

        current_symbols = set(self.constituents_as_of(session, universe=universe, as_of=as_of))
        added = sorted(target_membership - current_symbols)
        removed = sorted(current_symbols - target_membership)
        unchanged = len(target_membership & current_symbols)

        for symbol in added:
            session.add(
                SymbolUniverseConstituent(
                    universe_id=universe.id,
                    symbol=symbol,
                    effective_from=as_of_dt,
                    effective_to=None,
                )
            )

        if removed:
            close_stmt = (
                update(SymbolUniverseConstituent)
                .where(SymbolUniverseConstituent.universe_id == universe.id)
                .where(SymbolUniverseConstituent.symbol.in_(removed))
                .where(SymbolUniverseConstituent.effective_to.is_(None))
                .values(effective_to=as_of_dt)
            )
            session.execute(close_stmt)

        session.commit()
        return UniverseRefreshStats(added=len(added), closed=len(removed), unchanged=unchanged)

    def create_refresh_run(
        self,
        session: Session,
        *,
        universe_id,
        as_of: date,
        status: str,
        started_at: datetime | None = None,
    ) -> SymbolUniverseRefreshRun:
        started = started_at or datetime.now(UTC)
        record = SymbolUniverseRefreshRun(
            universe_id=universe_id,
            as_of=_as_of_start(as_of),
            status=status,
            started_at=started,
            finished_at=None,
            stats={},
            error=None,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record
