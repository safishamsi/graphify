import json
import tempfile
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json, to_cypher, to_graphml, to_html, to_canvas
from graphify.graph_loader import GRAPHIFY_PROFILE_KEY, load_graph

FIXTURES = Path(__file__).parent / "fixtures"


def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))


def test_to_json_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        assert out.exists()


def test_to_json_valid_json():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        assert "nodes" in data
        assert "links" in data


def test_to_json_nodes_have_community():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        for node in data["nodes"]:
            assert "community" in node


def test_to_cypher_creates_file():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        assert out.exists()


def test_to_cypher_contains_merge_statements():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        content = out.read_text()
        assert "MERGE" in content


def test_to_graphml_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        assert out.exists()


def test_to_graphml_valid_xml():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "<graphml" in content
        assert "<node" in content


def test_to_graphml_has_community_attribute():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "community" in content


def test_to_html_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        assert out.exists()


def test_to_html_contains_visjs():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "vis-network" in content


def test_to_html_pins_visjs_version_with_sri():
    """vis-network script tag must use a pinned versioned URL with a sha384
    Subresource Integrity hash and crossorigin=anonymous. Without this,
    a compromised CDN could ship arbitrary JavaScript into every rendered
    graph viewer. The hash was verified against the upstream file at
    https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js
    (sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1).
    Bumping the vis-network version MUST update both the URL and the hash.
    """
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()

    # Versioned URL — unversioned `vis-network/standalone/...` is rejected.
    assert "vis-network@9.1.6/standalone/umd/vis-network.min.js" in content
    assert "https://unpkg.com/vis-network/standalone" not in content

    # SRI integrity attribute pinning the known-good hash.
    assert (
        'integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"'
        in content
    )

    # crossorigin="anonymous" is required for SRI on cross-origin scripts.
    assert 'crossorigin="anonymous"' in content


def test_to_html_contains_search():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "search" in content.lower()


def test_to_html_contains_legend_with_labels():
    G = make_graph()
    communities = cluster(G)
    labels = {cid: f"Group {cid}" for cid in communities}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), community_labels=labels)
        content = out.read_text()
        assert "Group 0" in content


def test_to_html_contains_nodes_and_edges():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "RAW_NODES" in content
        assert "RAW_EDGES" in content


def test_to_html_member_counts_accepted():
    """to_html accepts member_counts without raising."""
    G = make_graph()
    communities = cluster(G)
    member_counts = {cid: len(members) for cid, members in communities.items()}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), member_counts=member_counts)
        assert out.exists()


def test_to_canvas_file_paths_relative_to_vault():
    """Node file paths in canvas must be vault-root-relative (just fname.md), not hardcoded."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        assert file_nodes, "canvas should contain file nodes"
        for node in file_nodes:
            assert "/" not in node["file"], f"file path should not contain '/': {node['file']}"
            assert node["file"].endswith(".md")


# ── Issue #834: backup_if_protected ──────────────────────────────────────────


def test_backup_no_graph_json(tmp_path):
    """No graph.json → no backup."""
    from graphify.export import backup_if_protected

    assert backup_if_protected(tmp_path) is None


def test_backup_no_markers(tmp_path):
    """graph.json present but no sentinel and no curated labels → no backup."""
    from graphify.export import backup_if_protected

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    assert backup_if_protected(tmp_path) is None


def test_backup_semantic_marker(tmp_path):
    """graph.json + .graphify_semantic_marker → backup taken."""
    from graphify.export import backup_if_protected

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / "GRAPH_REPORT.md").write_text("# Report")
    (tmp_path / ".graphify_semantic_marker").write_text('{"output_tokens": 1234}')
    result = backup_if_protected(tmp_path)
    assert result is not None
    assert result.is_dir()
    assert (result / "graph.json").exists()
    assert (result / "GRAPH_REPORT.md").exists()
    assert (result / ".graphify_semantic_marker").exists()


def test_backup_curated_labels(tmp_path):
    """graph.json + non-default label in .graphify_labels.json → backup taken."""
    import json
    from graphify.export import backup_if_protected

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_labels.json").write_text(
        json.dumps({"0": "Auth Pipeline", "1": "Community 1"})
    )
    result = backup_if_protected(tmp_path)
    assert result is not None


def test_backup_default_labels_only(tmp_path):
    """All-default labels → no backup (not curated)."""
    import json
    from graphify.export import backup_if_protected

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_labels.json").write_text(
        json.dumps({"0": "Community 0", "1": "Community 1"})
    )
    assert backup_if_protected(tmp_path) is None


def test_backup_same_day_no_accumulation(tmp_path):
    """Same content on same day returns existing backup dir without re-copying."""
    from graphify.export import backup_if_protected
    from datetime import date

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    b1 = backup_if_protected(tmp_path)
    b2 = backup_if_protected(tmp_path)
    assert b1 is not None and b2 is not None
    assert b1 == b2  # same dir, no _2 accumulation
    assert b1.name == date.today().isoformat()


def test_backup_same_day_changed_content(tmp_path):
    """Changed graph.json on same day overwrites the existing backup in place."""
    from graphify.export import backup_if_protected

    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    b1 = backup_if_protected(tmp_path)
    (tmp_path / "graph.json").write_text('{"nodes":[{"id":"x"}],"links":[]}')
    b2 = backup_if_protected(tmp_path)
    assert b2 is not None
    assert b1 == b2  # still one folder per day
    assert (b2 / "graph.json").read_text() == '{"nodes":[{"id":"x"}],"links":[]}'


def test_backup_env_disable(tmp_path, monkeypatch):
    """GRAPHIFY_NO_BACKUP=1 disables backup entirely."""
    from graphify.export import backup_if_protected

    monkeypatch.setenv("GRAPHIFY_NO_BACKUP", "1")
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    assert backup_if_protected(tmp_path) is None


# ── PR 7: graph profile persistence in graph.json ────────────────────────────
#
# to_json must stamp G.graph[GRAPHIFY_PROFILE_KEY] with a graph_type derived
# from the live NetworkX instance so a later load can detect a
# simple-vs-multidigraph mismatch (cache invalidation / watch). The graph_type
# vocabulary ("simple"/"digraph"/"multidigraph") is shared with graph_loader.


def _build_extraction():
    return json.loads((FIXTURES / "extraction.json").read_text())


def test_to_json_writes_multidigraph_profile():
    """A MultiDiGraph export records graph_type=multidigraph and the NetworkX
    multigraph flag in the saved JSON."""
    G = build_from_json(_build_extraction(), multigraph=True)
    assert isinstance(G, nx.MultiDiGraph)
    communities = {0: list(G.nodes)}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out), force=True)
        data = json.loads(out.read_text())
    assert data["graph"][GRAPHIFY_PROFILE_KEY]["graph_type"] == "multidigraph"
    assert data["multigraph"] is True
    assert data["directed"] is True


def test_to_json_writes_digraph_profile():
    """A directed simple graph records graph_type=digraph with directed=True,
    multigraph=False."""
    G = build_from_json(_build_extraction(), directed=True)
    assert isinstance(G, nx.DiGraph) and not G.is_multigraph()
    communities = {0: list(G.nodes)}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out), force=True)
        data = json.loads(out.read_text())
    assert data["graph"][GRAPHIFY_PROFILE_KEY]["graph_type"] == "digraph"
    assert data["directed"] is True
    assert data["multigraph"] is False


def test_to_json_writes_simple_profile():
    """An undirected nx.Graph records graph_type=simple."""
    G = build_from_json(_build_extraction())
    assert type(G) is nx.Graph
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
    assert data["graph"][GRAPHIFY_PROFILE_KEY]["graph_type"] == "simple"
    assert data["directed"] is False
    assert data["multigraph"] is False


def test_to_json_profile_roundtrips_through_loader():
    """to_json -> load_graph reconstructs the same graph_type for every type,
    proving the profile survives a save/load cycle."""
    cases = [
        (build_from_json(_build_extraction()), "simple", nx.Graph),
        (build_from_json(_build_extraction(), directed=True), "digraph", nx.DiGraph),
        (build_from_json(_build_extraction(), multigraph=True), "multidigraph", nx.MultiDiGraph),
    ]
    for G, expected_type, expected_cls in cases:
        communities = {0: list(G.nodes)}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "graph.json"
            to_json(G, communities, str(out), force=True)
            data = json.loads(out.read_text())
            reloaded = load_graph(data, require_capabilities=False)
        assert isinstance(reloaded, expected_cls)
        assert reloaded.graph[GRAPHIFY_PROFILE_KEY]["graph_type"] == expected_type
        # node_link_graph (the lower-level loader) also sees G.graph metadata.
        nlg = json_graph.node_link_graph(data, edges="links")
        assert nlg.graph[GRAPHIFY_PROFILE_KEY]["graph_type"] == expected_type


def test_to_json_simple_graph_regression():
    """Simple-graph output is unchanged except for the added graphify_profile.

    The "graph" metadata object gains exactly one key (graphify_profile); it was
    empty ({}) before. Stripping that key leaves the pre-PR7 empty object, and
    every other structural key (nodes/links/directed/multigraph/hyperedges) is
    unaffected.
    """
    G = build_from_json(_build_extraction())
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())

    # The only added graph-metadata content is the profile.
    assert data["graph"] == {GRAPHIFY_PROFILE_KEY: {"graph_type": "simple"}}
    # Removing the profile yields the pre-change empty "graph" object — nothing
    # else leaked into the graph-level metadata.
    data["graph"].pop(GRAPHIFY_PROFILE_KEY)
    assert data["graph"] == {}
    # Core structural keys remain present and well-formed.
    assert isinstance(data["nodes"], list) and data["nodes"]
    assert isinstance(data["links"], list)
    assert data["directed"] is False
    assert data["multigraph"] is False
    for node in data["nodes"]:
        assert "id" in node and "community" in node


# ── RISK 4: empty-merge floor in to_json (Guard 1) ───────────────────────────
#
# to_json must refuse to overwrite a populated on-disk graph.json (>0 nodes)
# with an EMPTY (0-node) graph — a 0-node write over a populated graph is a
# failed/aborted extraction, never a real result. This floor engages
# REGARDLESS of force=True (force is the bug enabler here), and only when the
# *new* graph has 0 nodes AND the existing file is populated. It must NOT block
# a fresh empty write (no existing file), a non-zero dedup shrink, or a
# 0-over-0 write (nothing populated to protect).


def test_to_json_floor_blocks_zero_over_populated_even_with_force(tmp_path):
    """Existing populated graph.json + a 0-node graph with force=True must be
    refused (return False) and leave the on-disk graph untouched. This is the
    RED-before-fix case: without the floor, force=True wipes 4 nodes to 0."""
    out = tmp_path / "graph.json"

    # Seed a populated graph.json (4 nodes) via the real write path.
    populated = build_from_json(_build_extraction())
    assert populated.number_of_nodes() == 4
    assert to_json(populated, cluster(populated), str(out), force=True) is True
    assert len(json.loads(out.read_text())["nodes"]) == 4

    # Attempt to overwrite with a 0-node graph, force=True.
    empty = nx.Graph()
    assert empty.number_of_nodes() == 0
    assert to_json(empty, {}, str(out), force=True) is False

    # The previous populated graph is preserved on disk.
    assert len(json.loads(out.read_text())["nodes"]) == 4


def test_to_json_floor_blocks_zero_over_populated_without_force(tmp_path, capsys):
    """Guard 1 (not the pre-existing shrink guard) fires for force=False + 0-node
    over populated.  Pre-fix the shrink guard fired and emitted a WARNING; Guard 1
    emits a distinct ERROR message.  Asserting the exact Guard-1 text makes this
    test red-before-fix / green-after-fix, eliminating the vacuousness identified
    by the bug-hunter."""
    out = tmp_path / "graph.json"

    populated = build_from_json(_build_extraction())
    assert populated.number_of_nodes() == 4
    assert to_json(populated, cluster(populated), str(out), force=True) is True
    assert len(json.loads(out.read_text())["nodes"]) == 4

    empty = nx.Graph()
    result = to_json(empty, {}, str(out), force=False)

    # Guard 1 must have fired: return False and preserve the on-disk graph.
    assert result is False
    assert len(json.loads(out.read_text())["nodes"]) == 4

    # The exact Guard-1 ERROR message must appear on stderr.  Pre-fix the shrink
    # guard fires instead and emits a WARNING with different text, making the
    # assertion below fail on unfixed code.
    captured = capsys.readouterr()
    assert (
        "[graphify] ERROR: refusing to overwrite a populated graph.json "
        "(4 nodes) with an EMPTY (0-node) graph - this is a "
        "failed/aborted extraction, not a real result. The previous "
        "graph is preserved."
    ) in captured.err


def test_to_json_allows_fresh_empty_no_existing_file(tmp_path):
    """A7: no existing file + 0-node graph + force=True is allowed — the floor
    must NOT engage when existing_path.exists() is False. Writes a valid
    0-node graph.json."""
    out = tmp_path / "graph.json"
    assert not out.exists()

    empty = nx.Graph()
    assert to_json(empty, {}, str(out), force=True) is True

    data = json.loads(out.read_text())
    assert data["nodes"] == []


def test_to_json_allows_nonzero_dedup_shrink_with_force(tmp_path):
    """A10: existing 4 nodes, new 2-node graph, force=True is allowed — only a
    new graph with 0 nodes trips the floor. A non-zero dedup/shrink under force
    is a legitimate result."""
    out = tmp_path / "graph.json"

    populated = build_from_json(_build_extraction())
    assert populated.number_of_nodes() == 4
    assert to_json(populated, cluster(populated), str(out), force=True) is True
    assert len(json.loads(out.read_text())["nodes"]) == 4

    smaller = nx.Graph()
    smaller.add_node("a")
    smaller.add_node("b")
    assert smaller.number_of_nodes() == 2
    assert to_json(smaller, {}, str(out), force=True) is True

    assert len(json.loads(out.read_text())["nodes"]) == 2


def test_to_json_allows_zero_over_empty_existing(tmp_path):
    """An existing file with 0 nodes + a new 0-node graph is allowed — there is
    nothing populated to protect, so the floor must NOT engage."""
    out = tmp_path / "graph.json"

    # Seed a 0-node graph.json (no existing file → floor inert on first write).
    first_empty = nx.Graph()
    assert to_json(first_empty, {}, str(out), force=True) is True
    assert json.loads(out.read_text())["nodes"] == []

    # Overwrite 0-over-0: allowed.
    second_empty = nx.Graph()
    assert to_json(second_empty, {}, str(out), force=True) is True
    assert json.loads(out.read_text())["nodes"] == []
