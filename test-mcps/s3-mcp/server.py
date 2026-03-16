from __future__ import annotations

import fnmatch
import os
from contextlib import asynccontextmanager
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_MAX_ITEMS = 100
MAX_MAX_ITEMS = 1_000
DEFAULT_MAX_BYTES = 10_240  # 10 KB

# Module-level client — initialised in lifespan
_s3: Any = None  # boto3.client("s3")

# ---------------------------------------------------------------------------
# Lifespan — boto3 session
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(server: FastMCP):  # noqa: ARG001
    global _s3
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    _s3 = session.client("s3")
    try:
        yield
    finally:
        _s3 = None


mcp = FastMCP(
    "s3-mcp",
    instructions=(
        "AWS S3 MCP server for LangSight testing. "
        "Provides bucket listing, object browsing, read, write, delete, and search tools. "
        "Credentials are read from environment variables."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client() -> Any:
    if _s3 is None:
        raise RuntimeError("S3 client is not initialised.")
    return _s3


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def _raise_aws_error(exc: Exception, operation: str) -> None:
    """Translate boto3 errors into actionable RuntimeError messages."""
    if isinstance(exc, ClientError):
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        raise RuntimeError(
            f"S3 error during {operation}: [{code}] {msg}"
        ) from exc
    raise RuntimeError(f"Unexpected error during {operation}: {exc}") from exc


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_buckets() -> list[dict[str, Any]]:
    """List all S3 buckets accessible with the configured credentials."""
    try:
        response = _client().list_buckets()
        return [
            {
                "name": b["Name"],
                "created_at": b["CreationDate"].isoformat(),
            }
            for b in response.get("Buckets", [])
        ]
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, "list_buckets")


@mcp.tool()
async def list_objects(
    bucket: str,
    prefix: str = "",
    max_items: int = DEFAULT_MAX_ITEMS,
) -> list[dict[str, Any]]:
    """List objects in an S3 bucket with optional prefix filtering.

    Args:
        bucket: S3 bucket name.
        prefix: Key prefix to filter results (e.g. 'logs/2026/').
        max_items: Maximum number of objects to return (1–1000, default 100).
    """
    max_items = _clamp(max_items, 1, MAX_MAX_ITEMS)
    try:
        paginator = _client().get_paginator("list_objects_v2")
        objects: list[dict[str, Any]] = []
        for page in paginator.paginate(
            Bucket=bucket,
            Prefix=prefix,
            PaginationConfig={"MaxItems": max_items},
        ):
            for obj in page.get("Contents", []):
                objects.append(
                    {
                        "key": obj["Key"],
                        "size_bytes": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                        "storage_class": obj.get("StorageClass", "STANDARD"),
                    }
                )
        return objects
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"list_objects(bucket={bucket!r})")


@mcp.tool()
async def get_object_metadata(bucket: str, key: str) -> dict[str, Any]:
    """Get metadata for an S3 object without downloading its content.

    Args:
        bucket: S3 bucket name.
        key: Object key (full path, e.g. 'data/report.csv').
    """
    try:
        resp = _client().head_object(Bucket=bucket, Key=key)
        return {
            "bucket": bucket,
            "key": key,
            "size_bytes": resp["ContentLength"],
            "last_modified": resp["LastModified"].isoformat(),
            "content_type": resp.get("ContentType", "application/octet-stream"),
            "etag": resp.get("ETag", "").strip('"'),
            "metadata": resp.get("Metadata", {}),
        }
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"get_object_metadata({bucket}/{key})")


@mcp.tool()
async def read_object(
    bucket: str,
    key: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Read the content of a text S3 object.

    Args:
        bucket: S3 bucket name.
        key: Object key to read.
        max_bytes: Maximum bytes to retrieve (default 10 KB). Larger objects
                   are truncated — check the 'truncated' flag in the response.
    """
    try:
        resp = _client().get_object(
            Bucket=bucket,
            Key=key,
            Range=f"bytes=0-{max_bytes - 1}",
        )
        raw = resp["Body"].read()
        total_size_str = resp.get("ContentRange", "").split("/")[-1]

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Object '{key}' is not a UTF-8 text file. "
                "Use get_object_metadata() to inspect its content type."
            ) from exc

        return {
            "bucket": bucket,
            "key": key,
            "content": text,
            "bytes_read": len(raw),
            "total_size_bytes": int(total_size_str) if total_size_str.isdigit() else None,
            "truncated": len(raw) >= max_bytes,
        }
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"read_object({bucket}/{key})")


@mcp.tool()
async def put_object(
    bucket: str,
    key: str,
    content: str,
    content_type: str = "text/plain",
) -> dict[str, str]:
    """Upload text content to an S3 object.

    Args:
        bucket: S3 bucket name.
        key: Destination object key (e.g. 'uploads/report.txt').
        content: UTF-8 text content to upload.
        content_type: MIME type (default: text/plain).
    """
    try:
        resp = _client().put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
        return {
            "bucket": bucket,
            "key": key,
            "etag": resp.get("ETag", "").strip('"'),
            "status": "uploaded",
        }
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"put_object({bucket}/{key})")


@mcp.tool()
async def delete_object(bucket: str, key: str) -> dict[str, str]:
    """Delete an object from S3.

    Args:
        bucket: S3 bucket name.
        key: Object key to delete.
    """
    try:
        _client().delete_object(Bucket=bucket, Key=key)
        return {"bucket": bucket, "key": key, "status": "deleted"}
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"delete_object({bucket}/{key})")


@mcp.tool()
async def search_objects(
    bucket: str,
    pattern: str,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """Search for S3 objects whose keys match a glob pattern.

    Args:
        bucket: S3 bucket name.
        pattern: Glob pattern to match against object keys
                 (e.g. '*.json', 'logs/2026-*.csv').
        prefix: Key prefix to narrow the search scope before pattern matching.
    """
    try:
        paginator = _client().get_paginator("list_objects_v2")
        matches: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if fnmatch.fnmatch(obj["Key"], pattern):
                    matches.append(
                        {
                            "key": obj["Key"],
                            "size_bytes": obj["Size"],
                            "last_modified": obj["LastModified"].isoformat(),
                        }
                    )
        return matches
    except (BotoCoreError, ClientError) as exc:
        _raise_aws_error(exc, f"search_objects({bucket}, pattern={pattern!r})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
