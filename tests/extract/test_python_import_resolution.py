from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1
    return matches[0]


def _has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    return any(
        edge["source"] == source
        and edge["target"] == target
        and edge["relation"] == relation
        for edge in result["edges"]
    )


def test_python_package_reexport_resolves_import_and_call_to_origin_symbol(tmp_path: Path):
    origin = _write(tmp_path / "pkg/foo.py", "def Foo():\n    return 1\n")
    barrel = _write(tmp_path / "pkg/__init__.py", "from .foo import Foo as PublicFoo\n")
    consumer = _write(
        tmp_path / "app.py",
        "from pkg import PublicFoo\n\n"
        "def X():\n"
        "    return PublicFoo()\n",
    )

    result = extract([origin, barrel, consumer], cache_root=tmp_path)

    origin_file = _node_id(result, "foo.py", "pkg/foo.py")
    barrel_file = _node_id(result, "__init__.py", "pkg/__init__.py")
    consumer_file = _node_id(result, "app.py", "app.py")
    origin_symbol = _node_id(result, "Foo()", "pkg/foo.py")
    consumer_symbol = _node_id(result, "X()", "app.py")

    assert _has_edge(result, barrel_file, origin_file, "re_exports")
    assert _has_edge(result, consumer_file, origin_symbol, "imports")
    assert _has_edge(result, consumer_symbol, origin_symbol, "calls")


def test_python_parameter_return_and_generic_contexts(tmp_path: Path):
    model = tmp_path / "pkg" / "model.py"
    model.parent.mkdir(parents=True)
    model.write_text(
        "class Payload:\n"
        "    pass\n\n"
        "class Result:\n"
        "    pass\n",
        encoding="utf-8",
    )
    service = tmp_path / "pkg" / "service.py"
    service.write_text(
        "from .model import Payload, Result\n\n"
        "def process(item: Payload) -> Result:\n"
        "    return Result()\n\n"
        "def process_many(items: list[Payload]) -> Result:\n"
        "    return Result()\n",
        encoding="utf-8",
    )

    result = extract([model, service], cache_root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    edges = [edge for edge in result["edges"] if edge.get("relation") == "references"]
    pairs = {
        (labels.get(e["source"], e["source"]), labels.get(e["target"], e["target"]), e.get("context"))
        for e in edges
    }

    assert ("process()", "Payload", "parameter_type") in pairs
    assert ("process()", "Result", "return_type") in pairs
    assert ("process_many()", "Payload", "generic_arg") in pairs
