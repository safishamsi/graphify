import json
import tempfile
from pathlib import Path
import pytest
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import (
    to_json, to_cypher, to_graphml, to_html, to_canvas, to_obsidian,
    _obsidian_tag, _strip_diacritics, _yaml_str, _viz_node_limit,
    _cypher_escape, _cypher_label, _git_head, prune_dangling_edges,
    attach_hyperedges, to_svg, push_to_neo4j,
)
import networkx as nx

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


# ---------------------------------------------------------------------------
# _obsidian_tag
# ---------------------------------------------------------------------------

def test_obsidian_tag_spaces_become_underscores():
    assert _obsidian_tag("machine learning") == "machine_learning"


def test_obsidian_tag_strips_special_chars():
    assert _obsidian_tag("hello!@#$%world") == "helloworld"


def test_obsidian_tag_preserves_hyphens_and_slashes():
    assert _obsidian_tag("sub-group/part") == "sub-group/part"


# ---------------------------------------------------------------------------
# _strip_diacritics
# ---------------------------------------------------------------------------

def test_strip_diacritics_removes_accents():
    assert _strip_diacritics("café résumé") == "cafe resume"


def test_strip_diacritics_passthrough_ascii():
    assert _strip_diacritics("hello world") == "hello world"


# ---------------------------------------------------------------------------
# _yaml_str
# ---------------------------------------------------------------------------

def test_yaml_str_export_none():
    assert _yaml_str(None) == ""


def test_yaml_str_export_escapes_backslash():
    assert "\\\\" in _yaml_str("\\")


def test_yaml_str_export_escapes_double_quote():
    result = _yaml_str('say "hello"')
    assert '\\"' in result


def test_yaml_str_export_escapes_control():
    result = _yaml_str("\x01")
    assert "\\x01" in result


# ---------------------------------------------------------------------------
# _viz_node_limit
# ---------------------------------------------------------------------------

def test_viz_node_limit_default(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    assert _viz_node_limit() == 5_000


def test_viz_node_limit_from_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "100")
    assert _viz_node_limit() == 100


def test_viz_node_limit_env_zero(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "0")
    assert _viz_node_limit() == 0


def test_viz_node_limit_invalid_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "notanumber")
    assert _viz_node_limit() == 5_000


# ---------------------------------------------------------------------------
# _cypher_escape
# ---------------------------------------------------------------------------

def test_cypher_escape_escapes_quote():
    result = _cypher_escape("it's fine")
    assert "\\'" in result  # backslash + escaped quote


def test_cypher_escape_escapes_backslash():
    result = _cypher_escape("c:\\path")
    assert "\\\\" in result


def test_cypher_escape_removes_null():
    result = _cypher_escape("hello\x00world")
    assert "\x00" not in result


def test_cypher_escape_strips_newline():
    """_cypher_escape filters newlines via the C0 control strip, not by escaping."""
    result = _cypher_escape("line1\nline2")
    assert "\n" not in result


# ---------------------------------------------------------------------------
# _cypher_label
# ---------------------------------------------------------------------------

def test_cypher_label_valid():
    assert _cypher_label("Python", "Fallback") == "Python"


def test_cypher_label_strips_special():
    assert _cypher_label("C++", "Fallback") == "C"


def test_cypher_label_falls_back_on_empty():
    assert _cypher_label("123", "Fallback") == "Fallback"


def test_cypher_label_falls_back_on_none():
    assert _cypher_label(None, "Fallback") == "Fallback"


# ---------------------------------------------------------------------------
# _git_head
# ---------------------------------------------------------------------------

def test_git_head_returns_string_or_none():
    result = _git_head()
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# prune_dangling_edges
# ---------------------------------------------------------------------------

def test_prune_dangling_edges_removes_orphan():
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},  # c is missing
        ],
    }
    cleaned, pruned = prune_dangling_edges(data)
    assert pruned == 1
    assert len(cleaned["links"]) == 1


def test_prune_dangling_edges_no_orphans():
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [{"source": "a", "target": "b"}],
    }
    cleaned, pruned = prune_dangling_edges(data)
    assert pruned == 0
    assert len(cleaned["links"]) == 1


def test_prune_dangling_edges_handles_edges_key():
    data = {
        "nodes": [{"id": "a"}],
        "edges": [
            {"source": "a", "target": "missing"},
        ],
    }
    cleaned, pruned = prune_dangling_edges(data)
    assert pruned == 1


# ---------------------------------------------------------------------------
# attach_hyperedges
# ---------------------------------------------------------------------------

def test_attach_hyperedges_adds_to_empty():
    G = nx.Graph()
    attach_hyperedges(G, [{"id": "h1", "label": "foo"}])
    assert G.graph["hyperedges"] == [{"id": "h1", "label": "foo"}]


def test_attach_hyperedges_deduplicates_by_id():
    G = nx.Graph()
    G.graph["hyperedges"] = [{"id": "h1", "label": "first"}]
    attach_hyperedges(G, [{"id": "h1", "label": "duplicate"}, {"id": "h2", "label": "second"}])
    assert len(G.graph["hyperedges"]) == 2
    assert G.graph["hyperedges"][0]["label"] == "first"


# ---------------------------------------------------------------------------
# to_json force
# ---------------------------------------------------------------------------

def test_to_json_force_override(tmp_path):
    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.json"
    # Write a huge graph first
    huge = {"nodes": [{"id": f"n{i}"} for i in range(1000)], "links": []}
    out.write_text(json.dumps(huge))
    # Without force, smaller graph is refused
    result = to_json(G, communities, str(out), force=False)
    assert result is False
    # With force, it overwrites
    result = to_json(G, communities, str(out), force=True)
    assert result is True
    data = json.loads(out.read_text())
    assert len(data["nodes"]) < 1000


# ---------------------------------------------------------------------------
# to_obsidian (minimal)
# ---------------------------------------------------------------------------

def test_to_obsidian_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        out.mkdir()
        to_obsidian(G, communities, str(out))
        # Should create community notes
        notes = list(out.glob("*.md"))
        assert len(notes) > 0


# ---------------------------------------------------------------------------
# _yaml_str edge cases
# ---------------------------------------------------------------------------

def test_yaml_str_newline():
    result = _yaml_str("line1\nline2")
    assert "\\n" in result


def test_yaml_str_carriage_return():
    result = _yaml_str("a\rb")
    assert "\\r" in result


def test_yaml_str_tab():
    result = _yaml_str("a\tb")
    assert "\\t" in result


def test_yaml_str_null_char():
    result = _yaml_str("a\x00b")
    assert "\\0" in result


def test_yaml_str_u2028():
    result = _yaml_str("a\u2028b")
    assert "\\L" in result


def test_yaml_str_u2029():
    result = _yaml_str("a\u2029b")
    assert "\\P" in result


def test_yaml_str_control_char_below_0x20():
    result = _yaml_str("\x1b")
    assert "\\x1b" in result


def test_yaml_str_del_char():
    result = _yaml_str("\x7f")
    assert "\\x7f" in result


# ---------------------------------------------------------------------------
# _git_head exception path
# ---------------------------------------------------------------------------

def test_git_head_exception_returns_none(monkeypatch):
    import subprocess
    def mock_run(*args, **kwargs):
        raise OSError("git not found")
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert _git_head() is None


# ---------------------------------------------------------------------------
# to_json exception handling
# ---------------------------------------------------------------------------

def test_to_json_corrupted_existing_file(tmp_path):
    """to_json handles corrupted existing json gracefully."""
    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.json"
    out.write_text("not valid json{{{[[[")
    result = to_json(G, communities, str(out), force=False)
    assert result is True  # proceeds with write despite unreadable existing


# ---------------------------------------------------------------------------
# to_canvas duplicate filenames
# ---------------------------------------------------------------------------

def test_to_canvas_duplicate_filenames():
    """Canvas handles duplicate label nodes."""
    G = nx.Graph()
    G.add_node("a", label="same")
    G.add_node("b", label="same")
    communities = {0: ["a", "b"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        filenames = [n["file"] for n in file_nodes]
        # Both should have .md extension but different names
        assert all(f.endswith(".md") for f in filenames)
        assert len(filenames) == len(set(filenames))  # no duplicate filenames


# ---------------------------------------------------------------------------
# to_obsidian cohesion
# ---------------------------------------------------------------------------

def test_to_obsidian_with_cohesion():
    """to_obsidian writes cohesion values in frontmatter and description."""
    G = make_graph()
    communities = cluster(G)
    cohesion = {cid: 0.75 for cid in communities}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        out.mkdir()
        to_obsidian(G, communities, str(out), cohesion=cohesion)
        notes = list(out.glob("_COMMUNITY_*.md"))
        assert len(notes) > 0
        content = notes[0].read_text()
        assert "cohesion" in content
        assert "0.75" in content
        assert "tightly connected" in content


def test_to_obsidian_cohesion_moderate():
    """to_obsidian with cohesion=0.5 says 'moderately connected'."""
    G = nx.Graph()
    G.add_node("a", label="test")
    communities = {0: ["a"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        out.mkdir()
        to_obsidian(G, communities, str(out), cohesion={0: 0.5})
        notes = list(out.glob("_COMMUNITY_*.md"))
        content = notes[0].read_text()
        assert "moderately connected" in content


def test_to_obsidian_cohesion_loose():
    """to_obsidian with low cohesion says 'loosely connected'."""
    G = nx.Graph()
    G.add_node("a", label="test")
    communities = {0: ["a"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        out.mkdir()
        to_obsidian(G, communities, str(out), cohesion={0: 0.3})
        notes = list(out.glob("_COMMUNITY_*.md"))
        content = notes[0].read_text()
        assert "loosely connected" in content


def test_to_obsidian_duplicate_labels():
    """Duplicate node labels get numeric suffixes in filenames."""
    G = nx.Graph()
    G.add_node("a", label="dupe")
    G.add_node("b", label="dupe")
    communities = {0: ["a", "b"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        out.mkdir()
        to_obsidian(G, communities, str(out))
        files = list(out.glob("*.md"))
        names = [f.stem for f in files]
        assert any("_1" in n or "_" in n for n in names if "_COMMUNITY" not in n)


# ---------------------------------------------------------------------------
# to_svg (mocked matplotlib)
# ---------------------------------------------------------------------------

def test_to_svg_creates_file(tmp_path, monkeypatch):
    """to_svg writes an SVG file."""
    pytest.importorskip('matplotlib')
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.svg"
    to_svg(G, communities, str(out))
    assert out.exists()
    content = out.read_text()
    assert "<svg" in content


def test_to_svg_with_labels(tmp_path):
    """to_svg with community_labels includes legend."""
    pytest.importorskip('matplotlib')
    import matplotlib
    matplotlib.use("Agg")
    G = make_graph()
    communities = cluster(G)
    labels = {cid: f"Group {cid}" for cid in communities}
    out = tmp_path / "graph.svg"
    to_svg(G, communities, str(out), community_labels=labels)
    assert out.exists()


def test_to_svg_import_error(monkeypatch, tmp_path):
    """to_svg raises ImportError when matplotlib is missing."""
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("No matplotlib")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.svg"
    with pytest.raises(ImportError, match="matplotlib"):
        to_svg(G, communities, str(out))


# ---------------------------------------------------------------------------
# push_to_neo4j (mocked)
# ---------------------------------------------------------------------------

def test_push_to_neo4j_import_error(monkeypatch):
    """push_to_neo4j raises ImportError when neo4j is not installed."""
    G = make_graph()
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "neo4j" or name.startswith("neo4j."):
            raise ImportError("No module named neo4j")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="neo4j"):
        push_to_neo4j(G, "bolt://localhost:7687", "neo4j", "password")


# ---------------------------------------------------------------------------
# push_to_neo4j — actual push logic (lines 1134-1176)
# ---------------------------------------------------------------------------

def test_push_to_neo4j_successful_push(monkeypatch):
    """push_to_neo4j pushes nodes and edges to Neo4j successfully."""
    import sys
    from unittest.mock import MagicMock, patch

    G = nx.Graph()
    G.add_node("n1", label="Node1", file_type="code")
    G.add_node("n2", label="Node2", file_type="code")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver

    mock_neo4j = MagicMock()
    mock_neo4j.GraphDatabase = mock_graph_db

    with patch.dict(sys.modules, {"neo4j": mock_neo4j}):
        result = push_to_neo4j(G, "bolt://localhost:7687", "neo4j", "password")

    assert result["nodes"] == 2
    assert result["edges"] == 1
    assert mock_session.run.call_count >= 3  # 2 MERGE nodes + 1 MERGE edge


def test_push_to_neo4j_with_communities(monkeypatch):
    """push_to_neo4j attaches community IDs to nodes."""
    import sys
    from unittest.mock import MagicMock, patch

    G = nx.Graph()
    G.add_node("n1", label="Node1", file_type="code")
    G.add_node("n2", label="Node2", file_type="code")
    communities = {0: ["n1", "n2"]}

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver

    mock_neo4j = MagicMock()
    mock_neo4j.GraphDatabase = mock_graph_db

    with patch.dict(sys.modules, {"neo4j": mock_neo4j}):
        result = push_to_neo4j(G, "bolt://localhost:7687", "neo4j", "password", communities=communities)

    assert result["nodes"] == 2

    # Verify community was passed as a property
    all_calls = [str(c) for c in mock_session.run.call_args_list]
    assert any("community" in c for c in all_calls)


# ---------------------------------------------------------------------------
# to_json TypeError fallback (lines 424-425)
# ---------------------------------------------------------------------------

def test_to_json_typeerror_fallback(tmp_path, monkeypatch):
    """to_json handles TypeError when node_link_data doesn't accept edges kwarg."""
    from networkx.readwrite import json_graph

    G = make_graph()
    communities = cluster(G)
    out = tmp_path / "graph.json"

    # Store the real node_link_data for reference
    _real_nld = json_graph.node_link_data
    calls = []

    def mock_node_link_data_first_fails(G_in, **kwargs):
        if "edges" in kwargs and len(calls) == 0:
            calls.append("typeerror")
            raise TypeError("unexpected keyword argument 'edges'")
        calls.append("fallback")
        # When called without edges= kwarg (the fallback),
        # return data with "links" key (simulating older NetworkX behavior)
        data = _real_nld(G_in, **kwargs)
        # Rename "edges" to "links" to match what the code expects
        if "edges" in data:
            data["links"] = data.pop("edges")
        return data

    monkeypatch.setattr(json_graph, "node_link_data", mock_node_link_data_first_fails)

    to_json(G, communities, str(out))
    assert len(calls) >= 2
    assert "typeerror" in calls[0]
    assert out.exists()


# ---------------------------------------------------------------------------
# to_html — aggregated community view (lines 560-586)
# ---------------------------------------------------------------------------

def test_to_html_aggregated_view_explicit_limit(tmp_path, monkeypatch):
    """to_html builds aggregated community view when graph exceeds node_limit."""
    G = nx.Graph()
    # Create more nodes than the limit
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node{i}")
    for i in range(9):
        G.add_edge(f"n{i}", f"n{i+1}")
    communities = {0: [f"n{i}" for i in range(5)], 1: [f"n{i}" for i in range(5, 10)]}

    out = tmp_path / "graph.html"
    to_html(G, communities, str(out), node_limit=5)

    assert out.exists()
    content = out.read_text()
    # Aggregated view should have community nodes
    assert "vis-network" in content


def test_to_html_aggregated_single_community(tmp_path):
    """to_html skips aggregated view when only one community."""
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node{i}")
    communities = {0: [f"n{i}" for i in range(10)]}

    out = tmp_path / "graph.html"
    to_html(G, communities, str(out), node_limit=5)

    # With single community, aggregated view is not useful → no file
    assert not out.exists()


def test_to_html_aggregated_with_labels(tmp_path):
    """to_html aggregated view passes community_labels and member_counts."""
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node{i}")
    for i in range(9):
        G.add_edge(f"n{i}", f"n{i+1}")
    communities = {0: [f"n{i}" for i in range(5)], 1: [f"n{i}" for i in range(5, 10)]}
    labels = {0: "Group A", 1: "Group B"}
    member_counts = {0: 5, 1: 5}

    out = tmp_path / "graph.html"
    to_html(G, communities, str(out), node_limit=5,
            community_labels=labels, member_counts=member_counts)

    assert out.exists()
    content = out.read_text()
    assert "Group A" in content


def test_to_html_default_viz_limit_raises(tmp_path, monkeypatch):
    """to_html raises ValueError when node_limit is None and graph exceeds env limit."""
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "5")
    G = nx.Graph()
    for i in range(10):
        G.add_node(f"n{i}", label=f"Node{i}")
    for i in range(9):
        G.add_edge(f"n{i}", f"n{i+1}")
    communities = {0: [f"n{i}" for i in range(5)], 1: [f"n{i}" for i in range(5, 10)]}

    out = tmp_path / "graph.html"
    with pytest.raises(ValueError, match="too large for HTML viz"):
        to_html(G, communities, str(out))  # node_limit=None → uses env var, raises ValueError
