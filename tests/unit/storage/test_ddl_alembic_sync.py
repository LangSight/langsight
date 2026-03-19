"""Detect drift between inline DDL in postgres.py and Alembic migrations.

LangSight has schema defined in two places:

1. ``_DDL_STATEMENTS`` in ``src/langsight/storage/postgres.py`` — used for fresh
   installs and CI (``CREATE TABLE IF NOT EXISTS``).
2. Alembic migrations in ``migrations/versions/`` — used for production DB
   upgrades (``op.create_table``, ``op.add_column``, ``op.drop_column``, etc.).

When a migration adds or drops a column, the inline DDL must be updated in the
same commit. This test catches that drift automatically — no running database
required.

Approach:
  - Parse ``CREATE TABLE`` blocks from ``_DDL_STATEMENTS`` via regex.
  - Walk the Alembic migration chain (oldest-first) and replay
    ``create_table`` / ``add_column`` / ``drop_column`` / ``drop_table`` calls
    to build the expected final schema.
  - Compare the two column sets per table and fail with a clear diff.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_POSTGRES_PY = _PROJECT_ROOT / "src" / "langsight" / "storage" / "postgres.py"
_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations" / "versions"


# ---------------------------------------------------------------------------
# 1. Parse inline DDL from postgres.py
# ---------------------------------------------------------------------------

def _split_ignoring_parens(text: str) -> list[str]:
    """Split *text* on commas that are not nested inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _parse_ddl_tables(ddl_statements: list[str]) -> dict[str, set[str]]:
    """Extract {table_name: {col1, col2, ...}} from CREATE TABLE statements.

    Only considers ``CREATE TABLE`` DDL — index statements are ignored.
    Composite PRIMARY KEY lines and constraint clauses are skipped.
    """
    table_re = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.+)\)\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    tables: dict[str, set[str]] = {}

    for stmt in ddl_statements:
        stmt = stmt.strip()
        m = table_re.search(stmt)
        if not m:
            continue
        table_name = m.group(1).lower()
        body = m.group(2)

        # Split on commas that are NOT inside parentheses.
        # This avoids splitting "PRIMARY KEY (col_a, col_b)" into fragments.
        parts = _split_ignoring_parens(body)

        columns: set[str] = set()
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Skip pure constraints (PRIMARY KEY (...), UNIQUE (...), etc.)
            upper = part.upper()
            if upper.startswith(("PRIMARY KEY", "UNIQUE ", "UNIQUE(", "FOREIGN KEY", "CHECK ", "CHECK(", "CONSTRAINT")):
                continue
            # First token is the column name
            token = part.split()[0].strip()
            # Skip if it looks like a keyword rather than a column name
            if token.upper() in {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}:
                continue
            columns.add(token.lower())

        tables[table_name] = columns

    return tables


def _load_ddl_statements() -> list[str]:
    """Import _DDL_STATEMENTS from postgres.py without importing asyncpg.

    We read the source file and use AST to extract the list literal so we
    don't need any runtime dependencies (asyncpg, structlog, etc.).
    """
    source = _POSTGRES_PY.read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_DDL_STATEMENTS":
                    # Evaluate the list of string literals safely
                    return ast.literal_eval(node.value)

    raise RuntimeError("Could not find _DDL_STATEMENTS in postgres.py")


# ---------------------------------------------------------------------------
# 2. Parse Alembic migrations
# ---------------------------------------------------------------------------

def _parse_migration_file(path: Path) -> dict[str, Any]:
    """Parse a single Alembic migration file and return structured metadata.

    Returns:
        {
            "revision": str,
            "down_revision": str | None,
            "create_tables": {table_name: {col1, col2, ...}},
            "drop_tables": [table_name, ...],
            "add_columns": {table_name: {col1, col2, ...}},
            "drop_columns": {table_name: {col1, col2, ...}},
        }
    """
    source = path.read_text()
    tree = ast.parse(source)

    result: dict[str, Any] = {
        "revision": None,
        "down_revision": None,
        "create_tables": {},
        "drop_tables": [],
        "add_columns": {},
        "drop_columns": {},
    }

    # Extract revision and down_revision from module-level assignments.
    # Alembic files use annotated assignments (e.g. ``revision: str = "abc"``),
    # which are ast.AnnAssign nodes — not ast.Assign.
    for node in ast.iter_child_nodes(tree):
        name: str | None = None
        value_node: ast.expr | None = None

        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value_node = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    value_node = node.value

        if name == "revision" and value_node is not None:
            result["revision"] = ast.literal_eval(value_node)
        elif name == "down_revision" and value_node is not None:
            val = ast.literal_eval(value_node)
            result["down_revision"] = val

    # Find the upgrade() function and parse op.* calls
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            _parse_upgrade_body(node, result)

    return result


def _parse_upgrade_body(func_node: ast.FunctionDef, result: dict[str, Any]) -> None:
    """Walk upgrade() body and extract op.create_table / add_column / drop_column."""
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue

        # Match op.xxx(...)
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "op"):
            continue

        method = func.attr

        if method == "create_table":
            _handle_create_table(node, result)
        elif method == "add_column":
            _handle_add_column(node, result)
        elif method == "drop_column":
            _handle_drop_column(node, result)
        elif method == "drop_table":
            _handle_drop_table(node, result)


def _handle_create_table(call: ast.Call, result: dict[str, Any]) -> None:
    """Extract table name and column names from op.create_table(...)."""
    if not call.args:
        return
    table_name = ast.literal_eval(call.args[0]).lower()
    columns: set[str] = set()

    # Remaining positional args are sa.Column(...) or sa.*Constraint(...)
    for arg in call.args[1:]:
        col_name = _extract_column_name(arg)
        if col_name:
            columns.add(col_name.lower())

    result["create_tables"][table_name] = columns


def _extract_column_name(node: ast.expr) -> str | None:
    """Extract column name from a sa.Column("name", ...) AST node.

    Returns None for non-Column nodes (constraints, etc.).
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    # Match sa.Column(...)
    if isinstance(func, ast.Attribute) and func.attr == "Column":
        if node.args:
            try:
                return ast.literal_eval(node.args[0])
            except (ValueError, TypeError):
                return None
    return None


def _handle_add_column(call: ast.Call, result: dict[str, Any]) -> None:
    """Extract table + column from op.add_column("table", sa.Column("col", ...))."""
    if len(call.args) < 2:
        return
    table_name = ast.literal_eval(call.args[0]).lower()
    col_name = _extract_column_name(call.args[1])
    if col_name:
        result["add_columns"].setdefault(table_name, set()).add(col_name.lower())


def _handle_drop_column(call: ast.Call, result: dict[str, Any]) -> None:
    """Extract table + column from op.drop_column("table", "col")."""
    if len(call.args) < 2:
        return
    table_name = ast.literal_eval(call.args[0]).lower()
    col_name = ast.literal_eval(call.args[1]).lower()
    result["drop_columns"].setdefault(table_name, set()).add(col_name)


def _handle_drop_table(call: ast.Call, result: dict[str, Any]) -> None:
    """Extract table name from op.drop_table("table")."""
    if not call.args:
        return
    table_name = ast.literal_eval(call.args[0]).lower()
    result["drop_tables"].append(table_name)


def _build_migration_chain() -> list[dict[str, Any]]:
    """Read all migration files and return them in chain order (oldest first)."""
    if not _MIGRATIONS_DIR.exists():
        return []

    migrations: dict[str, dict[str, Any]] = {}
    for path in _MIGRATIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        parsed = _parse_migration_file(path)
        rev = parsed["revision"]
        if rev:
            migrations[rev] = parsed

    # Build ordered chain by following down_revision links
    # Find the root (down_revision is None)
    roots = [m for m in migrations.values() if m["down_revision"] is None]
    if not roots:
        return []

    chain: list[dict[str, Any]] = []
    current = roots[0]
    visited: set[str] = set()

    while current:
        rev = current["revision"]
        if rev in visited:
            break  # safety: avoid infinite loops on broken chains
        visited.add(rev)
        chain.append(current)
        # Find next migration whose down_revision points to current
        next_mig = None
        for m in migrations.values():
            if m["down_revision"] == rev:
                next_mig = m
                break
        current = next_mig

    return chain


def _replay_migrations(chain: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Replay the migration chain and return the final {table: {columns}} state."""
    tables: dict[str, set[str]] = {}

    for mig in chain:
        # create_table
        for table_name, columns in mig["create_tables"].items():
            tables[table_name] = set(columns)

        # add_column
        for table_name, columns in mig["add_columns"].items():
            if table_name in tables:
                tables[table_name].update(columns)

        # drop_column
        for table_name, columns in mig["drop_columns"].items():
            if table_name in tables:
                tables[table_name] -= columns

        # drop_table
        for table_name in mig["drop_tables"]:
            tables.pop(table_name, None)

    return tables


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDDLAlembicSync:
    """Ensure inline DDL in postgres.py stays in sync with Alembic migrations."""

    @pytest.fixture(scope="class")
    def ddl_tables(self) -> dict[str, set[str]]:
        ddl_statements = _load_ddl_statements()
        return _parse_ddl_tables(ddl_statements)

    @pytest.fixture(scope="class")
    def migration_tables(self) -> dict[str, set[str]]:
        chain = _build_migration_chain()
        return _replay_migrations(chain)

    @pytest.fixture(scope="class")
    def shared_table_names(
        self,
        ddl_tables: dict[str, set[str]],
        migration_tables: dict[str, set[str]],
    ) -> set[str]:
        """Tables that exist in both DDL and migrations (the overlap we verify)."""
        return set(ddl_tables.keys()) & set(migration_tables.keys())

    # ── Core drift test ────────────────────────────────────────────────────

    def test_columns_match_for_all_shared_tables(
        self,
        ddl_tables: dict[str, set[str]],
        migration_tables: dict[str, set[str]],
        shared_table_names: set[str],
    ) -> None:
        """Every table present in both sources must have identical columns."""
        mismatches: list[str] = []

        for table in sorted(shared_table_names):
            ddl_cols = ddl_tables[table]
            mig_cols = migration_tables[table]

            only_in_ddl = ddl_cols - mig_cols
            only_in_migrations = mig_cols - ddl_cols

            if only_in_ddl or only_in_migrations:
                parts = [f"\n  Table: {table}"]
                if only_in_ddl:
                    parts.append(f"    In DDL but NOT in migrations: {sorted(only_in_ddl)}")
                if only_in_migrations:
                    parts.append(f"    In migrations but NOT in DDL: {sorted(only_in_migrations)}")
                mismatches.append("\n".join(parts))

        assert not mismatches, (
            "DDL/migration column drift detected! "
            "Update _DDL_STATEMENTS in postgres.py to match migrations "
            "(or vice versa):\n" + "\n".join(mismatches)
        )

    # ── Migration-added columns must appear in DDL ─────────────────────────

    def test_migration_added_columns_present_in_ddl(
        self,
        ddl_tables: dict[str, set[str]],
    ) -> None:
        """Every column added by op.add_column in a migration must exist in the DDL."""
        chain = _build_migration_chain()
        missing: list[str] = []

        for mig in chain:
            for table_name, columns in mig["add_columns"].items():
                if table_name not in ddl_tables:
                    # Table itself might be DDL-only or migration-only;
                    # the shared-tables test covers that separately.
                    continue
                for col in sorted(columns):
                    if col not in ddl_tables[table_name]:
                        missing.append(
                            f"  Migration {mig['revision']}: "
                            f"op.add_column('{table_name}', Column('{col}')) "
                            f"-- missing from _DDL_STATEMENTS"
                        )

        assert not missing, (
            "Columns added by migrations are missing from inline DDL:\n"
            + "\n".join(missing)
        )

    # ── Migration-dropped columns must be absent from DDL ──────────────────

    def test_migration_dropped_columns_absent_from_ddl(
        self,
        ddl_tables: dict[str, set[str]],
    ) -> None:
        """Every column removed by op.drop_column must NOT exist in the DDL."""
        chain = _build_migration_chain()
        stale: list[str] = []

        for mig in chain:
            for table_name, columns in mig["drop_columns"].items():
                if table_name not in ddl_tables:
                    continue
                for col in sorted(columns):
                    if col in ddl_tables[table_name]:
                        stale.append(
                            f"  Migration {mig['revision']}: "
                            f"op.drop_column('{table_name}', '{col}') "
                            f"-- still present in _DDL_STATEMENTS"
                        )

        assert not stale, (
            "Columns dropped by migrations are still in inline DDL:\n"
            + "\n".join(stale)
        )

    # ── Structural sanity checks ───────────────────────────────────────────

    def test_ddl_has_tables(self, ddl_tables: dict[str, set[str]]) -> None:
        """Sanity: the DDL parser found at least one table."""
        assert len(ddl_tables) > 0, "_DDL_STATEMENTS contains no CREATE TABLE statements"

    def test_migrations_have_tables(self, migration_tables: dict[str, set[str]]) -> None:
        """Sanity: the migration parser found at least one table."""
        assert len(migration_tables) > 0, "No tables found after replaying migrations"

    def test_migration_chain_is_contiguous(self) -> None:
        """Sanity: the migration chain has no gaps or orphans."""
        if not _MIGRATIONS_DIR.exists():
            pytest.skip("No migrations directory")

        all_files = [p for p in _MIGRATIONS_DIR.glob("*.py") if p.name != "__init__.py"]
        chain = _build_migration_chain()

        assert len(chain) == len(all_files), (
            f"Migration chain has {len(chain)} entries but there are "
            f"{len(all_files)} migration files — possible orphan or broken link"
        )

    def test_ddl_tables_are_superset_of_migration_tables(
        self,
        ddl_tables: dict[str, set[str]],
        migration_tables: dict[str, set[str]],
    ) -> None:
        """DDL should contain all tables from migrations.

        The DDL may have extra tables (e.g. added inline before a migration was
        written), but every migration-created table must appear in the DDL.
        """
        only_in_migrations = set(migration_tables.keys()) - set(ddl_tables.keys())
        assert not only_in_migrations, (
            f"Tables created by migrations but missing from _DDL_STATEMENTS: "
            f"{sorted(only_in_migrations)}"
        )


# ---------------------------------------------------------------------------
# Parser unit tests — validate that our regex/AST helpers work correctly
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDDLParser:
    """Verify the DDL regex parser against known patterns."""

    def test_simple_create_table(self) -> None:
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS foo (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age  INTEGER
            )
            """
        ]
        tables = _parse_ddl_tables(ddl)
        assert "foo" in tables
        assert tables["foo"] == {"id", "name", "age"}

    def test_composite_primary_key_is_skipped(self) -> None:
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS bar (
                project_id TEXT NOT NULL,
                user_id    TEXT NOT NULL,
                role       TEXT NOT NULL,
                PRIMARY KEY (project_id, user_id)
            )
            """
        ]
        tables = _parse_ddl_tables(ddl)
        assert tables["bar"] == {"project_id", "user_id", "role"}

    def test_index_statement_is_ignored(self) -> None:
        ddl = [
            "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY)",
            "CREATE INDEX IF NOT EXISTS idx_t_id ON t (id)",
        ]
        tables = _parse_ddl_tables(ddl)
        assert "t" in tables
        assert len(tables) == 1  # only the table, not the index

    def test_last_column_before_closing_paren(self) -> None:
        """The last column (no trailing comma) must be captured."""
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS t (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                last_col TIMESTAMPTZ NOT NULL
            )
            """
        ]
        tables = _parse_ddl_tables(ddl)
        assert "last_col" in tables["t"], (
            f"Last column missing. Found: {sorted(tables['t'])}"
        )

    def test_health_results_has_checked_at(self) -> None:
        """Regression: column names starting with 'check' must not be
        confused with CHECK constraints (e.g. checked_at)."""
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS health_results (
                id         SERIAL PRIMARY KEY,
                error      TEXT,
                checked_at TIMESTAMPTZ NOT NULL
            )
            """
        ]
        tables = _parse_ddl_tables(ddl)
        assert "checked_at" in tables["health_results"]

    def test_empty_list_returns_empty(self) -> None:
        assert _parse_ddl_tables([]) == {}


@pytest.mark.unit
class TestMigrationParser:
    """Verify migration AST parser against known migration file patterns."""

    def test_chain_starts_from_initial(self) -> None:
        chain = _build_migration_chain()
        if not chain:
            pytest.skip("No migrations found")
        assert chain[0]["down_revision"] is None, "First migration should have no parent"

    def test_each_migration_has_revision(self) -> None:
        chain = _build_migration_chain()
        for mig in chain:
            assert mig["revision"] is not None, f"Migration missing revision: {mig}"

    def test_add_column_detected(self) -> None:
        """The user_id addition to api_keys should be detected."""
        chain = _build_migration_chain()
        found = False
        for mig in chain:
            if "api_keys" in mig["add_columns"] and "user_id" in mig["add_columns"]["api_keys"]:
                found = True
                break
        assert found, "op.add_column('api_keys', Column('user_id')) not detected in any migration"
