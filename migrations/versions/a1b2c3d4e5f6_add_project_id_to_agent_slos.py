"""add_project_id_to_agent_slos

Revision ID: a1b2c3d4e5f6
Revises: b3c9e1f2a047
Create Date: 2026-03-23

Adds project_id to agent_slos so SLOs are project-scoped.
Existing rows default to '' (empty string = unscoped / sample project data).
Without this column, all projects share all SLOs — a new project sees
sample-project SLOs bleeding into its overview dashboard.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "b3c9e1f2a047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_slos",
        sa.Column("project_id", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_agent_slos_project", "agent_slos", ["project_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_slos_project", table_name="agent_slos")
    op.drop_column("agent_slos", "project_id")
