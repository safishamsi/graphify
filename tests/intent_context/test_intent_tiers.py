"""Deterministic intent tiers, policy merge, and manifest contract fields."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from depos.analysis.config import IntelligenceConfig
from depos.intent_context.build import run_intent_context_build
from depos.intent_context.schemas import DocSignalsRecord

FIXTURE_REPO = Path(__file__).resolve().parent / "fixtures" / "minimal_repo"

_FIXED_GIT = DocSignalsRecord(
    git_commit_at="2020-01-01T00:00:00+00:00",
    git_commit_sha="abc1234",
    git_available=True,
    degraded_warning=None,
)


def _write(root: Path, rel: str, content: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_manifest_has_schema_version_and_tier_fields(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(
        root,
        ".depos/intent.yaml",
        'default_tier: P2\ntier_rules:\n  - glob: "docs/arch/**/*.md"\n    tier: P0\n',
    )
    _write(root, "docs/arch/x.md", "# X\nThe system MUST do X.\n")
    _write(root, "README.md", "Hello world.\n")
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    out = tmp_path / "out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out, cfg) == 0
    man = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    assert man["intent_schema_version"] == 2
    by_rel = {f["relpath"]: f for f in man["files"]}
    assert by_rel["docs/arch/x.md"]["effective_tier"] == "P0"
    assert by_rel["docs/arch/x.md"]["policy_tier"] == "P0"
    assert by_rel["README.md"]["effective_tier"] == "P2"
    assert by_rel["README.md"]["policy_tier"] == "P2"
    assert man["counts_by_tier"]["P0"] >= 1
    assert "docs/arch/x.md" in man["p0_paths"]


def test_binding_glob_floors_to_p1(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(
        root,
        ".depos/intent.yaml",
        "default_tier: P2\nbinding_globs:\n  - \"policies/**/*.md\"\n",
    )
    _write(root, "policies/p.md", "The system MUST alpha.\n")
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    out = tmp_path / "out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out, cfg) == 0
    man = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    f = next(x for x in man["files"] if x["relpath"] == "policies/p.md")
    assert f["effective_tier"] == "P1"
    assert f["normative_surface"] is True


def test_frontmatter_normative_floors_to_p1(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(root, "docs/n.md", "---\nnormative: true\n---\nThe system SHOULD beta.\n")
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    out = tmp_path / "out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out, cfg) == 0
    man = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    f = next(x for x in man["files"] if x["relpath"] == "docs/n.md")
    assert f["effective_tier"] == "P1"


def test_oft_pattern_in_chunk_tightens_tier(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(
        root,
        "README.md",
        "# Readme\nIdle text.\n\n`req~sample-auth~1`\nNeeds:\nCovers:\n",
    )
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    out = tmp_path / "out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out, cfg) == 0
    chunks = [
        json.loads(line)
        for line in (out / "intent_chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(c.get("effective_tier") == "P1" for c in chunks)


def test_default_intent_tier_env_override(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(root, "README.md", "No cues here.\n")
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    cfg.intent_context.default_intent_tier = "P0"
    out = tmp_path / "out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out, cfg) == 0
    man = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    f = next(x for x in man["files"] if x["relpath"] == "README.md")
    assert f["policy_tier"] == "P0"
    assert f["effective_tier"] == "P0"


def test_two_runs_identical_manifest_tiers(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _write(
        root,
        ".depos/intent.yaml",
        'default_tier: P2\ntier_rules:\n  - glob: "docs/**/*.md"\n    tier: P1\n',
    )
    _write(root, "docs/a.md", "MUST be stable.\n")
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    out1 = tmp_path / "o1"
    out2 = tmp_path / "o2"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(root, out1, cfg) == 0
        assert run_intent_context_build(root, out2, cfg) == 0
    m1 = json.loads((out1 / "intent_manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((out2 / "intent_manifest.json").read_text(encoding="utf-8"))
    t1 = sorted((f["relpath"], f["effective_tier"], f["policy_tier"]) for f in m1["files"])
    t2 = sorted((f["relpath"], f["effective_tier"], f["policy_tier"]) for f in m2["files"])
    assert t1 == t2


@pytest.mark.parametrize("repo", [FIXTURE_REPO])
def test_fixture_repo_chunks_have_tier_contract(repo: Path, tmp_path: Path) -> None:
    cfg = IntelligenceConfig()
    cfg.intent_context.llm_mode = "rules"
    cfg.intent_context.chunk_max_chars = 12000
    out = tmp_path / "intent-out"
    with patch("depos.intent_context.build.git_doc_signals", return_value=_FIXED_GIT):
        assert run_intent_context_build(repo, out, cfg) == 0
    man = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    assert man["intent_schema_version"] == 2
    assert all("effective_tier" in f and "tier_lineage" in f for f in man["files"])
    chunks = [json.loads(line) for line in (out / "intent_chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all(c.get("effective_tier") and c.get("tier_lineage") is not None for c in chunks)
    units = json.loads((out / "intent_units.json").read_text(encoding="utf-8"))
    assert all("effective_weight" in u and "effective_tier" in u for u in units)
