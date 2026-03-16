"""
LangSight PostgreSQL MCP Server
Provides tools for querying a PostgreSQL database.
"""

import os
import json
from typing import Any
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from fastmcp import FastMCP

load_dotenv()

# Database connection config
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "langsight_test"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

mcp = FastMCP(
    name="langsight-postgres-mcp",
    instructions="PostgreSQL database MCP server. Use this to query data, list tables, and inspect schemas.",
)


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@mcp.tool()
def query(sql: str, limit: int = 100) -> str:
    """
    Execute a SELECT SQL query and return results as JSON.
    Only SELECT statements are allowed for safety.

    Args:
        sql: The SQL SELECT query to execute
        limit: Maximum number of rows to return (default 100, max 1000)
    """
    sql = sql.strip()
    if not sql.upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed"})

    limit = min(limit, 1000)

    # Append LIMIT if not already present
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {limit}"

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return json.dumps({"rows": [dict(r) for r in rows], "count": len(rows)}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_tables(schema: str = "public") -> str:
    """
    List all tables in the specified schema.

    Args:
        schema: Database schema name (default: public)
    """
    sql = """
        SELECT
            table_name,
            pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size,
            (SELECT COUNT(*) FROM information_schema.columns
             WHERE table_schema = t.table_schema AND table_name = t.table_name) AS column_count
        FROM information_schema.tables t
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, (schema,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return json.dumps({"schema": schema, "tables": [dict(r) for r in rows]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def describe_table(table_name: str, schema: str = "public") -> str:
    """
    Get column definitions, types, and constraints for a table.

    Args:
        table_name: Name of the table to describe
        schema: Database schema name (default: public)
    """
    sql = """
        SELECT
            c.column_name,
            c.data_type,
            c.character_maximum_length,
            c.is_nullable,
            c.column_default,
            CASE WHEN pk.column_name IS NOT NULL THEN 'YES' ELSE 'NO' END AS is_primary_key
        FROM information_schema.columns c
        LEFT JOIN (
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
              ON tc.constraint_name = ku.constraint_name
             AND tc.table_schema = ku.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_name = %s
              AND tc.table_schema = %s
        ) pk ON c.column_name = pk.column_name
        WHERE c.table_name = %s
          AND c.table_schema = %s
        ORDER BY c.ordinal_position
    """
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, (table_name, schema, table_name, schema))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return json.dumps({"error": f"Table '{schema}.{table_name}' not found"})
        return json.dumps({"table": f"{schema}.{table_name}", "columns": [dict(r) for r in rows]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_row_count(table_name: str, schema: str = "public") -> str:
    """
    Get the approximate row count for a table.

    Args:
        table_name: Name of the table
        schema: Database schema name (default: public)
    """
    sql = """
        SELECT reltuples::BIGINT AS estimated_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s AND n.nspname = %s
    """
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, (table_name, schema))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return json.dumps({"error": f"Table '{schema}.{table_name}' not found"})
        return json.dumps({"table": f"{schema}.{table_name}", "estimated_row_count": row["estimated_count"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_schema_summary() -> str:
    """
    Get a high-level summary of the entire database: schemas, tables, and row counts.
    """
    sql = """
        SELECT
            t.table_schema,
            t.table_name,
            reltuples::BIGINT AS estimated_rows
        FROM information_schema.tables t
        JOIN pg_class c ON c.relname = t.table_name
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema
        WHERE t.table_type = 'BASE TABLE'
          AND t.table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY t.table_schema, t.table_name
    """
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        db_name = DB_CONFIG["database"]
        return json.dumps({
            "database": db_name,
            "tables": [dict(r) for r in rows],
            "total_tables": len(rows)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
