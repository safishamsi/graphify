"""Tests for graphify.semantic_cleanup.validate_semantic_fragment (#825)."""

import json

from graphify import semantic_cleanup as sc


def _valid_fragment():
    return {
        "nodes": [{"id": "module_func", "label": "func", "file_type": "code"}],
        "edges": [{"source": "module_func", "target": "other_node"}],
        "hyperedges": [],
    }


def test_validate_semantic_fragment_accepts_valid():
    assert sc.validate_semantic_fragment(_valid_fragment()) == []


def test_validate_semantic_fragment_rejects_non_object():
    errors = sc.validate_semantic_fragment(["not", "an", "object"])
    assert any("object" in e.lower() for e in errors)


def test_validate_semantic_fragment_rejects_oversize_payload(monkeypatch):
    monkeypatch.setattr(sc, "MAX_SEMANTIC_FRAGMENT_BYTES", 64)
    fragment = _valid_fragment()
    fragment["nodes"][0]["label"] = "x" * 128
    errors = sc.validate_semantic_fragment(fragment)
    assert any("payload" in e.lower() for e in errors)


def test_validate_semantic_fragment_rejects_too_many_nodes(monkeypatch):
    monkeypatch.setattr(sc, "MAX_SEMANTIC_FRAGMENT_NODES", 1)
    fragment = _valid_fragment()
    fragment["nodes"].append({"id": "extra", "label": "extra", "file_type": "code"})
    errors = sc.validate_semantic_fragment(fragment)
    assert any("nodes" in e.lower() for e in errors)


def test_validate_semantic_fragment_rejects_too_many_edges(monkeypatch):
    monkeypatch.setattr(sc, "MAX_SEMANTIC_FRAGMENT_EDGES", 0)
    errors = sc.validate_semantic_fragment(_valid_fragment())
    assert any("edges" in e.lower() for e in errors)


def test_validate_semantic_fragment_rejects_path_separator_in_id():
    fragment = _valid_fragment()
    fragment["nodes"][0]["id"] = "../etc/passwd"
    errors = sc.validate_semantic_fragment(fragment)
    assert any("nodes[0].id" in e for e in errors)


def test_validate_semantic_fragment_rejects_invalid_file_type():
    fragment = _valid_fragment()
    fragment["nodes"][0]["file_type"] = "executable"
    errors = sc.validate_semantic_fragment(fragment)
    assert any("file_type" in e for e in errors)


def test_validate_semantic_fragment_accepts_rationale_file_type():
    """LLM output with file_type='rationale' must pass validation so the cleanup
    pass can convert or remove it.  Validation must not reject it before cleanup runs."""
    fragment = _valid_fragment()
    fragment["nodes"][0]["file_type"] = "rationale"
    errors = sc.validate_semantic_fragment(fragment)
    assert not any("file_type" in e for e in errors), (
        f"'rationale' must be accepted by validate_semantic_fragment; got errors: {errors}"
    )


def test_validate_semantic_fragment_accepts_concept_file_type():
    """LLM output with file_type='concept' must pass validation for the same reason."""
    fragment = _valid_fragment()
    fragment["nodes"][0]["file_type"] = "concept"
    errors = sc.validate_semantic_fragment(fragment)
    assert not any("file_type" in e for e in errors), (
        f"'concept' must be accepted by validate_semantic_fragment; got errors: {errors}"
    )


def test_load_validated_semantic_fragment_accepts_valid(tmp_path):
    chunk = tmp_path / ".graphify_chunk_00.json"
    chunk.write_text(json.dumps(_valid_fragment()))
    fragment, errors = sc.load_validated_semantic_fragment(chunk)
    assert errors == []
    assert fragment == _valid_fragment()


def test_load_validated_semantic_fragment_rejects_oversize_before_parse(tmp_path, monkeypatch):
    """Oversize files are rejected by stat() — payload is never parsed."""
    monkeypatch.setattr(sc, "MAX_SEMANTIC_FRAGMENT_BYTES", 64)
    chunk = tmp_path / ".graphify_chunk_99.json"
    # Write something that would PARSE successfully if read, but exceeds the size guard.
    chunk.write_text("[" + ",".join(['"x"'] * 50) + "]")
    fragment, errors = sc.load_validated_semantic_fragment(chunk)
    assert fragment is None
    assert any("payload" in e.lower() for e in errors)


def test_load_validated_semantic_fragment_rejects_invalid_json(tmp_path):
    """Invalid JSON returns an error instead of raising."""
    chunk = tmp_path / ".graphify_chunk_bad.json"
    chunk.write_text("{not valid json")
    fragment, errors = sc.load_validated_semantic_fragment(chunk)
    assert fragment is None
    assert any("invalid json" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Hyperedge validation (F2)
# ---------------------------------------------------------------------------


def test_validate_hyperedge_rejects_bad_id():
    fragment = _valid_fragment()
    fragment["hyperedges"] = [
        {"id": "../escape", "label": "x", "nodes": ["module_func", "module_func"]}
    ]
    errors = sc.validate_semantic_fragment(fragment)
    assert any("hyperedges[0].id" in e for e in errors)


def test_validate_hyperedge_rejects_bad_node_ref():
    fragment = _valid_fragment()
    fragment["hyperedges"] = [
        {"id": "valid_he", "label": "x", "nodes": ["module_func", "../bad_ref"]}
    ]
    errors = sc.validate_semantic_fragment(fragment)
    assert any("hyperedges[0].nodes[1]" in e for e in errors)


def test_validate_hyperedge_requires_list():
    fragment = _valid_fragment()
    fragment["hyperedges"] = [{"id": "valid_he", "label": "x", "nodes": "not a list"}]
    errors = sc.validate_semantic_fragment(fragment)
    assert any("hyperedges[0].nodes" in e for e in errors)


def test_validate_hyperedge_caps_count(monkeypatch):
    monkeypatch.setattr(sc, "MAX_SEMANTIC_FRAGMENT_HYPEREDGES", 1)
    fragment = _valid_fragment()
    fragment["hyperedges"] = [
        {"id": f"he_{i}", "label": "x", "nodes": ["module_func", "module_func"]} for i in range(3)
    ]
    errors = sc.validate_semantic_fragment(fragment)
    assert any("hyperedges has 3" in e for e in errors)


# ---------------------------------------------------------------------------
# Sanitizer behavior (F3 + F4 + rationale conversion)
# ---------------------------------------------------------------------------


def test_sanitize_drops_rationale_filetype_node():
    """A node with file_type='rationale' is removed wholesale."""
    fragment = {
        "nodes": [
            {"id": "real_node", "label": "Real", "file_type": "code"},
            {"id": "garbage", "label": "junk", "file_type": "rationale"},
        ],
        "edges": [],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    ids = {n["id"] for n in out["nodes"]}
    assert "real_node" in ids
    assert "garbage" not in ids


def test_sanitize_converts_sentence_rationale_node_to_attribute():
    """Sentence-like rationale node connected via `rationale_for` → attribute on target."""
    fragment = {
        "nodes": [
            {"id": "real_node", "label": "Real", "file_type": "code"},
            {
                "id": "why_node",
                "label": "We chose tree-sitter because the deterministic parser is faster than regex-based extraction.",
                "file_type": "rationale",
            },
        ],
        "edges": [{"source": "why_node", "target": "real_node", "relation": "rationale_for"}],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    ids = {n["id"] for n in out["nodes"]}
    assert "why_node" not in ids
    target = next(n for n in out["nodes"] if n["id"] == "real_node")
    assert "tree-sitter" in target.get("rationale", "")


def test_sanitize_converts_allowed_filetype_sentence_via_rationale_for_edge():
    """F3: a node with file_type='document' (allowed) that is BOTH sentence-like
    AND sources a `rationale_for` edge is still cleaned to an attribute."""
    fragment = {
        "nodes": [
            {"id": "real_node", "label": "Real", "file_type": "code"},
            {
                "id": "sentence_node",
                "label": (
                    "Decision: this node has sentence-like rationale text but uses an "
                    "allowed file_type, so it should not survive as a standalone graph node."
                ),
                "file_type": "document",
            },
        ],
        "edges": [{"source": "sentence_node", "target": "real_node", "relation": "rationale_for"}],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    ids = {n["id"] for n in out["nodes"]}
    assert "sentence_node" not in ids
    target = next(n for n in out["nodes"] if n["id"] == "real_node")
    assert "Decision" in target.get("rationale", "")


def test_sanitize_keeps_short_concept_named_node_with_punctuation():
    """A short named node with a period (e.g. abbreviation) is NOT sentence-like."""
    fragment = {
        "nodes": [
            {"id": "a_b", "label": "a.b.c", "file_type": "document"},
            {"id": "anchor", "label": "Anchor", "file_type": "code"},
        ],
        "edges": [{"source": "a_b", "target": "anchor", "relation": "rationale_for"}],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    ids = {n["id"] for n in out["nodes"]}
    assert "a_b" in ids
    assert "anchor" in ids


def test_sanitize_filters_hyperedges_after_node_removal():
    """F4: hyperedges referencing removed nodes are repaired or dropped."""
    fragment = {
        "nodes": [
            {"id": "real_node", "label": "Real", "file_type": "code"},
            {"id": "other", "label": "Other", "file_type": "code"},
            {"id": "garbage", "label": "junk", "file_type": "rationale"},
        ],
        "edges": [],
        "hyperedges": [
            {
                "id": "group_a",
                "label": "Group A",
                "nodes": ["garbage", "real_node", "other"],
                "relation": "participate_in",
            },
            {
                "id": "group_b",
                "label": "Group B (only one survivor)",
                "nodes": ["garbage", "real_node"],
                "relation": "participate_in",
            },
        ],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    he_ids = {he["id"] for he in out["hyperedges"]}
    # group_a survives with garbage filtered out
    assert "group_a" in he_ids
    group_a = next(he for he in out["hyperedges"] if he["id"] == "group_a")
    assert "garbage" not in group_a["nodes"]
    assert set(group_a["nodes"]) == {"real_node", "other"}
    # group_b had only 1 surviving member → dropped
    assert "group_b" not in he_ids


def test_sanitize_drops_hyperedge_with_only_unknown_refs():
    """A hyperedge referencing only nodes not present in the fragment is dropped."""
    fragment = {
        "nodes": [{"id": "real_node", "label": "Real", "file_type": "code"}],
        "edges": [],
        "hyperedges": [{"id": "phantom", "label": "Phantom", "nodes": ["ghost1", "ghost2"]}],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    assert out["hyperedges"] == []


def test_sanitize_boundary_sentence_threshold():
    """Boundary: a label with exactly 8 words + colon is sentence-like;
    a 7-word label without sentence punctuation is not."""
    # 8 words, has colon → sentence-like
    long_label = "Note: alpha beta gamma delta epsilon zeta eta"
    fragment = {
        "nodes": [
            {"id": "anchor", "label": "Anchor", "file_type": "code"},
            {"id": "n1", "label": long_label, "file_type": "rationale"},
        ],
        "edges": [{"source": "n1", "target": "anchor", "relation": "rationale_for"}],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    assert {n["id"] for n in out["nodes"]} == {"anchor"}
    anchor = out["nodes"][0]
    assert "alpha" in anchor.get("rationale", "")

    # 7 words no terminal punctuation → not sentence-like
    short_label = "alpha beta gamma delta epsilon zeta eta"
    fragment = {
        "nodes": [
            {"id": "anchor", "label": "Anchor", "file_type": "code"},
            {"id": "n2", "label": short_label, "file_type": "rationale"},
        ],
        "edges": [],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    # n2 has file_type=rationale, so it's still removed via pass 1 — but should NOT
    # become a rationale attribute on anchor (no rationale_for edge, no sentence pattern).
    assert {n["id"] for n in out["nodes"]} == {"anchor"}
    assert "rationale" not in out["nodes"][0]


def test_sanitize_rationale_only_propagates_through_rationale_for_edges():
    """A rationale node connected to ONE target via `rationale_for` and to ANOTHER
    target via a non-rationale-for relation must NOT attach the rationale text
    to the second target. Codex v2 caught the bug where every outgoing edge
    propagated the rationale, corrupting unrelated nodes."""
    fragment = {
        "nodes": [
            {"id": "rationale_target", "label": "Rationale Target", "file_type": "code"},
            {"id": "unrelated_target", "label": "Unrelated Target", "file_type": "code"},
            {
                "id": "why_node",
                "label": (
                    "Decision: we chose tree-sitter because the deterministic parser "
                    "is faster than regex-based extraction."
                ),
                "file_type": "rationale",
            },
        ],
        "edges": [
            {"source": "why_node", "target": "rationale_target", "relation": "rationale_for"},
            {"source": "why_node", "target": "unrelated_target", "relation": "references"},
        ],
        "hyperedges": [],
    }
    out = sc.sanitize_semantic_fragment(fragment)
    ids = {n["id"]: n for n in out["nodes"]}
    assert "why_node" not in ids
    # rationale_target should have the rationale attribute
    assert "tree-sitter" in ids["rationale_target"].get("rationale", "")
    # unrelated_target should NOT have rationale leaked from the `references` edge
    assert "rationale" not in ids["unrelated_target"]
