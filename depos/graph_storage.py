"""Supabase Storage helpers for graph JSON blobs (service role)."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from depos.supabase_client import service_client


def graph_bucket() -> str:
    return os.environ.get("DEPOS_GRAPH_BUCKET", "graph-snapshots").strip()


def storage_bucket_configured() -> bool:
    return bool(graph_bucket())


def verify_bucket_exists() -> bool:
    """Return True if the bucket exists for the service role."""
    try:
        service_client().storage.from_(graph_bucket()).list(None, {"limit": 1})
        return True
    except Exception:
        return False


def create_signed_upload(storage_path: str) -> dict[str, Any]:
    """Return signed upload payload from storage3 (signed_url, token, path)."""
    client = service_client()
    return client.storage.from_(graph_bucket()).create_signed_upload_url(storage_path)


def download_bytes(storage_path: str) -> bytes:
    client = service_client()
    return client.storage.from_(graph_bucket()).download(storage_path)


def download_graph_json_bytes(storage_path: str) -> bytes:
    return download_bytes(storage_path)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_node_link_json(data: bytes) -> tuple[int, str]:
    """Parse JSON, ensure node-link shape; return (byte_size, sha256)."""
    h = sha256_hex(data)
    obj = json.loads(data.decode("utf-8"))
    if not isinstance(obj, dict) or "nodes" not in obj:
        raise ValueError("graph JSON must be an object with 'nodes'")
    return len(data), h
