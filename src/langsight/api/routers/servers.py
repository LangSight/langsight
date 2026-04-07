"""MCP Server catalog API — metadata CRUD, mirroring agents metadata pattern."""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from starlette import status as http_status

from langsight.api.dependencies import get_active_project_id, get_storage, require_admin
from langsight.storage.base import StorageBackend

router = APIRouter(prefix="/servers", tags=["servers"])

# RFC-1918 + loopback + link-local (IMDS) private ranges
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC-1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC-1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC-1918
    ipaddress.ip_network("169.254.0.0/16"),    # link-local / AWS IMDS
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# Blocked hostnames (exact match or suffix match for *.internal)
_BLOCKED_HOSTNAMES = frozenset(["localhost", "metadata.google.internal"])


def _validate_server_url(url: str) -> str:
    """Validate a server URL against SSRF targets.

    Allows empty string (no URL configured yet).
    Raises ValueError on any SSRF risk — Pydantic converts this to HTTP 422.
    """
    if not url:
        return url

    parsed = urlparse(url)

    # Only http/https allowed
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme '{parsed.scheme}' is not allowed; only http and https are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a valid hostname.")

    # Exact hostname blocks and *.internal suffix
    hostname_lower = hostname.lower()
    if hostname_lower in _BLOCKED_HOSTNAMES:
        raise ValueError(
            f"Hostname '{hostname}' is blocked; internal/loopback hostnames are not permitted."
        )
    if hostname_lower.endswith(".internal"):
        raise ValueError(
            f"Hostname '{hostname}' matches blocked pattern '*.internal'."
        )

    # Resolve hostname to IP and check against blocked networks
    try:
        addr = ipaddress.ip_address(hostname)
        addresses = [addr]
    except ValueError:
        # Not a bare IP — resolve DNS
        try:
            resolved = socket.getaddrinfo(hostname, None)
            addresses = [ipaddress.ip_address(r[4][0]) for r in resolved]
        except socket.gaierror:
            # Cannot resolve — allow through; connection will fail at runtime
            addresses = []

    for addr in addresses:
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(
                    f"URL '{url}' resolves to a private or reserved IP address "
                    f"({addr}) and is blocked to prevent SSRF."
                )

    return url


class ServerMetadataUpdate(BaseModel):
    description: str = ""
    owner: str = ""
    tags: list[str] = []
    transport: str = ""
    url: str = ""
    runbook_url: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def validate_url_no_ssrf(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        return _validate_server_url(v)


class ServerMetadataResponse(BaseModel):
    id: str
    server_name: str
    description: str
    owner: str
    tags: list[str]
    transport: str
    url: str = ""
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
        url=body.url,
        runbook_url=body.runbook_url,
        project_id=project_id,
    )
    return _coerce(row)


@router.post(
    "/discover",
    summary="Auto-register servers seen in traces",
    response_model=dict[str, Any],
)
async def discover_servers_from_spans(
    storage: StorageBackend = Depends(get_storage),
    project_id: str | None = Depends(get_active_project_id),
    _admin: None = Depends(require_admin),
) -> dict[str, Any]:
    """Scan recent spans for server_name values and register any that are not
    already in the server catalog.

    Useful after initial SDK instrumentation — run once to populate the
    MCP Servers page from existing trace data without manual registration.
    """
    if not hasattr(storage, "get_distinct_span_server_names"):
        # ClickHouse not available — nothing to discover
        return {"discovered": 0, "servers": []}

    span_servers = await storage.get_distinct_span_server_names(project_id=project_id)

    # Find which ones are not yet in the catalog
    existing = await storage.get_all_server_metadata(project_id=project_id)
    existing_names = {m["server_name"] for m in existing}
    new_servers = span_servers - existing_names

    # Register each new server with basic metadata
    registered = []
    for name in sorted(new_servers):
        await storage.upsert_server_metadata(
            server_name=name,
            description="",
            project_id=project_id,
        )
        registered.append(name)

    return {"discovered": len(registered), "servers": registered}


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
