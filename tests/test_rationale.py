"""Tests for rationale/docstring extraction in extract.py.

Rationale is now stored as a 'rationale' attribute on the parent node
rather than as separate rationale nodes with rationale_for edges.
"""
import textwrap
from pathlib import Path
import pytest
from graphify.extract import extract_python


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
