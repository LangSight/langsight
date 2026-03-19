"""add_user_id_to_api_keys

Revision ID: b3c9e1f2a047
Revises: 0eaccc40f932
Create Date: 2026-03-19

Adds user_id column to api_keys so API keys have an owning user.
This closes the key-ID-as-user-ID shim in get_active_project_id and
get_project_access — project membership checks can now use the real user_id
instead of the key record's own id.

Nullable for backwards compatibility with keys created before this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c9e1f2a047"
down_revision: str | Sequence[str] | None = "0eaccc40f932"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("user_id", sa.Text(), nullable=True),
    )
    op.create_index("idx_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_api_keys_user_id", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
