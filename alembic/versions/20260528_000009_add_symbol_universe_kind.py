"""Add kind column to symbol_universes.

Revision ID: 20260528_000009
Revises: 20260528_000008
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260528_000009"
down_revision = "20260528_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("symbol_universes")}
    indexes = {index["name"] for index in inspector.get_indexes("symbol_universes")}

    if "kind" not in columns:
        op.add_column(
            "symbol_universes",
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="registry"),
        )

    if "ix_symbol_universes_kind" not in indexes:
        op.create_index("ix_symbol_universes_kind", "symbol_universes", ["kind"])

    if bind.dialect.name != "sqlite":
        op.alter_column("symbol_universes", "provider", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column("symbol_universes", "provider", existing_type=sa.String(length=64), nullable=False)
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("symbol_universes")}
    indexes = {index["name"] for index in inspector.get_indexes("symbol_universes")}

    if "ix_symbol_universes_kind" in indexes:
        op.drop_index("ix_symbol_universes_kind", table_name="symbol_universes")
    if "kind" in columns:
        op.drop_column("symbol_universes", "kind")
