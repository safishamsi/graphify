"""Tests for graphify.mcp_ingest — MCP config file extraction."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.mcp_ingest import (
    MCP_CONFIG_FILENAMES,
    extract_mcp_config,
    is_mcp_config_path,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _labels(result):
    return [n["label"] for n in result["nodes"]]


def _node_kinds(result):
    return {n["metadata"]["mcp_kind"] for n in result["nodes"] if "metadata" in n}


def _relations(result):
    return {e["relation"] for e in result["edges"]}


def _label_by_kind(result, kind):
    return [
        n["label"]
        for n in result["nodes"]
        if n.get("metadata", {}).get("mcp_kind") == kind
    ]


def _write(tmp_path: Path, name: str, payload) -> Path:
    p = tmp_path / name
    if isinstance(payload, (dict, list)):
        p.write_text(json.dumps(payload), encoding="utf-8")
    else:
        p.write_text(str(payload), encoding="utf-8")
    return p


# ── Detection ────────────────────────────────────────────────────────────────


def test_is_mcp_config_path_recognises_known_filenames():
    for name in (".mcp.json", "claude_desktop_config.json", "mcp.json", "mcp_servers.json"):
        assert is_mcp_config_path(Path(f"/some/dir/{name}")), name


def test_is_mcp_config_path_rejects_generic_json():
    assert not is_mcp_config_path(Path("package.json"))
    assert not is_mcp_config_path(Path("config.json"))
    assert not is_mcp_config_path(Path("tsconfig.json"))


def test_recognised_filenames_set_is_frozen():
    # Public contract: the filename set is exposed and stable.
    assert isinstance(MCP_CONFIG_FILENAMES, frozenset)
    assert ".mcp.json" in MCP_CONFIG_FILENAMES


# ── Happy path with the bundled fixture ──────────────────────────────────────


def test_fixture_parses_without_error():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    assert "error" not in r, r.get("error")
    assert r["nodes"]
    assert r["edges"]


def test_fixture_emits_every_server():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    server_labels = set(_label_by_kind(r, "mcp_server"))
    assert server_labels == {"filesystem", "fetch", "github", "time"}


def test_fixture_emits_commands_as_global_nodes():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    commands = set(_label_by_kind(r, "mcp_command"))
    assert commands == {"npx", "uvx"}


def test_fixture_emits_npm_packages():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    packages = set(_label_by_kind(r, "mcp_package"))
    assert "@modelcontextprotocol/server-filesystem" in packages
    assert "@modelcontextprotocol/server-github" in packages


def test_fixture_emits_python_packages():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    packages = set(_label_by_kind(r, "mcp_package"))
    assert "mcp-server-fetch" in packages
    assert "mcp-server-time" in packages


def test_fixture_strips_version_from_npm_package():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    packages = set(_label_by_kind(r, "mcp_package"))
    # Source has "@modelcontextprotocol/server-github@0.6.2"
    assert "@modelcontextprotocol/server-github" in packages
    assert "@modelcontextprotocol/server-github@0.6.2" not in packages


def test_fixture_emits_env_var_names():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    env_vars = set(_label_by_kind(r, "env_var"))
    assert "FILESYSTEM_ROOT" in env_vars
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in env_vars


def test_env_var_values_never_appear_anywhere():
    # The fixture has GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_PLACEHOLDER_NOT_A_REAL_TOKEN".
    # That string must not appear in any node label, edge label, or metadata value.
    secret = "ghp_PLACEHOLDER_NOT_A_REAL_TOKEN"
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    for n in r["nodes"]:
        assert secret not in n["label"]
        for v in n.get("metadata", {}).values():
            assert secret not in str(v)
    for e in r["edges"]:
        for v in e.values():
            assert secret not in str(v)


def test_filesystem_path_not_persisted_as_node():
    # `args` contains "/tmp/workspace" — args are intentionally NOT persisted
    # as nodes/edges to avoid leaking local filesystem paths.
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    for n in r["nodes"]:
        assert "/tmp/workspace" not in n["label"]


def test_fixture_relations_include_contains_references_requires_env():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    rels = _relations(r)
    assert "contains" in rels
    assert "references" in rels
    assert "requires_env" in rels


def test_no_dangling_edges():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_every_edge_has_confidence_score():
    r = extract_mcp_config(FIXTURES / "sample.mcp.json")
    for e in r["edges"]:
        assert e["confidence"] == "EXTRACTED"
        assert e["confidence_score"] == 1.0
        assert e["weight"] == 1.0


# ── Cross-config emergent edges (global node IDs) ────────────────────────────


def test_same_command_collapses_to_one_node_across_configs(tmp_path):
    # Two configs both use "npx". The mcp_command node should be shared.
    config_a = _write(tmp_path, ".mcp.json", {
        "mcpServers": {"a": {"command": "npx", "args": ["@scope/server-a"]}},
    })
    (tmp_path / "subdir").mkdir()
    config_b = _write(tmp_path / "subdir", "claude_desktop_config.json", {
        "mcpServers": {"b": {"command": "npx", "args": ["@scope/server-b"]}},
    })
    r_a = extract_mcp_config(config_a)
    r_b = extract_mcp_config(config_b)
    cmd_id_a = next(n["id"] for n in r_a["nodes"] if n["metadata"]["mcp_kind"] == "mcp_command")
    cmd_id_b = next(n["id"] for n in r_b["nodes"] if n["metadata"]["mcp_kind"] == "mcp_command")
    assert cmd_id_a == cmd_id_b


def test_same_env_var_collapses_to_one_node_across_configs(tmp_path):
    # Two configs both require OPENAI_API_KEY. The env_var node ID must be identical.
    a = _write(tmp_path, ".mcp.json", {
        "mcpServers": {
            "x": {"command": "npx", "args": ["@scope/x"], "env": {"OPENAI_API_KEY": "v1"}},
        },
    })
    (tmp_path / "sub").mkdir()
    b = _write(tmp_path / "sub", "claude_desktop_config.json", {
        "mcpServers": {
            "y": {"command": "uvx", "args": ["mcp-server-y"], "env": {"OPENAI_API_KEY": "v2"}},
        },
    })
    r_a = extract_mcp_config(a)
    r_b = extract_mcp_config(b)
    env_id_a = next(n["id"] for n in r_a["nodes"] if n["metadata"]["mcp_kind"] == "env_var")
    env_id_b = next(n["id"] for n in r_b["nodes"] if n["metadata"]["mcp_kind"] == "env_var")
    assert env_id_a == env_id_b


def test_same_server_name_in_different_dirs_does_not_collide(tmp_path):
    # Two .mcp.json files in different dirs both declare a "filesystem" server.
    # The server nodes should NOT collide (stem-scoped via parent dir).
    (tmp_path / "proj_a").mkdir()
    (tmp_path / "proj_b").mkdir()
    a = _write(tmp_path / "proj_a", ".mcp.json", {
        "mcpServers": {"filesystem": {"command": "npx", "args": ["@scope/a"]}},
    })
    b = _write(tmp_path / "proj_b", ".mcp.json", {
        "mcpServers": {"filesystem": {"command": "npx", "args": ["@scope/b"]}},
    })
    r_a = extract_mcp_config(a)
    r_b = extract_mcp_config(b)
    srv_a = next(n["id"] for n in r_a["nodes"] if n["metadata"]["mcp_kind"] == "mcp_server")
    srv_b = next(n["id"] for n in r_b["nodes"] if n["metadata"]["mcp_kind"] == "mcp_server")
    assert srv_a != srv_b


# ── Error handling ───────────────────────────────────────────────────────────


def test_missing_mcp_servers_key(tmp_path):
    p = _write(tmp_path, ".mcp.json", {"unrelated": "shape"})
    r = extract_mcp_config(p)
    assert r["nodes"] == []
    assert r["edges"] == []
    assert "no mcpServers map" in r.get("error", "")


def test_nested_mcp_servers_shape(tmp_path):
    # Some tools wrap the map: {"mcp": {"servers": {...}}}
    p = _write(tmp_path, ".mcp.json", {
        "mcp": {"servers": {"x": {"command": "node", "args": ["dist/index.js"]}}},
    })
    r = extract_mcp_config(p)
    assert "error" not in r
    assert "x" in _label_by_kind(r, "mcp_server")
    assert "node" in _label_by_kind(r, "mcp_command")


def test_malformed_json_returns_error(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("{not valid json", encoding="utf-8")
    r = extract_mcp_config(p)
    assert r["nodes"] == []
    assert r["edges"] == []
    assert "json error" in r.get("error", "")


def test_oversize_file_skipped(tmp_path):
    p = tmp_path / ".mcp.json"
    payload = '{"mcpServers":{"x":{"command":"npx","args":["' + ("a" * 2_000_000) + '"]}}}'
    p.write_text(payload, encoding="utf-8")
    r = extract_mcp_config(p)
    assert "too large" in r.get("error", "")


def test_root_not_an_object(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    r = extract_mcp_config(p)
    assert "root is not an object" in r.get("error", "")


def test_non_dict_server_entry_skipped(tmp_path):
    p = _write(tmp_path, ".mcp.json", {
        "mcpServers": {
            "valid": {"command": "npx", "args": ["@scope/pkg"]},
            "broken": ["this", "is", "not", "an", "object"],
        },
    })
    r = extract_mcp_config(p)
    server_labels = _label_by_kind(r, "mcp_server")
    assert "valid" in server_labels
    assert "broken" not in server_labels


# ── Edge case: package detection ─────────────────────────────────────────────


def test_package_detection_skips_flags(tmp_path):
    # First arg is -y (flag); second is the package. Detection should skip the flag.
    p = _write(tmp_path, ".mcp.json", {
        "mcpServers": {"x": {"command": "npx", "args": ["-y", "@scope/server-x"]}},
    })
    r = extract_mcp_config(p)
    assert "@scope/server-x" in _label_by_kind(r, "mcp_package")


def test_no_package_detected_for_unknown_arg_shape(tmp_path):
    # Args don't look like any known package pattern => no package node.
    p = _write(tmp_path, ".mcp.json", {
        "mcpServers": {"x": {"command": "node", "args": ["./local-script.js", "--verbose"]}},
    })
    r = extract_mcp_config(p)
    assert _label_by_kind(r, "mcp_package") == []


def test_server_without_command_still_emits_server_node(tmp_path):
    p = _write(tmp_path, ".mcp.json", {
        "mcpServers": {"x": {"args": ["@scope/server-x"]}},
    })
    r = extract_mcp_config(p)
    assert "x" in _label_by_kind(r, "mcp_server")
    assert _label_by_kind(r, "mcp_command") == []


# ── Integration: dispatch routes filename-matched files to mcp_ingest ────────


def test_dispatch_routes_mcp_filename_to_mcp_extractor(tmp_path):
    # End-to-end: a .mcp.json file goes through _get_extractor and ends up at
    # extract_mcp_config, NOT extract_json.
    from graphify.extract import _get_extractor

    p = _write(tmp_path, ".mcp.json", {
        "mcpServers": {"x": {"command": "npx", "args": ["@scope/server-x"]}},
    })
    extractor = _get_extractor(p)
    assert extractor is extract_mcp_config


def test_dispatch_does_not_reroute_generic_json(tmp_path):
    from graphify.extract import _get_extractor, extract_json

    p = _write(tmp_path, "package.json", {"name": "x", "version": "1.0.0"})
    extractor = _get_extractor(p)
    assert extractor is extract_json
