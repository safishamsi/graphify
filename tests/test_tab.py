"""Tests for generic .tab structured extraction."""
from __future__ import annotations

from pathlib import Path

from graphify.extract import _make_id, collect_files, extract, extract_tab
from graphify.validate import validate_extraction


def labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


def relations(result: dict) -> set[str]:
    return {e["relation"] for e in result["edges"]}


def edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (by_id.get(e["source"], e["source"]), by_id.get(e["target"], e["target"]))
        for e in result["edges"]
        if e["relation"] == relation
    }


def test_uppercase_tab_dispatches_to_extractor(tmp_path):
    path = tmp_path / "CONFIG.TAB"
    path.write_text("ID\tName\n1\tAlpha\n", encoding="utf-8")

    result = extract([path], cache_root=tmp_path, parallel=False)

    assert "CONFIG.TAB" in labels(result)
    assert "ID (column)" in labels(result)
    assert "ID 1" in labels(result)
    assert validate_extraction(result) == []


def test_collect_files_includes_uppercase_tab(tmp_path):
    path = tmp_path / "CONFIG.TAB"
    path.write_text("ID\tName\n1\tAlpha\n", encoding="utf-8")

    assert path in collect_files(tmp_path)


def test_extract_tab_finds_file_columns_and_rows(tmp_path):
    path = tmp_path / "sample.tab"
    path.write_text("ID\tName\tMode\n1\tAlpha\tactive\n2\tBeta\tinactive\n", encoding="utf-8")

    result = extract_tab(path)

    assert "sample.tab" in labels(result)
    assert "ID (column)" in labels(result)
    assert "Name (column)" in labels(result)
    assert "Mode (column)" in labels(result)
    assert "ID 1" in labels(result)
    assert "ID 2" in labels(result)
    assert "contains" in relations(result)
    assert validate_extraction(result) == []


def test_extract_tab_decodes_gb18030(tmp_path):
    path = tmp_path / "sample_gb18030.tab"
    body = "AIType\tScriptFile\tIsPositive\n17673\tscripts\\Map\\成都\\ai\\动物表现\\动物逃跑.lua\t0\n"
    path.write_bytes(body.encode("gb18030"))

    result = extract_tab(path)

    assert "AIType 17673" in labels(result)
    assert "ScriptFile (column)" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_decodes_utf8_bom(tmp_path):
    path = tmp_path / "bom.tab"
    path.write_bytes("ID\tName\n1\tAlpha\n".encode("utf-8-sig"))

    result = extract_tab(path)

    assert "ID 1" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_handles_crlf(tmp_path):
    path = tmp_path / "crlf.tab"
    path.write_bytes(b"ID\tName\r\n1\tAlpha\r\n")

    result = extract_tab(path)

    assert "ID 1" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_header_only_file(tmp_path):
    path = tmp_path / "header-only.tab"
    path.write_text("ID\tName\n", encoding="utf-8")

    result = extract_tab(path)

    assert "ID (column)" in labels(result)
    assert "Name (column)" in labels(result)
    assert "ID 1" not in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_single_column_file(tmp_path):
    path = tmp_path / "single-column.tab"
    path.write_text("Name\nAlpha\nBeta\n", encoding="utf-8")

    result = extract_tab(path)

    assert "Name (column)" in labels(result)
    assert "Name Alpha" in labels(result)
    assert "Name Beta" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_falls_back_to_line_number_when_no_identity_column(tmp_path):
    path = tmp_path / "no-identity.tab"
    path.write_text("A\tB\nx\t1\nx\t1\n\t\n", encoding="utf-8")

    result = extract_tab(path)

    assert "row 2" in labels(result)
    assert "row 3" in labels(result)
    assert "row 4" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_handles_ragged_rows(tmp_path):
    path = tmp_path / "ragged.tab"
    path.write_text("ID\tName\n1\tAlpha\tExtra\n2\n", encoding="utf-8")

    result = extract_tab(path)

    assert "ID 1" in labels(result)
    assert "ID 2" in labels(result)
    assert "extra_1 (column)" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_falls_back_to_line_number_for_empty_identity(tmp_path):
    path = tmp_path / "empty-id.tab"
    path.write_text("ID\tName\n\tAlpha\n2\tBeta\n", encoding="utf-8")

    result = extract_tab(path)

    assert "row 2" in labels(result)
    assert "ID 2" in labels(result)
    assert validate_extraction(result) == []


def test_extract_tab_empty_file_returns_file_node_only(tmp_path):
    path = tmp_path / "empty.tab"
    path.write_text("", encoding="utf-8")

    result = extract_tab(path)

    assert labels(result) == {"empty.tab"}
    assert result["edges"] == []
    assert validate_extraction(result) == []


def test_extract_tab_blank_file_returns_file_node_only(tmp_path):
    path = tmp_path / "blank.tab"
    path.write_text("\n\n", encoding="utf-8")

    result = extract_tab(path)

    assert labels(result) == {"blank.tab"}
    assert result["edges"] == []
    assert validate_extraction(result) == []


def test_extract_tab_normalizes_empty_and_duplicate_headers(tmp_path):
    path = tmp_path / "headers.tab"
    path.write_text("\tName\tName\n1\tAlpha\tBeta\n", encoding="utf-8")

    result = extract_tab(path)

    assert "column_1 (column)" in labels(result)
    assert len([n for n in result["nodes"] if n["label"] == "Name (column)"]) == 2
    assert validate_extraction(result) == []


def test_path_like_cells_emit_references_to_existing_file(tmp_path):
    scripts = tmp_path / "scripts" / "ai"
    scripts.mkdir(parents=True)
    target = scripts / "StandardAI.lua"
    target.write_text("function tick() end\n", encoding="utf-8")
    tab = tmp_path / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/StandardAI.lua\n", encoding="utf-8")

    result = extract_tab(tab)

    assert ("ID 1", "StandardAI.lua") in edge_labels(result, "references")
    target_nodes = [n for n in result["nodes"] if n["label"] == "StandardAI.lua"]
    assert target_nodes
    assert target_nodes[0]["source_file"] == str(tab)
    assert _make_id(str(target)) not in {n["id"] for n in result["nodes"]}
    assert validate_extraction(result) == []


def test_path_reference_connects_to_scanned_file_node(tmp_path):
    scripts = tmp_path / "scripts" / "ai"
    scripts.mkdir(parents=True)
    target = scripts / "StandardAI.lua"
    target.write_text("function tick() end\n", encoding="utf-8")
    tab = tmp_path / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/StandardAI.lua\n", encoding="utf-8")

    result = extract([tab, target], cache_root=tmp_path, parallel=False)

    target_file_ids = {
        n["id"]
        for n in result["nodes"]
        if n["label"] == "StandardAI.lua" and n["source_file"].endswith("scripts/ai/StandardAI.lua")
    }
    assert target_file_ids
    assert any(
        e["target"] in target_file_ids
        for e in result["edges"]
        if e["relation"] == "references"
    )
    assert not any(e.get("target_ref") for e in result["edges"])
    assert not any(
        n["label"] == "StandardAI.lua" and n["source_file"].endswith("ai.tab")
        for n in result["nodes"]
    )
    assert validate_extraction(result) == []


def test_path_reference_resolves_against_project_root_fallback(tmp_path):
    (tmp_path / ".git").mkdir()
    scripts = tmp_path / "scripts" / "ai"
    scripts.mkdir(parents=True)
    target = scripts / "StandardAI.lua"
    target.write_text("function tick() end\n", encoding="utf-8")
    config_dir = tmp_path / "data" / "config"
    config_dir.mkdir(parents=True)
    tab = config_dir / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/StandardAI.lua\n", encoding="utf-8")

    result = extract_tab(tab)

    assert ("ID 1", "StandardAI.lua") in edge_labels(result, "references")
    target_nodes = [n for n in result["nodes"] if n["label"] == "StandardAI.lua"]
    assert target_nodes
    assert target_nodes[0]["source_file"] == str(tab)
    assert _make_id(str(target)) not in {n["id"] for n in result["nodes"]}
    assert validate_extraction(result) == []


def test_project_root_path_reference_connects_to_scanned_file_node(tmp_path):
    (tmp_path / ".git").mkdir()
    scripts = tmp_path / "scripts" / "ai"
    scripts.mkdir(parents=True)
    target = scripts / "StandardAI.lua"
    target.write_text("function tick() end\n", encoding="utf-8")
    config_dir = tmp_path / "data" / "config"
    config_dir.mkdir(parents=True)
    tab = config_dir / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/StandardAI.lua\n", encoding="utf-8")

    result = extract([tab, target], cache_root=tmp_path, parallel=False)

    target_file_ids = {
        n["id"]
        for n in result["nodes"]
        if n["label"] == "StandardAI.lua" and n["source_file"].endswith("scripts/ai/StandardAI.lua")
    }
    assert target_file_ids
    assert any(
        e["target"] in target_file_ids
        for e in result["edges"]
        if e["relation"] == "references"
    )
    assert not any(e.get("target_ref") for e in result["edges"])
    assert not any(
        n["label"] == "StandardAI.lua" and n["source_file"].endswith("ai.tab")
        for n in result["nodes"]
    )
    assert validate_extraction(result) == []


def test_path_like_cells_emit_stub_for_missing_file(tmp_path):
    tab = tmp_path / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts/ai/MissingAI.lua\n", encoding="utf-8")

    result = extract_tab(tab)

    assert ("ID 1", "scripts/ai/MissingAI.lua") in edge_labels(result, "references")
    stub_nodes = [n for n in result["nodes"] if n["label"] == "scripts/ai/MissingAI.lua"]
    assert stub_nodes
    assert stub_nodes[0]["source_file"] == str(tab)
    assert validate_extraction(result) == []


def test_existing_absolute_path_is_kept_as_tab_owned_stub(tmp_path):
    outside = tmp_path.parent / "OutsideAI.lua"
    outside.write_text("function tick() end\n", encoding="utf-8")
    tab = tmp_path / "ai.tab"
    tab.write_text(f"ID\tScript\n1\t{outside}\n", encoding="utf-8")

    result = extract_tab(tab)

    assert ("ID 1", str(outside)) in edge_labels(result, "references")
    stub_nodes = [n for n in result["nodes"] if n["label"] == str(outside)]
    assert stub_nodes
    assert stub_nodes[0]["source_file"] == str(tab)
    assert str(outside) not in {n["source_file"] for n in result["nodes"]}
    assert validate_extraction(result) == []


def test_parent_traversal_path_is_kept_as_tab_owned_stub(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "OutsideAI.lua").write_text("function tick() end\n", encoding="utf-8")
    config_dir = project / "data" / "config"
    config_dir.mkdir(parents=True)
    tab = config_dir / "ai.tab"
    tab.write_text("ID\tScript\n1\t../../../outside/OutsideAI.lua\n", encoding="utf-8")

    result = extract_tab(tab)

    assert ("ID 1", "../../../outside/OutsideAI.lua") in edge_labels(result, "references")
    stub_nodes = [n for n in result["nodes"] if n["label"] == "../../../outside/OutsideAI.lua"]
    assert stub_nodes
    assert stub_nodes[0]["source_file"] == str(tab)
    assert str(outside / "OutsideAI.lua") not in {n["source_file"] for n in result["nodes"]}
    assert validate_extraction(result) == []


def test_url_values_are_not_local_path_references(tmp_path):
    tab = tmp_path / "urls.tab"
    tab.write_text("ID\tUrl\n1\thttps://cdn.example.com/config.json\n", encoding="utf-8")

    result = extract_tab(tab)

    assert "https://cdn.example.com/config.json" not in labels(result)
    assert "references" not in relations(result)
    assert validate_extraction(result) == []


def test_path_columns_do_not_create_value_nodes(tmp_path):
    tab = tmp_path / "paths.tab"
    tab.write_text(
        "ID\tScript\n"
        "1\tscripts/ai/A.lua\n"
        "2\tscripts/ai/B.lua\n"
        "3\tscripts/ai/A.lua\n",
        encoding="utf-8",
    )

    result = extract_tab(tab)

    assert "Script=scripts/ai/A.lua" not in labels(result)
    assert "Script=scripts/ai/B.lua" not in labels(result)
    assert "references" in relations(result)
    assert validate_extraction(result) == []


def test_backslash_paths_are_normalized(tmp_path):
    tab = tmp_path / "ai.tab"
    tab.write_text("ID\tScript\n1\tscripts\\Map\\成都\\ai\\动物表现\\动物逃跑.lua\n", encoding="utf-8")

    result = extract_tab(tab)

    assert any("scripts/Map/成都/ai/动物表现/动物逃跑.lua" == label for label in labels(result))
    assert "references" in relations(result)
    assert validate_extraction(result) == []


def test_low_cardinality_non_constant_values_emit_sets_edges(tmp_path):
    path = tmp_path / "modes.tab"
    path.write_text("ID\tMode\n1\tactive\n2\tinactive\n3\tactive\n", encoding="utf-8")

    result = extract_tab(path)

    assert "Mode=active" in labels(result)
    assert "Mode=inactive" in labels(result)
    value_nodes = [n for n in result["nodes"] if n["label"] == "Mode=active"]
    assert value_nodes[0].get("context") == "table_value"
    assert "sets" in relations(result)
    assert validate_extraction(result) == []


def test_constant_columns_do_not_create_value_hubs(tmp_path):
    path = tmp_path / "constant.tab"
    path.write_text("ID\tAlertRange\n1\t768\n2\t768\n3\t768\n", encoding="utf-8")

    result = extract_tab(path)

    assert "AlertRange=768" not in labels(result)
    assert validate_extraction(result) == []


def test_high_cardinality_columns_do_not_create_value_nodes(tmp_path):
    path = tmp_path / "high-cardinality.tab"
    rows = ["ID\tName"] + [f"{i}\tName{i}" for i in range(1, 31)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = extract_tab(path)

    assert "Name=Name1" not in labels(result)
    assert validate_extraction(result) == []


def test_tab_row_cap_sets_warning_not_error(tmp_path, monkeypatch, capsys):
    import graphify.extract as gx

    monkeypatch.setattr(gx, "_TAB_MAX_ROWS", 2)
    path = tmp_path / "large.tab"
    path.write_text("ID\tName\n1\tA\n2\tB\n3\tC\n", encoding="utf-8")

    result = extract_tab(path)

    assert result.get("truncated") is True
    assert "warnings" in result
    assert "error" not in result
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert validate_extraction(result) == []


def test_tab_byte_cap_does_not_decode_partial_record(tmp_path, monkeypatch, capsys):
    import graphify.extract as gx

    monkeypatch.setattr(gx, "_TAB_MAX_BYTES", 4)
    path = tmp_path / "partial.tab"
    path.write_text("ID\tName\n1\tAlpha\n", encoding="utf-8")

    result = extract_tab(path)

    assert labels(result) == {"partial.tab"}
    assert result["edges"] == []
    assert result.get("truncated") is True
    assert "error" not in result
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert validate_extraction(result) == []
