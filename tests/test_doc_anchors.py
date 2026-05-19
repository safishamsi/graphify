import tempfile
from pathlib import Path

import pytest

from graphify.extract import extract_doc_anchors, _make_id
from graphify.validate import validate_extraction


class TestDocAnchors:
    def test_yaml_frontmatter_graphify_id(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\ngraphify_id: auth_flow\n---\n# Auth Documentation\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 1
            assert result["nodes"][0]["file_type"] == "doc"
            assert result["nodes"][0]["section"] == "auth_flow"

    def test_yaml_frontmatter_anchors_list(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\nanchors: [setup, teardown, validate]\n---\nContent\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 3
            labels = {n["label"] for n in result["nodes"]}
            assert any("setup" in label for label in labels)

    def test_html_comment_graph_directive(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- GRAPH: SessionManager -->\nSome text\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 1
            assert len(result["edges"]) == 1
            assert result["edges"][0]["relation"] == "explains"
            assert result["edges"][0]["confidence"] == "EXTRACTED"

    def test_html_comment_see_directive(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- SEE: validate_token -->\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["edges"]) == 1
            assert result["edges"][0]["relation"] == "references"

    def test_html_comment_anchor_directive(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- ANCHOR: some_anchor -->\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["edges"]) == 1
            assert result["edges"][0]["relation"] == "references"

    def test_fenced_directive(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("```graphify id=auth_flow\nThis explains the auth flow\n```\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 1
            node = result["nodes"][0]
            assert node["section"] == "auth_flow"
            assert node["content"] == "This explains the auth flow"

    def test_header_with_explicit_id(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("## Authentication {#auth-init}\nContent about auth.\n## Next Section {#next}\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 2
            node = result["nodes"][0]
            assert "Authentication" in node["label"]
            assert node["section"] == "Authentication"
            assert node["content"] is not None

    def test_no_anchors_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Regular Markdown\n\nNo anchors here.\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert result["nodes"] == []
            assert result["edges"] == []

    def test_dedup_same_anchor_in_one_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- GRAPH: Foo -->\n<!-- GRAPH: Foo -->\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["nodes"]) == 1

    def test_validation_passes(self):
        """Doc anchors alone may have dangling edges (target code symbols from AST).
        Validation should pass when combined with AST nodes that provide the targets."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- GRAPH: Bar -->\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])

            # Edge should target _make_id("Bar") = "bar"
            assert len(result["edges"]) == 1
            assert result["edges"][0]["target"] == _make_id("Bar")

            # When combined with a matching AST node, validation passes
            combined = {
                "nodes": result["nodes"] + [
                    {"id": _make_id("Bar"), "label": "Bar", "file_type": "code", "source_file": "bar.py"}
                ],
                "edges": result["edges"],
            }
            errors = validate_extraction(combined)
            assert errors == [], f"Validation errors: {errors}"

    def test_doc_anchor_coexists_with_document_node(self):
        """A doc anchor node and a regular document node from the same file must coexist."""
        from graphify.extract import extract_markdown

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Auth Guide\n\n<!-- GRAPH: SessionManager -->\n\n## Setup {#setup}\n")
            f.flush()
            path = Path(f.name)

            md_result = extract_markdown(path)
            doc_result = extract_doc_anchors([path])

            md_node_ids = {n["id"] for n in md_result["nodes"]}
            doc_node_ids = {n["id"] for n in doc_result["nodes"]}

            assert len(md_node_ids & doc_node_ids) == 0, "No ID collision between document and doc nodes"

            combined_nodes = md_result["nodes"] + doc_result["nodes"]
            combined_ids = {n["id"] for n in combined_nodes}
            assert len(combined_ids) == len(combined_nodes), "All IDs unique when combined"

            doc_types = {n.get("file_type") for n in combined_nodes}
            assert "document" in doc_types
            assert "doc" in doc_types

    def test_multiple_files(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f1:
            f1.write("<!-- GRAPH: Alpha -->\n")
            f1.flush()
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f2:
                f2.write("<!-- GRAPH: Beta -->\n")
                f2.flush()
                result = extract_doc_anchors([Path(f1.name), Path(f2.name)])
                assert len(result["nodes"]) == 2

    def test_edge_target_matches_ast_id_format(self):
        """Edge targets from GRAPH directives should match _make_id(symbol) format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("<!-- GRAPH: SessionManager -->\n")
            f.flush()
            result = extract_doc_anchors([Path(f.name)])
            assert len(result["edges"]) == 1
            expected_target = _make_id("SessionManager")
            assert result["edges"][0]["target"] == expected_target

    def test_oserror_handled_gracefully(self):
        """Non-existent files should be skipped without raising."""
        result = extract_doc_anchors([Path("/nonexistent/path/file.md")])
        assert result["nodes"] == []
        assert result["edges"] == []
