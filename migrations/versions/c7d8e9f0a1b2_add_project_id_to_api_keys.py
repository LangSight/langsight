"""add_project_id_to_api_keys

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-26

Adds project_id to api_keys so a key can be bound to a specific project.
Implements the "API key = project" pattern: setting LANGSIGHT_API_KEY to a
project-scoped key automatically scopes all CLI health checks, monitor runs,
and API calls to that project without requiring explicit --project-id flags.

Nullable for backwards compatibility with keys created before this migration
(unscoped keys continue to work as global-admin or open-install keys).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("project_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "project_id")
