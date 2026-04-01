"""add_project_id_to_schema_snapshots_and_alert_config

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-01

Adds project_id to schema_snapshots (Postgres) and alert_config so both
tables are properly project-scoped.  Existing rows default to '' (global /
unscoped) so current data continues to work without changes.

alert_config historically used a singleton row with id='singleton'.  We
migrate that row to id='' (the empty-string project_id convention used
everywhere else) so the same code path handles both legacy and new rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── schema_snapshots ──────────────────────────────────────────────────────
    op.add_column(
        "schema_snapshots",
        sa.Column("project_id", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index(
        "idx_schema_snapshots_project",
        "schema_snapshots",
        ["project_id", "server_name", sa.text("recorded_at DESC")],
    )

    # ── alert_config ──────────────────────────────────────────────────────────
    op.add_column(
        "alert_config",
        sa.Column("project_id", sa.Text(), nullable=False, server_default=""),
    )
    # Migrate legacy singleton row: id='singleton' → id='' (project_id convention)
    op.execute("UPDATE alert_config SET id = '', project_id = '' WHERE id = 'singleton'")


def downgrade() -> None:
    op.execute("UPDATE alert_config SET id = 'singleton' WHERE id = ''")
    op.drop_column("alert_config", "project_id")
    op.drop_index("idx_schema_snapshots_project", table_name="schema_snapshots")
    op.drop_column("schema_snapshots", "project_id")
