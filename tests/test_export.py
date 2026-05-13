import json
import re
import tempfile
import networkx as nx
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json, to_cypher, to_graphml, to_html, to_canvas, to_obsidian

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
    """Canvas file refs must point at the per-community subfolder the obsidian
    vault writes nodes into (e.g. 'community-0/foo.md'), so the canvas opens
    correctly when used as a vault."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        canvas_path = out_dir / "graph.canvas"
        to_obsidian(G, communities, str(out_dir))
        to_canvas(G, communities, str(canvas_path))
        data = json.loads(canvas_path.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        assert file_nodes, "canvas should contain file nodes"
        for node in file_nodes:
            assert node["file"].endswith(".md")
            # Every canvas file ref must resolve to a real file written by to_obsidian
            assert (out_dir / node["file"]).exists(), (
                f"canvas references {node['file']!r} but it doesn't exist on disk"
            )


# --- to_obsidian: per-community-folder layout -------------------------------

def _tiny_graph_with_colliding_labels():
    """Two functions named foo() in different files + an empty-everything node + a
    plain symbol — exercises the path-aware naming and dedup logic."""
    G = nx.Graph()
    G.add_node("a", label="foo()", source_file="/proj/src/a.py", file_type="code")
    G.add_node("b", label="foo()", source_file="/proj/src/b.py", file_type="code")
    G.add_node("c", label="", source_file="", file_type="code")
    G.add_node("d", label="Bar", source_file="/proj/x.ts", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G.add_edge("a", "d", relation="uses", confidence="INFERRED")
    return G


def test_to_obsidian_writes_per_community_subfolders():
    G = _tiny_graph_with_colliding_labels()
    communities = {0: ["a", "b"], 1: ["c", "d"]}
    labels = {0: "alpha", 1: "beta"}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        to_obsidian(G, communities, str(out), community_labels=labels)
        assert (out / "alpha").is_dir()
        assert (out / "beta").is_dir()
        # Each community folder has an _OVERVIEW.md, not a top-level _COMMUNITY_*.md
        assert (out / "alpha" / "_OVERVIEW.md").exists()
        assert (out / "beta" / "_OVERVIEW.md").exists()
        assert not any(p.name.startswith("_COMMUNITY_") for p in out.iterdir())
        # Top-level _INDEX.md exists and lists both communities
        idx = (out / "_INDEX.md").read_text()
        assert "alpha" in idx and "beta" in idx


def test_to_obsidian_filenames_disambiguate_by_source_path():
    """Two functions with the same label in different files must produce distinct
    filenames derived from the source path — not a `_1` numeric suffix."""
    G = _tiny_graph_with_colliding_labels()
    communities = {0: ["a", "b"], 1: ["c", "d"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        to_obsidian(G, communities, str(out))
        files = list((out / "community-0").glob("*.md"))
        names = sorted(p.stem for p in files if p.name != "_OVERVIEW.md")
        # Both foo() nodes wrote files in community-0, with path-disambiguated stems
        assert len(names) == 2, f"expected 2 distinct files, got {names!r}"
        assert all("foo" in n for n in names)
        # Neither file uses the legacy `_1` collision suffix
        assert not any(n.endswith("_1") for n in names)
        # The disambiguator carries the differing path segment
        assert any("a-py" in n for n in names)
        assert any("b-py" in n for n in names)


def test_to_obsidian_unique_folders_when_community_labels_collide():
    """If three communities all share the same label, each still gets its own
    subfolder and its own _OVERVIEW.md."""
    G = nx.Graph()
    for i, nid in enumerate(["n1", "n2", "n3"]):
        G.add_node(nid, label=f"sym{i}", source_file=f"/p/{i}.py", file_type="code")
    communities = {0: ["n1"], 1: ["n2"], 2: ["n3"]}
    labels = {0: "main", 1: "main", 2: "main"}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        to_obsidian(G, communities, str(out), community_labels=labels)
        # Expect main, main-2, main-3 (in some order)
        subfolders = sorted(p.name for p in out.iterdir() if p.is_dir() and p.name != ".obsidian")
        assert subfolders == ["main", "main-2", "main-3"], subfolders
        for f in subfolders:
            assert (out / f / "_OVERVIEW.md").exists()


def test_to_obsidian_has_no_dangling_wikilinks():
    """Every [[wikilink]] in the vault must resolve to a real file."""
    G = _tiny_graph_with_colliding_labels()
    communities = {0: ["a", "b", "d"], 1: ["c"]}
    labels = {0: "core", 1: "misc"}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        to_obsidian(G, communities, str(out), community_labels=labels)
        md_files = list(out.rglob("*.md"))
        stem_set = {p.stem for p in md_files}
        rel_set = {str(p.relative_to(out).with_suffix("")) for p in md_files}
        link_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
        for md in md_files:
            for m in link_re.finditer(md.read_text()):
                tgt = m.group(1)
                assert tgt in stem_set or tgt in rel_set, (
                    f"dangling wikilink [[{tgt}]] in {md.relative_to(out)}"
                )
