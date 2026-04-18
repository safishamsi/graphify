from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL required (e.g. local supabase start)",
)

from depos import db as db_mod
from depos.api_server import app

client = TestClient(app)


def test_health_ok() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_snapshot_ok(tmp_path: Path) -> None:
    db_mod.reset_engine_for_tests()
    p = tmp_path / "x.py"
    p.write_text("a = 1\n", encoding="utf-8")
    headers = {}
    key = os.environ.get("DEPOS_INTERNAL_API_KEY")
    if key:
        headers["X-DepOS-Internal-Key"] = key
    r = client.post("/v1/snapshot", json={"root": str(tmp_path)}, headers=headers)
    assert r.status_code == 200
    assert r.json().get("ok") is True
