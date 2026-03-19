"""add_model_pricing

Revision ID: 0eaccc40f932
Revises: dc0bf058f21c
Create Date: 2026-03-19

Creates model_pricing table and seeds it with current public pricing for
major LLM providers. Prices are per 1M tokens (industry standard convention).

Update prices when providers change rates:
  alembic revision -m "update_<model>_pricing"
  Then: deactivate old row (set effective_to) + insert new row.
  Never UPDATE existing rows — preserve cost history.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0eaccc40f932"
down_revision: Union[str, Sequence[str], None] = "dc0bf058f21c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Seed data: (provider, model_id, display_name, input_per_1m, output_per_1m, cache_read_per_1m, notes)
# Prices as of 2026-03. Update via new migration when providers change rates.
_SEED: list[tuple[str, str, str, float, float, float, str]] = [
    # Anthropic
    ("anthropic", "claude-opus-4-6",       "Claude Opus 4.6",       15.00, 75.00, 1.50,  "Public pricing 2026-03"),
    ("anthropic", "claude-sonnet-4-6",     "Claude Sonnet 4.6",      3.00, 15.00, 0.30,  "Public pricing 2026-03"),
    ("anthropic", "claude-haiku-4-5-20251001", "Claude Haiku 4.5",   0.80,  4.00, 0.08,  "Public pricing 2026-03"),
    ("anthropic", "claude-opus-4-5",       "Claude Opus 4.5",       15.00, 75.00, 1.50,  "Public pricing 2026-03"),
    ("anthropic", "claude-sonnet-4-5",     "Claude Sonnet 4.5",      3.00, 15.00, 0.30,  "Public pricing 2026-03"),
    # OpenAI
    ("openai",    "gpt-4o",                "GPT-4o",                 2.50, 10.00, 0.00,  "Public pricing 2026-03"),
    ("openai",    "gpt-4o-mini",           "GPT-4o Mini",            0.15,  0.60, 0.00,  "Public pricing 2026-03"),
    ("openai",    "o3",                    "o3",                    10.00, 40.00, 0.00,  "Public pricing 2026-03"),
    ("openai",    "o3-mini",               "o3-mini",                1.10,  4.40, 0.00,  "Public pricing 2026-03"),
    ("openai",    "o1",                    "o1",                    15.00, 60.00, 0.00,  "Public pricing 2026-03"),
    ("openai",    "gpt-4-turbo",           "GPT-4 Turbo",           10.00, 30.00, 0.00,  "Public pricing 2026-03"),
    # Google
    ("google",    "gemini-1.5-pro",        "Gemini 1.5 Pro",         1.25,  5.00, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-1.5-flash",      "Gemini 1.5 Flash",       0.075, 0.30, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-2.0-flash",      "Gemini 2.0 Flash",       0.10,  0.40, 0.00,  "Public pricing 2026-03"),
    ("google",    "gemini-2.5-pro",        "Gemini 2.5 Pro",         1.25,  10.00, 0.00, "Public pricing 2026-03"),
    # Meta / self-hosted (track usage, $0 API cost)
    ("meta",      "llama-3.1-70b",         "Llama 3.1 70B",          0.00,  0.00, 0.00,  "Self-hosted — no API cost"),
    ("meta",      "llama-3.1-8b",          "Llama 3.1 8B",           0.00,  0.00, 0.00,  "Self-hosted — no API cost"),
    ("meta",      "llama-3.3-70b",         "Llama 3.3 70B",          0.00,  0.00, 0.00,  "Self-hosted — no API cost"),
    # AWS Bedrock Nova
    ("aws",       "amazon.nova-pro-v1",    "Amazon Nova Pro",        0.80,  3.20, 0.00,  "Public pricing 2026-03"),
    ("aws",       "amazon.nova-lite-v1",   "Amazon Nova Lite",       0.06,  0.24, 0.00,  "Public pricing 2026-03"),
    ("aws",       "amazon.nova-micro-v1",  "Amazon Nova Micro",      0.035, 0.14, 0.00,  "Public pricing 2026-03"),
]


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("input_per_1m_usd", sa.Double(), nullable=False, server_default="0"),
        sa.Column("output_per_1m_usd", sa.Double(), nullable=False, server_default="0"),
        sa.Column("cache_read_per_1m_usd", sa.Double(), nullable=False, server_default="0"),
        sa.Column("effective_from", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("effective_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_model_pricing_model_id", "model_pricing", ["model_id", "effective_from"]
    )

    # Seed pricing data
    conn = op.get_bind()
    now = datetime.now(UTC)
    for provider, model_id, display_name, inp, out, cache, notes in _SEED:
        conn.execute(
            sa.text(
                "INSERT INTO model_pricing "
                "(id, provider, model_id, display_name, input_per_1m_usd, output_per_1m_usd, "
                "cache_read_per_1m_usd, effective_from, notes, is_custom) "
                "VALUES (:id, :provider, :model_id, :display_name, :inp, :out, :cache, :now, :notes, false)"
            ),
            {
                "id": uuid.uuid4().hex,
                "provider": provider,
                "model_id": model_id,
                "display_name": display_name,
                "inp": inp,
                "out": out,
                "cache": cache,
                "now": now,
                "notes": notes,
            },
        )


def downgrade() -> None:
    op.drop_index("idx_model_pricing_model_id", table_name="model_pricing")
    op.drop_table("model_pricing")
