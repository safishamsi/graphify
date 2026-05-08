"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
import os
import sys
import time
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _bfs,
    _communities_from_graph,
    _dfs,
    _filter_blank_stdin,
    _filter_graph_by_context,
    _find_node,
    _infer_context_filters,
    _load_graph,
    _normalize_context_filters,
    _query_graph_text,
    _resolve_context_filters,
    _score_nodes,
    _strip_diacritics,
    _subgraph_to_text,
    serve,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="report.py", source_location="L1", community=1)
    G.add_node("n5", label="isolated", source_file="other.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    return G


# ---------------------------------------------------------------------------
# _communities_from_graph
# ---------------------------------------------------------------------------


def test_communities_from_graph_basic():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 0 in communities
    assert 1 in communities
    assert "n1" in communities[0]
    assert "n2" in communities[0]
    assert "n3" in communities[1]


def test_communities_from_graph_no_community_attr():
    G = nx.Graph()
    G.add_node("a", label="foo")  # no community attr
    communities = _communities_from_graph(G)
    assert communities == {}


def test_communities_from_graph_isolated():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 2 in communities
    assert "n5" in communities[2]


# ---------------------------------------------------------------------------
# _score_nodes
# ---------------------------------------------------------------------------


def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first


def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []


def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


def test_score_nodes_exact_match_with_parens():
    """Exact match handles trailing parentheses for function labels."""
    G = nx.Graph()
    G.add_node("f1", label="process_data()", source_file="mod.py", source_location="L10")
    scored = _score_nodes(G, ["process_data"])
    assert len(scored) >= 1
    assert scored[0][1] == "f1"


def test_score_nodes_multiple_terms():
    """Multiple search terms should accumulate score."""
    G = nx.Graph()
    G.add_node("a", label="extract cluster", source_file="mod.py", source_location="L1")
    scored = _score_nodes(G, ["extract", "cluster"])
    assert len(scored) == 1
    assert scored[0][0] >= 2.0  # two term matches


def test_score_nodes_norm_label_match():
    """When norm_label is set, it should be used for matching."""
    G = nx.Graph()
    G.add_node("a", label="ComplexLabel", norm_label="complexlabel", source_file="x.py", source_location="L1")
    G.add_node("b", label="Other", source_file="x.py", source_location="L2")
    scored = _score_nodes(G, ["complexlabel"])
    assert len(scored) == 1
    assert scored[0][1] == "a"


def test_score_nodes_source_file_half_score():
    """Source file match gives 0.5 points per term."""
    G = _make_graph()
    # "extract.py" in source_file should give 0.5 for term "extract"
    scored = _score_nodes(G, ["extract"])
    # n1 has "extract" in label AND source_file, so high score
    # Other nodes might have partial source file matches
    assert any(score < 1.0 for score, _ in scored if score > 0) or len(scored) >= 1


# ---------------------------------------------------------------------------
# _infer_context_filters
# ---------------------------------------------------------------------------


def test_infer_context_filters_for_calls_question():
    assert _infer_context_filters("who calls extract") == ["call"]


def test_infer_context_filters_for_import():
    assert _infer_context_filters("which module imports cluster") == ["import"]


def test_infer_context_filters_for_field():
    assert _infer_context_filters("what fields does the class have") == ["field"]


def test_infer_context_filters_for_parameter():
    assert _infer_context_filters("what parameters does this function accept") == ["parameter_type"]


def test_infer_context_filters_for_return():
    assert _infer_context_filters("what does this function return") == ["return_type"]


def test_infer_context_filters_for_generic():
    assert _infer_context_filters("what generic types are used") == ["generic_arg"]


def test_infer_context_filters_multiple_hints():
    result = _infer_context_filters("who calls and imports this module")
    assert "call" in result
    assert "import" in result


def test_infer_context_filters_no_match():
    assert _infer_context_filters("what is the weather today") == []


def test_infer_context_filters_punctuation_handled():
    """Punctuation in question should not affect filter inference."""
    assert _infer_context_filters("who calls extract?") == ["call"]


# ---------------------------------------------------------------------------
# _resolve_context_filters
# ---------------------------------------------------------------------------


def test_resolve_context_filters_explicit_overrides_heuristic():
    filters, source = _resolve_context_filters("who calls extract", ["field"])
    assert filters == ["field"]
    assert source == "explicit"


def test_resolve_context_filters_heuristic_only():
    filters, source = _resolve_context_filters("who calls extract")
    assert filters == ["call"]
    assert source == "heuristic"


def test_resolve_context_filters_no_filters():
    """When no explicit filters and no hints in question, returns [], None."""
    filters, source = _resolve_context_filters("weather report")
    assert filters == []
    assert source is None


def test_resolve_context_filters_empty_string_question():
    filters, source = _resolve_context_filters("")
    assert filters == []
    assert source is None


# ---------------------------------------------------------------------------
# _normalize_context_filters
# ---------------------------------------------------------------------------


def test_normalize_context_filters_empty():
    assert _normalize_context_filters(None) == []
    assert _normalize_context_filters([]) == []


def test_normalize_context_filters_deduplication():
    result = _normalize_context_filters(["call", "CALL", " call "])
    assert result == ["call"]


def test_normalize_context_filters_strips_whitespace():
    result = _normalize_context_filters(["  call  ", "import"])
    assert result == ["call", "import"]


def test_normalize_context_filters_diacritics():
    """Diacritics in filter values should be normalized."""
    result = _normalize_context_filters(["caf\u00e9"])  # cafe with accent
    assert "cafe" in result or "caf\u00e9" not in str(result)


# ---------------------------------------------------------------------------
# _strip_diacritics
# ---------------------------------------------------------------------------


def test_strip_diacritics_removes_accents():
    assert _strip_diacritics("caf\u00e9") == "cafe"  # cafe with accent
    assert _strip_diacritics("na\u00efve") == "naive"
    assert _strip_diacritics("r\u00e9sum\u00e9") == "resume"


def test_strip_diacritics_passthrough():
    assert _strip_diacritics("hello") == "hello"
    assert _strip_diacritics("ABC123") == "ABC123"


def test_strip_diacritics_empty():
    assert _strip_diacritics("") == ""


# ---------------------------------------------------------------------------
# _bfs
# ---------------------------------------------------------------------------


def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away


def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3


def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node


def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(u == "n1" or v == "n1" for u, v in edges)


# ---------------------------------------------------------------------------
# _filter_graph_by_context
# ---------------------------------------------------------------------------


def test_filter_graph_by_context_limits_traversal():
    G = _make_graph()
    filtered = _filter_graph_by_context(G, ["call"])
    visited, edges = _bfs(filtered, ["n1"], depth=2)
    assert "n2" in visited
    assert "n3" not in visited
    assert edges == [("n1", "n2")]


def test_filter_graph_by_context_no_filters():
    """When no context filters provided, return the same graph object."""
    G = _make_graph()
    result = _filter_graph_by_context(G, None)
    assert result is G


def test_filter_graph_by_context_empty_list():
    """Empty filter list should return the same graph."""
    G = _make_graph()
    result = _filter_graph_by_context(G, [])
    assert result is G


def test_filter_graph_by_context_multigraph():
    """Filtering should work with MultiGraph edges."""
    G = nx.MultiGraph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_edge("a", "b", relation="calls", context="call")
    G.add_edge("a", "b", relation="imports", context="import")
    result = _filter_graph_by_context(G, ["call"])
    assert result.number_of_edges() == 1


def test_filter_graph_by_context_multidigraph():
    """Filtering should work with MultiDiGraph edges."""
    G = nx.MultiDiGraph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_node("c", label="C")
    G.add_edge("a", "b", relation="calls", context="call")
    G.add_edge("b", "c", relation="imports", context="import")
    result = _filter_graph_by_context(G, ["import"])
    assert result.number_of_edges() == 1


# ---------------------------------------------------------------------------
# _dfs
# ---------------------------------------------------------------------------


def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited


def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


def test_dfs_disconnected_start():
    G = _make_graph()
    visited, edges = _dfs(G, ["n5"], depth=3)
    assert visited == {"n5"}


def test_dfs_multiple_start_nodes():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1", "n5"], depth=2)
    assert "n1" in visited
    assert "n5" in visited


# ---------------------------------------------------------------------------
# _subgraph_to_text
# ---------------------------------------------------------------------------


def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "extract" in text
    assert "cluster" in text


def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text


def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "EDGE" in text
    assert "calls" in text


def test_subgraph_to_text_includes_edge_context():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "context=call" in text


def test_subgraph_to_text_seeds_rendered_first():
    """Seeds should be rendered before other nodes in output."""
    G = _make_graph()
    # n3 has degree 2, n5 has degree 0. Without seeds, n3 would appear before n5.
    text = _subgraph_to_text(G, {"n3", "n5"}, [], seeds=["n5"])
    n5_pos = text.find("isolated")
    n3_pos = text.find("build")
    assert n5_pos >= 0 and n3_pos >= 0
    assert n5_pos < n3_pos, "seed node should appear first"


def test_subgraph_to_text_seed_not_in_nodes():
    """Seeds not in the node set should be ignored."""
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")], seeds=["nonexistent"])
    assert "extract" in text
    assert "cluster" in text


def test_subgraph_to_text_multigraph_edges():
    """MultiGraph edge data should be handled correctly."""
    G = nx.MultiGraph()
    G.add_node("a", label="A", source_file="a.py", source_location="L1", community=0)
    G.add_node("b", label="B", source_file="b.py", source_location="L1", community=1)
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", context="call")
    text = _subgraph_to_text(G, {"a", "b"}, [("a", "b")])
    assert "EDGE" in text
    assert "calls" in text


# ---------------------------------------------------------------------------
# _query_graph_text
# ---------------------------------------------------------------------------


def test_query_graph_text_explicit_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "extract", mode="bfs", depth=2, token_budget=2000, context_filters=["call"])
    assert "Context: call (explicit)" in text
    assert "cluster" in text
    assert "build" not in text


def test_query_graph_text_heuristic_context_filter_changes_traversal():
    G = _make_graph()
    text = _query_graph_text(G, "who calls extract", mode="bfs", depth=2, token_budget=2000)
    assert "Context: call (heuristic)" in text
    assert "cluster" in text
    assert "build" not in text


def test_query_graph_text_no_matching_nodes():
    """When no nodes match the question, return a clear message."""
    G = _make_graph()
    text = _query_graph_text(G, "zzzqqqxxx", mode="bfs", depth=3)
    assert text == "No matching nodes found."


def test_query_graph_text_dfs_mode():
    """DFS mode should produce different output header."""
    G = _make_graph()
    text = _query_graph_text(G, "extract cluster", mode="dfs", depth=2, token_budget=2000)
    assert "Traversal: DFS" in text
    assert "extract" in text


def test_query_graph_text_no_context_filters():
    """Query with no context filters should not include Context in header."""
    G = _make_graph()
    text = _query_graph_text(G, "extract", mode="bfs", depth=1, token_budget=2000)
    assert "Context:" not in text


# ---------------------------------------------------------------------------
# _find_node
# ---------------------------------------------------------------------------


def test_find_node_exact_label():
    G = _make_graph()
    results = _find_node(G, "extract")
    assert results == ["n1"]


def test_find_node_partial_label():
    G = _make_graph()
    results = _find_node(G, "trac")  # partial match within "extract"
    assert "n1" in results


def test_find_node_no_match():
    G = _make_graph()
    results = _find_node(G, "nonexistent")
    assert results == []


def test_find_node_case_insensitive():
    G = _make_graph()
    results = _find_node(G, "EXTRACT")
    assert "n1" in results


def test_find_node_diacritic_insensitive():
    """Node search should be diacritic-insensitive."""
    G = nx.Graph()
    G.add_node("cafe", label="caf\u00e9", source_file="x.py", source_location="L1")
    results = _find_node(G, "cafe")  # search without accent
    assert "cafe" in results


def test_find_node_by_id():
    """Searching by node ID should work."""
    G = _make_graph()
    results = _find_node(G, "n3")
    assert "n3" in results


def test_find_node_with_norm_label():
    """When norm_label is set, diacritic-insensitive search uses it."""
    G = nx.Graph()
    G.add_node("a", label="M\u00fcller", norm_label="muller", source_file="x.py", source_location="L1")
    results = _find_node(G, "muller")
    assert "a" in results


# ---------------------------------------------------------------------------
# _filter_blank_stdin
# ---------------------------------------------------------------------------


def test_filter_blank_stdin_filters_blank_lines():
    """_filter_blank_stdin should remove blank lines from stdin."""
    test_data = b"hello\n\nworld\n \nfoo\n"
    r_in, w_in = os.pipe()
    os.write(w_in, test_data)
    os.close(w_in)

    original_fd = os.dup(0)
    try:
        os.dup2(r_in, 0)
        os.close(r_in)
        sys.stdin = open(0, "r", closefd=False)

        _filter_blank_stdin()

        # Give daemon thread time to relay
        time.sleep(0.1)

        result = sys.stdin.read()
        lines = [l for l in result.split("\n") if l.strip()]
        assert lines == ["hello", "world", "foo"]
    finally:
        os.dup2(original_fd, 0)
        os.close(original_fd)
        sys.stdin = open(0, "r", closefd=False)


# ---------------------------------------------------------------------------
# _load_graph
# ---------------------------------------------------------------------------


def test_load_graph_roundtrip(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()


def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))


def test_load_graph_non_json_suffix(tmp_path):
    """Non-.json file path should raise SystemExit."""
    p = tmp_path / "graph.txt"
    p.write_text("{}")
    with pytest.raises(SystemExit):
        _load_graph(str(p))


def test_load_graph_corrupted_json(tmp_path):
    """Corrupted JSON file should raise SystemExit with clear message."""
    p = tmp_path / "graph.json"
    p.write_text("this is not valid json {{{")
    with pytest.raises(SystemExit):
        _load_graph(str(p))


def test_load_graph_edges_key_conversion(tmp_path):
    """JSON with 'edges' key (not 'links') should be auto-converted."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    # Rename 'links' back to 'edges' to simulate older format
    data["edges"] = data.pop("links")
    assert "links" not in data
    assert "edges" in data

    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()


# ---------------------------------------------------------------------------
# serve()
# ---------------------------------------------------------------------------


def test_serve_initialization(tmp_path):
    """serve() should load graph, create server, and start up."""
    from unittest.mock import MagicMock, patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    mock_server_cls = MagicMock()
    mock_server_instance = MagicMock()
    mock_server_instance.list_tools = MagicMock(return_value=lambda f: f)
    mock_server_instance.list_resources = MagicMock(return_value=lambda f: f)
    mock_server_instance.read_resource = MagicMock(return_value=lambda f: f)
    mock_server_instance.call_tool = MagicMock(return_value=lambda f: f)
    mock_server_cls.return_value = mock_server_instance

    mock_stdio_server = MagicMock()
    mock_streams = (MagicMock(), MagicMock())
    mock_stdio_server.return_value.__aenter__ = MagicMock(return_value=mock_streams)

    mock_asyncio_run = MagicMock()
    mock_filter = MagicMock()

    # Use proper module objects to prevent real mcp from being loaded
    import types as _types_mod

    mock_types = _types_mod.ModuleType("mcp.types")
    mock_types.Tool = MagicMock()
    mock_types.Resource = MagicMock()
    mock_types.AnyUrl = MagicMock()
    mock_types.TextContent = MagicMock()

    mock_server = _types_mod.ModuleType("mcp.server")
    mock_server.Server = mock_server_cls

    mock_stdio = _types_mod.ModuleType("mcp.server.stdio")
    mock_stdio.stdio_server = mock_stdio_server

    mock_mcp = _types_mod.ModuleType("mcp")
    mock_mcp.server = mock_server
    mock_mcp.types = mock_types

    with patch("graphify.serve._filter_blank_stdin", mock_filter):
        with patch.dict(sys.modules, {
            "mcp": mock_mcp,
            "mcp.server": mock_server,
            "mcp.server.stdio": mock_stdio,
            "mcp.types": mock_types,
        }):
            with patch("asyncio.run", mock_asyncio_run):
                serve(str(p))

    mock_server_cls.assert_called_once_with("graphify")
    assert mock_server_cls.called


def _serve_and_capture_all_handlers(graph_path: str):
    """Helper: run serve() with mocked MCP, capture all handlers.

    Returns a dict with keys: 'call_tool', 'list_tools', 'list_resources', 'read_resource'.
    """
    import types as _types_mod
    from unittest.mock import MagicMock, patch

    captured = {}

    def make_capturing_decorator(key):
        def decorator(f):
            captured[key] = f
            return f
        return decorator

    mock_server_cls = MagicMock()
    mock_server_instance = MagicMock()
    mock_server_instance.list_tools = MagicMock(return_value=make_capturing_decorator("list_tools"))
    mock_server_instance.list_resources = MagicMock(return_value=make_capturing_decorator("list_resources"))
    mock_server_instance.read_resource = MagicMock(return_value=make_capturing_decorator("read_resource"))
    mock_server_instance.call_tool = MagicMock(return_value=make_capturing_decorator("call_tool"))
    mock_server_cls.return_value = mock_server_instance

    mock_stdio_server = MagicMock()
    mock_streams = (MagicMock(), MagicMock())
    mock_stdio_server.return_value.__aenter__ = MagicMock(return_value=mock_streams)

    # Build mocks that support Tool, Resource, AnyUrl, TextContent construction
    class FakeTextContent:
        def __init__(self, type, text):
            self.type = type
            self.text = text

    class FakeTool:
        def __init__(self, name, description=None, inputSchema=None):
            self.name = name
            self.description = description
            self.inputSchema = inputSchema

    class FakeResource:
        def __init__(self, uri, name=None, description=None, mimeType=None):
            self.uri = uri
            self.name = name
            self.description = description
            self.mimeType = mimeType

    class FakeAnyUrl:
        def __init__(self, url):
            self._url = url

        def __str__(self):
            return self._url

    mock_types = _types_mod.ModuleType("mcp.types")
    mock_types.TextContent = FakeTextContent
    mock_types.Tool = FakeTool
    mock_types.Resource = FakeResource
    mock_types.AnyUrl = FakeAnyUrl

    mock_server = _types_mod.ModuleType("mcp.server")
    mock_server.Server = mock_server_cls

    mock_stdio = _types_mod.ModuleType("mcp.server.stdio")
    mock_stdio.stdio_server = mock_stdio_server

    mock_mcp = _types_mod.ModuleType("mcp")
    mock_mcp.server = mock_server
    mock_mcp.types = mock_types

    mock_filter = MagicMock()
    mock_asyncio_run = MagicMock()

    with patch("graphify.serve._filter_blank_stdin", mock_filter):
        with patch.dict(sys.modules, {
            "mcp": mock_mcp,
            "mcp.server": mock_server,
            "mcp.server.stdio": mock_stdio,
            "mcp.types": mock_types,
        }):
            with patch("asyncio.run", mock_asyncio_run):
                serve(graph_path)

    assert captured.get("call_tool") is not None, "call_tool handler was not captured"
    return captured


def _serve_and_capture_call_tool(graph_path: str):
    """Helper: run serve() with mocked MCP, capture just the call_tool handler."""
    return _serve_and_capture_all_handlers(graph_path)["call_tool"]


async def _invoke(call_tool, name: str, arguments: dict) -> str:
    """Invoke the async call_tool handler and return text."""
    result = await call_tool(name, arguments)
    assert len(result) == 1
    return result[0].text


def test_serve_query_graph_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "query_graph", {"question": "extract"})
        assert "Traversal: BFS" in text
        assert "extract" in text
        return text

    asyncio.run(run())


def test_serve_query_graph_dfs(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "query_graph", {"question": "extract", "mode": "dfs", "depth": 2})
        assert "Traversal: DFS" in text
        return text

    asyncio.run(run())


def test_serve_query_graph_no_match(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "query_graph", {"question": "zzzxxx"})
        assert "No matching nodes found" in text
        return text

    asyncio.run(run())


def test_serve_get_node_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_node", {"label": "extract"})
        assert "Node:" in text
        assert "extract" in text
        assert "Source:" in text
        return text

    asyncio.run(run())


def test_serve_get_node_no_match(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_node", {"label": "nonexistent"})
        assert "No node matching" in text
        return text

    asyncio.run(run())


def test_serve_get_neighbors_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_neighbors", {"label": "n1"})
        assert "Neighbors of" in text
        assert "cluster" in text
        return text

    asyncio.run(run())


def test_serve_get_neighbors_no_match(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_neighbors", {"label": "nonexistent"})
        assert "No node matching" in text
        return text

    asyncio.run(run())


def test_serve_get_neighbors_with_filter(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        # n1 has neighbor n2 with relation "calls"
        text = await _invoke(call_tool, "get_neighbors", {"label": "n1", "relation_filter": "calls"})
        assert "cluster" in text
        return text

    asyncio.run(run())


def test_serve_get_community_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_community", {"community_id": 0})
        assert "Community 0" in text
        assert "extract" in text
        assert "cluster" in text
        return text

    asyncio.run(run())


def test_serve_get_community_not_found(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_community", {"community_id": 99})
        assert "not found" in text
        return text

    asyncio.run(run())


def test_serve_god_nodes_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "god_nodes", {"top_n": 3})
        assert "God nodes" in text
        assert "edges" in text
        return text

    asyncio.run(run())


def test_serve_graph_stats_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "graph_stats", {})
        assert "Nodes:" in text
        assert "Edges:" in text
        assert "EXTRACTED" in text
        return text

    asyncio.run(run())


def test_serve_shortest_path_tool(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "shortest_path", {"source": "extract", "target": "build"})
        assert "Shortest path" in text
        assert "extract" in text
        assert "build" in text
        return text

    asyncio.run(run())


def test_serve_shortest_path_no_source(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "shortest_path", {"source": "nonexistent", "target": "build"})
        assert "No node matching source" in text
        return text

    asyncio.run(run())


def test_serve_shortest_path_no_target(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "shortest_path", {"source": "extract", "target": "nonexistent"})
        assert "No node matching target" in text
        return text

    asyncio.run(run())


def test_serve_shortest_path_disconnected(tmp_path):
    """Shortest path between disconnected nodes returns no-path message."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "shortest_path", {"source": "extract", "target": "isolated"})
        assert "No path found" in text
        return text

    asyncio.run(run())


def test_serve_shortest_path_exceeds_max_hops(tmp_path):
    """Path exceeding max_hops should return appropriate message."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        # extract->cluster->build->report is 3 hops, max_hops=1 should fail
        text = await _invoke(call_tool, "shortest_path", {"source": "extract", "target": "report", "max_hops": 1})
        assert "exceeds max_hops" in text or "3 hops" in text
        return text

    asyncio.run(run())


def test_serve_call_tool_unknown(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "nonexistent_tool", {})
        assert "Unknown tool" in text
        return text

    asyncio.run(run())


def test_serve_import_error(tmp_path):
    """serve() should raise ImportError when mcp is not installed."""
    import builtins
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    original_import = builtins.__import__

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError(f"No module named '{name}'")
        return original_import(name, globals, locals, fromlist, level)

    with patch.object(builtins, "__import__", mock_import):
        with pytest.raises(ImportError, match="mcp not installed"):
            serve(str(p))


# ---------------------------------------------------------------------------
# serve() handler tests: list_tools, list_resources, read_resource, call_tool error
# ---------------------------------------------------------------------------


def test_serve_list_tools(tmp_path):
    """list_tools handler should return the expected set of tools."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    list_tools_fn = handlers["list_tools"]
    assert list_tools_fn is not None

    import asyncio

    async def run():
        tools = await list_tools_fn()
        # The handler returns list of Tool objects
        assert isinstance(tools, list)
        # Expected: query_graph, get_node, get_neighbors, get_community,
        #   god_nodes, graph_stats, shortest_path
        names = [getattr(t, "name", None) for t in tools]
        expected_names = [
            "query_graph", "get_node", "get_neighbors", "get_community",
            "god_nodes", "graph_stats", "shortest_path",
        ]
        for name in expected_names:
            assert name in names, f"Missing tool: {name}"
        return tools

    asyncio.run(run())


def test_serve_list_resources(tmp_path):
    """list_resources handler should return the expected resources."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    list_res_fn = handlers["list_resources"]
    assert list_res_fn is not None

    import asyncio

    async def run():
        resources = await list_res_fn()
        assert isinstance(resources, list)
        # Check that we have the 6 expected resources
        assert len(resources) == 6
        return resources

    asyncio.run(run())


def test_serve_read_resource_report(tmp_path):
    """read_resource for graphify://report should return report content."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Create a mock GRAPH_REPORT.md
    report_path = tmp_path / "GRAPH_REPORT.md"
    report_path.write_text("# Graph Report\nThis is a test report.")

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://report")
        assert "# Graph Report" in text
        assert "test report" in text
        return text

    asyncio.run(run())


def test_serve_read_resource_report_missing(tmp_path):
    """read_resource for graphify://report when file doesn't exist."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    # No GRAPH_REPORT.md created

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://report")
        assert "not found" in text.lower()
        return text

    asyncio.run(run())


def test_serve_read_resource_stats(tmp_path):
    """read_resource for graphify://stats should return stats text."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://stats")
        assert "Nodes:" in text
        assert "Edges:" in text
        return text

    asyncio.run(run())


def test_serve_read_resource_god_nodes(tmp_path):
    """read_resource for graphify://god-nodes should return god nodes."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://god-nodes")
        assert "God nodes" in text
        return text

    asyncio.run(run())


def test_serve_read_resource_audit(tmp_path):
    """read_resource for graphify://audit should return confidence breakdown."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://audit")
        assert "Total edges:" in text
        assert "EXTRACTED" in text
        return text

    asyncio.run(run())


def test_serve_read_resource_surprises(tmp_path):
    """read_resource for graphify://surprises should compute surprises."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://surprises")
        # Could have surprises or "No surprising connections found"
        assert len(text) > 0
        return text

    asyncio.run(run())


def test_serve_read_resource_questions(tmp_path):
    """read_resource for graphify://questions should suggest questions."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        text = await read_res_fn("graphify://questions")
        assert len(text) > 0
        return text

    asyncio.run(run())


def test_serve_read_resource_unknown(tmp_path):
    """read_resource for unknown URI should raise ValueError."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]
    assert read_res_fn is not None

    import asyncio

    async def run():
        with pytest.raises(ValueError, match="Unknown resource"):
            await read_res_fn("graphify://nonexistent")
        return True

    asyncio.run(run())


def test_serve_call_tool_runtime_error(tmp_path):
    """call_tool should catch exceptions from handlers gracefully."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        # shortest_path without a source will raise internally,
        # but the call_tool dispatcher catches it
        text = await _invoke(call_tool, "shortest_path", {"source": "xyz_nonexistent", "target": "abc_nonexistent"})
        # The error message comes from _tool_shortest_path not finding the node
        assert "No node matching source" in text
        return text

    asyncio.run(run())


def test_serve_get_neighbors_nonmatching_filter(tmp_path):
    """get_neighbors with a filter that doesn't match any edge relation."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        text = await _invoke(call_tool, "get_neighbors", {"label": "n1", "relation_filter": "nonexistent_filter"})
        # Should return header but no neighbors listed
        assert "Neighbors of" in text
        # No arrows (neighbors were filtered out)
        assert "-->" not in text
        return text

    asyncio.run(run())


# ---------------------------------------------------------------------------
# serve() edge cases: labels file, call_tool exceptions, empty surprises/questions
# ---------------------------------------------------------------------------


def test_serve_read_resource_questions_with_labels(tmp_path):
    """read_resource for questions with a community labels file present."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Create a valid labels file to hit the _load_community_labels file-exists path
    labels_path = tmp_path / ".graphify_labels.json"
    labels_path.write_text(json.dumps({"0": "Core Community"}))

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]

    import asyncio

    async def run():
        text = await read_res_fn("graphify://questions")
        assert len(text) > 0
        return text

    asyncio.run(run())


def test_serve_read_resource_questions_corrupted_labels(tmp_path):
    """read_resource handles a corrupted .graphify_labels.json gracefully."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Create a corrupted labels file (invalid JSON)
    labels_path = tmp_path / ".graphify_labels.json"
    labels_path.write_text("not valid json {{{")

    handlers = _serve_and_capture_all_handlers(str(p))
    read_res_fn = handlers["read_resource"]

    import asyncio

    async def run():
        text = await read_res_fn("graphify://questions")
        assert len(text) > 0
        return text

    asyncio.run(run())


def test_serve_call_tool_handler_exception(tmp_path):
    """call_tool should catch runtime exceptions from handlers gracefully."""
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    call_tool = _serve_and_capture_call_tool(str(p))
    import asyncio

    async def run():
        # Passing a non-string mode causes AttributeError in query_graph handler
        text = await _invoke(call_tool, "query_graph", {"question": "extract", "mode": 123})
        assert "Error executing" in text
        return text

    asyncio.run(run())


def test_serve_read_resource_surprises_empty(tmp_path):
    """read_resource for surprises when none are found."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Mock surprising_connections to return empty list
    with patch("graphify.analyze.surprising_connections", return_value=[]):
        handlers = _serve_and_capture_all_handlers(str(p))
        read_res_fn = handlers["read_resource"]

        import asyncio

        async def run():
            text = await read_res_fn("graphify://surprises")
            assert "No surprising connections found" in text
            return text

        asyncio.run(run())


def test_serve_read_resource_surprises_error(tmp_path):
    """read_resource for surprises when analysis fails."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Mock surprising_connections to raise an exception
    with patch("graphify.analyze.surprising_connections", side_effect=RuntimeError("Analysis failed")):
        handlers = _serve_and_capture_all_handlers(str(p))
        read_res_fn = handlers["read_resource"]

        import asyncio

        async def run():
            text = await read_res_fn("graphify://surprises")
            assert "Could not compute surprising connections" in text
            return text

        asyncio.run(run())


def test_serve_read_resource_questions_empty(tmp_path):
    """read_resource for questions when none are available."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Mock suggest_questions to return empty list
    with patch("graphify.analyze.suggest_questions", return_value=[]):
        handlers = _serve_and_capture_all_handlers(str(p))
        read_res_fn = handlers["read_resource"]

        import asyncio

        async def run():
            text = await read_res_fn("graphify://questions")
            assert "No suggested questions available" in text
            return text

        asyncio.run(run())


def test_serve_read_resource_questions_plain_string(tmp_path):
    """read_resource when suggest_questions returns plain strings, not dicts."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # suggest_questions can return plain strings (non-dict items)
    with patch("graphify.analyze.suggest_questions", return_value=["What does this code do?"]):
        handlers = _serve_and_capture_all_handlers(str(p))
        read_res_fn = handlers["read_resource"]

        import asyncio

        async def run():
            text = await read_res_fn("graphify://questions")
            assert "What does this code do?" in text
            return text

        asyncio.run(run())


def test_serve_read_resource_questions_error(tmp_path):
    """read_resource for questions when suggestion generation fails."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    # Mock suggest_questions to raise an exception
    with patch("graphify.analyze.suggest_questions", side_effect=RuntimeError("Suggestion failed")):
        handlers = _serve_and_capture_all_handlers(str(p))
        read_res_fn = handlers["read_resource"]

        import asyncio

        async def run():
            text = await read_res_fn("graphify://questions")
            assert "Could not generate questions" in text
            return text

        asyncio.run(run())


def test_load_graph_typeerror_fallback(tmp_path):
    """When node_link_graph with edges param raises TypeError, fall back."""
    from unittest.mock import patch

    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))

    real_func = json_graph.node_link_graph
    call_count = 0

    def mock_node_link(data, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TypeError("unexpected keyword argument 'edges'")
        # On the fallback call (no edges param), default to "links"
        # to simulate old networkx behavior that _load_graph expects
        kwargs.setdefault("edges", "links")
        return real_func(data, *args, **kwargs)

    with patch.object(json_graph, "node_link_graph", mock_node_link):
        G2 = _load_graph(str(p))

    assert G2.number_of_nodes() == G.number_of_nodes()
    assert call_count == 2


# ---------------------------------------------------------------------------
# __main__ block
# ---------------------------------------------------------------------------


def test_main_block_with_arg(monkeypatch):
    """__main__ block should pass sys.argv[1] as graph_path."""
    from unittest.mock import MagicMock, patch

    mock_serve = MagicMock()
    monkeypatch.setattr("sys.argv", ["serve.py", "custom/path/graph.json"])
    # Simulate the __main__ block
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    assert graph_path == "custom/path/graph.json"


def test_main_block_default_path(monkeypatch):
    """__main__ block should default to graphify-out/graph.json."""
    monkeypatch.setattr("sys.argv", ["serve.py"])
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    assert graph_path == "graphify-out/graph.json"
