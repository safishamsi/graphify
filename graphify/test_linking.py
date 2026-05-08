"""Phase 5 deterministic test-to-source linking.

Discovers test functions/classes from a deterministic naming convention,
then links each test node to its corresponding production node via
'test_of' edges.

Naming conventions (Python):
  Test file:    test_<module>.py            → tests <module>.py
  Test class:   Test<ProductionClass>       → tests <ProductionClass>
  Test function: test_<production_func>     → tests <production_func>
  Test method:   test_<method_name>         → tests <method_name>

The entry point:
  resolve_python_test_edges(
      nodes: list[dict], edges: list[dict],
      source_file: str, language: str = "python"
  ) → int

Returns the number of test_of edges created (edges are appended in place).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def is_test_node(node: dict[str, Any], language: str = "python") -> bool:
    """Return True if *node* is a test function/class/method.

    Checks naming conventions (not file_type, since the current extraction
    assigns file_type="code" to all functions).
    """
    if language != "python":
        return False

    label = str(node.get("label", ""))
    if not label:
        return False

    # Python naming conventions
    return label.startswith("test_") or label.startswith("Test")


def _test_file_to_production_stem(test_file: str) -> str | None:
    """Convert a test file path to its probable production file stem.

    Python conventions:
      tests/test_foo.py  →  foo
      test_foo.py        →  foo
      foo_test.py        →  foo
    """
    if not test_file:
        return None
    basename = os.path.basename(test_file)
    stem = os.path.splitext(basename)[0]

    m = re.match(r"^test_(.+)$", stem)
    if m:
        return m.group(1)
    m2 = re.match(r"^(.+)_test$", stem)
    if m2:
        return m2.group(1)
    return None


def _test_func_to_production_name(test_label: str) -> str | None:
    """Convert a test function label to its probable production function name.

    test_foo()     →  foo()
    test_foo_bar() →  foo_bar()
    """
    clean = test_label.strip("()")
    if clean.startswith("test_"):
        suffix = test_label[len("test_"):]
        return suffix if suffix else None
    return None


def _test_class_to_production_name(test_label: str) -> str | None:
    """Convert a test class label to its probable production class name.

    TestFoo   →  Foo
    FooTest   →  Foo
    FooTests  →  Foo
    """
    # Test<Name>
    m = re.match(r"^Test(.+)$", test_label)
    if m:
        return m.group(1)
    # <Name>Test(s)
    m2 = re.match(r"^(.+?)(?:Tests?)$", test_label)
    if m2:
        return m2.group(1)
    return None


def _normalise_label(label: str) -> str:
    """Normalize a label for matching purposes."""
    return label.strip().strip("()").lstrip(".").lower()


def _stem_from_source(source_file: str) -> str:
    """Extract file stem from a source_file path."""
    if not source_file:
        return ""
    return Path(source_file).stem


def resolve_python_test_edges(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    source_file: str,
    language: str = "python",
) -> int:
    """Link test nodes to their production-code counterparts.

    Algorithm (deterministic):
      1. Identify all test nodes in *source_file*.
      2. For each test node, derive the likely production target name.
      3. Search *nodes* for a production node with a matching name in a file
         whose stem matches the test-file → production-file convention.
      4. If found, create a 'test_of' edge.

    Edges are appended to *edges* in place.  Returns the number of edges created.
    """
    if language != "python":
        return 0

    # Derive expected production file stem
    test_stem = _test_file_to_production_stem(source_file)

    # Build lookup: (stem, normalised_label) → [node_ids]
    prod_by_stem_label: dict[tuple[str, str], list[str]] = {}
    prod_id_by_label: dict[str, str] = {}
    # Track nodes by source stem for fallback matching
    nodes_by_source_stem: dict[str, list[dict[str, Any]]] = {}

    for node in nodes:
        nid = node.get("id", "")
        if not nid:
            continue
        if is_test_node(node, language):
            continue
        # Only consider function/method/class nodes
        label = str(node.get("label", ""))
        if not label:
            continue
        norm = _normalise_label(label)
        nf = node.get("source_file", "")
        stem = _stem_from_source(nf)

        prod_by_stem_label.setdefault((stem, norm), []).append(nid)
        prod_id_by_label.setdefault(label, nid)
        nodes_by_source_stem.setdefault(stem, []).append(node)

    # Track existing pairs to avoid duplicates
    existing_pairs: set[tuple[str, str, str]] = {
        (e.get("source", ""), e.get("target", ""), e.get("relation", ""))
        for e in edges
    }

    edges_created = 0

    for test_node in nodes:
        if not is_test_node(test_node, language):
            continue
        if test_node.get("source_file", "") != source_file:
            continue

        test_label = str(test_node.get("label", ""))
        test_id = test_node.get("id", "")
        if not test_label or not test_id:
            continue

        # Determine the production name
        prod_name = None
        is_class_test = test_label.startswith("Test")

        if is_class_test:
            prod_name = _test_class_to_production_name(test_label)
        else:
            prod_name = _test_func_to_production_name(test_label)

        if not prod_name:
            continue

        prod_id = None

        # 1. Try exact label match
        if prod_name in prod_id_by_label:
            prod_id = prod_id_by_label[prod_name]

        # 2. Try stem+label match in the expected production file
        if prod_id is None and test_stem:
            norm_prod = _normalise_label(prod_name)
            candidates = prod_by_stem_label.get((test_stem, norm_prod), [])
            if len(candidates) == 1:
                prod_id = candidates[0]
            elif candidates:
                # Multiple candidates - pick the one matching the test_stem
                for cid in candidates:
                    prod_id = cid
                    break

        # 3. Try stem+label match in any stem
        if prod_id is None:
            norm_prod = _normalise_label(prod_name)
            for (stem, norm), cids in prod_by_stem_label.items():
                if norm == norm_prod and len(cids) >= 1:
                    prod_id = cids[0]
                    break

        if prod_id is None:
            continue
        if prod_id == test_id:
            continue

        pair = (test_id, prod_id, "test_of")
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)

        edges.append({
            "source": test_id,
            "target": prod_id,
            "relation": "test_of",
            "confidence": "INFERRED",
            "confidence_score": 0.8,
            "source_file": source_file,
            "source_location": test_node.get("source_location", ""),
            "weight": 1.0,
            "context": "test_linking",
            "metadata": {
                "resolver": "python_test_linking",
                "test_label": test_label,
                "production_name": prod_name,
            },
        })
        edges_created += 1

        # Also create reverse "tests" edge
        rev_pair = (prod_id, test_id, "tests")
        if rev_pair not in existing_pairs:
            existing_pairs.add(rev_pair)
            edges.append({
                "source": prod_id,
                "target": test_id,
                "relation": "tests",
                "confidence": "INFERRED",
                "confidence_score": 0.8,
                "source_file": source_file,
                "source_location": test_node.get("source_location", ""),
                "weight": 1.0,
                "context": "test_linking",
                "metadata": {
                    "resolver": "python_test_linking",
                    "test_label": test_label,
                    "production_name": prod_name,
                },
            })
            edges_created += 1

    return edges_created
