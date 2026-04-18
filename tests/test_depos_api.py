from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastapi")

from depos.api_server import app

client = TestClient(app)


def test_health_routes_exist(tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_text("a = 1\n", encoding="utf-8")
    r = client.post("/v1/snapshot", json={"root": str(tmp_path)})
    assert r.status_code == 200
    assert r.json().get("ok") is True
