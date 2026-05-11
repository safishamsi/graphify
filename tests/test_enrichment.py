from __future__ import annotations

import json
import sys

from graphify.build import build, build_from_json, build_merge, edge_data
from graphify.ast_lsp import write_lsp_exchange
from graphify.enrichment import load_enrichments, merge_enrichments
from graphify.export import to_json
from graphify.lsp_definition_hook import (
    command_label,
    initialize_capabilities,
    main as lsp_definition_main,
    sanitized_command,
    under_limit,
)
from graphify.lsp_enrichment import apply_lsp_enrichment
from graphify.pipeline_hooks import has_disabled_lsp_hooks, load_hook_config, run_lsp_hooks
from graphify.pipeline import finalize_extraction_files, finalize_extraction_for_build, merge_ast_semantic


def _enable_hooks(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_NO_HOOKS", raising=False)
    monkeypatch.setenv("GRAPHIFY_ENABLE_HOOKS", "1")


def test_lsp_initialize_capabilities_do_not_advertise_workspace_configuration():
    capabilities = initialize_capabilities()

    assert capabilities["textDocument"]["definition"]["linkSupport"] is True
    assert "workspace" not in capabilities


def test_enrichment_fragments_merge_into_exported_graph(tmp_path):
    base = {
        "nodes": [
            {
                "id": "runner",
                "label": "runner()",
                "file_type": "code",
                "source_file": "runner.rb",
            },
            {
                "id": "inventory_record_first",
                "label": "Inventory::Record.first()",
                "file_type": "code",
                "source_file": "inventory/record.rb",
            },
        ],
        "edges": [],
    }
    sidecar = tmp_path / "lsp_edges.json"
    sidecar.write_text(
        json.dumps({
            "generated_by": "ruby-lsp-injector-test",
            "language": "ruby",
            "edges": [
                {
                    "source": "runner",
                    "target": "inventory_record_first",
                    "relation": "calls",
                    "context": "lsp_definition",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": "runner.rb",
                    "source_location": "L2",
                }
            ],
        }),
        encoding="utf-8",
    )

    merged = merge_enrichments(base, load_enrichments([sidecar]))
    G = build([merged], dedup=False)
    out = tmp_path / "graph.json"
    to_json(G, {0: list(G.nodes)}, str(out), force=True)
    data = json.loads(out.read_text(encoding="utf-8"))

    assert any(
        e["source"] == "runner"
        and e["target"] == "inventory_record_first"
        and e["context"] == "lsp_definition"
        for e in data["links"]
    )
    assert "unresolved_calls" not in data
    assert data["enrichments"][0]["generated_by"] == "ruby-lsp-injector-test"


def test_build_preserves_structural_edge_when_lsp_duplicates_pair():
    graph = build_from_json({
        "nodes": [
            {
                "id": "runner",
                "label": "runner()",
                "file_type": "code",
                "source_file": "runner.rb",
            },
            {
                "id": "target",
                "label": "target()",
                "file_type": "code",
                "source_file": "target.rb",
            },
        ],
        "edges": [
            {
                "source": "runner",
                "target": "target",
                "relation": "calls",
                "context": "call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": "runner.rb",
                "source_location": "L2",
            },
            {
                "source": "runner",
                "target": "target",
                "relation": "calls",
                "context": "lsp_definition:ruby:ruby-lsp",
                "confidence": "INFERRED",
                "confidence_score": 0.82,
                "lsp_promotion": "unique_local_definition",
                "lsp_resolvers": ["ruby-lsp"],
                "lsp_servers": ["ruby-lsp"],
                "lsp_callsite_count": 1,
            },
        ],
    })

    edge = edge_data(graph, "runner", "target")

    assert edge["context"] == "call"
    assert edge["confidence"] == "EXTRACTED"
    assert edge["lsp_contexts"] == ["lsp_definition:ruby:ruby-lsp"]
    assert edge["lsp_promotion"] == "unique_local_definition"
    assert edge["contexts"] == ["call", "lsp_definition:ruby:ruby-lsp"]


def test_unresolved_calls_written_as_lsp_exchange(tmp_path):
    graphify_out = tmp_path / "graphify-out"
    path, languages = write_lsp_exchange(
        graphify_out,
        {
            "nodes": [
                {
                    "id": "runner",
                    "label": "runner()",
                    "source_file": "runner.rb",
                    "source_location": "L1",
                }
            ],
            "unresolved_calls": [
                {
                    "caller": "runner",
                    "callee": "first",
                    "receiver": "self",
                    "source_file": "runner.rb",
                }
            ],
        },
        root=tmp_path,
        source_files=[tmp_path / "runner.rb"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert languages == {"ruby"}
    assert data["count"] == 1
    assert data["symbol_count"] == 1
    assert "root" not in data
    assert data["languages"] == ["ruby"]
    assert data["unresolved_calls"][0]["language"] == "ruby"
    assert data["unresolved_calls"][0]["call_id"].startswith("call_")
    assert data["symbols"][0]["language"] == "ruby"
    assert data["symbols"][0]["source_line"] == 1


def test_lsp_evidence_skips_receiver_call_without_type_proof(tmp_path):
    sidecar = tmp_path / "ruby_lsp.json"
    sidecar.write_text(
        json.dumps({
            "generated_by": "test",
            "language": "ruby",
            "lsp_server": "ruby-lsp",
            "lsp_evidence": [
                {
                    "call_id": "call_1",
                    "caller": "caller",
                    "callee": "first",
                    "receiver": "items",
                    "source_file": "caller.rb",
                    "source_location": "L2",
                    "definitions": [
                        {
                            "uri": "file:///workspace/src/inventory/record.rb",
                            "range": {"start": {"line": 0, "character": 0}},
                            "target_id": "inventory_record_first",
                            "target": {"id": "inventory_record_first"},
                            "definition_file": "src/inventory/record.rb",
                        }
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )

    chunk = load_enrichments([sidecar])[0]

    assert chunk["edges"] == []
    assert chunk["enrichments"][0]["promotion"]["receiver_without_type_skipped"] == 1


def test_lsp_evidence_promotes_unique_target_with_receiver_type_proof(tmp_path):
    sidecar = tmp_path / "ruby_lsp.json"
    sidecar.write_text(
        json.dumps({
            "generated_by": "test",
            "language": "ruby",
            "lsp_server": "ruby-lsp",
            "lsp_evidence": [
                {
                    "call_id": "call_1",
                    "caller": "caller",
                    "callee": "domain_call",
                    "receiver": "service",
                    "receiver_type": "Services::Domain",
                    "receiver_type_confidence": 0.9,
                    "source_file": "caller.rb",
                    "source_location": "L2",
                    "definitions": [
                        {
                            "uri": "file:///workspace/src/services/domain.rb",
                            "range": {"start": {"line": 4, "character": 2}},
                            "target_id": "services_domain_domain_call",
                            "target": {"id": "services_domain_domain_call"},
                            "definition_file": "src/services/domain.rb",
                        }
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )

    chunk = load_enrichments([sidecar])[0]

    assert len(chunk["edges"]) == 1
    edge = chunk["edges"][0]
    assert edge["confidence"] == "INFERRED"
    assert edge["target"] == "services_domain_domain_call"
    assert edge["definition_file"] == "src/services/domain.rb"
    assert "definition_uri" not in edge
    assert edge["receiver_type"] == "Services::Domain"


def test_lsp_evidence_aggregates_duplicate_promoted_callsites(tmp_path):
    sidecar = tmp_path / "ruby_lsp.json"
    evidence = []
    for line in ("L2", "L5"):
        evidence.append({
            "call_id": f"call_{line}",
            "caller": "caller",
            "callee": "target",
            "receiver": "self",
            "source_file": "caller.rb",
            "source_location": line,
            "definitions": [
                {
                    "target_id": "target_method",
                    "target": {"id": "target_method"},
                    "definition_file": "target.rb",
                }
            ],
        })
    sidecar.write_text(
        json.dumps({
            "generated_by": "test",
            "language": "ruby",
            "lsp_server": "ruby-lsp",
            "lsp_evidence": evidence,
        }),
        encoding="utf-8",
    )

    chunk = load_enrichments([sidecar])[0]

    assert len(chunk["edges"]) == 1
    edge = chunk["edges"][0]
    assert edge["source"] == "caller"
    assert edge["target"] == "target_method"
    assert edge["lsp_callsite_count"] == 2
    assert "call_id" not in edge
    promotion = chunk["enrichments"][0]["promotion"]
    assert promotion["promoted_callsites"] == 2
    assert promotion["promoted"] == 1
    assert promotion["collapsed_promoted_callsites"] == 1


def test_lsp_evidence_confirms_same_callsite_across_resolvers(tmp_path):
    for index, resolver in enumerate(("ruby-lsp", "solargraph"), start=1):
        (tmp_path / f"{resolver}.json").write_text(
            json.dumps({
                "generated_by": "test",
                "language": "ruby",
                "lsp_server": resolver,
                "metadata": {
                    "resolver_name": resolver,
                    "request_concurrency": index,
                    "request_timeout": 30,
                    "root": "<workspace>",
                    "root_uri": "file://<workspace>",
                    "server_cwd": "<workspace>",
                    "settle_seconds": 5,
                },
                "lsp_evidence": [
                    {
                        "call_id": "call_1",
                        "caller": "caller",
                        "callee": "target",
                        "receiver": "self",
                        "source_file": "caller.rb",
                        "source_location": "L2",
                        "definitions": [
                            {
                                "target_id": "target_method",
                                "target": {"id": "target_method"},
                                "definition_file": "target.rb",
                            }
                        ],
                    }
                ],
            }),
            encoding="utf-8",
        )

    chunk = load_enrichments([tmp_path])[0]

    assert len(chunk["edges"]) == 1
    edge = chunk["edges"][0]
    assert edge["target"] == "target_method"
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.92
    assert edge["lsp_promotion"] == "confirmed_unique_local_definition"
    assert edge["lsp_resolvers"] == ["ruby-lsp", "solargraph"]
    assert edge["lsp_resolver_count"] == 2
    promotion = chunk["enrichments"][0]["promotion"]
    assert promotion["confirmed_callsites"] == 1
    assert promotion["promoted"] == 1
    assert promotion["promoted_callsites"] == 1
    metadata = chunk["enrichments"][0]
    assert metadata["request_concurrency"] == [1, 2]
    assert metadata["request_timeout"] == 30
    assert metadata["root"] == "<workspace>"
    assert metadata["root_uri"] == "file://<workspace>"
    assert metadata["server_cwd"] == "<workspace>"
    assert metadata["settle_seconds"] == 5


def test_lsp_evidence_conflict_across_resolvers_becomes_ambiguous(tmp_path):
    for resolver, target in (
        ("ruby-lsp", "target_method_a"),
        ("solargraph", "target_method_b"),
    ):
        (tmp_path / f"{resolver}.json").write_text(
            json.dumps({
                "generated_by": "test",
                "language": "ruby",
                "lsp_server": resolver,
                "metadata": {"resolver_name": resolver},
                "lsp_evidence": [
                    {
                        "call_id": "call_1",
                        "caller": "caller",
                        "callee": "target",
                        "receiver": "self",
                        "source_file": "caller.rb",
                        "source_location": "L2",
                        "definitions": [
                            {
                                "target_id": target,
                                "target": {"id": target},
                                "definition_file": f"{target}.rb",
                            }
                        ],
                    }
                ],
            }),
            encoding="utf-8",
        )

    chunk = load_enrichments([tmp_path])[0]

    assert len(chunk["edges"]) == 2
    assert {edge["target"] for edge in chunk["edges"]} == {
        "target_method_a",
        "target_method_b",
    }
    assert {edge["confidence"] for edge in chunk["edges"]} == {"AMBIGUOUS"}
    assert {edge["lsp_promotion"] for edge in chunk["edges"]} == {"conflicting_definitions"}
    for edge in chunk["edges"]:
        assert edge["confidence_score"] == 0.25
        assert edge["lsp_conflict_targets"] == ["target_method_a", "target_method_b"]
    promotion = chunk["enrichments"][0]["promotion"]
    assert promotion["ambiguous"] == 1
    assert promotion["conflicting_callsites"] == 1
    assert promotion["ambiguous_edges"] == 2
    assert promotion["promoted"] == 2


def test_enrichment_metadata_summarizes_large_debug_fields(tmp_path):
    sidecar = tmp_path / "debug.json"
    sidecar.write_text(
        json.dumps({
            "generated_by": "test",
            "metadata": {
                "resolver_name": "ruby-lsp",
                "unmapped_definitions": [{"i": i} for i in range(50)],
                "empty_definition_calls": [{"i": i} for i in range(20)],
                "error_details": [{"error": "boom"}],
                "server_command": ["/home/dev/.local/bin/ruby-lsp"],
                "server_stderr_tail": ["/home/dev/.cache/tool/index"],
            },
            "edges": [],
        }),
        encoding="utf-8",
    )

    metadata = load_enrichments([sidecar])[0]["enrichments"][0]

    assert "unmapped_definitions" not in metadata
    assert metadata["unmapped_definitions_count"] == 50
    assert metadata["empty_definition_calls_count"] == 20
    assert metadata["error_details_count"] == 1
    assert "error_details_sample" not in metadata
    assert "server_command" not in metadata
    assert metadata["server_command_count"] == 1
    assert metadata["server_stderr_tail_count"] == 1
    assert "server_stderr_tail_sample" not in metadata


def test_lsp_command_metadata_sanitizes_path_tokens():
    command = [
        "/home/dev/.local/pipx/venvs/graphify/bin/python",
        "/home/dev/work/graphify/graphify/lsp_definition_hook.py",
        "ruby",
        "--",
        "/home/dev/.local/bin/ruby-lsp",
    ]

    assert sanitized_command(command) == [
        "python",
        "lsp_definition_hook.py",
        "ruby",
        "--",
        "ruby-lsp",
    ]
    assert command_label(command) == "python lsp_definition_hook.py ruby -- ruby-lsp"
    assert sanitized_command([r"C:\Users\dev\bin\ruby-lsp.cmd"]) == ["ruby-lsp.cmd"]


def test_lsp_debug_limit_semantics():
    assert not under_limit([], 0)
    assert not under_limit([{"i": 1}], 0)
    assert under_limit([], 1)
    assert not under_limit([{"i": 1}], 1)
    assert under_limit([{"i": i} for i in range(100)], -1)


def test_lsp_definition_hook_records_runtime_metadata_without_absolute_paths(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    graphify_out = root / "graphify-out"
    enrichment_dir = graphify_out / "enrichment" / "lsp"
    exchange = graphify_out / "unresolved_calls.json"
    enrichment_dir.mkdir(parents=True)
    exchange.write_text(
        json.dumps({
            "schema_version": 1,
            "unresolved_calls": [],
            "symbols": [],
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("GRAPHIFY_ROOT", str(root))
    monkeypatch.setenv("GRAPHIFY_UNRESOLVED_CALLS", str(exchange))
    monkeypatch.setenv("GRAPHIFY_ENRICHMENT_DIR", str(enrichment_dir))
    monkeypatch.setenv("GRAPHIFY_HOOK_NAME", "ruby:ruby-lsp")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lsp_definition_hook.py",
            "ruby",
            "--settle-seconds",
            "6",
            "--request-timeout",
            "30",
            "--",
            "/Users/example/.local/bin/ruby-lsp",
        ],
    )

    assert lsp_definition_main() == 0

    output = json.loads((enrichment_dir / "ruby_ruby-lsp_lsp_edges.json").read_text(encoding="utf-8"))
    metadata = output["metadata"]
    assert metadata["root"] == "<workspace>"
    assert metadata["root_uri"] == "file://<workspace>"
    assert metadata["server_cwd"] == "<workspace>"
    assert metadata["settle_seconds"] == 6
    assert metadata["request_timeout"] == 30
    assert metadata["server_command"] == ["ruby-lsp"]
    assert str(root) not in json.dumps(metadata)


def test_hook_config_loads_config_json_and_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_CONFIG", raising=False)

    assert load_hook_config(tmp_path) == {}

    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps({"lsp": {"cache": False}}), encoding="utf-8")

    assert load_hook_config(tmp_path)["lsp"]["cache"] is False

    override = tmp_path / "override.json"
    override.write_text(json.dumps({"lsp": {"cache": True}}), encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_CONFIG", str(override))

    assert load_hook_config(tmp_path)["lsp"]["cache"] is True

    monkeypatch.setenv("GRAPHIFY_CONFIG", str(tmp_path / "missing.json"))
    assert load_hook_config(tmp_path) == {}


def test_lsp_hook_chain_runs_for_matching_language(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    unresolved_path, languages = write_lsp_exchange(
        graphify_out,
        {
            "nodes": [{"id": "runner", "source_file": "runner.rb"}],
            "unresolved_calls": [
                {"caller": "runner", "callee": "first", "source_file": "runner.rb"}
            ],
        },
        root=tmp_path,
        source_files=[tmp_path / "runner.rb"],
    )
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, pathlib\n"
        "out = pathlib.Path(os.environ['GRAPHIFY_ENRICHMENT_DIR']) / 'hook_edges.json'\n"
        "out.write_text(json.dumps({\n"
        "  'generated_by': 'test-hook',\n"
        "  'language': 'ruby',\n"
        "  'edges': [{\n"
        "    'source': 'runner', 'target': 'resolved_first', 'relation': 'calls',\n"
        "    'context': 'test_hook', 'confidence': 'EXTRACTED',\n"
        "    'source_file': 'runner.rb'\n"
        "  }]\n"
        "}))\n",
        encoding="utf-8",
    )
    (graphify_out / ".graphify_python").write_text(
        f"File: .graphify_python\n{sys.executable}\n",
        encoding="utf-8",
    )
    config = {
        "lsp": {
            "chains": [
                {
                    "name": "ruby",
                    "languages": ["ruby"],
                    "hooks": [
                        {
                            "name": "test-hook",
                            "command": ["{python}", str(script)],
                        }
                    ],
                }
            ]
        }
    }

    ran = run_lsp_hooks(
        root=tmp_path,
        graphify_out=graphify_out,
        languages=languages,
        unresolved_calls_path=unresolved_path,
        config=config,
    )

    assert ran == ["ruby:test-hook"]
    chunks = load_enrichments([graphify_out / "enrichment" / "lsp"])
    assert chunks[0]["enrichments"][0]["generated_by"] == "test-hook"


def test_build_merge_prunes_stale_lsp_edges_for_changed_sources(tmp_path):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps({
            "nodes": [
                {"id": "caller", "source_file": "caller.rb"},
                {"id": "old_target", "source_file": "old.rb"},
                {"id": "new_target", "source_file": "new.rb"},
                {"id": "structural_target", "source_file": "structural.rb"},
            ],
            "links": [
                {
                    "source": "caller",
                    "target": "old_target",
                    "relation": "calls",
                    "context": "lsp_definition:ruby",
                    "source_file": "caller.rb",
                },
                {
                    "source": "caller",
                    "target": "structural_target",
                    "relation": "calls",
                    "context": "call",
                    "source_file": "caller.rb",
                },
            ],
        }),
        encoding="utf-8",
    )

    graph = build_merge(
        [
            {
                "nodes": [],
                "edges": [
                    {
                        "source": "caller",
                        "target": "new_target",
                        "relation": "calls",
                        "context": "lsp_definition:ruby",
                        "source_file": "caller.rb",
                    }
                ],
            }
        ],
        graph_path=graph_path,
        prune_edge_sources=["caller.rb"],
        dedup=False,
    )

    edges = {(u, v, data.get("context")) for u, v, data in graph.edges(data=True)}

    assert ("caller", "old_target", "lsp_definition:ruby") not in edges
    assert ("caller", "new_target", "lsp_definition:ruby") in edges
    assert ("caller", "structural_target", "call") in edges


def test_lsp_hook_chain_skips_non_matching_language(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    unresolved_path, languages = write_lsp_exchange(
        graphify_out,
        {
            "nodes": [{"id": "runner", "source_file": "runner.rb"}],
            "unresolved_calls": [
                {"caller": "runner", "callee": "first", "source_file": "runner.rb"}
            ],
        },
        root=tmp_path,
        source_files=[tmp_path / "runner.rb"],
    )
    config = {
        "lsp": {
            "hooks": [
                {
                    "name": "python-only",
                    "languages": ["python"],
                    "command": [sys.executable, "-c", "raise SystemExit(99)"],
                }
            ]
        }
    }

    ran = run_lsp_hooks(
        root=tmp_path,
        graphify_out=graphify_out,
        languages=languages,
        unresolved_calls_path=unresolved_path,
        config=config,
    )

    assert ran == []


def test_lsp_enrichment_no_config_does_not_write_sidecar_or_merge_stale_output(tmp_path):
    graphify_out = tmp_path / "graphify-out"
    stale_dir = graphify_out / "enrichment"
    stale_dir.mkdir(parents=True)
    (stale_dir / "stale.json").write_text(
        json.dumps({
            "generated_by": "stale",
            "edges": [
                {
                    "source": "runner",
                    "target": "stale_target",
                    "relation": "calls",
                }
            ],
        }),
        encoding="utf-8",
    )
    extraction = {
        "nodes": [{"id": "runner", "source_file": "runner.rb"}],
        "edges": [],
        "unresolved_calls": [
            {"caller": "runner", "callee": "first", "source_file": "runner.rb"}
        ],
    }

    merged, summary = apply_lsp_enrichment(
        extraction,
        root=tmp_path,
        graphify_out=graphify_out,
        source_files=[tmp_path / "runner.rb"],
    )

    assert summary.enabled is False
    assert "unresolved_calls" not in merged
    assert merged["edges"] == []
    assert not (graphify_out / "unresolved_calls.json").exists()


def test_lsp_hooks_require_explicit_enable(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_ENABLE_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_ALLOW_HOOKS", raising=False)
    graphify_out = tmp_path / "graphify-out"
    marker = tmp_path / "hook-ran"
    script = tmp_path / "hook.py"
    script.write_text(
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "disabled-test",
                        "languages": ["python"],
                        "command": [sys.executable, str(script)],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    extraction = {
        "nodes": [{"id": "runner", "source_file": "runner.py", "source_location": "L1"}],
        "edges": [
            {
                "source": "runner",
                "target": "stale_lsp_target",
                "relation": "calls",
                "context": "lsp_definition:python",
                "confidence": "INFERRED",
                "lsp_resolver": "pyright",
            },
            {
                "source": "runner",
                "target": "structural_target",
                "relation": "calls",
                "context": "call",
                "contexts": ["call", "lsp_definition:python"],
                "confidence": "EXTRACTED",
                "lsp_contexts": ["lsp_definition:python"],
                "lsp_resolvers": ["pyright"],
                "definition_file": "target.py",
                "definition_uri": "file:///tmp/target.py",
                "receiver_type": "Target",
                "receiver_type_confidence": 0.9,
            },
        ],
        "enrichments": [
            {"generated_by": "graphify-lsp-promotion", "source": "lsp_evidence"},
            {"generated_by": "semantic-test", "source": "manual"},
        ],
        "unresolved_calls": [
            {"caller": "runner", "callee": "target", "source_file": "runner.py"}
        ],
    }

    merged, summary = apply_lsp_enrichment(
        extraction,
        root=tmp_path,
        graphify_out=graphify_out,
        source_files=[tmp_path / "runner.py"],
    )

    assert summary.enabled is False
    assert not marker.exists()
    assert "unresolved_calls" not in merged
    assert not (graphify_out / "unresolved_calls.json").exists()
    assert [
        (edge["source"], edge["target"], edge["context"])
        for edge in merged["edges"]
    ] == [("runner", "structural_target", "call")]
    assert "contexts" not in merged["edges"][0]
    assert not any(key.startswith("lsp_") for key in merged["edges"][0])
    for key in ("definition_file", "definition_uri", "receiver_type", "receiver_type_confidence"):
        assert key not in merged["edges"][0]
    assert merged["enrichments"] == [{"generated_by": "semantic-test", "source": "manual"}]


def test_lsp_opt_in_tip_prints_for_configured_disabled_hooks(tmp_path, monkeypatch, capsys):
    from graphify.__main__ import _print_lsp_opt_in_tip

    monkeypatch.delenv("GRAPHIFY_CONFIG", raising=False)
    monkeypatch.delenv("GRAPHIFY_ENABLE_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_ALLOW_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_NO_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_NO_TIPS", raising=False)
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "tip-test",
                        "languages": ["python"],
                        "command": [sys.executable, "-c", "pass"],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )

    _print_lsp_opt_in_tip(tmp_path)

    assert "GRAPHIFY_ENABLE_HOOKS=1" in capsys.readouterr().out


def test_has_disabled_lsp_hooks_uses_central_hook_env_state(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_CONFIG", raising=False)
    monkeypatch.delenv("GRAPHIFY_ENABLE_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_ALLOW_HOOKS", raising=False)
    monkeypatch.delenv("GRAPHIFY_NO_HOOKS", raising=False)
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "tip-test",
                        "languages": ["python"],
                        "command": [sys.executable, "-c", "pass"],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )

    assert has_disabled_lsp_hooks(tmp_path) is True

    monkeypatch.setenv("GRAPHIFY_ENABLE_HOOKS", "1")
    assert has_disabled_lsp_hooks(tmp_path) is False


def test_lsp_enrichment_applies_configured_chain(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, pathlib\n"
        "out = pathlib.Path(os.environ['GRAPHIFY_ENRICHMENT_DIR']) / 'edges.json'\n"
        "out.write_text(json.dumps({\n"
        "  'generated_by': 'apply-test',\n"
        "  'edges': [{\n"
        "    'source': 'runner', 'target': 'target_func', 'relation': 'calls',\n"
        "    'context': 'lsp_definition:python', 'confidence': 'EXTRACTED'\n"
        "  }]\n"
        "}))\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "python-test",
                        "languages": ["python"],
                        "command": [sys.executable, str(script)],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    extraction = {
        "nodes": [
            {"id": "runner", "source_file": "runner.py", "source_location": "L1"},
            {"id": "target_func", "source_file": "target.py", "source_location": "L1"},
        ],
        "edges": [
            {
                "source": "runner",
                "target": "stale_target",
                "relation": "calls",
                "context": "lsp_definition:python",
            }
        ],
        "unresolved_calls": [
            {"caller": "runner", "callee": "target", "source_file": "runner.py"}
        ],
    }

    merged, summary = apply_lsp_enrichment(
        extraction,
        root=tmp_path,
        graphify_out=graphify_out,
        source_files=[tmp_path / "runner.py"],
    )

    assert summary.enabled is True
    assert summary.ran_hooks == ("python-test",)
    assert summary.merged_edges == 1
    assert "unresolved_calls" not in merged
    assert [edge["target"] for edge in merged["edges"]] == ["target_func"]


def test_snippet_style_pipeline_preserves_unresolved_calls_and_runs_enrichment(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, pathlib\n"
        "out = pathlib.Path(os.environ['GRAPHIFY_ENRICHMENT_DIR']) / 'edges.json'\n"
        "out.write_text(json.dumps({\n"
        "  'generated_by': 'snippet-test',\n"
        "  'edges': [{\n"
        "    'source': 'runner', 'target': 'target_func', 'relation': 'calls',\n"
        "    'context': 'lsp_definition:python', 'confidence': 'INFERRED'\n"
        "  }]\n"
        "}))\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "snippet-test",
                        "languages": ["python"],
                        "command": [sys.executable, str(script)],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    ast = {
        "nodes": [
            {"id": "runner", "source_file": "runner.py", "source_location": "L1"},
            {"id": "target_func", "source_file": "target.py", "source_location": "L1"},
        ],
        "edges": [],
        "unresolved_calls": [
            {"caller": "runner", "callee": "target", "source_file": "runner.py"}
        ],
    }
    semantic = {
        "nodes": [{"id": "guide", "source_file": "README.md"}],
        "edges": [{"source": "guide", "target": "runner", "relation": "references"}],
        "input_tokens": 10,
        "output_tokens": 5,
    }

    merged = merge_ast_semantic(ast, semantic)
    assert len(merged["unresolved_calls"]) == 1

    finalized, summary = finalize_extraction_for_build(
        merged,
        root=tmp_path,
        graphify_out=graphify_out,
    )

    assert summary.ran_hooks == ("snippet-test",)
    assert (graphify_out / "unresolved_calls.json").exists()
    assert "unresolved_calls" not in finalized
    assert {edge["target"] for edge in finalized["edges"]} == {"runner", "target_func"}
    assert finalized["input_tokens"] == 10
    assert finalized["output_tokens"] == 5


def test_finalize_extraction_files_writes_final_payload(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, pathlib\n"
        "out = pathlib.Path(os.environ['GRAPHIFY_ENRICHMENT_DIR']) / 'edges.json'\n"
        "out.write_text(json.dumps({\n"
        "  'generated_by': 'file-helper-test',\n"
        "  'edges': [{\n"
        "    'source': 'runner', 'target': 'target_func', 'relation': 'calls',\n"
        "    'context': 'lsp_definition:python', 'confidence': 'INFERRED'\n"
        "  }]\n"
        "}))\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "file-helper-test",
                        "languages": ["python"],
                        "command": [sys.executable, str(script)],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    ast_path = tmp_path / ".graphify_ast.json"
    semantic_path = tmp_path / ".graphify_semantic.json"
    output_path = tmp_path / ".graphify_extract.json"
    ast_path.write_text(
        json.dumps({
            "nodes": [
                {"id": "runner", "source_file": "runner.py", "source_location": "L1"},
                {"id": "target_func", "source_file": "target.py", "source_location": "L1"},
            ],
            "edges": [],
            "unresolved_calls": [
                {"caller": "runner", "callee": "target", "source_file": "runner.py"}
            ],
        }),
        encoding="utf-8",
    )

    finalized, summary, stats = finalize_extraction_files(
        ast_path=ast_path,
        semantic_path=semantic_path,
        output_path=output_path,
        root=tmp_path,
        graphify_out=graphify_out,
    )

    assert summary.ran_hooks == ("file-helper-test",)
    assert stats == {
        "ast_nodes": 2,
        "semantic_nodes": 0,
        "total_nodes": 2,
        "total_edges": 1,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == finalized


def test_lsp_enrichment_cache_reuses_full_workspace_sidecars(tmp_path, monkeypatch):
    _enable_hooks(monkeypatch)
    graphify_out = tmp_path / "graphify-out"
    source = tmp_path / "runner.py"
    source.write_text("def runner():\n    target()\n", encoding="utf-8")
    counter = tmp_path / "counter.txt"
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, os, pathlib\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "count = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(count + 1))\n"
        "out = pathlib.Path(os.environ['GRAPHIFY_ENRICHMENT_DIR']) / 'edges.json'\n"
        "out.write_text(json.dumps({'generated_by': 'cache-test', 'edges': []}))\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / ".graphify"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps({
            "lsp": {
                "hooks": [
                    {
                        "name": "python-cache-test",
                        "languages": ["python"],
                        "command": [sys.executable, str(script)],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    extraction = {
        "nodes": [{"id": "runner", "source_file": "runner.py", "source_location": "L1"}],
        "edges": [],
        "unresolved_calls": [
            {
                "caller": "runner",
                "callee": "target",
                "source_file": "runner.py",
                "callee_range": {"start": {"line": 1, "character": 4}},
            }
        ],
    }

    _merged, first = apply_lsp_enrichment(
        extraction,
        root=tmp_path,
        graphify_out=graphify_out,
        source_files=[source],
    )
    _merged, second = apply_lsp_enrichment(
        extraction,
        root=tmp_path,
        graphify_out=graphify_out,
        source_files=[source],
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert counter.read_text() == "1"
