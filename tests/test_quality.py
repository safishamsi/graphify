import json

from graphify.quality import format_report, inspect_graph


def test_quality_passes_clean_graph(tmp_path):
    graph = {
        "nodes": [{"id": "a", "label": "A", "source_file": "a.md"}],
        "links": [],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    report = inspect_graph(path)
    assert report["status"] == "pass"
    assert report["total_issues"] == 0


def test_quality_reports_schema_defects(tmp_path):
    graph = {
        "nodes": [
            {"id": "a", "source_file": ""},
            "bad",
            {"id": "a", "label": "Duplicate", "source_file": "a.md"},
        ],
        "links": [
            {"source": "a", "target": "missing", "confidence": "INFERRED", "confience_score": 0.8},
            "bad",
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    report = inspect_graph(path)
    assert report["status"] == "fail"
    assert report["issues"]["non_object_nodes"] == 1
    assert report["issues"]["non_object_edges"] == 1
    assert report["issues"]["missing_node_labels"] == 1
    assert report["issues"]["missing_node_source_files"] == 1
    assert report["issues"]["missing_edge_relations"] == 1
    assert report["issues"]["missing_edge_source_files"] == 1
    assert report["issues"]["typo_confience_score_edges"] == 1
    assert report["issues"]["duplicate_node_ids"] == 1
    assert report["issues"]["dangling_edge_endpoints"] == 1
    assert "Graph quality: fail" in format_report(report)


def test_quality_reports_non_list_graph_fields(tmp_path):
    graph = {
        "nodes": {"id": "not_a_list"},
        "links": {"source": "not_a_list"},
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    report = inspect_graph(path)
    assert report["status"] == "fail"
    assert report["nodes"] == 0
    assert report["edges"] == 0
    assert report["issues"]["non_object_nodes"] == 1
    assert report["issues"]["non_object_edges"] == 1
