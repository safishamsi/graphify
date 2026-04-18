"""Graph snapshot prepare/complete logic with mocked Storage."""
from __future__ import annotations

import json

import pytest

from depos.graph_storage import sha256_hex, verify_node_link_json


def test_verify_node_link_json_accepts_node_link() -> None:
    payload = {"nodes": [{"id": "n1"}], "links": []}
    raw = json.dumps(payload).encode("utf-8")
    size, h = verify_node_link_json(raw)
    assert size == len(raw)
    assert h == sha256_hex(raw)


def test_verify_node_link_json_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        verify_node_link_json(b"{}")
    with pytest.raises(json.JSONDecodeError):
        verify_node_link_json(b"not json")


def test_graph_snapshot_complete_body_optional_sha() -> None:
    from depos.api_server import GraphSnapshotCompleteBody

    b = GraphSnapshotCompleteBody()
    assert b.expected_sha256 is None
