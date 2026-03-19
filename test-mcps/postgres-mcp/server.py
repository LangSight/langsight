from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_POSTGRES_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'langsight_test')}"
)

MAX_QUERY_LIMIT = 1000
DEFAULT_QUERY_LIMIT = 100

# Module-level pool — initialised in lifespan, used by all tools
_pool: asyncpg.Pool | None = None

# ---------------------------------------------------------------------------
# Lifespan — connection pool
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(server: FastMCP):  # noqa: ARG001
    global _pool
    _pool = await asyncpg.create_pool(_POSTGRES_DSN, min_size=2, max_size=10)
    try:
        yield
    finally:
        await _pool.close()
        _pool = None


mcp = FastMCP(
    "postgres-mcp",
    instructions=(
        "PostgreSQL MCP server for LangSight testing. "
        "Provides read-only query and schema-inspection tools for a sample e-commerce database. "
        "Only SELECT, WITH, and EXPLAIN statements are permitted."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------
_ALLOWED_STMT = re.compile(r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)


def _require_select_only(sql: str) -> None:
    """Raise ValueError if sql is not a read-only statement."""
    if not _ALLOWED_STMT.match(sql):
        raise ValueError(
            f"Only SELECT, WITH, and EXPLAIN statements are allowed. "
            f"Received: {sql[:60]!r}"
        )


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised.")
    return _pool


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def query(sql: str, limit: int = DEFAULT_QUERY_LIMIT) -> list[dict[str, Any]]:
    """Execute a read-only SQL query and return results as a list of row dicts.

    Args:
        sql: SQL SELECT (or WITH/EXPLAIN) query to execute. Mutating statements
             are rejected.
        limit: Maximum number of rows to return (1–1000, default 100). A LIMIT
               clause is appended automatically when the query has none.
    """
    _require_select_only(sql)
    limit = _clamp(limit, 1, MAX_QUERY_LIMIT)

    normalized = sql.rstrip().rstrip(";")
    if not re.search(r"\bLIMIT\b", normalized, re.IGNORECASE):
        normalized = f"{normalized} LIMIT {limit}"

    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(normalized)

    return [dict(row) for row in rows]


@mcp.tool()
async def list_tables(schema: str = "public") -> list[dict[str, Any]]:
    """List all user tables in a schema with their live row-count estimates.

    Args:
        schema: PostgreSQL schema name (default: public).
    """
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                t.table_name,
                t.table_type,
                COALESCE(s.n_live_tup::text, '0') AS estimated_rows
            FROM information_schema.tables t
            LEFT JOIN pg_stat_user_tables s
                ON s.schemaname = t.table_schema
               AND s.relname     = t.table_name
            WHERE t.table_schema = $1
            ORDER BY t.table_name
            """,
            schema,
        )
    return [dict(row) for row in rows]


@mcp.tool()
async def describe_table(
    table_name: str,
    schema: str = "public",
) -> list[dict[str, Any]]:
    """Return column definitions for a table: name, type, nullability, default.

    Args:
        table_name: Name of the table to describe.
        schema: PostgreSQL schema name (default: public).
    """
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = $1
              AND table_name   = $2
            ORDER BY ordinal_position
            """,
            schema,
            table_name,
        )

    if not rows:
        raise ValueError(
            f"Table '{schema}.{table_name}' not found. "
            "Use list_tables() to see available tables."
        )

    return [dict(row) for row in rows]


@mcp.tool()
async def get_row_count(
    table_name: str,
    schema: str = "public",
) -> dict[str, Any]:
    """Return the exact and estimated row count for a table.

    Args:
        table_name: Name of the table.
        schema: PostgreSQL schema name (default: public).
    """
    async with _get_pool().acquire() as conn:
        # Validate table exists before building dynamic query
        exists = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = $1 AND table_name = $2
            """,
            schema,
            table_name,
        )
        if not exists:
            raise ValueError(
                f"Table '{schema}.{table_name}' not found. "
                "Use list_tables() to see available tables."
            )

        # Fast stats estimate
        estimate_row = await conn.fetchrow(
            """
            SELECT n_live_tup AS estimate
            FROM pg_stat_user_tables
            WHERE schemaname = $1 AND relname = $2
            """,
            schema,
            table_name,
        )

        # Exact count — safe: name validated above, quoted to handle edge cases
        exact = await conn.fetchval(
            f'SELECT COUNT(*) FROM "{schema}"."{table_name}"'
        )

    return {
        "table": f"{schema}.{table_name}",
        "exact_count": exact,
        "estimated_count": estimate_row["estimate"] if estimate_row else None,
    }


@mcp.tool()
async def get_schema_summary() -> list[dict[str, Any]]:
    """Return a summary of all user schemas, tables, and row-count estimates.

    Excludes PostgreSQL internal schemas (pg_catalog, information_schema).
    """
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                t.table_schema,
                t.table_name,
                t.table_type,
                COALESCE(s.n_live_tup, 0) AS estimated_rows
            FROM information_schema.tables t
            LEFT JOIN pg_stat_user_tables s
                ON s.schemaname = t.table_schema
               AND s.relname     = t.table_name
            WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY t.table_schema, t.table_name
            """
        )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
