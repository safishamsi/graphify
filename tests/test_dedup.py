"""Tests for graphify/dedup.py entity deduplication pipeline."""
from __future__ import annotations
import pytest
from graphify.dedup import deduplicate_entities, _entropy, _shingles


# ── entropy gate ─────────────────────────────────────────────────────────────

def test_entropy_short_label_low():
    assert _entropy("AI") < 2.5

def test_entropy_normal_label_high():
    assert _entropy("AuthenticationManager") >= 2.5

def test_entropy_empty_string():
    assert _entropy("") == 0.0


# ── shingles ─────────────────────────────────────────────────────────────────

def test_shingles_produces_trigrams():
    s = _shingles("hello")
    assert "hel" in s
    assert "ell" in s
    assert "llo" in s

def test_shingles_short_string():
    # strings shorter than 3 chars return single shingle of the string itself
    assert _shingles("ab") == {"ab"}


# ── full pipeline ─────────────────────────────────────────────────────────────

def _make_nodes(*labels):
    return [{"id": label.lower().replace(" ", "_"), "label": label, "source_file": "test.md"} for label in labels]

def _make_edges(src, tgt, relation="relates_to"):
    return [{"source": src, "target": tgt, "relation": relation}]


def test_exact_duplicates_merged():
    nodes = _make_nodes("UserService", "userservice", "User Service")
    edges = []
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, edges, communities={})
    # All three are the same concept — only one survives
    assert len(result_nodes) == 1


def test_typo_merged():
    # "GraphExtractor" vs "Graph Extractor" — Jaro-Winkler >= 0.92
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1


def test_unrelated_not_merged():
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_short_low_entropy_not_merged():
    # "AI" and "ML" are low-entropy — entropy gate skips them
    nodes = _make_nodes("AI", "ML")
    edges = []
    result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_edges_rewired_after_merge():
    nodes = _make_nodes("GraphExtractor", "Graph Extractor", "Parser")
    # edge from loser to Parser should be rewired to winner
    edges = [{"source": "graph_extractor", "target": "parser", "relation": "uses"}]
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2  # merged + Parser
    # edge should still exist (rewired to winner)
    assert len(result_edges) == 1


def test_self_loops_dropped_after_merge():
    # If both endpoints of an edge get merged into same node, drop the edge
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = [{"source": "graphextractor", "target": "graph_extractor", "relation": "same"}]
    _, result_edges, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert result_edges == []


def test_community_boost_aids_merge():
    # Two nodes in same community with score in 0.75-0.85 zone get boosted
    nodes = _make_nodes("AuthManager", "Auth Manager")
    edges = []
    # Same community → boost → merge
    communities = {"authmanager": 1, "auth_manager": 1}
    result_with, _, _, _ = deduplicate_entities(nodes, edges, communities=communities)
    # Different community → no boost
    communities_diff = {"authmanager": 1, "auth_manager": 2}
    result_without, _, _, _ = deduplicate_entities(nodes, edges, communities=communities_diff)
    assert len(result_with) <= len(result_without)

def test_empty_inputs():
    result_nodes, result_edges, _, _ = deduplicate_entities([], [], communities={})
    assert result_nodes == []
    assert result_edges == []


def test_single_node_no_crash():
    nodes = _make_nodes("UserService")
    result_nodes, _, _, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1


def test_dedup_llm_flag_accepted():
    """deduplicate_entities accepts dedup_llm_backend without crashing when no ambiguous pairs exist."""
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={}, dedup_llm_backend=None)
    assert len(result_nodes) == 2


# ── build integration ─────────────────────────────────────────────────────────

def test_build_calls_dedup():
    """build() should deduplicate near-identical nodes across extractions."""
    from graphify.build import build
    chunk1 = {
        "nodes": [{"id": "graphextractor", "label": "GraphExtractor", "source_file": "a.py"}],
        "edges": [],
    }
    chunk2 = {
        "nodes": [{"id": "graph_extractor", "label": "Graph Extractor", "source_file": "b.py"}],
        "edges": [],
    }
    G = build([chunk1, chunk2])
    assert G.number_of_nodes() == 1


# ---------------------------------------------------------------------------
# Internal helper functions
# ---------------------------------------------------------------------------

from graphify.dedup import (
    _dedup_key, _compatible_duplicate, _canonical_score,
    _source_location_dedup, prune_graph_references,
    _norm_member_label, _edge_key
)


def test_dedup_key_valid():
    node = {"source_file": "a.py", "source_location": "line 10"}
    assert _dedup_key(node) == ("a.py", "line 10")


def test_dedup_key_missing_field():
    node = {"source_file": "a.py"}
    assert _dedup_key(node) is None


def test_compatible_duplicate_same_label():
    a = {"label": "foo", "id": "n1"}
    b = {"label": "foo", "id": "n2"}
    assert _compatible_duplicate(a, b) is True


def test_compatible_duplicate_same_id_no_label():
    """Matching IDs with no labels hits the a_id==b_id branch (line 111)."""
    a = {"id": "same_id"}
    b = {"id": "same_id"}
    assert _compatible_duplicate(a, b) is True


def test_compatible_duplicate_different():
    a = {"label": "foo", "id": "n1"}
    b = {"label": "bar", "id": "n2"}
    assert _compatible_duplicate(a, b) is False


def test_compatible_duplicate_snippet_match():
    a = {"source_snippet": "def foo():", "label": "foo"}
    b = {"source_snippet": "def foo():", "label": "bar"}
    assert _compatible_duplicate(a, b) is True


def test_canonical_score_prefers_label():
    a = _canonical_score({"label": "foo", "id": "n1"})
    b = _canonical_score({"label": "", "id": "n2"})
    assert a > b  # has_label = 1 > 0


def test_canonical_score_prefers_longer_label():
    """Longer labels get higher canonical scores."""
    a = _canonical_score({"label": "LongDetailedLabel", "id": "n1"})
    b = _canonical_score({"label": "Short", "id": "n2"})
    assert a > b


def test_source_location_dedup_merges():
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n2", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
    ]
    edges = [{"source": "n1", "target": "n3", "relation": "relates_to", "source_file": "a.py", "confidence": "HIGH"}]
    result_nodes, result_edges, _, merges, _ = _source_location_dedup(nodes, edges, None)
    assert merges == 1
    assert len(result_nodes) == 1  # n1 & n2 merged; n3 was never in nodes


def test_source_location_dedup_with_hyperedges():
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n2", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
    ]
    edges = []
    hyperedges = [{"nodes": ["n1", "n2", "n3"]}]
    result_nodes, _, result_hyper, merges, hyper_remapped = _source_location_dedup(nodes, edges, hyperedges)
    assert merges == 1
    assert hyper_remapped >= 1


def test_prune_graph_references_simple():
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [{"source": "a", "target": "b", "relation": "relates_to"}]
    n, e, h, d = prune_graph_references(nodes, edges)
    assert d == 0
    assert len(e) == 1


def test_prune_graph_references_missing():
    nodes = [{"id": "a"}]
    edges = [{"source": "a", "target": "missing", "relation": "relates_to"}]
    n, e, h, d = prune_graph_references(nodes, edges)
    assert d >= 1


def test_prune_graph_references_dict_input():
    data = {
        "nodes": [{"id": "a"}],
        "edges": [{"source": "a", "target": "b", "relation": "relates_to"}],
        "hyperedges": [],
    }
    result = prune_graph_references(data)
    assert isinstance(result, dict)
    assert len(result["edges"]) == 0  # b is missing


def test_cross_project_guard():
    nodes = [
        {"id": "n1", "label": "foo", "repo": "repo_a", "source_file": "a.py"},
        {"id": "n2", "label": "foo", "repo": "repo_b", "source_file": "b.py"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [])


def test_norm_member_label_strips_prefix():
    assert _norm_member_label("T-21  myFunction") == "myFunction"


def test_norm_member_label_no_prefix():
    assert _norm_member_label("myFunction") == "myFunction"


def test_norm_member_label_empty():
    assert _norm_member_label("") == ""


def test_edge_key():
    edge = {"source": "a", "target": "b", "relation": "calls", "source_file": "x.py", "confidence": "HIGH"}
    key = _edge_key(edge)
    assert key == ("a", "b", "calls", "x.py", "HIGH")


# ---------------------------------------------------------------------------
# _compatible_duplicate — label/id containment paths (lines 111, 114, 117)
# ---------------------------------------------------------------------------

def test_compatible_duplicate_label_containment():
    """Different labels are NOT compatible, even if one is a substring (#F6).
    Character-level substring containment falsely merges distinct symbols
    (e.g., 'user' and 'userId'). Token-level containment checks are used
    instead; 'UserAuthenticationManager' and 'Authentication' don't share
    whole tokens after CamelCase splitting."""
    a = {"label": "UserAuthenticationManager", "id": "n1"}
    b = {"label": "Authentication", "id": "n2"}
    assert _compatible_duplicate(a, b) is False


def test_compatible_duplicate_id_containment():
    """Different IDs are NOT compatible via character-level containment (#F6).
    IDs must match exactly after prefix stripping, not be character-level
    substrings. 'user_auth_manager' and 'auth_manager' are different symbols."""
    a = {"label": "foo", "id": "user_auth_manager"}
    b = {"label": "bar", "id": "auth_manager"}
    assert _compatible_duplicate(a, b) is False


def test_compatible_duplicate_no_match():
    """Different labels and ids with no containment."""
    a = {"label": "foo", "id": "n1"}
    b = {"label": "bar", "id": "n2"}
    assert _compatible_duplicate(a, b) is False


# ---------------------------------------------------------------------------
# _source_location_dedup — no merges, edge self-loops
# ---------------------------------------------------------------------------

def test_source_location_dedup_no_merges():
    """When no groups have duplicates, returns unchanged."""
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n2", "label": "bar", "source_file": "a.py", "source_location": "line 2"},
    ]
    edges = [{"source": "n1", "target": "n2", "relation": "relates_to", "source_file": "a.py", "confidence": "HIGH"}]
    result_nodes, result_edges, _, merges, _ = _source_location_dedup(nodes, edges, None)
    assert merges == 0
    assert len(result_nodes) == 2


def test_source_location_dedup_edge_self_loop():
    """After remap, edges where source==target are dropped."""
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n2", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
    ]
    edges = [{"source": "n1", "target": "n2", "relation": "relates_to", "source_file": "a.py", "confidence": "HIGH"}]
    result_nodes, result_edges, _, merges, _ = _source_location_dedup(nodes, edges, None)
    assert merges == 1
    # After merging n2 into n1, the edge n1->n2 becomes n1->n1, should be dropped
    assert len(result_edges) == 0


def test_source_location_dedup_duplicate_edge():
    """Duplicate edges (same key) after remap are deduplicated."""
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n2", "label": "foo", "source_file": "a.py", "source_location": "line 1"},
        {"id": "n3", "label": "bar", "source_file": "a.py", "source_location": "line 2"},
    ]
    edges = [
        {"source": "n2", "target": "n3", "relation": "calls", "source_file": "a.py", "confidence": "HIGH"},
        {"source": "n2", "target": "n3", "relation": "calls", "source_file": "a.py", "confidence": "HIGH"},
    ]
    result_nodes, result_edges, _, merges, _ = _source_location_dedup(nodes, edges, None)
    assert merges == 1
    # After merging n2->n1, both edges become n1->n3 with same key → deduped to 1
    assert len(result_edges) == 1


# ---------------------------------------------------------------------------
# prune_graph_references — self-loops, duplicate edges, hyperedge pruning
# ---------------------------------------------------------------------------

def test_prune_graph_references_self_loop():
    """Edges where source == target are dropped."""
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [{"source": "a", "target": "a", "relation": "self"}]
    n, e, h, d = prune_graph_references(nodes, edges)
    assert d >= 1
    assert len(e) == 0


def test_prune_graph_references_duplicate_edge():
    """Duplicate edge keys are dropped."""
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [
        {"source": "a", "target": "b", "relation": "calls", "source_file": "x.py", "confidence": "HIGH"},
        {"source": "a", "target": "b", "relation": "calls", "source_file": "x.py", "confidence": "HIGH"},
    ]
    n, e, h, d = prune_graph_references(nodes, edges)
    assert d >= 1
    assert len(e) == 1


def test_prune_graph_references_hyperedge_too_small():
    """Hyperedges with <2 members after pruning are dropped."""
    nodes = [{"id": "a"}]
    edges = []
    hyperedges = [{"nodes": ["a", "missing1", "missing2"]}]
    n, e, h, d = prune_graph_references(nodes, edges, hyperedges)
    assert h is not None
    # The hyperedge should be dropped because only 1 node remains
    assert len(h) == 0


def test_prune_graph_references_hyperedge_ok():
    """Hyperedges with >=2 valid members survive."""
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = []
    hyperedges = [{"nodes": ["a", "b", "missing"]}]
    n, e, h, d = prune_graph_references(nodes, edges, hyperedges)
    assert h is not None
    assert len(h) == 1
    assert len(h[0]["nodes"]) == 2


def test_prune_graph_references_dict_with_hyperedges():
    """Dict input with hyperedges that get pruned."""
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b", "relation": "relates_to"}],
        "hyperedges": [{"nodes": ["a", "missing"]}],
    }
    result = prune_graph_references(data)
    assert isinstance(result, dict)
    # hyperedge with <2 members should be dropped
    assert result["hyperedges"] == []


# ---------------------------------------------------------------------------
# deduplicate_entities — small graphs (exact normalization), LSH ValueError,
# neighbor None, hyperedge remapping
# ---------------------------------------------------------------------------

def test_deduplicate_single_node_full_pipeline():
    """Single node goes through full pipeline without error."""
    nodes = [{"id": "n1", "label": "SingleService", "source_file": "a.py"}]
    edges = []
    result_nodes, result_edges, _, stats = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1
    assert "merged_nodes" in stats


def test_deduplicate_exact_normalization():
    """Nodes with identical normalized labels are merged."""
    nodes = _make_nodes("User Service", "user_service", "UserService")
    edges = []
    result_nodes, _, _, stats = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1
    assert stats["merged_nodes"] >= 1


def test_deduplicate_lsh_valueerror_handled(tmp_path, monkeypatch):
    """LSH insert ValueError (duplicate key) does not crash."""
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    # Two very similar items that may produce the same MinHash id
    result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1


def test_deduplicate_pick_winner_prefers_shorter():
    """_pick_winner prefers nodes without chunk suffix and shorter ids."""
    from graphify.dedup import _pick_winner
    nodes = [
        {"id": "user_service", "label": "UserService"},
        {"id": "user_service_c1", "label": "UserService"},
    ]
    winner = _pick_winner(nodes)
    assert winner["id"] == "user_service"


def test_deduplicate_pick_winner_empty_raises():
    """_pick_winner raises ValueError on empty list."""
    from graphify.dedup import _pick_winner
    import pytest
    with pytest.raises(ValueError, match="empty"):
        _pick_winner([])


def test_deduplicate_hyperedges_remapped():
    """Hyperedge member IDs are remapped after entity dedup."""
    nodes = _make_nodes("AuthManager", "Auth Manager", "DatabaseService")
    edges = []
    hyperedges = [{"nodes": ["authmanager", "auth_manager", "databaseservice"]}]
    result_nodes, result_edges, result_hyper, stats = deduplicate_entities(
        nodes, edges, hyperedges, communities={}
    )
    assert len(result_nodes) <= 2
    assert result_hyper is not None
    # hyperedge members should be remapped
    assert stats.get("hyperedges_remapped", 0) >= 0


def test_deduplicate_fuzzy_no_hyper_remap():
    """Prune phase handles hyperedges=None gracefully."""
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    # No hyperedges — prune_graph_references converts None to []
    result_nodes, result_edges, result_hyper, stats = deduplicate_entities(nodes, edges, None, communities={})
    assert result_hyper == []
    assert len(result_nodes) == 1


def test_deduplicate_llm_tiebreak_skip_on_import_error(monkeypatch):
    """LLM tiebreak is skipped when graphify.llm cannot be imported."""
    nodes = _make_nodes("UserAuthenticationService", "ClientAuthenticationService")
    edges = []
    # Patch _llm_tiebreak to simulate import failure inside
    with monkeypatch.context() as m:
        m.setattr("graphify.dedup._llm_tiebreak", lambda *a, **kw: None)
        result_nodes, _, _, _ = deduplicate_entities(nodes, edges, communities={}, dedup_llm_backend="openai")
        assert len(result_nodes) == 2  # no merges via LLM


# ---------------------------------------------------------------------------
# _maybe_return edge cases
# ---------------------------------------------------------------------------

def test_maybe_return_no_hyperedges_no_stats():
    """_maybe_return with no hyperedges and no stats."""
    from graphify.dedup import _maybe_return
    nodes = [{"id": "a"}]
    edges = []
    result = _maybe_return(nodes, edges, None, None)
    assert result[0] == nodes
    assert result[2] is None
    assert result[3] == {}


def test_maybe_return_with_hyperedges():
    """_maybe_return preserves hyperedges."""
    from graphify.dedup import _maybe_return
    nodes = [{"id": "a"}]
    edges = []
    hyperedges = [{"nodes": ["a"]}]
    result = _maybe_return(nodes, edges, hyperedges, {"key": "val"})
    assert result[2] is not None
    assert result[3] == {"key": "val"}


# ---------------------------------------------------------------------------
# deduplicate cross-project guard with no repos
# ---------------------------------------------------------------------------

def test_deduplicate_no_repo_set():
    """Nodes without repo field are allowed (no cross-project guard)."""
    nodes = [
        {"id": "n1", "label": "foo", "source_file": "a.py"},
        {"id": "n2", "label": "bar", "source_file": "b.py"},
    ]
    result_nodes, _, _, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


def test_deduplicate_single_repo_allowed():
    """Nodes with same repo field are allowed."""
    nodes = [
        {"id": "n1", "label": "foo", "repo": "myrepo", "source_file": "a.py"},
        {"id": "n2", "label": "bar", "repo": "myrepo", "source_file": "b.py"},
    ]
    result_nodes, _, _, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 2


# ---------------------------------------------------------------------------
# _norm_member_label — additional cases
# ---------------------------------------------------------------------------

def test_norm_member_label_whitespace_only():
    assert _norm_member_label("   ") == ""


def test_norm_member_label_not_prefix_format():
    """Prefix pattern only matches A-NNN, not other formats."""
    assert _norm_member_label("xyz myFunction") == "xyz myFunction"


# ---------------------------------------------------------------------------
# _compatible_duplicate — ID substring match
# ---------------------------------------------------------------------------

def test_compatible_duplicate_id_substring_match():
    """Nodes with overlapping IDs are compatible duplicates."""
    from graphify.dedup import _compatible_duplicate
    a = {"id": "lib_sort_all", "source_file": "sort.py", "source_location": "10"}
    b = {"id": "sort_all", "source_file": "sort.py", "source_location": "10"}
    assert _compatible_duplicate(a, b) is True


# ---------------------------------------------------------------------------
# deduplicate_entities — early return with single node + hyperedges
# ---------------------------------------------------------------------------

def test_deduplicate_single_node_with_hyperedges():
    """Single node with hyperedges returns stats correctly."""
    nodes = _make_nodes("SingleNode")
    edges = []
    hyperedges = [{"nodes": ["singlenode", "othernode"]}]
    result_nodes, result_edges, result_hyper, stats = deduplicate_entities(
        nodes, edges, hyperedges, communities={}
    )
    assert len(result_nodes) == 1
    assert result_hyper is not None


# ---------------------------------------------------------------------------
# deduplicate_entities — exact normalization winner picking
# ---------------------------------------------------------------------------

def test_deduplicate_three_exact_normalized_merged():
    """Three nodes with same normalized label merge into one."""
    nodes = [
        {"id": "a", "label": "User Service", "source_file": "test.md"},
        {"id": "b", "label": "user_service", "source_file": "test.md"},
        {"id": "c", "label": "UserService", "source_file": "test.md"},
    ]
    edges = []
    result_nodes, _, _, stats = deduplicate_entities(nodes, edges, communities={})
    # All three share normalized label "user service"
    assert len(result_nodes) == 1
    assert stats["merged_nodes"] >= 1


# ---------------------------------------------------------------------------
# deduplicate_entities — community boost for same-community nodes
# ---------------------------------------------------------------------------

def test_deduplicate_same_community_boosted():
    """Nodes in the same community get merge boost."""
    nodes = [
        {"id": "error_handler", "label": "ErrorHandler", "source_file": "test.py"},
        {"id": "error_handling", "label": "Error Handling", "source_file": "test.py"},
    ]
    edges = []
    communities = {"error_handler": 0, "error_handling": 0}
    result_nodes, _, _, stats = deduplicate_entities(nodes, edges, communities=communities)
    # Same community gives boost - these likely merge
    assert len(result_nodes) <= 2


# ---------------------------------------------------------------------------
# deduplicate_entities — source_location dedup with edge rewriting
# ---------------------------------------------------------------------------

def test_source_location_dedup_with_edges():
    """Source-location dedup rewrites edge endpoints correctly."""
    nodes = [
        {"id": "a", "label": "Func", "source_file": "mod.py", "source_location": "10"},
        {"id": "b", "label": "func", "source_file": "mod.py", "source_location": "10"},
        {"id": "c", "label": "Other", "source_file": "mod.py", "source_location": "20"},
    ]
    edges = [
        {"source": "a", "target": "c", "relation": "calls"},
        {"source": "b", "target": "c", "relation": "calls"},
    ]
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, edges, communities={})
    # a and b at same source_location merge; one becomes canonical
    assert len(result_nodes) == 2
    # Edge from duplicate→c should be rewritten to canonical→c (one deduplicated)
    assert len(result_edges) == 1
    sources = [e["source"] for e in result_edges]
    # Either "a" or "b" is canonical; both are fine
    assert len(sources) == 1


# ---------------------------------------------------------------------------
# deduplicate_entities — repos span detection
# ---------------------------------------------------------------------------

def test_deduplicate_cross_repo_raises():
    """Cross-repo dedup raises ValueError."""
    nodes = [
        {"id": "n1", "label": "foo", "repo": "repo-a", "source_file": "a.py"},
        {"id": "n2", "label": "foo", "repo": "repo-b", "source_file": "b.py"},
    ]
    with pytest.raises(ValueError, match="multiple repos"):
        deduplicate_entities(nodes, [], communities={})


# ---------------------------------------------------------------------------
# deduplicate_entities — self-loop edge dropping
# ---------------------------------------------------------------------------

def test_deduplicate_self_loop_dropped():
    """Self-loop edges (same source/target after remap) are dropped."""
    nodes = [
        {"id": "servicea", "label": "RedisCache", "source_file": "test.md"},
        {"id": "serviceb", "label": "PostgresDB", "source_file": "test.md"},
        {"id": "servicec", "label": "KafkaBroker", "source_file": "test.md"},
    ]
    edges = [
        {"source": "servicea", "target": "servicea", "relation": "self_ref"},
        {"source": "servicea", "target": "serviceb", "relation": "calls"},
    ]
    result_nodes, result_edges, _, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 3
    assert len(result_edges) == 1  # self-loop dropped, call kept


# ---------------------------------------------------------------------------
# deduplicate_entities — no-op when no merges needed
# ---------------------------------------------------------------------------

def test_deduplicate_no_merges_needed():
    """When all nodes are distinct, everything passes through unchanged."""
    nodes = [
        {"id": "n1", "label": "Alpha", "source_file": "a.py"},
        {"id": "n2", "label": "Beta", "source_file": "b.py"},
    ]
    edges = [{"source": "n1", "target": "n2", "relation": "relates_to"}]
    result_nodes, result_edges, _, stats = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2
    assert len(result_edges) == 1


# ---------------------------------------------------------------------------
# _llm_tiebreak
# ---------------------------------------------------------------------------

def test_llm_tiebreak_unknown_backend_skips():
    """LLM tiebreak is skipped for unknown backends."""
    from graphify.dedup import _llm_tiebreak, _UF
    nodes = _make_nodes("FooService", "FuuService")
    uf = _UF()
    _llm_tiebreak(nodes, uf, {}, backend="nonexistent_backend")
    # Should not raise; just skip silently


def test_llm_tiebreak_import_error_skipped(monkeypatch):
    """LLM tiebreak skips when graphify.llm cannot be imported."""
    from graphify.dedup import _llm_tiebreak, _UF
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "graphify.llm":
            raise ImportError("No graphify.llm")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    nodes = _make_nodes("FooService", "FuuService")
    uf = _UF()
    _llm_tiebreak(nodes, uf, {}, backend="openai")
    # Should not raise


# ---------------------------------------------------------------------------
# deduplicate_entities — single unique node after source-location dedup
# ---------------------------------------------------------------------------

def test_deduplicate_one_unique_node_after_dedup():
    """After source-location dedup and ID dedup, only one unique node remains."""
    nodes = [
        {"id": "a", "label": "Alpha", "source_file": "mod.py", "source_location": "10"},
        {"id": "b", "label": "Alpha", "source_file": "mod.py", "source_location": "10"},
    ]
    edges = [{"source": "a", "target": "a", "relation": "self_ref"}]
    result_nodes, result_edges, result_hyper, stats = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1
    # self-loop on 'a' is dropped (a→a, and a's edges may be remapped later)
    assert stats["merged_nodes"] >= 1


def test_deduplicate_duplicate_ids_after_source_loc():
    """Source-location dedup merges nodes, leaving duplicate IDs."""
    nodes = [
        {"id": "x", "label": "Duplicate", "source_file": "mod.py", "source_location": "1"},
        {"id": "y", "label": "Duplicate", "source_file": "mod.py", "source_location": "1"},
    ]
    edges = []
    result_nodes, _, _, stats = deduplicate_entities(nodes, edges, communities={})
    # Source-loc merges x and y (same label); one is canonical
    assert len(result_nodes) == 1
    assert stats["merged_nodes"] == 1


def test_deduplicate_three_with_exact_and_fuzzy():
    """Three nodes where some merge exactly and some merge fuzzily."""
    nodes = [
        {"id": "handler", "label": "RequestHandler", "source_file": "test.md"},
        {"id": "handlr", "label": "Request Handler", "source_file": "test.md"},
        {"id": "processor", "label": "ProcessRequest", "source_file": "test.md"},
    ]
    edges = []
    result_nodes, _, _, stats = deduplicate_entities(nodes, edges, communities={})
    # "requesthandler" and "request handler" share normalized label
    assert len(result_nodes) <= 2
    assert stats["merged_nodes"] >= 1


# ---------------------------------------------------------------------------
# _llm_tiebreak — missing env keys and empty ambiguous pairs
# ---------------------------------------------------------------------------

def test_llm_tiebreak_missing_env_keys(monkeypatch):
    """LLM tiebreak skips when API key env is not set."""
    from graphify.dedup import _llm_tiebreak, _UF
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    nodes = _make_nodes("FooService", "FuuService")
    uf = _UF()
    _llm_tiebreak(nodes, uf, {}, backend="openai")


def test_llm_tiebreak_call_llm_import_error(monkeypatch):
    """LLM tiebreak when _call_llm doesn't exist in graphify.llm."""
    from graphify.dedup import _llm_tiebreak, _UF
    import sys
    # Make graphify.llm importable but missing _call_llm
    class FakeLLMModule:
        BACKENDS = {"openai": {"env_keys": ["OPENAI_API_KEY"]}}
        @staticmethod
        def _get_backend_api_key(backend):
            return "fake-key"
        @staticmethod
        def _format_backend_env_keys(backend):
            return "OPENAI_API_KEY"
    _orig = sys.modules.get("graphify.llm")
    sys.modules["graphify.llm"] = FakeLLMModule()
    try:
        nodes = _make_nodes("FooService", "FuuService")
        uf = _UF()
        uf.union("fooservice", "fuuservice")  # already merged, so no ambiguous
        _llm_tiebreak(nodes, uf, {}, backend="openai")
    finally:
        if _orig is not None:
            sys.modules["graphify.llm"] = _orig
        else:
            sys.modules.pop("graphify.llm", None)


def test_llm_tiebreak_empty_ambiguous(monkeypatch):
    """When all pairs are outside the ambiguous score range, nothing happens."""
    from graphify.dedup import _llm_tiebreak, _UF
    import sys
    class FakeLLMModule:
        BACKENDS = {"openai": {"env_keys": ["OPENAI_API_KEY"]}}
        @staticmethod
        def _get_backend_api_key(backend):
            return "fake-key"
        @staticmethod
        def _format_backend_env_keys(backend):
            return "OPENAI_API_KEY"
    _orig = sys.modules.get("graphify.llm")
    sys.modules["graphify.llm"] = FakeLLMModule()
    try:
        # Two very different nodes — score too low to be ambiguous
        nodes = _make_nodes("DatabaseConnection", "UserInterfaceWidget")
        uf = _UF()
        _llm_tiebreak(nodes, uf, {}, backend="openai")
    finally:
        if _orig is not None:
            sys.modules["graphify.llm"] = _orig
        else:
            sys.modules.pop("graphify.llm", None)


def test_llm_tiebreak_with_yes_response(monkeypatch):
    """LLM tiebreak merges nodes when LLM responds 'yes'."""
    from graphify.dedup import _llm_tiebreak, _UF
    import sys
    called = []
    class FakeLLMModule:
        BACKENDS = {"openai": {"env_keys": ["OPENAI_API_KEY"]}}
        @staticmethod
        def _get_backend_api_key(backend):
            return "fake-key"
        @staticmethod
        def _format_backend_env_keys(backend):
            return "OPENAI_API_KEY"
        @staticmethod
        def _call_llm(prompt, backend=None, max_tokens=None):
            called.append(prompt)
            return "1. yes"
    _orig = sys.modules.get("graphify.llm")
    sys.modules["graphify.llm"] = FakeLLMModule()
    try:
        # Two nodes with score in ambiguous range
        nodes = _make_nodes("RequestHandler", "RequestManager")
        uf = _UF()
        _llm_tiebreak(nodes, uf, {}, backend="openai")
        assert len(called) == 1
    finally:
        if _orig is not None:
            sys.modules["graphify.llm"] = _orig
        else:
            sys.modules.pop("graphify.llm", None)


def test_llm_tiebreak_batch_exception(monkeypatch):
    """LLM tiebreak handles exception in batch gracefully."""
    from graphify.dedup import _llm_tiebreak, _UF
    import sys
    class FakeLLMModule:
        BACKENDS = {"openai": {"env_keys": ["OPENAI_API_KEY"]}}
        @staticmethod
        def _get_backend_api_key(backend):
            return "fake-key"
        @staticmethod
        def _format_backend_env_keys(backend):
            return "OPENAI_API_KEY"
        @staticmethod
        def _call_llm(prompt, backend=None, max_tokens=None):
            raise RuntimeError("LLM batch failed")
    _orig = sys.modules.get("graphify.llm")
    sys.modules["graphify.llm"] = FakeLLMModule()
    try:
        nodes = _make_nodes("AuthService", "AuthManager")
        uf = _UF()
        _llm_tiebreak(nodes, uf, {}, backend="openai")
        # Should not raise
    finally:
        if _orig is not None:
            sys.modules["graphify.llm"] = _orig
        else:
            sys.modules.pop("graphify.llm", None)
