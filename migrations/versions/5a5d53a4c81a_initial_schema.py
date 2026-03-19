"""initial_schema

Revision ID: 5a5d53a4c81a
Revises:
Create Date: 2026-03-19

Creates all LangSight PostgreSQL tables:
  api_keys        — API key management with RBAC role (admin/viewer)
  health_results  — MCP server health check history
  schema_snapshots — MCP tool schema versions for drift detection
  agent_slos      — User-defined agent SLO definitions (P5.5)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a5d53a4c81a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="admin"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("idx_api_keys_hash", "api_keys", ["key_hash"])

    op.create_table(
        "health_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("server_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Double(), nullable=True),
        sa.Column("tools_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schema_hash", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_health_server_time", "health_results", ["server_name", "checked_at"])

    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("server_name", sa.Text(), nullable=False),
        sa.Column("schema_hash", sa.Text(), nullable=False),
        sa.Column("tools_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_schema_server_time", "schema_snapshots", ["server_name", "recorded_at"])

    op.create_table(
        "agent_slos",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("target", sa.Double(), nullable=False),
        sa.Column("window_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_slos")
    op.drop_index("idx_schema_server_time", table_name="schema_snapshots")
    op.drop_table("schema_snapshots")
    op.drop_index("idx_health_server_time", table_name="health_results")
    op.drop_table("health_results")
    op.drop_index("idx_api_keys_hash", table_name="api_keys")
    op.drop_table("api_keys")
