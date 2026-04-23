"""Regression test for PR #476 (v0.4.25) — empty-community filter.

The v2 report rewrite dropped the filter that skipped clustering artifacts
whose entire membership is file-level stubs (`_is_file_node`).  These
"empty" communities inflated the Summary count, added blank "Nodes (0):"
blocks to the Communities section, and polluted the Knowledge Gaps list
with noise.

This test drives `generate` directly with a minimal 2-node graph + two
communities (one real, one stub-only) and asserts the stub community is
suppressed everywhere downstream.  No clustering pipeline (graspologic)
is required.
"""

import networkx as nx

from graphify.report import generate


def _make_graph():
    """Graph with a non-stub class node + two file-level stubs.

    `analyze._is_file_node` treats labels ending in `.py` (or other code
    extensions) as file-level hubs, and labels ending in `()` with degree
    ≤ 1 as isolated function stubs.  Our "class Authenticator" label
    dodges both filters so it reads as a real, non-stub node.
    """
    G = nx.Graph()
    G.add_node("real_class", label="class Authenticator", kind="class")
    G.add_node("file_stub_a", label="auth.py",   kind="file")
    G.add_node("file_stub_b", label="models.py", kind="file")
    G.add_edge("real_class", "file_stub_a", confidence="EXTRACTED")
    G.add_edge("real_class", "file_stub_b", confidence="EXTRACTED")
    return G


def _inputs():
    G = _make_graph()
    communities = {
        0: ["real_class"],                     # non-empty — keep
        1: ["file_stub_a", "file_stub_b"],     # stub-only — drop
    }
    cohesion = {0: 1.0, 1: 0.5}
    labels   = {0: "Community 0", 1: "Community 1"}
    gods     = [{"label": "class Authenticator", "edges": 2}]
    surprises = []
    detection = {"total_files": 2, "total_words": 42, "needs_graph": True, "warning": None}
    tokens = {"input": 0, "output": 0}
    return G, communities, cohesion, labels, gods, surprises, detection, tokens


def test_summary_counts_only_non_empty_communities():
    report = generate(*_inputs(), root="./fixture")
    # 2 raw communities → 1 non-empty.
    assert "1 communities detected" in report
    assert "2 communities detected" not in report


def test_empty_community_not_rendered_in_communities_section():
    report = generate(*_inputs(), root="./fixture")
    # Stub-only community should be fully suppressed — not even an
    # empty "Nodes (0):" block should be emitted.
    assert 'Community 1 - "Community 1"' not in report
    # Sanity: the real one IS rendered.
    assert 'Community 0 - "Community 0"' in report


def test_stub_only_community_excluded_from_knowledge_gaps():
    report = generate(*_inputs(), root="./fixture")
    # thin_communities filter must not flag the stub-only community as
    # "too small to be a meaningful cluster" — it was never a community
    # of real nodes in the first place.
    assert "Thin community `Community 1`" not in report
