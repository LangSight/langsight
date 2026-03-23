"""MCP Server catalog API — metadata CRUD, mirroring agents metadata pattern."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette import status as http_status

from langsight.api.dependencies import get_active_project_id, get_storage, require_admin
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/servers", tags=["servers"])


class ServerMetadataUpdate(BaseModel):
    description: str = ""
    owner: str = ""
    tags: list[str] = []
    transport: str = ""
    runbook_url: str = ""


class ServerMetadataResponse(BaseModel):
    id: str
    server_name: str
    description: str
    owner: str
    tags: list[str]
    transport: str
    runbook_url: str
    project_id: str | None
    created_at: str
    updated_at: str


def _coerce(row: dict[str, Any]) -> dict[str, Any]:
    row["created_at"] = str(row["created_at"])
    row["updated_at"] = str(row["updated_at"])
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"])
    return row


@router.get("/metadata", response_model=list[ServerMetadataResponse])
async def list_server_metadata(
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    rows = await storage.get_all_server_metadata(project_id=project_id)
    return [_coerce(r) for r in rows]


@router.get("/metadata/{server_name}", response_model=ServerMetadataResponse)
async def get_server_metadata(
    server_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, Any]:
    row = await storage.get_server_metadata(server_name, project_id=project_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"No metadata for server '{server_name}'")
    return _coerce(row)


@router.put(
    "/metadata/{server_name}",
    response_model=ServerMetadataResponse,
    status_code=http_status.HTTP_200_OK,
)
async def upsert_server_metadata(
    server_name: str,
    body: ServerMetadataUpdate,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    row = await storage.upsert_server_metadata(
        server_name=server_name,
        description=body.description,
        owner=body.owner,
        tags=body.tags,
        transport=body.transport,
        runbook_url=body.runbook_url,
        project_id=project_id,
    )
    return _coerce(row)


@router.delete("/metadata/{server_name}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_server_metadata(
    server_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
    _admin: None = Depends(require_admin),
) -> None:
    """Delete server metadata scoped to the active project."""
    deleted = await storage.delete_server_metadata(server_name, project_id=project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No metadata for server '{server_name}'")


# ── Tool schema capture (from SDK list_tools() interception) ─────────────────


class ToolSchemaPayload(BaseModel):
    tools: list[dict[str, Any]]
    project_id: str | None = None


class ToolSchemaEntry(BaseModel):
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    first_seen_at: str
    last_seen_at: str


@router.post("/{server_name}/tools", status_code=http_status.HTTP_200_OK)
async def record_tool_schemas(
    server_name: str,
    body: ToolSchemaPayload,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> dict[str, int]:
    """Called by the SDK whenever list_tools() is invoked.
    Upserts tool names, descriptions and input schemas for the server.
    project_id comes from the authenticated request context, not the body.
    """
    if not body.tools:
        return {"upserted": 0}
    await storage.upsert_server_tools(server_name, body.tools, project_id=project_id)
    return {"upserted": len(body.tools)}


@router.get("/{server_name}/tools", response_model=list[ToolSchemaEntry])
async def get_tool_schemas(
    server_name: str,
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
) -> list[dict[str, Any]]:
    """Return declared tools for a server scoped to the active project."""
    rows = await storage.get_server_tools(server_name, project_id=project_id)
    for r in rows:
        r["first_seen_at"] = str(r["first_seen_at"])
        r["last_seen_at"] = str(r["last_seen_at"])
        if isinstance(r.get("input_schema"), str):
            r["input_schema"] = json.loads(str(r["input_schema"]))
        r.setdefault("server_name", server_name)
    return rows
