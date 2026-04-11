"""add_thinking_pricing

Revision ID: d1e2f3a4b5c6
Revises: b3c9e1f2a047
Create Date: 2026-04-11

Adds thinking_per_1m_usd column to model_pricing table for reasoning/thinking
token pricing (Gemini 2.5, o1, o3, etc.).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_pricing",
        sa.Column(
            "thinking_per_1m_usd",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    # Set thinking token pricing for known models
    op.execute(
        "UPDATE model_pricing SET thinking_per_1m_usd = 2.50 WHERE model_id = 'gemini-2.5-flash'"
    )
    op.execute(
        "UPDATE model_pricing SET thinking_per_1m_usd = 10.00 WHERE model_id = 'gemini-2.5-pro'"
    )


def downgrade() -> None:
    op.drop_column("model_pricing", "thinking_per_1m_usd")
