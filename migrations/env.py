"""Alembic migration environment for LangSight PostgreSQL schema.

Connection URL is read from the LANGSIGHT_POSTGRES_URL environment variable.
Falls back to alembic.ini sqlalchemy.url if the env var is not set.

Usage:
    # Apply all pending migrations
    uv run alembic upgrade head

    # Rollback one step
    uv run alembic downgrade -1

    # Generate a new migration (after changing storage/postgres.py DDL)
    uv run alembic revision --autogenerate -m "add X column"

    # Show current revision
    uv run alembic current
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment variable — never hardcode credentials
postgres_url = os.environ.get("LANGSIGHT_POSTGRES_URL")
if postgres_url:
    config.set_main_option("sqlalchemy.url", postgres_url)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
