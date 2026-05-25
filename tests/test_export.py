import json
import tempfile
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json, to_cypher, to_graphml, to_html, to_canvas

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
    assert 'integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"' in content

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
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({"0": "Auth Pipeline", "1": "Community 1"}))
    result = backup_if_protected(tmp_path)
    assert result is not None


def test_backup_default_labels_only(tmp_path):
    """All-default labels → no backup (not curated)."""
    import json
    from graphify.export import backup_if_protected
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({"0": "Community 0", "1": "Community 1"}))
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
    from datetime import date
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    b1 = backup_if_protected(tmp_path)
    (tmp_path / "graph.json").write_text('{"nodes":[{"id":"x"}],"links":[]}')
    b2 = backup_if_protected(tmp_path)
    assert b1 == b2  # still one folder per day
    assert (b2 / "graph.json").read_text() == '{"nodes":[{"id":"x"}],"links":[]}'


def test_backup_env_disable(tmp_path, monkeypatch):
    """GRAPHIFY_NO_BACKUP=1 disables backup entirely."""
    from graphify.export import backup_if_protected
    monkeypatch.setenv("GRAPHIFY_NO_BACKUP", "1")
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    assert backup_if_protected(tmp_path) is None
