"""Tests for rationale/docstring extraction in extract.py.

Rationale is now stored as a 'rationale' attribute on the parent node
rather than as separate rationale nodes with rationale_for edges.
"""
import textwrap
from pathlib import Path
import pytest
from graphify.extract import extract_python
from graphify.build import build_from_json


def _write_py(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(code))
    return p


def _nodes_with_rationale(result):
    return [n for n in result["nodes"] if n.get("rationale")]


def test_module_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        """This module handles authentication because legacy sessions were insecure."""
        def login(): pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert len(nodes) >= 1
    assert any("authentication" in n["rationale"] for n in nodes)


def test_function_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        def process():
            """We use chunked processing here because the full dataset exceeds RAM."""
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert any("chunked" in n["rationale"] for n in nodes)


def test_class_docstring_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        class Cache:
            """Chosen over Redis because we need zero external dependencies in the test env."""
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert any("Redis" in n["rationale"] for n in nodes)


def test_rationale_comment_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        def build():
            # NOTE: must run before compile() or linker will fail
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert any("NOTE" in n["rationale"] for n in nodes)


def test_no_rationale_for_edges(tmp_path):
    """Rationale is now an attribute, not a node+edge — no rationale_for edges."""
    path = _write_py(tmp_path, '''
        """Module docstring explaining the why."""
        def foo():
            """Function docstring with rationale."""
            pass
    ''')
    result = extract_python(path)
    rationale_edges = [e for e in result["edges"] if e.get("relation") == "rationale_for"]
    assert len(rationale_edges) == 0


def test_no_rationale_nodes(tmp_path):
    """No separate rationale nodes are emitted — rationale lives on parent nodes."""
    path = _write_py(tmp_path, '''
        """Module docstring explaining the why."""
        def foo():
            """Function docstring with rationale."""
            pass
    ''')
    result = extract_python(path)
    rationale_nodes = [n for n in result["nodes"] if n.get("file_type") == "rationale"]
    assert len(rationale_nodes) == 0


def test_short_docstring_ignored(tmp_path):
    """Trivial docstrings under 20 chars should not set the rationale attribute."""
    path = _write_py(tmp_path, '''
        def foo():
            """Constructor."""
            pass
    ''')
    result = extract_python(path)
    assert len(_nodes_with_rationale(result)) == 0


def test_alembic_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """initial schema

        Revision ID: 0001abcd
        Revises:
        Create Date: 2023-01-01 00:00:00
        """
        revision = "0001abcd"
        down_revision = None
        branch_labels = None

        def upgrade():
            pass

        def downgrade():
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert not any("Revision ID" in n["rationale"] for n in nodes)


def test_alembic_function_docstrings_still_extracted(tmp_path):
    """Function docstrings inside upgrade/downgrade should still be captured."""
    path = _write_py(tmp_path, '''
        """Revision ID: 0002 Revises: 0001"""
        revision = "0002"
        down_revision = "0001"

        def upgrade():
            """Add users table because auth was added in this release."""
            pass

        def downgrade():
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert not any("Revision ID" in n["rationale"] for n in nodes)
    assert any("auth" in n["rationale"] for n in nodes)


def test_non_migration_revision_var_not_suppressed(tmp_path):
    """A file with a `revision` variable but no Alembic markers keeps its docstring."""
    path = _write_py(tmp_path, '''
        """This module tracks document revisions because we need audit history."""
        revision = 42

        def get_revision(): pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert any("audit history" in n["rationale"] for n in nodes)


def test_django_migration_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """Add post_priority_config table."""
        from django.db import migrations

        class Migration(migrations.Migration):
            dependencies = [("myapp", "0001_initial")]
            operations = []
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert not any("post_priority" in n["rationale"] for n in nodes)


def test_generated_file_module_docstring_suppressed(tmp_path):
    path = _write_py(tmp_path, '''
        """Generated by the protocol buffer compiler. DO NOT EDIT!"""
        from google.protobuf import descriptor as _descriptor

        class UserMessage:
            pass
    ''')
    result = extract_python(path)
    nodes = _nodes_with_rationale(result)
    assert not any("protocol buffer" in n["rationale"].lower() for n in nodes)


def test_decorated_method_node_id_is_class_qualified(tmp_path):
    """Regression for #1050: @property / @staticmethod / @classmethod methods
    were emitted with a class-unqualified node id (e.g. ``file_baz``). The
    rationale walker uses class-qualified ids, so the docstring rationale must
    land on the same method node id.
    """
    path = _write_py(tmp_path, '''
        class Bar:
            @property
            def baz(self) -> int:
                """Return the baz value because callers expect a cached integer."""
                return 1

            @staticmethod
            def helper() -> int:
                """A static helper documented for downstream callers."""
                return 2

            @classmethod
            def factory(cls) -> "Bar":
                """Construct a Bar via the canonical classmethod entry point."""
                return cls()

            def normal(self) -> int:
                """A normal instance method documented for comparison."""
                return 3
    ''')
    result = extract_python(path)
    nodes_by_id = {n["id"]: n for n in result["nodes"]}

    # The plain method's id is the baseline: stem + class + name.
    normal_ids = [nid for nid, n in nodes_by_id.items()
                  if n.get("label") == ".normal()"]
    assert len(normal_ids) == 1, "expected exactly one ``.normal()`` method node"
    normal_id = normal_ids[0]
    assert normal_id.endswith("_bar_normal"), normal_id

    # Each decorated method must share the same class-qualified id shape so the
    # extracted rationale lands on the actual method node.
    for decorated_name in ("baz", "helper", "factory"):
        matches = [nid for nid, n in nodes_by_id.items()
                   if n.get("label") == f".{decorated_name}()"]
        assert len(matches) == 1, (
            f"expected exactly one ``.{decorated_name}()`` method node, got {matches}"
        )
        method_id = matches[0]
        assert method_id.endswith(f"_bar_{decorated_name}"), method_id
        # Unqualified id (the buggy form) must NOT also be present.
        unqualified_buggy_id = method_id.replace(f"_bar_{decorated_name}",
                                                  f"_{decorated_name}")
        assert unqualified_buggy_id not in nodes_by_id, (
            f"buggy unqualified id {unqualified_buggy_id} should not exist alongside "
            f"the class-qualified id"
        )

    # Rationale is stored directly on method nodes, not as rationale_for edges.
    g = build_from_json(result)
    for decorated_name in ("baz", "helper", "factory", "normal"):
        method_id = next(
            nid for nid, n in nodes_by_id.items()
            if n.get("label") == f".{decorated_name}()"
        )
        assert nodes_by_id[method_id].get("rationale"), (
            f"method node for ``.{decorated_name}()`` is missing docstring rationale"
        )
        assert method_id in g.nodes, f"method node {method_id} missing from graph"
        assert g.nodes[method_id].get("rationale"), (
            f"method node {method_id} lost rationale after build_from_json"
        )
