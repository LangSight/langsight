"""add_projects_and_members

Revision ID: dc0bf058f21c
Revises: e368ec31ce04
Create Date: 2026-03-19

Adds project isolation tables:
  projects        — top-level grouping for all observability data
  project_members — user memberships with owner/member/viewer roles
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "dc0bf058f21c"
down_revision: str | Sequence[str] | None = "e368ec31ce04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_projects_slug", "projects", ["slug"])

    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
        sa.Column("added_by", sa.Text(), nullable=False),
        sa.Column(
            "added_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_index("idx_project_members_user", "project_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_project_members_user", table_name="project_members")
    op.drop_table("project_members")
    op.drop_index("idx_projects_slug", table_name="projects")
    op.drop_table("projects")
