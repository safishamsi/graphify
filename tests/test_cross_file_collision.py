"""Tests for cross-file call resolution with label collisions.

Bug fix: when multiple nodes share the same normalised label across files
(e.g. two Python functions named `shared`, or the ubiquitous PHP `.get()`),
the legacy resolver silently picked one winner via dict overwrite, losing
(N-1)/N of the signal. The new resolver must:

  * Emit a single INFERRED edge (0.8) when exactly one candidate exists.
  * Emit N AMBIGUOUS edges (0.2, with `ambiguity_degree`) when N > 1.
  * Never emit a self-referential edge.
"""
from pathlib import Path

from graphify.extract import extract

FIXTURES = Path(__file__).parent / "fixtures" / "collision"


def _calls(result):
    return [e for e in result["edges"] if e["relation"] == "calls"]


def test_unique_candidate_keeps_inferred_high_confidence():
    """c.py calls only_in_a(), which exists in exactly one other file → INFERRED 0.8."""
    files = sorted(FIXTURES.glob("*.py"))
    result = extract(files)
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}

    src = node_by_label["caller_unique()"]
    tgt = node_by_label["only_in_a()"]

    matches = [e for e in _calls(result) if e["source"] == src and e["target"] == tgt]
    assert len(matches) == 1, f"Expected exactly one caller_unique → only_in_a edge, got {matches}"
    edge = matches[0]
    assert edge["confidence"] == "INFERRED", f"Expected INFERRED, got {edge['confidence']}"
    assert edge["confidence_score"] == 0.8, f"Expected 0.8, got {edge['confidence_score']}"
    # Backward compat: single-candidate edges must not carry ambiguity_degree.
    assert "ambiguity_degree" not in edge, f"Single-candidate edge should not have ambiguity_degree: {edge}"


def test_multi_candidate_emits_ambiguous_edges_to_all_candidates():
    """d.py calls shared(), which exists in a.py and b.py → 2 AMBIGUOUS edges at 0.2."""
    files = sorted(FIXTURES.glob("*.py"))
    result = extract(files)
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}

    src = node_by_label["caller_ambiguous()"]
    # There are two `shared()` nodes (one per file); look them up by id prefix.
    shared_ids = sorted(n["id"] for n in result["nodes"] if n["label"] == "shared()")
    assert len(shared_ids) == 2, f"Expected two shared() nodes, got {shared_ids}"

    edges_from_caller = [e for e in _calls(result) if e["source"] == src]
    # Only edges into the two shared() targets should be AMBIGUOUS from this caller.
    edges_to_shared = [e for e in edges_from_caller if e["target"] in shared_ids]
    assert len(edges_to_shared) == 2, (
        f"Expected 2 AMBIGUOUS edges from caller_ambiguous to both shared() targets, "
        f"got {edges_to_shared}"
    )

    for edge in edges_to_shared:
        assert edge["confidence"] == "AMBIGUOUS", f"Expected AMBIGUOUS, got {edge}"
        assert edge["confidence_score"] == 0.2, f"Expected 0.2, got {edge}"
        assert edge.get("ambiguity_degree") == 2, (
            f"Expected ambiguity_degree=2, got {edge.get('ambiguity_degree')} in {edge}"
        )

    # Both candidates must be covered exactly once (no duplicates, no winner-takes-all).
    targets = sorted(e["target"] for e in edges_to_shared)
    assert targets == shared_ids, f"Candidate coverage mismatch: {targets} vs {shared_ids}"


def test_no_self_referential_cross_file_calls():
    """A caller must never receive a cross-file edge pointing back at itself."""
    files = sorted(FIXTURES.glob("*.py"))
    result = extract(files)
    for edge in _calls(result):
        assert edge["source"] != edge["target"], f"Self-loop in cross-file call edge: {edge}"


def test_ambiguous_edge_carries_source_location():
    """AMBIGUOUS cross-file edges preserve source_file and source_location metadata."""
    files = sorted(FIXTURES.glob("*.py"))
    result = extract(files)
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label["caller_ambiguous()"]

    ambiguous_edges = [
        e for e in _calls(result)
        if e["source"] == src and e.get("confidence") == "AMBIGUOUS"
    ]
    assert ambiguous_edges, "No AMBIGUOUS edges emitted"
    for edge in ambiguous_edges:
        assert edge.get("source_file"), f"Missing source_file: {edge}"
        assert edge.get("source_location"), f"Missing source_location: {edge}"
        assert edge.get("weight") == 1.0, f"Weight should be 1.0: {edge}"


# ---------------------------------------------------------------------------
# W3.5 — degree cap + ambiguity_degree consistency guardrails
# ---------------------------------------------------------------------------

def _make_high_degree_fixture(tmp_path, n_definitions: int):
    """Create N files each defining `def foo()` plus one file that calls foo()."""
    files = []
    for i in range(n_definitions):
        p = tmp_path / f"def_{i:02d}.py"
        p.write_text(f'def foo():\n    return {i}\n', encoding="utf-8")
        files.append(p)
    caller = tmp_path / "caller.py"
    caller.write_text(
        '"""Caller module that triggers the ambiguous fan-out."""\n'
        'def entry_point():\n'
        '    return foo()  # noqa: F821 — resolved cross-file\n',
        encoding="utf-8",
    )
    files.append(caller)
    return sorted(files)


def test_degree_cap_respected_default_20(tmp_path):
    """25 candidate definitions > default cap (20) → no AMBIGUOUS edges, stats log truncation."""
    files = _make_high_degree_fixture(tmp_path, n_definitions=25)
    result = extract(files)
    stats = result.get("cross_file_call_stats")
    assert stats is not None, "extract() must expose cross_file_call_stats"
    assert stats["max_ambiguity_fanout"] == 20

    ambiguous = [e for e in _calls(result) if e.get("confidence") == "AMBIGUOUS"]
    assert ambiguous == [], (
        f"Expected zero AMBIGUOUS edges under default cap=20 with 25 candidates, "
        f"got {len(ambiguous)}"
    )
    assert stats["truncated_high_degree"] >= 1, (
        f"truncated_high_degree must register the drop: {stats}"
    )
    assert "foo" in stats["truncated_examples"], (
        f"Expected 'foo' in truncated_examples, got {stats['truncated_examples']}"
    )


def test_degree_cap_override_allows_fanout(tmp_path):
    """Explicit cap=30 lets the same 25-candidate scenario fan out normally."""
    files = _make_high_degree_fixture(tmp_path, n_definitions=25)
    result = extract(files, max_ambiguity_fanout=30)
    stats = result["cross_file_call_stats"]
    assert stats["max_ambiguity_fanout"] == 30
    assert stats["truncated_high_degree"] == 0

    ambiguous = [e for e in _calls(result) if e.get("confidence") == "AMBIGUOUS"]
    assert len(ambiguous) == 25, (
        f"Expected 25 AMBIGUOUS edges with cap=30 and 25 candidates, got {len(ambiguous)}"
    )
    for edge in ambiguous:
        assert edge["ambiguity_degree"] == 25, (
            f"Every AMBIGUOUS edge must report degree=25, got {edge}"
        )


def test_ambiguity_degree_matches_fanout(tmp_path):
    """With 5 same-name definitions + 1 caller, each AMBIGUOUS edge reports degree=5 exactly.

    Belt-and-braces guard against the P1 bug where `ambiguity_degree` could
    drift above the actual fan-out if the candidate pool contained duplicate
    nids (e.g. from layered extractors or label-variant collisions).
    """
    files = _make_high_degree_fixture(tmp_path, n_definitions=5)
    result = extract(files)
    ambiguous = [e for e in _calls(result) if e.get("confidence") == "AMBIGUOUS"]
    assert len(ambiguous) == 5, f"Expected 5 AMBIGUOUS edges, got {len(ambiguous)}"

    # Every edge's ambiguity_degree must equal the real number of emitted edges.
    observed_fanout = len(ambiguous)
    for edge in ambiguous:
        assert edge["ambiguity_degree"] == observed_fanout == 5, (
            f"ambiguity_degree={edge['ambiguity_degree']} must match fanout={observed_fanout}: {edge}"
        )

    # Targets must be unique — no duplicate edges to the same node.
    targets = [e["target"] for e in ambiguous]
    assert len(set(targets)) == len(targets), (
        f"Duplicate AMBIGUOUS edge targets indicate candidate pool dedup failure: {targets}"
    )


def test_env_var_overrides_default_cap(tmp_path, monkeypatch):
    """GRAPHIFY_MAX_AMBIGUITY_FANOUT env var is honoured when no explicit kwarg."""
    files = _make_high_degree_fixture(tmp_path, n_definitions=25)
    monkeypatch.setenv("GRAPHIFY_MAX_AMBIGUITY_FANOUT", "30")
    result = extract(files)
    stats = result["cross_file_call_stats"]
    assert stats["max_ambiguity_fanout"] == 30
    assert stats["truncated_high_degree"] == 0
    ambiguous = [e for e in _calls(result) if e.get("confidence") == "AMBIGUOUS"]
    assert len(ambiguous) == 25
