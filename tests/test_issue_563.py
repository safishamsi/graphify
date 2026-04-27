"""Regression tests for issue #563.

Two extractor bugs were inflating god-node centrality:

1. `_resolve_cross_file_imports` accepted rationale nodes as "importing
   classes", causing a phantom `<file>_rationale_N --uses--> ImportedThing`
   edge for every imported entity in every file with docstrings. Cross-file
   call resolution had the same leak via `global_label_to_nid`.

2. The `to_json` exporter serialized a NetworkX undirected graph and lost
   edge direction; `_src` / `_tgt` were stashed by `build` precisely to
   restore direction at export time, but were not consulted.

Both bugs are observable in the AST-only path (no LLM required).

Note: the fixture uses module name ``jobq`` rather than ``queue`` to avoid
colliding with the Python stdlib ``queue`` module that graphify's update
path imports.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_repro(root: Path) -> None:
    (root / "jobq.py").write_text(textwrap.dedent('''
        """Job-queue module — provides SQLiteQueue for idempotent job tracking."""


        class SQLiteQueue:
            """Lightweight SQLite-backed queue.

            Used by middleware routers and CLI commands to enqueue work and
            deduplicate via idempotency keys.
            """

            def check_idempotency(self, key):
                """Return existing lead for key, or None."""
                return None

            def enqueue(self, payload):
                """Persist payload to the queue."""
                return True
    ''').lstrip())

    (root / "contact_form.py").write_text(textwrap.dedent('''
        """HTTP router for the contact form endpoint."""
        from jobq import SQLiteQueue

        q = SQLiteQueue()


        def contact_form(payload_obj):
            """Handle a contact form submission.

            Idempotency is keyed on payload_obj.idempotency_key.
            """
            existing_lead = q.check_idempotency(payload_obj.idempotency_key)
            if existing_lead:
                return existing_lead
            q.enqueue(payload_obj)
            return {"ok": True}
    ''').lstrip())

    (root / "test_customer_dedup.py").write_text(textwrap.dedent('''
        """Tests for customer dedup — exercises phone normalization and Odoo tagging."""
        from jobq import SQLiteQueue
        from contact_form import contact_form


        def test_us_phone_no_country_code():
            """US phone without country code uses default region US -> +1 prefix."""
            assert True


        def test_uk_phone_with_prefix():
            """UK phone with +44 prefix parses regardless of default region."""
            assert True


        def test_invalid_phone_returns_none():
            """Phone that parses but isn't a valid number -> None."""
            assert True


        def test_odoo_tag_missing_still_chatter():
            """If the tag isn't seeded, still post the chatter note."""
            queue = SQLiteQueue()
            queue.enqueue({})
            contact_form(None)
    ''').lstrip())


def _run_graphify_update(root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(root)],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    assert result.returncode == 0, (
        f"graphify update failed: {result.stderr}\nstdout: {result.stdout}"
    )
    graph_path = root / "graphify-out" / "graph.json"
    assert graph_path.exists(), f"graph.json not produced. stderr: {result.stderr}"
    return json.loads(graph_path.read_text())


@pytest.fixture
def repro_graph(tmp_path: Path) -> dict:
    _write_repro(tmp_path)
    return _run_graphify_update(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# Bug 1: rationale node leakage into cross-file resolvers
# ─────────────────────────────────────────────────────────────────────────────


def _file_type_map(graph: dict) -> dict[str, str]:
    """Map node id -> file_type from the serialized graph.

    Identifying rationale nodes via node metadata (file_type == "rationale")
    is more durable than substring-matching on the id, which couples to the
    current `<stem>_rationale_<line>` naming scheme.
    """
    return {n["id"]: n.get("file_type", "") for n in graph["nodes"]}


def test_no_rationale_nodes_in_uses_or_calls_edges(repro_graph):
    """Rationale nodes describe code; they cannot `use`, `call`, or `reference`
    anything. The only relation a rationale node may participate in is
    `rationale_for` (extractor emits `rationale --rationale_for--> parent`)."""
    ftype = _file_type_map(repro_graph)
    bad = [
        e for e in repro_graph["links"]
        if (ftype.get(e["source"]) == "rationale"
            or ftype.get(e["target"]) == "rationale")
        and e["relation"] != "rationale_for"
    ]
    assert bad == [], (
        f"Rationale nodes must only appear in rationale_for edges. "
        f"Found {len(bad)} bad edges with relations "
        f"{sorted({e['relation'] for e in bad})}: {bad[:3]}"
    )


def test_rationale_for_direction_is_rationale_to_parent(repro_graph):
    """Rationale_for edges encode "this docstring fragment is the rationale
    for this code entity": source is the rationale node, target is the parent.
    The export-side direction restore (#563) was the only thing that made
    this hold under undirected NetworkX storage."""
    ftype = _file_type_map(repro_graph)
    rats = [e for e in repro_graph["links"] if e["relation"] == "rationale_for"]
    assert rats, "expected some rationale_for edges in the repro"
    bad = [e for e in rats if ftype.get(e["source"]) != "rationale"]
    assert bad == [], (
        f"rationale_for edges must have a rationale node as source. "
        f"Found {len(bad)} flipped: {bad[:3]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bug 2: `calls` direction must be caller -> callee
# ─────────────────────────────────────────────────────────────────────────────


def _calls(graph: dict) -> list[tuple[str, str]]:
    return [
        (e["source"], e["target"])
        for e in graph["links"]
        if e.get("relation") == "calls"
    ]


def test_calls_direction_is_caller_to_callee(repro_graph):
    """The exact directions reported as inverted in #563 must hold."""
    calls = _calls(repro_graph)

    # contact_form() calls SQLiteQueue.check_idempotency() and SQLiteQueue.enqueue()
    assert (
        "contact_form_contact_form",
        "jobq_sqlitequeue_check_idempotency",
    ) in calls, f"expected caller->callee edge missing. got: {calls}"
    assert (
        "contact_form_contact_form",
        "jobq_sqlitequeue_enqueue",
    ) in calls, f"contact_form->enqueue edge missing. got: {calls}"

    # The test function calls contact_form()
    assert (
        "test_customer_dedup_test_odoo_tag_missing_still_chatter",
        "contact_form_contact_form",
    ) in calls, f"test->contact_form edge missing. got: {calls}"

    # And critically, none of the inversions exist:
    inversions = {
        ("jobq_sqlitequeue_check_idempotency", "contact_form_contact_form"),
        ("jobq_sqlitequeue_enqueue", "contact_form_contact_form"),
        ("contact_form_contact_form",
         "test_customer_dedup_test_odoo_tag_missing_still_chatter"),
    }
    leaked = set(calls) & inversions
    assert not leaked, f"Found inverted calls edges: {leaked}"


def test_calls_direction_on_existing_sample_calls_fixture():
    """Pin the direction on the in-tree fixture too — adds direction
    coverage to the existing AST extractor tests."""
    from graphify.extract import extract_python

    fixture = REPO_ROOT / "tests" / "fixtures" / "sample_calls.py"
    result = extract_python(fixture)

    calls = [
        (e["source"], e["target"])
        for e in result["edges"]
        if e.get("relation") == "calls"
    ]
    assert calls, "sample_calls.py must produce some calls edges"

    # In sample_calls.py:
    #   compute_score and normalize are LEAF functions — they call nothing.
    #   They must appear as callees, never as callers.
    leaf_callers = [
        src for src, _ in calls
        if src.endswith("compute_score") or src.endswith("normalize")
    ]
    assert leaf_callers == [], (
        f"Leaf functions appearing as callers means direction is inverted: "
        f"{leaf_callers}"
    )

    # And they should appear at least once as callees.
    leaf_callees = [
        tgt for _, tgt in calls
        if "compute_score" in tgt or "normalize" in tgt
    ]
    assert leaf_callees, f"leaf functions should appear as callees. got: {calls}"


def test_src_tgt_metadata_not_leaked_into_graph_json(repro_graph):
    """The _src/_tgt direction-preservation fields are an internal detail
    of the build path; they must be consumed by the exporter and stripped
    from graph.json."""
    leaks = [e for e in repro_graph["links"] if "_src" in e or "_tgt" in e]
    assert leaks == [], (
        f"_src/_tgt are internal; must not appear in graph.json. Leaks: {leaks[:3]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bug 2 (HTML export): graph.html arrows must respect direction too
# ─────────────────────────────────────────────────────────────────────────────


def _vis_edges_from_html(html: str) -> list[dict]:
    """Extract the vis.js edges array embedded in graph.html.

    `_html_script` emits `const RAW_EDGES = <json>;` — pull that JSON out
    directly rather than parsing the surrounding script.
    """
    import re
    m = re.search(r"const RAW_EDGES = (\[.*?\]);", html, re.DOTALL)
    assert m, "could not locate RAW_EDGES in graph.html"
    return json.loads(m.group(1))


def test_to_html_preserves_calls_and_rationale_for_direction(tmp_path: Path):
    """to_html must read _src/_tgt before assigning vis.js `from`/`to`,
    otherwise undirected NetworkX storage flips arrows on render (#563)."""
    from graphify.build import build_from_json
    from graphify.export import to_html

    _write_repro(tmp_path)
    repro_graph = _run_graphify_update(tmp_path)

    G = build_from_json(repro_graph)
    out_html = tmp_path / "graph.html"
    to_html(G, communities={0: list(G.nodes())}, output_path=str(out_html))

    vis_edges = _vis_edges_from_html(out_html.read_text(encoding="utf-8"))
    pairs = {(e["from"], e["to"]): e.get("label") for e in vis_edges}

    # rationale_for: source must be the rationale node (file_type metadata
    # isn't on vis_edges, so we check via the json graph's node map).
    ftype = _file_type_map(repro_graph)
    rats_html = [
        (frm, to) for (frm, to), rel in pairs.items() if rel == "rationale_for"
    ]
    assert rats_html, "expected rationale_for edges in graph.html"
    flipped_rats = [
        (frm, to) for (frm, to) in rats_html if ftype.get(frm) != "rationale"
    ]
    assert flipped_rats == [], (
        f"rationale_for arrows in graph.html must point rationale->parent. "
        f"Flipped: {flipped_rats[:3]}"
    )

    # calls: pin the same caller->callee directions asserted on graph.json.
    assert (
        "contact_form_contact_form",
        "jobq_sqlitequeue_check_idempotency",
    ) in pairs, "contact_form->check_idempotency arrow missing in graph.html"
    assert (
        "contact_form_contact_form",
        "jobq_sqlitequeue_enqueue",
    ) in pairs, "contact_form->enqueue arrow missing in graph.html"

    # And the inversions must not be present.
    inversions = {
        ("jobq_sqlitequeue_check_idempotency", "contact_form_contact_form"),
        ("jobq_sqlitequeue_enqueue", "contact_form_contact_form"),
    }
    leaked = inversions & {
        (frm, to) for (frm, to), rel in pairs.items() if rel == "calls"
    }
    assert not leaked, f"Inverted calls arrows in graph.html: {leaked}"
