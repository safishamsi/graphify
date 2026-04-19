"""Safe DSL evaluator for detector expressions."""
from __future__ import annotations

import ast
from typing import Any

from depos.analysis.detectors.dsl_helpers import HELPERS


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
)


class _SafetyVisitor(ast.NodeVisitor):
    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"unsupported DSL node: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            raise ValueError("dunder attribute access is not allowed")
        self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            raise ValueError("dunder names are not allowed")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id not in HELPERS:
                raise ValueError(f"helper '{node.func.id}' is not allowed")
        else:
            raise ValueError("only direct helper calls are allowed")
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)


def evaluate(expression: str, **context: Any) -> Any:
    tree = ast.parse(expression, mode="eval")
    _SafetyVisitor().visit(tree)
    safe_globals = {"__builtins__": {}}
    safe_locals = dict(HELPERS)
    safe_locals.update(context)
    return eval(compile(tree, "<detector-dsl>", "eval"), safe_globals, safe_locals)


__all__ = ["evaluate"]
