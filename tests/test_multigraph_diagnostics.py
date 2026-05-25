from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify.diagnostics import (
    diagnose_extraction,
    diagnose_file,
    format_diagnostic_json,
    format_diagnostic_report,
    scan_producer_suppression_sites,
)


def _diagnostic_fixture() -> dict:
    return {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
            {"id": "c", "label": "C", "file_type": "code", "source_file": "c.py"},
        ],
        "edges": [
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L1",
                "context": "call",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "imports",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L2",
                "context": "import",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "INFERRED",
                "source_file": "a.py",
                "source_location": "L3",
                "context": "call",
            },
            {
                "source": "a",
                "target": "b",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
                "source_location": "L1",
                "context": "call",
            },
            {
                "source": "a",
                "target": "missing",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
            },
            {
                "source": "a",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": "a.py",
            },
            {
                "source": "c",
                "target": "c",
                "relation": "references",
                "confidence": "EXTRACTED",
                "source_file": "c.py",
            },
        ],
    }


def test_diagnose_extraction_categorizes_same_endpoint_collapse() -> None:
    summary = diagnose_extraction(_diagnostic_fixture(), directed=True)

    assert summary["node_count"] == 3
    assert summary["raw_edge_count"] == 7
    assert summary["valid_candidate_edges"] == 5
    assert summary["missing_endpoint_edges"] == 1
    assert summary["dangling_endpoint_edges"] == 1
    assert summary["self_loop_edges"] == 1
    assert summary["exact_duplicate_edges"] == 1
    assert summary["directed_unique_endpoint_pairs"] == 2
    assert summary["directed_same_endpoint_collapsed_edges"] == 3
    assert summary["same_endpoint_group_count"] == 1
    assert summary["relation_variant_groups"] == 1
    assert summary["source_location_variant_groups"] == 1
    assert summary["post_build_graph_type"] == "DiGraph"
    assert summary["post_build_edge_count"] == 2


def test_diagnose_extraction_accepts_node_link_links_key() -> None:
    extraction = _diagnostic_fixture()
    extraction["links"] = extraction.pop("edges")

    summary = diagnose_extraction(extraction, directed=True)

    assert summary["raw_edge_count"] == 7
    assert summary["directed_same_endpoint_collapsed_edges"] == 3


def test_diagnose_extraction_does_not_mutate_input() -> None:
    extraction = _diagnostic_fixture()
    original = deepcopy(extraction)

    diagnose_extraction(extraction, directed=True)

    assert extraction == original


def test_diagnose_extraction_handles_malformed_shapes_without_crashing() -> None:
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            ["not", "a", "node"],
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [
            None,
            ["not", "an", "edge"],
            {"from": "a", "to": "b", "relation": "legacy_from_to"},
            {"source": "a", "target": {"unhashable": "target"}, "relation": "bad-target"},
            {"source": "a", "target": "missing", "relation": "dangling"},
            {"source": "", "target": "b", "relation": "missing-source"},
        ],
    }

    summary = diagnose_extraction(extraction, directed=True)

    assert summary["node_count"] == 2
    assert summary["raw_edge_count"] == 6
    assert summary["non_object_edges"] == 2
    assert summary["missing_endpoint_edges"] == 1
    assert summary["dangling_endpoint_edges"] == 2
    assert summary["valid_candidate_edges"] == 1
    assert summary["post_build_error"].startswith("TypeError:")


def test_diagnose_extraction_handles_non_list_nodes_and_edges() -> None:
    summary = diagnose_extraction(
        {"nodes": {"id": "a"}, "edges": {"source": "a", "target": "b"}},
        directed=True,
    )

    assert summary["node_count"] == 0
    assert summary["raw_edge_count"] == 0
    assert summary["valid_candidate_edges"] == 0


def test_diagnose_extraction_bounds_examples() -> None:
    summary = diagnose_extraction(_diagnostic_fixture(), directed=True, max_examples=0)

    assert summary["directed_same_endpoint_collapsed_edges"] == 3
    assert summary["examples"] == []


def test_diagnose_extraction_stops_examples_at_requested_limit() -> None:
    extraction = _diagnostic_fixture()
    extraction["nodes"].append(
        {"id": "d", "label": "D", "file_type": "code", "source_file": "d.py"}
    )
    extraction["edges"].extend(
        [
            {"source": "b", "target": "d", "relation": "imports", "source_file": "b.py"},
            {"source": "b", "target": "d", "relation": "calls", "source_file": "b.py"},
        ]
    )

    summary = diagnose_extraction(extraction, directed=True, max_examples=1)

    assert summary["same_endpoint_group_count"] == 2
    assert len(summary["examples"]) == 1


def test_diagnose_extraction_defaults_raw_inputs_to_directed(tmp_path: Path) -> None:
    graph_path = tmp_path / "raw-extraction.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")

    summary = diagnose_file(graph_path)

    assert summary["effective_directed"] is True
    assert summary["post_build_graph_type"] == "DiGraph"


def test_diagnose_file_reads_json_and_formats_report(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")

    summary = diagnose_file(graph_path, directed=True, max_examples=2)
    report = format_diagnostic_report(summary)

    assert summary["input_path"] == str(graph_path)
    assert "[graphify] MultiDiGraph edge-collapse diagnostic" in report
    assert "directed_same_endpoint_collapsed_edges: 3" in report
    assert "relation_variant_groups: 1" in report
    assert "producer_suppression_sites:" in report
    assert "examples:" in report
    assert "a -> b" in report


def test_format_diagnostic_report_includes_build_and_suppression_errors(
    tmp_path: Path,
) -> None:
    summary = diagnose_extraction(
        {
            "nodes": [
                {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
                ["not", "a", "node"],
            ],
            "edges": [],
        },
        extract_path=tmp_path / "missing-extract.py",
    )

    report = format_diagnostic_report(summary)

    assert "post_build_error: TypeError:" in report
    assert "producer_suppression_error: file not found" in report


def test_diagnostic_json_report_is_serializable(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")

    summary = diagnose_file(graph_path, directed=True)
    payload = format_diagnostic_json(summary)

    assert payload["schema_version"] == 1
    assert payload["summary"]["raw_edge_count"] == 7
    assert "producer_suppression" in payload
    json.dumps(payload)


def test_scan_producer_suppression_sites_finds_seen_sets(tmp_path: Path) -> None:
    source = tmp_path / "extract.py"
    source.write_text(
        "\n".join(
            [
                "seen_call_pairs: set[tuple[str, str]] = set()",
                "seen_static_ref_pairs: set[tuple[str, str, str]] = set()",
                "other = set()",
            ]
        ),
        encoding="utf-8",
    )

    result = scan_producer_suppression_sites(source)

    assert result["total_sites"] == 2
    assert result["sites"][0]["name"] == "seen_call_pairs"
    assert result["sites"][0]["tuple_arity"] == 2
    assert result["sites"][1]["tuple_arity"] == 3


def test_scan_producer_suppression_sites_handles_unknown_tuple_arity(tmp_path: Path) -> None:
    source = tmp_path / "extract.py"
    source.write_text("seen_blank: set[tuple[ ]] = set()\n", encoding="utf-8")

    result = scan_producer_suppression_sites(source)

    assert result["total_sites"] == 1
    assert result["sites"][0]["tuple_arity"] == 0


def test_diagnose_file_rejects_oversized_graph(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 16)

    with pytest.raises(ValueError, match="exceeds"):
        diagnose_file(graph_path)


def test_diagnose_file_rejects_non_object_json(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        diagnose_file(graph_path)


def test_diagnose_file_defaults_to_json_directed_flag(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    payload = _diagnostic_fixture()
    payload["directed"] = False
    graph_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = diagnose_file(graph_path)

    assert summary["effective_directed"] is False
    assert summary["post_build_graph_type"] == "Graph"


def test_diagnose_file_explicit_directed_override(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    payload = _diagnostic_fixture()
    payload["directed"] = False
    graph_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = diagnose_file(graph_path, directed=True)

    assert summary["effective_directed"] is True
    assert summary["post_build_graph_type"] == "DiGraph"


def test_scan_producer_suppression_sites_reports_missing_file(tmp_path: Path) -> None:
    result = scan_producer_suppression_sites(tmp_path / "missing-extract.py")

    assert result["total_sites"] == 0
    assert result["sites"] == []
    assert result["error"] == "file not found"


def test_diagnose_multigraph_cli_human_output(monkeypatch, tmp_path: Path, capsys) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "diagnose", "multigraph", "--graph", str(graph_path)],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "[graphify] MultiDiGraph edge-collapse diagnostic" in out
    assert "raw_edges: 7" in out
    assert "effective_directed: True" in out
    assert "directed_same_endpoint_collapsed_edges: 3" in out


def test_diagnose_multigraph_cli_undirected_override(monkeypatch, tmp_path: Path, capsys) -> None:
    graph_path = tmp_path / "graph.json"
    payload = _diagnostic_fixture()
    payload["directed"] = True
    graph_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "diagnose", "multigraph", "--graph", str(graph_path), "--undirected"],
    )

    mainmod.main()

    out = capsys.readouterr().out
    assert "effective_directed: False" in out
    assert "post_build_graph_type: Graph" in out


def test_diagnose_multigraph_cli_max_examples_zero(monkeypatch, tmp_path: Path, capsys) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "diagnose",
            "multigraph",
            "--graph",
            str(graph_path),
            "--max-examples",
            "0",
        ],
    )

    mainmod.main()

    assert "\nexamples:" not in capsys.readouterr().out


def test_diagnose_multigraph_cli_json_output(monkeypatch, tmp_path: Path, capsys) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "diagnose", "multigraph", "--graph", str(graph_path), "--json"],
    )

    mainmod.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["summary"]["directed_same_endpoint_collapsed_edges"] == 3


@pytest.mark.parametrize(
    ("argv_tail", "expected"),
    [
        ([], "Usage: graphify diagnose multigraph"),
        (["wrong"], "Usage: graphify diagnose multigraph"),
        (["multigraph", "--graph"], "error: --graph requires a path"),
        (["multigraph", "--max-examples"], "error: --max-examples requires an integer"),
        (["multigraph", "--max-examples", "many"], "error: --max-examples requires an integer"),
        (["multigraph", "--max-examples", "-1"], "error: --max-examples must be >= 0"),
        (["multigraph", "--unknown"], "error: unknown diagnose option --unknown"),
    ],
)
def test_diagnose_multigraph_cli_usage_errors(
    monkeypatch,
    capsys,
    argv_tail: list[str],
    expected: str,
) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "diagnose", *argv_tail])

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    assert expected in capsys.readouterr().err


def test_diagnose_multigraph_cli_rejects_conflicting_direction_flags(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(_diagnostic_fixture()), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        [
            "graphify",
            "diagnose",
            "multigraph",
            "--graph",
            str(graph_path),
            "--directed",
            "--undirected",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    assert "--directed and --undirected are mutually exclusive" in capsys.readouterr().err
