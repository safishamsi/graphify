from __future__ import annotations

import networkx as nx
import pytest

from depos.analysis.detectors.dsl import evaluate


def test_safe_eval_allows_whitelisted_helpers() -> None:
    graph = nx.DiGraph()
    graph.add_edge("a", "b", relation="HTTP_CALLS_ROUTE")
    node = {"label": "AuthRoute", "source_file": "apps/web/app/page.tsx"}

    result = evaluate(
        "regex('Auth', attr(node, 'label')) and has_edge(graph, 'HTTP_CALLS_ROUTE')",
        node=node,
        graph=graph,
        manifest=None,
        config=None,
        now=None,
        ctx={},
    )

    assert result is True


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "getattr(node, 'label')",
        "(lambda x: x)(1)",
        "[x for x in [1, 2, 3]]",
        "node.__class__",
    ],
)
def test_safe_eval_rejects_unsafe_ast(expression: str) -> None:
    with pytest.raises(ValueError):
        evaluate(expression, node={"label": "x"}, graph=nx.DiGraph(), manifest=None, config=None, now=None, ctx={})
