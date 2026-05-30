"""Export round-trip and parallel-edge fidelity tests for MultiDiGraph (PR 6).

PR 6 go/no-go gate: "Every export either preserves every parallel edge OR
documents and tests an intentional projection/summarization."

These tests exercise the four fixed exporters (``to_cypher``, ``to_obsidian``,
``to_canvas``, ``to_html``/``to_svg``) plus the natively-lossless ``to_json`` /
``to_graphml`` round-trips, and pin the simple-graph regression strings so the
single-relation path stays byte-stable against the pre-PR6 output.

Fixture style mirrors ``tests/test_export.py`` (tempfile + ``build_from_json``).
"""

import json
import re
import tempfile
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from graphify.build import build_from_json
from graphify.edge_identity import make_stable_key
from graphify.export import (
    to_canvas,
    to_cypher,
    to_graphml,
    to_html,
    to_json,
    to_obsidian,
    to_svg,
)
from graphify.projections import DEFAULT_RELATIONSHIP_CAP

# Relations on the A->B pair (3 parallel edges, distinct source_location).
AB_RELATIONS = ["calls", "imports", "contains"]
# Relations on the C->D pair (5 parallel edges, above DEFAULT_RELATIONSHIP_CAP).
CD_RELATIONS = ["calls", "imports", "contains", "extends", "uses"]


def make_multigraph() -> nx.MultiDiGraph:
    """Build a MultiDiGraph with three pairs:

    - ``A->B``: 3 parallel edges (calls/imports/contains), distinct locations.
    - ``C->D``: 5 parallel edges (> cap), distinct locations.
    - ``E->F``: a single-edge simple-graph control inside the multigraph.
    """
    nodes = [
        {
            "id": n,
            "label": n.upper(),
            "file_type": "code",
            "source_file": f"{n}.py",
            "source_location": "L1",
        }
        for n in ("a", "b", "c", "d", "e", "f")
    ]
    edges = (
        [
            {
                "source": "a",
                "target": "b",
                "relation": rel,
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": f"L{i}",
            }
            for i, rel in enumerate(AB_RELATIONS)
        ]
        + [
            {
                "source": "c",
                "target": "d",
                "relation": rel,
                "confidence": "EXTRACTED",
                "source_file": "c.py",
                "source_location": f"L{i}",
            }
            for i, rel in enumerate(CD_RELATIONS)
        ]
        + [
            {
                "source": "e",
                "target": "f",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "e.py",
                "source_location": "L1",
            }
        ]
    )
    G = build_from_json({"nodes": nodes, "edges": edges}, multigraph=True)
    assert isinstance(G, nx.MultiDiGraph)
    # Sanity: 3 + 5 + 1 = 9 parallel edges preserved at build time.
    assert G.number_of_edges() == 9
    return G


def make_simple_digraph() -> nx.DiGraph:
    """Single-relation directed control graph for byte-stability regression."""
    extraction = {
        "nodes": [
            {
                "id": "A",
                "label": "Alpha",
                "file_type": "code",
                "source_file": "a.py",
                "source_location": "L1",
            },
            {
                "id": "B",
                "label": "Beta",
                "file_type": "code",
                "source_file": "b.py",
                "source_location": "L2",
            },
        ],
        "edges": [
            {
                "source": "A",
                "target": "B",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L1",
            }
        ],
    }
    G = build_from_json(extraction, directed=True)
    assert isinstance(G, nx.DiGraph)
    return G


COMMUNITIES = {0: ["a", "b", "c", "d", "e", "f"]}


# ── Lossless round-trips (preserve every parallel edge) ──────────────────────


def test_json_roundtrip_preserves_all_parallel_edges():
    """to_json -> node_link_graph reconstructs every parallel edge."""
    G = make_multigraph()
    original = G.number_of_edges()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, COMMUNITIES, str(out), force=True)
        data = json.loads(out.read_text())
        # node_link_data stamps multigraph/directed flags so the loader
        # reconstructs a MultiDiGraph automatically.
        assert data.get("multigraph") is True
        assert data.get("directed") is True
        G2 = json_graph.node_link_graph(data, edges="links")
    assert isinstance(G2, nx.MultiDiGraph)
    assert G2.number_of_edges() == original == 9


def test_graphml_roundtrip_preserves_parallel_edges():
    """write_graphml -> read_graphml preserves the parallel edge count."""
    G = make_multigraph()
    original = G.number_of_edges()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        # Must not raise on the multigraph diagnostics graph-attr (dict value).
        to_graphml(G, COMMUNITIES, str(out))
        G2 = nx.read_graphml(out)
    assert G2.is_multigraph()
    assert G2.number_of_edges() == original == 9


# ── Cypher: one distinct relationship per parallel edge ──────────────────────


def test_cypher_emits_distinct_edge_per_parallel():
    """Each parallel edge produces its own MERGE with a distinct edge_key."""
    G = make_multigraph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        content = out.read_text()

    merge_lines = [ln for ln in content.splitlines() if ln.startswith("MATCH")]
    # One MERGE per parallel edge — no Neo4j-side collapse.
    assert len(merge_lines) == G.number_of_edges() == 9

    edge_keys = re.findall(r"edge_key: '([^']+)'", content)
    assert len(edge_keys) == 9
    # Every emitted relationship carries a globally distinct distinguishing key.
    assert len(set(edge_keys)) == 9

    # The three A->B parallel edges all sit between the same endpoints but keep
    # distinct keys, so MERGE treats them as three relationships, not one.
    ab_lines = [
        ln
        for ln in merge_lines
        if "{id: 'a'}" in ln and "{id: 'b'}" in ln
    ]
    assert len(ab_lines) == 3
    ab_keys = set()
    for ln in ab_lines:
        m = re.search(r"edge_key: '([^']+)'", ln)
        assert m is not None
        ab_keys.add(m.group(1))
    assert len(ab_keys) == 3


# ── Canvas: globally unique edge ids + visual cap summary ────────────────────


def test_canvas_edge_ids_unique():
    """Every canvas edge id is unique (no parallel-edge id collisions)."""
    G = make_multigraph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, COMMUNITIES, str(out))
        data = json.loads(out.read_text())

    edge_ids = [e["id"] for e in data["edges"]]
    assert edge_ids, "canvas should contain edges"
    assert len(edge_ids) == len(set(edge_ids)), "canvas edge ids must be unique"

    # Golden / deterministic ordering for the A->B trio (3 <= cap, all drawn).
    ab_ids = sorted(
        e["id"]
        for e in data["edges"]
        if e["fromNode"] == "n_a" and e["toNode"] == "n_b"
    )
    assert ab_ids == ["e_a_b_0", "e_a_b_1", "e_a_b_2"]


def test_canvas_visual_cap_summary():
    """A >cap pair draws at most cap+1 canvas edges with an overflow summary."""
    G = make_multigraph()
    cap = DEFAULT_RELATIONSHIP_CAP
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, COMMUNITIES, str(out))
        data = json.loads(out.read_text())

    cd_edges = [
        e for e in data["edges"] if e["fromNode"] == "n_c" and e["toNode"] == "n_d"
    ]
    # 5 parallel edges -> cap drawn + 1 summary edge.
    assert len(cd_edges) == cap + 1
    cd_ids = sorted(e["id"] for e in cd_edges)
    assert cd_ids == ["e_c_d_0", "e_c_d_1", "e_c_d_2", "e_c_d_summary"]

    summary = next(e for e in cd_edges if e["id"] == "e_c_d_summary")
    # Envelope overflow text: "(+K more, N total)".
    assert "more" in summary["label"]
    assert "5 total" in summary["label"]


# ── Obsidian: all relations per neighbor (capped when > cap) ─────────────────


def test_obsidian_shows_all_relations():
    """to_obsidian lists every relation to a neighbor, capped when above cap."""
    G = make_multigraph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        to_obsidian(G, COMMUNITIES, str(out))
        a_note = (out / "A.md").read_text()
        c_note = (out / "C.md").read_text()

    a_conn = [ln for ln in a_note.splitlines() if ln.startswith("- [[")]
    assert len(a_conn) == 1
    # All three A->B relations are listed, not just the first edge. Assert on the
    # SET of relations present (and the wikilink prefix) rather than a pinned
    # joined order, so a future envelope ordering change does not false-positive.
    assert a_conn[0].startswith("- [[B]] - ")
    for rel in AB_RELATIONS:
        assert rel in a_conn[0]
    # No overflow marker — 3 relations is within DEFAULT_RELATIONSHIP_CAP.
    assert "more" not in a_conn[0]

    # The 5-relation C->D bundle renders the capped envelope form.
    c_conn = [ln for ln in c_note.splitlines() if ln.startswith("- [[")]
    assert len(c_conn) == 1
    assert "more" in c_conn[0]
    assert "5 total" in c_conn[0]


# ── HTML / SVG: visual cap + summary label ───────────────────────────────────


def test_html_svg_visual_cap():
    """HTML and SVG cap parallel edges and surface an overflow summary label."""
    G = make_multigraph()
    cap = DEFAULT_RELATIONSHIP_CAP
    with tempfile.TemporaryDirectory() as tmp:
        html_out = Path(tmp) / "graph.html"
        to_html(G, COMMUNITIES, str(html_out))
        html = html_out.read_text()

        svg_out = Path(tmp) / "graph.svg"
        to_svg(G, COMMUNITIES, str(svg_out), community_labels={0: "Group 0"})
        svg = svg_out.read_text()

    # Summary label for the 5-parallel C->D pair appears in both surfaces.
    assert "5 total" in html
    assert f"+{len(CD_RELATIONS) - cap} more" in html
    assert "5 total" in svg

    # The HTML edge dataset draws at most cap "real" C->D edges plus one summary.
    # Parse RAW_EDGES out of the embedded script to count C->D draws precisely.
    m = re.search(r"const RAW_EDGES = (\[.*?\]);", html, re.DOTALL)
    assert m, "RAW_EDGES array must be embedded in the HTML"
    raw_edges = json.loads(m.group(1))
    cd_real = [
        e
        for e in raw_edges
        if e.get("from") == "c"
        and e.get("to") == "d"
        and e.get("confidence") != "SUMMARY"
    ]
    cd_summary = [
        e
        for e in raw_edges
        if e.get("from") == "c"
        and e.get("to") == "d"
        and e.get("confidence") == "SUMMARY"
    ]
    assert len(cd_real) == cap
    assert len(cd_summary) == 1


# ── Regression: canvas summary edges must not evict real edges (BLOCK 1) ──────


def test_canvas_summary_does_not_displace_real_edges_over_cap():
    """With > 200 real edges, the 200-cap keeps the highest-weight REAL edges and
    summary edges are strictly additive (never evict a real edge).

    Reproduces the priority-inversion bug: summary edges were pushed into the
    weighted top-200 selection with ``float("inf")`` weight, sorting to the FRONT
    and displacing the 201st-highest-weight real edge. A graph with 210 ascending-
    weight single-edge pairs PLUS one low-weight 5-parallel overflow pair must:
      - emit exactly 200 real edges (no summary stealing a real slot),
      - retain the highest-weight real edge,
      - drop the lowest-weight real edge (legitimately over the 200-cap).
    """
    G = nx.MultiDiGraph()
    members: list[str] = []
    for i in range(210):
        a, b = f"a{i}", f"b{i}"
        G.add_node(a, label=a)
        G.add_node(b, label=b)
        # Ascending weights 1..210 so ordering is unambiguous.
        G.add_edge(
            a,
            b,
            relation="calls",
            confidence="EXTRACTED",
            source_file="f.py",
            source_location=f"L{i}",
            weight=float(i + 1),
        )
        members += [a, b]
    # Low-weight overflow pair (5 parallels) — its reals are below the cap line.
    G.add_node("X", label="X")
    G.add_node("Y", label="Y")
    for j in range(5):
        G.add_edge(
            "X",
            "Y",
            relation=f"r{j}",
            confidence="EXTRACTED",
            source_file="x.py",
            source_location=f"LX{j}",
            weight=0.1,
        )
    members += ["X", "Y"]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, {0: members}, str(out))
        edges = json.loads(out.read_text())["edges"]

    real = [e for e in edges if not e["id"].endswith("_summary")]
    # Real edges are capped at EXACTLY 200 — a summary never consumed a real slot.
    assert len(real) == 200
    # Highest-weight real edge survives; lowest-weight one is legitimately dropped.
    assert any(e["fromNode"] == "n_a209" and e["toNode"] == "n_b209" for e in real)
    assert not any(e["fromNode"] == "n_a0" and e["toNode"] == "n_b0" for e in real)
    # All ids remain globally unique.
    ids = [e["id"] for e in edges]
    assert len(ids) == len(set(ids))


def test_canvas_summary_additive_when_overflow_pair_survives():
    """When a high-weight overflow pair survives the 200-cap, its summary edge is
    ADDED on top of the 200 real edges (total > 200), not in place of one."""
    G = nx.MultiDiGraph()
    members: list[str] = []
    for i in range(199):
        a, b = f"a{i}", f"b{i}"
        G.add_node(a, label=a)
        G.add_node(b, label=b)
        G.add_edge(
            a,
            b,
            relation="calls",
            confidence="EXTRACTED",
            source_file="f.py",
            source_location=f"L{i}",
            weight=1.0,
        )
        members += [a, b]
    G.add_node("X", label="X")
    G.add_node("Y", label="Y")
    for j in range(5):
        G.add_edge(
            "X",
            "Y",
            relation=f"r{j}",
            confidence="EXTRACTED",
            source_file="x.py",
            source_location=f"LX{j}",
            weight=100.0,  # high weight -> overflow pair's reals survive the cap
        )
    members += ["X", "Y"]

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, {0: members}, str(out))
        edges = json.loads(out.read_text())["edges"]

    real = [e for e in edges if not e["id"].endswith("_summary")]
    summary = [e for e in edges if e["id"].endswith("_summary")]
    assert len(real) == 200  # real edges still capped at 200
    assert len(summary) == 1  # summary additive (201 total)
    xy_summary = [e for e in summary if e["fromNode"] == "n_X" and e["toNode"] == "n_Y"]
    assert len(xy_summary) == 1
    assert "5 total" in xy_summary[0]["label"]
    ids = [e["id"] for e in edges]
    assert len(ids) == len(set(ids))


# ── Regression: integer positional keys distinguish parallels (BLOCK 2) ───────


def test_cypher_distinguishes_parallels_with_identical_identity_fields():
    """Parallel edges that share IDENTICAL relation/source_file/source_location
    still get DISTINCT edge_keys, so Neo4j MERGE preserves all of them.

    Reproduces the integer-key drop bug: a directly-constructed MultiDiGraph
    yields INTEGER positional keys (0, 1, 2…). The old ``isinstance(key, str)``
    guard discarded them and fell back to make_stable_key(relation, file,
    location) — identical for every edge here — collapsing them to ONE edge_key
    and letting MERGE dedup the parallels. The fix accepts any non-None
    positional key (stringified), which NetworkX guarantees unique per (u, v).
    """
    G = nx.MultiDiGraph()
    G.add_node("A", label="Alpha", file_type="code")
    G.add_node("B", label="Beta", file_type="code")
    # Three parallel edges, byte-identical semantic identity fields.
    for _ in range(3):
        G.add_edge(
            "A",
            "B",
            relation="calls",
            confidence="EXTRACTED",
            source_file="a.py",
            source_location="L1",
        )
    # Positional keys are integers (NetworkX default).
    positional_keys = [k for _u, _v, k in G.edges(keys=True)]
    assert positional_keys == [0, 1, 2]
    assert all(isinstance(k, int) for k in positional_keys)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        content = out.read_text()

    merge_lines = [ln for ln in content.splitlines() if ln.startswith("MATCH")]
    assert len(merge_lines) == G.number_of_edges() == 3
    edge_keys = re.findall(r"edge_key: '([^']+)'", content)
    assert len(edge_keys) == 3
    # The crux: distinct edge_key per parallel edge despite identical identity
    # fields — count distinct == parallel count, so MERGE keeps all three.
    assert len(set(edge_keys)) == 3


# ── Simple-graph regression: byte-stable single-relation output ──────────────


def test_export_simple_graph_regression():
    """Single-relation DiGraph output is pinned exactly (pre-PR6 stability).

    The Cypher line gains a documented `edge_key` property (required so Neo4j
    MERGE never collapses parallel edges); the canvas id gains a `_0` parallel
    suffix. Obsidian's single-relation Connections line is byte-identical to the
    pre-PR6 ``- [[label]] - `relation` [confidence]`` form.
    """
    G = make_simple_digraph()
    comm = {0: ["A", "B"]}
    expected_key = make_stable_key("calls", "a.py", "L1")

    with tempfile.TemporaryDirectory() as tmp:
        # Cypher — exact line including the new edge_key property.
        cypher_out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(cypher_out))
        cypher_lines = [
            ln for ln in cypher_out.read_text().splitlines() if ln.startswith("MATCH")
        ]
        assert cypher_lines == [
            "MATCH (a {id: 'A'}), (b {id: 'B'}) "
            f"MERGE (a)-[:CALLS {{edge_key: '{expected_key}', confidence: 'EXTRACTED'}}]->(b);"
        ]

        # Canvas — single edge keeps deterministic `_0` parallel suffix.
        canvas_out = Path(tmp) / "graph.canvas"
        to_canvas(G, comm, str(canvas_out))
        canvas_edges = json.loads(canvas_out.read_text())["edges"]
        assert canvas_edges == [
            {
                "id": "e_A_B_0",
                "fromNode": "n_A",
                "toNode": "n_B",
                "label": "calls [EXTRACTED]",
            }
        ]

        # Obsidian — byte-identical to the historical single-relation form.
        obs_out = Path(tmp) / "vault"
        to_obsidian(G, comm, str(obs_out))
        conn_lines = [
            ln
            for ln in (obs_out / "Alpha.md").read_text().splitlines()
            if ln.startswith("- [[")
        ]
        assert conn_lines == ["- [[Beta]] - `calls` [EXTRACTED]"]

        # HTML — single edge, no summary edge injected.
        html_out = Path(tmp) / "graph.html"
        to_html(G, comm, str(html_out))
        html = html_out.read_text()
        m = re.search(r"const RAW_EDGES = (\[.*?\]);", html, re.DOTALL)
        assert m
        raw_edges = json.loads(m.group(1))
        assert len(raw_edges) == 1
        assert raw_edges[0]["from"] == "A"
        assert raw_edges[0]["to"] == "B"
        assert raw_edges[0]["confidence"] == "EXTRACTED"
