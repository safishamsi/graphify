"""Cross-link prompt render/load calls to prompt template nodes."""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

_PROMPT_LOAD = re.compile(r"""(?:load_prompt|render_prompt|compile)\(\s*['"]([^'"]+)['"]""")
_PROMPT_BINDING = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:")


def emit_prompt_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    _ = repo_root
    prompts: dict[str, str] = {}
    for node_id, attrs in graph.nodes(data=True):
        if str(attrs.get("node_kind") or "") == "prompt_template":
            prompts[str(attrs.get("name") or Path(str(attrs.get("source_file") or "")).stem)] = node_id
    added = 0
    for source_id, attrs in list(graph.nodes(data=True)):
        if not attrs.get("source_file") or str(attrs.get("node_kind") or "") == "prompt_template":
            continue
        text = str(attrs.get("embedded_text") or attrs.get("label") or "")
        if not text and Path(str(attrs.get("source_file"))).exists():
            try:
                text = Path(str(attrs.get("source_file"))).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
        for match in _PROMPT_LOAD.finditer(text):
            name = match.group(1).split("/")[-1].split(".")[0]
            target_id = prompts.get(name)
            if not target_id or graph.has_edge(source_id, target_id):
                continue
            bindings = sorted(set(_PROMPT_BINDING.findall(text)))
            graph.add_edge(
                source_id,
                target_id,
                relation="RENDERED_BY_PROMPT",
                source_system="code",
                target_system="prompt",
                confidence=0.85,
                inferred=True,
                variable_bindings=bindings,
            )
            added += 1
    return added


__all__ = ["emit_prompt_edges"]
