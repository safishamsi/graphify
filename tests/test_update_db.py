"""Regression test: `graphify update <path>` against a graph.db KB must
preserve the backend AND the semantic (non-AST) nodes that were stored in
graph.db from the original full-pipeline run.

The risk being guarded: --update re-runs AST extraction on code files only.
If the preservation step in watch._rebuild_code regressed (or ignored the
db backend), semantic nodes contributed by the LLM phase of /aag would
silently disappear after the first --update — taking their cluster
memberships with them.
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

from graphify import store
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.extract import extract

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON = sys.executable


def _build_db_kb_with_semantic_node(root: Path) -> tuple[Path, str]:
    """Seed <root>/src/graphify-out/graph.db with real AST nodes from
    sample.py plus one synthetic semantic node whose ID will not be
    produced by re-extraction. Returns (out_dir, semantic_node_id)."""
    src = root / "src"
    src.mkdir()
    shutil.copy(FIXTURES / "sample.py", src / "sample.py")

    ast = extract([src / "sample.py"], cache_root=src)
    assert ast["nodes"], "AST extraction returned no nodes — fixture changed?"
    ast_anchor_id = ast["nodes"][0]["id"]

    semantic_id = "n_synth_semantic_concept"
    extraction = {
        "nodes": ast["nodes"] + [
            {
                "id": semantic_id,
                "label": "Architecture Pattern",
                "file_type": "document",
                "source_file": "paper.md",
                "source_location": "section-4",
            },
        ],
        "edges": ast["edges"] + [
            {
                "source": ast_anchor_id,
                "target": semantic_id,
                "relation": "implements",
                "confidence": "INFERRED",
                "confidence_score": 0.8,
                "source_file": "paper.md",
                "weight": 0.8,
            },
        ],
        "hyperedges": [],
        "input_tokens": 1000,
        "output_tokens": 200,
    }

    G = build_from_json(extraction)
    communities = cluster(G)

    # extract() with cache_root=src creates <src>/graphify-out/cache/, so
    # the dir may already exist from the AST step above.
    out = src / "graphify-out"
    out.mkdir(exist_ok=True)
    store.save(out, G, communities, backend="db")
    assert (out / "graph.db").exists()
    assert not (out / "graph.json").exists()
    return out, semantic_id


def test_update_with_graph_db_preserves_backend_and_semantic_nodes(tmp_path):
    out, semantic_id = _build_db_kb_with_semantic_node(tmp_path)
    src = out.parent

    pre = store.load(out)
    assert semantic_id in pre.nodes
    assert pre.nodes[semantic_id].get("community") is not None, \
        "semantic node was clustered into a community before --update"
    pre_total = pre.number_of_nodes()

    result = subprocess.run(
        [PYTHON, "-m", "graphify", "update", str(src)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"`graphify update` failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    assert store.detect_backend(out) == "db", (
        f"backend flipped from 'db' to {store.detect_backend(out)!r} during --update"
    )
    assert (out / "graph.db").exists()
    assert not (out / "graph.json").exists(), \
        "--update created graph.json next to graph.db (must stay on the db backend)"

    post = store.load(out)
    assert semantic_id in post.nodes, (
        "synthetic semantic node was dropped by --update — preservation logic "
        "in watch._rebuild_code is not honoring the db-backed extraction"
    )
    assert post.nodes[semantic_id].get("community") is not None, \
        "semantic node survived but lost its cluster assignment after --update"

    missing_community = [
        n for n, d in post.nodes(data=True) if d.get("community") is None
    ]
    assert not missing_community, (
        f"{len(missing_community)} node(s) have no community after --update; "
        f"first few: {missing_community[:5]}"
    )

    assert post.number_of_nodes() >= pre_total, (
        f"node count shrank from {pre_total} to {post.number_of_nodes()} after --update "
        f"— semantic content was likely thrown away"
    )


def _build_json_kb_with_aag_labels(root: Path) -> tuple[Path, dict[int, str]]:
    """Build a tiny JSON-backed KB and write community labels under the
    new `.aag_labels.json` filename (what the current aag skill emits)."""
    import json as _json
    src = root / "src"
    src.mkdir()
    shutil.copy(FIXTURES / "sample.py", src / "sample.py")

    ast = extract([src / "sample.py"], cache_root=src)
    assert ast["nodes"]
    extraction = {
        "nodes": ast["nodes"],
        "edges": ast["edges"],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    G = build_from_json(extraction)
    communities = cluster(G)

    out = src / "graphify-out"
    out.mkdir(exist_ok=True)
    store.save(out, G, communities)
    labels = {cid: f"Custom Group {cid}" for cid in communities}
    (out / ".aag_labels.json").write_text(
        _json.dumps({str(k): v for k, v in labels.items()})
    )
    return out, labels


def test_update_preserves_aag_labels_from_skill(tmp_path):
    """The aag skill writes `.aag_labels.json`; running `aag update .`
    afterwards must pick up those labels rather than resetting every
    community to "Community N"."""
    out, labels = _build_json_kb_with_aag_labels(tmp_path)
    src = out.parent

    result = subprocess.run(
        [PYTHON, "-m", "graphify", "update", str(src)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"`graphify update` failed: {result.stderr}\n{result.stdout}"
    )

    report = (out / "GRAPH_REPORT.md").read_text()
    expected_label = next(iter(labels.values()))
    assert expected_label in report, (
        f"label {expected_label!r} from .aag_labels.json missing from "
        f"GRAPH_REPORT.md after update — labels were reset to generic "
        f"'Community N'"
    )


def test_cluster_only_preserves_aag_labels_from_skill(tmp_path):
    """`aag cluster-only` reads community labels before regenerating the
    report. It must accept .aag_labels.json (skill-written), not just
    the legacy .graphify_labels.json."""
    out, labels = _build_json_kb_with_aag_labels(tmp_path)
    src = out.parent

    result = subprocess.run(
        [PYTHON, "-m", "graphify", "cluster-only", str(src)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"`graphify cluster-only` failed: {result.stderr}\n{result.stdout}"
    )

    report = (out / "GRAPH_REPORT.md").read_text()
    expected_label = next(iter(labels.values()))
    assert expected_label in report, (
        f"label {expected_label!r} from .aag_labels.json missing from "
        f"GRAPH_REPORT.md after cluster-only — labels were reset"
    )
