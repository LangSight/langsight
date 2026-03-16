"""
LangSight AWS S3 MCP Server
Provides tools for interacting with AWS S3 buckets and objects.
"""

import os
import json
from typing import Optional
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastmcp import FastMCP

load_dotenv()

# S3 client config
def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "eu-west-1"),
    )

mcp = FastMCP(
    name="langsight-s3-mcp",
    instructions="AWS S3 MCP server. Use this to list buckets, browse objects, read files, and upload content to S3.",
)


@mcp.tool()
def list_buckets() -> str:
    """
    List all S3 buckets accessible with the configured credentials.
    Returns bucket names, creation dates, and regions.
    """
    try:
        s3 = get_s3_client()
        response = s3.list_buckets()
        buckets = [
            {
                "name": b["Name"],
                "created_at": b["CreationDate"].isoformat(),
            }
            for b in response.get("Buckets", [])
        ]
        return json.dumps({"buckets": buckets, "count": len(buckets)})
    except NoCredentialsError:
        return json.dumps({"error": "AWS credentials not configured. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY."})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_objects(bucket: str, prefix: str = "", max_items: int = 100) -> str:
    """
    List objects in an S3 bucket, optionally filtered by prefix (folder path).

    Args:
        bucket: S3 bucket name
        prefix: Optional folder prefix to filter results (e.g. 'data/2026/')
        max_items: Maximum number of objects to return (default 100, max 1000)
    """
    max_items = min(max_items, 1000)
    try:
        s3 = get_s3_client()
        kwargs = {"Bucket": bucket, "MaxKeys": max_items}
        if prefix:
            kwargs["Prefix"] = prefix

        response = s3.list_objects_v2(**kwargs)
        objects = [
            {
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
                "storage_class": obj.get("StorageClass", "STANDARD"),
            }
            for obj in response.get("Contents", [])
        ]
        return json.dumps({
            "bucket": bucket,
            "prefix": prefix,
            "objects": objects,
            "count": len(objects),
            "is_truncated": response.get("IsTruncated", False),
        })
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_object_metadata(bucket: str, key: str) -> str:
    """
    Get metadata for an S3 object without downloading its content.
    Returns size, content type, last modified, ETag, and custom metadata.

    Args:
        bucket: S3 bucket name
        key: Object key (full path)
    """
    try:
        s3 = get_s3_client()
        response = s3.head_object(Bucket=bucket, Key=key)
        return json.dumps({
            "bucket": bucket,
            "key": key,
            "size_bytes": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "last_modified": response["LastModified"].isoformat(),
            "etag": response.get("ETag", "").strip('"'),
            "metadata": response.get("Metadata", {}),
            "storage_class": response.get("StorageClass", "STANDARD"),
        })
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def read_object(bucket: str, key: str, max_bytes: int = 10000) -> str:
    """
    Read the content of an S3 object.
    For text files (JSON, CSV, TXT, MD, YAML): returns decoded content.
    For binary files: returns metadata only with a note.

    Args:
        bucket: S3 bucket name
        key: Object key (full path)
        max_bytes: Maximum bytes to read (default 10KB, max 1MB)
    """
    max_bytes = min(max_bytes, 1_000_000)
    text_extensions = {".json", ".csv", ".txt", ".md", ".yaml", ".yml", ".log", ".sql", ".py", ".js", ".ts"}

    file_ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""

    try:
        s3 = get_s3_client()

        if file_ext not in text_extensions:
            # Binary file — return metadata only
            response = s3.head_object(Bucket=bucket, Key=key)
            return json.dumps({
                "bucket": bucket,
                "key": key,
                "note": f"Binary file ({file_ext}) — content not returned. Use get_object_metadata for details.",
                "size_bytes": response.get("ContentLength"),
                "content_type": response.get("ContentType"),
            })

        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read(max_bytes)
        content = body.decode("utf-8", errors="replace")
        truncated = response["ContentLength"] > max_bytes

        return json.dumps({
            "bucket": bucket,
            "key": key,
            "content": content,
            "size_bytes": response["ContentLength"],
            "truncated": truncated,
            "content_type": response.get("ContentType"),
        })
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def put_object(bucket: str, key: str, content: str, content_type: str = "text/plain") -> str:
    """
    Upload text content to an S3 object.

    Args:
        bucket: S3 bucket name
        key: Object key (destination path, e.g. 'data/report.txt')
        content: Text content to upload
        content_type: MIME type (default: text/plain)
    """
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType=content_type,
        )
        return json.dumps({
            "success": True,
            "bucket": bucket,
            "key": key,
            "size_bytes": len(content.encode("utf-8")),
            "content_type": content_type,
        })
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def delete_object(bucket: str, key: str) -> str:
    """
    Delete an object from S3.

    Args:
        bucket: S3 bucket name
        key: Object key to delete
    """
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=bucket, Key=key)
        return json.dumps({"success": True, "bucket": bucket, "key": key, "deleted": True})
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_objects(bucket: str, pattern: str, prefix: str = "") -> str:
    """
    Search for objects in a bucket whose key contains the given pattern.

    Args:
        bucket: S3 bucket name
        pattern: String to search for in object keys
        prefix: Optional folder prefix to limit search scope
    """
    try:
        s3 = get_s3_client()
        paginator = s3.get_paginator("list_objects_v2")
        kwargs = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix

        matches = []
        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents", []):
                if pattern.lower() in obj["Key"].lower():
                    matches.append({
                        "key": obj["Key"],
                        "size_bytes": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    })
                if len(matches) >= 100:
                    break
            if len(matches) >= 100:
                break

        return json.dumps({"bucket": bucket, "pattern": pattern, "matches": matches, "count": len(matches)})
    except ClientError as e:
        return json.dumps({"error": e.response["Error"]["Message"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
