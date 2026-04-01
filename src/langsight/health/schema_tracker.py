"""Schema drift detection with structural diff and breaking-change classification.

On each health check:
1. Compute a hash of the live tools/list response.
2. Compare against the stored hash for that server.
3. If hashes differ — run the structural differ to classify every change.
4. Emit a SchemaDriftEvent with BREAKING / COMPATIBLE / WARNING labels.
5. Save the event and update the stored snapshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from langsight.models import (
    DriftType,
    SchemaChange,
    SchemaDriftEvent,
    ToolInfo,
)
from langsight.storage.base import StorageBackend

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result returned to checker.py
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaDriftResult:
    """Outcome of a schema drift check for one server."""

    server_name: str
    drifted: bool
    previous_hash: str | None
    current_hash: str
    # Populated only when drifted=True
    changes: list[SchemaChange] = field(default_factory=list)
    has_breaking: bool = False


# ---------------------------------------------------------------------------
# Structural differ
# ---------------------------------------------------------------------------


def _tool_index(tools: list[ToolInfo]) -> dict[str, ToolInfo]:
    return {t.name: t for t in tools}


def classify_drift(
    old_tools: list[ToolInfo],
    new_tools: list[ToolInfo],
) -> list[SchemaChange]:
    """Compare two tool lists and return every atomic schema change.

    Change kinds and their drift types:

    BREAKING:
      tool_removed            — existing tool no longer exists
      required_param_removed  — agent sends it, server now rejects it
      required_param_added    — agent doesn't send it, server now requires it
      param_type_changed      — type mismatch will cause runtime errors

    COMPATIBLE:
      tool_added              — new capability, agents unaffected
      optional_param_added    — agents still work, can start using it

    WARNING:
      description_changed     — possible tool-poisoning vector
    """
    changes: list[SchemaChange] = []
    old_idx = _tool_index(old_tools)
    new_idx = _tool_index(new_tools)

    # --- Tools removed (BREAKING) ---
    for name in old_idx:
        if name not in new_idx:
            changes.append(
                SchemaChange(
                    drift_type=DriftType.BREAKING,
                    kind="tool_removed",
                    tool_name=name,
                )
            )

    # --- Tools added (COMPATIBLE) ---
    for name in new_idx:
        if name not in old_idx:
            changes.append(
                SchemaChange(
                    drift_type=DriftType.COMPATIBLE,
                    kind="tool_added",
                    tool_name=name,
                )
            )

    # --- Per-tool parameter changes ---
    for name, old_tool in old_idx.items():
        new_tool = new_idx.get(name)
        if new_tool is None:
            continue  # already recorded as tool_removed

        old_schema = old_tool.input_schema or {}
        new_schema = new_tool.input_schema or {}

        old_required: set[str] = set(old_schema.get("required", []))
        new_required: set[str] = set(new_schema.get("required", []))
        old_props: dict[str, Any] = old_schema.get("properties", {})
        new_props: dict[str, Any] = new_schema.get("properties", {})

        # Required param removed → BREAKING
        for param in old_required - new_required:
            changes.append(
                SchemaChange(
                    drift_type=DriftType.BREAKING,
                    kind="required_param_removed",
                    tool_name=name,
                    param_name=param,
                )
            )

        # Required param added → BREAKING (agents don't know to send it)
        for param in new_required - old_required:
            changes.append(
                SchemaChange(
                    drift_type=DriftType.BREAKING,
                    kind="required_param_added",
                    tool_name=name,
                    param_name=param,
                )
            )

        # Param type changed → BREAKING
        for param, old_def in old_props.items():
            new_def = new_props.get(param)
            if new_def is None:
                continue  # param removed — covered by required checks above
            old_type = old_def.get("type")
            new_type = new_def.get("type")
            if old_type and new_type and old_type != new_type:
                changes.append(
                    SchemaChange(
                        drift_type=DriftType.BREAKING,
                        kind="param_type_changed",
                        tool_name=name,
                        param_name=param,
                        old_value=old_type,
                        new_value=new_type,
                    )
                )

        # New optional param → COMPATIBLE
        for param in set(new_props) - set(old_props):
            if param not in new_required:
                changes.append(
                    SchemaChange(
                        drift_type=DriftType.COMPATIBLE,
                        kind="optional_param_added",
                        tool_name=name,
                        param_name=param,
                    )
                )

        # Description changed → WARNING (poisoning vector)
        if (old_tool.description or "") != (new_tool.description or ""):
            changes.append(
                SchemaChange(
                    drift_type=DriftType.WARNING,
                    kind="description_changed",
                    tool_name=name,
                    old_value=_truncate(old_tool.description),
                    new_value=_truncate(new_tool.description),
                )
            )

    return changes


def _truncate(s: str | None, max_len: int = 120) -> str | None:
    if s is None:
        return None
    return s if len(s) <= max_len else s[:max_len] + "…"


# ---------------------------------------------------------------------------
# SchemaTracker
# ---------------------------------------------------------------------------


class SchemaTracker:
    """Detects schema drift by comparing current tool schemas against stored snapshots.

    On each health check:
    1. Compare the new hash with the stored hash.
    2. If hashes differ, run structural diff against stored tool definitions.
    3. Classify each change as BREAKING / COMPATIBLE / WARNING.
    4. Persist a SchemaDriftEvent for the API and dashboard.
    5. Update the stored hash + tool snapshot.
    """

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    async def check_and_update(
        self,
        server_name: str,
        current_hash: str,
        tools_count: int,
        current_tools: list[ToolInfo] | None = None,
        project_id: str = "",
    ) -> SchemaDriftResult:
        """Compare current_hash against the stored snapshot.

        Args:
            server_name:   MCP server identifier.
            current_hash:  Hash of the current tools/list response.
            tools_count:   Number of tools in the current response.
            current_tools: Full tool list — required for structural diff.
                           When None, drift is detected but no diff is produced.

        Returns:
            SchemaDriftResult with drift details and classified changes.
        """
        previous_hash = await self._storage.get_latest_schema_hash(server_name, project_id)

        # First run — store baseline, no drift
        if previous_hash is None:
            await self._storage.save_schema_snapshot(
                server_name, current_hash, tools_count, project_id
            )
            if current_tools:
                await self._storage.upsert_server_tools(
                    server_name,
                    [_tool_to_dict(t) for t in current_tools],
                )
            logger.info(
                "schema_tracker.baseline_stored",
                server=server_name,
                hash=current_hash,
                tools=tools_count,
            )
            return SchemaDriftResult(
                server_name=server_name,
                drifted=False,
                previous_hash=None,
                current_hash=current_hash,
            )

        # No change
        if previous_hash == current_hash:
            logger.debug("schema_tracker.no_drift", server=server_name, hash=current_hash)
            return SchemaDriftResult(
                server_name=server_name,
                drifted=False,
                previous_hash=previous_hash,
                current_hash=current_hash,
            )

        # Hash changed — run structural diff
        changes: list[SchemaChange] = []
        if current_tools is not None:
            old_tool_dicts = await self._storage.get_server_tools(server_name)
            old_tools = [_dict_to_tool(d) for d in old_tool_dicts]
            changes = classify_drift(old_tools, current_tools)

        has_breaking = any(c.drift_type == DriftType.BREAKING for c in changes)

        logger.warning(
            "schema_tracker.drift_detected",
            server=server_name,
            previous_hash=previous_hash,
            current_hash=current_hash,
            changes=len(changes),
            has_breaking=has_breaking,
        )

        # Persist drift event
        event = SchemaDriftEvent(
            server_name=server_name,
            changes=changes,
            has_breaking=has_breaking,
            previous_hash=previous_hash,
            current_hash=current_hash,
            detected_at=datetime.now(UTC),
            project_id=project_id,
        )
        save_fn = getattr(self._storage, "save_schema_drift_event", None)
        if save_fn:
            await save_fn(event)

        # Update snapshot
        await self._storage.save_schema_snapshot(server_name, current_hash, tools_count, project_id)
        if current_tools:
            await self._storage.upsert_server_tools(
                server_name,
                [_tool_to_dict(t) for t in current_tools],
            )

        return SchemaDriftResult(
            server_name=server_name,
            drifted=True,
            previous_hash=previous_hash,
            current_hash=current_hash,
            changes=changes,
            has_breaking=has_breaking,
        )


# ---------------------------------------------------------------------------
# Tool serialisation helpers
# ---------------------------------------------------------------------------


def _tool_to_dict(tool: ToolInfo) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema or {},  # dict — upsert_server_tools encodes once
    }


def _dict_to_tool(d: dict[str, Any]) -> ToolInfo:
    schema = d.get("input_schema", {})
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except Exception:  # noqa: BLE001
            schema = {}
    return ToolInfo(
        name=str(d.get("name", "")),
        description=d.get("description") or None,
        input_schema=schema,
    )
