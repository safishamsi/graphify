"""Backend security: internal routes and tenant CI analyze constraints."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

pytest.importorskip("fastapi")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL required (e.g. local supabase start)",
)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    p = tmp_path / "mod.py"
    p.write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_health_unauthenticated() -> None:
    from fastapi.testclient import TestClient

    from depos.api_server import app

    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_snapshot_401_when_internal_key_configured(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPOS_INTERNAL_API_KEY", "test-internal-secret-do-not-reuse")
    from fastapi.testclient import TestClient

    from depos import api_server
    from depos import db as db_mod

    db_mod.reset_engine_for_tests()
    c = TestClient(api_server.app)
    r = c.post("/v1/snapshot", json={"root": str(tmp_repo)})
    assert r.status_code == 401


def test_snapshot_200_with_internal_key(tmp_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPOS_INTERNAL_API_KEY", "test-internal-secret-do-not-reuse")
    from fastapi.testclient import TestClient

    from depos import api_server
    from depos import db as db_mod

    db_mod.reset_engine_for_tests()
    c = TestClient(api_server.app)
    r = c.post(
        "/v1/snapshot",
        json={"root": str(tmp_repo)},
        headers={"X-DepOS-Internal-Key": "test-internal-secret-do-not-reuse"},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_ci_analyze_request_requires_graph_or_root() -> None:
    from depos.api_server import CIAnalyzeRequest

    with pytest.raises(ValidationError):
        CIAnalyzeRequest(org_slug="o", repo_slug="r")
    m = CIAnalyzeRequest(
        org_slug="o",
        repo_slug="r",
        graph_snapshot_id=UUID("00000000-0000-4000-8000-000000000001"),
    )
    assert m.graph_snapshot_id is not None
