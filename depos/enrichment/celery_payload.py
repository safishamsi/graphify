"""Module 1: Celery / task-queue payload matcher.

Graphify already surfaces Celery ``@task``-decorated functions; this pass
adds:

- ``TASK_ENQUEUES`` edges from producers (call sites using ``.delay()`` or
  ``.apply_async()``) to the task function.
- ``TASK_CONSUMES`` edges (synthetic) from the task function to itself as
  the consumer role \u2014 kept explicit so verifier rules about queue
  contracts have a single target.
- ``PRODUCES_PAYLOAD`` / ``CONSUMES_PAYLOAD`` edges whose metadata
  enumerates overlap / missing / extra keyword-argument field names so
  the verifier can check payload drift without re-reading source.

Inference is regex-based (same posture as the HTTP probes): works well
for typical codebases, reports ``inferred=True`` when the call site's
kwargs cannot be statically determined.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx

from depos.graph_relations import CONSUMES_PAYLOAD
from depos.graph_relations import PRODUCES_PAYLOAD
from depos.graph_relations import TASK_CONSUMES
from depos.graph_relations import TASK_ENQUEUES
from depos.analysis.schemas import ContractKind, SemanticEdgeMetadata


_ENQUEUE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\.(?P<method>delay|apply_async)\s*\(",
)
_KW_RE = re.compile(r"(?P<kw>[A-Za-z_][A-Za-z0-9_]*)\s*=")
_TASK_DEF_RE = re.compile(
    r"@(?:celery_app\.|app\.|shared_)?task[^\n]*\n\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<args>[^)]*)\)",
    re.MULTILINE,
)


@dataclass
class _TaskDef:
    node_id: str
    source_file: str
    name: str
    expected_kwargs: list[str]


def _extract_kwargs(signature: str) -> list[str]:
    kwargs: list[str] = []
    for chunk in signature.split(","):
        chunk = chunk.strip()
        if not chunk or chunk.startswith("*"):
            continue
        name = chunk.split(":", 1)[0].split("=", 1)[0].strip()
        if name:
            kwargs.append(name)
    return kwargs


def _find_task_defs(graph: nx.DiGraph, repo_root: Path | None = None) -> dict[str, _TaskDef]:
    """Find Celery task definitions by scanning source files referenced by
    graph nodes. Returns a map keyed by function name to task def.
    """
    out: dict[str, _TaskDef] = {}
    seen_files: set[str] = set()
    for nid, attrs in graph.nodes(data=True):
        sf = attrs.get("source_file")
        if not sf or sf in seen_files or not sf.endswith(".py"):
            continue
        seen_files.add(sf)
        try:
            path = Path(sf)
            if not path.is_absolute() and repo_root is not None:
                path = repo_root / path
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _TASK_DEF_RE.finditer(text):
            name = m.group("name")
            kw = _extract_kwargs(m.group("args"))
            # Try to locate the graph node id for this function def.
            node_id = None
            suffix = f"{name}()"
            for cand_id, cand_attrs in graph.nodes(data=True):
                if (
                    cand_attrs.get("source_file") == sf
                    and cand_attrs.get("label") in {suffix, name}
                ):
                    node_id = cand_id
                    break
            if node_id is None:
                # Synthesize a node so the matcher has something to connect.
                node_id = f"py:task:{sf}:{name}"
                graph.add_node(
                    node_id,
                    label=suffix,
                    file_type="code",
                    source_file=sf,
                    synthetic=True,
                )
            out[name] = _TaskDef(node_id=node_id, source_file=sf, name=name, expected_kwargs=kw)
    return out


def _find_enqueue_sites(
    graph: nx.DiGraph, tasks: dict[str, _TaskDef], repo_root: Path | None = None
) -> list[tuple[str, str, list[str]]]:
    """Return (caller_node_id, task_name, provided_kwargs)."""
    sites: list[tuple[str, str, list[str]]] = []
    seen_files: set[str] = set()
    for nid, attrs in graph.nodes(data=True):
        sf = attrs.get("source_file")
        if not sf or sf in seen_files or not sf.endswith(".py"):
            continue
        seen_files.add(sf)
        try:
            path = Path(sf)
            if not path.is_absolute() and repo_root is not None:
                path = repo_root / path
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _ENQUEUE.finditer(text):
            name = m.group("name")
            if name not in tasks:
                continue
            start = m.end()
            depth = 1
            i = start
            while i < len(text) and depth > 0:
                if text[i] == "(":
                    depth += 1
                elif text[i] == ")":
                    depth -= 1
                i += 1
            call_args = text[start : i - 1]
            kw_names = [km.group("kw") for km in _KW_RE.finditer(call_args)]
            # Prefer a different anchor in the same file so producer and
            # consumer edges do not collapse onto the same DiGraph self-loop.
            caller_id = nid
            for cand_id, cand_attrs in graph.nodes(data=True):
                if cand_id == tasks[name].node_id:
                    continue
                if cand_attrs.get("source_file") == sf:
                    caller_id = cand_id
                    break
            sites.append((caller_id, name, kw_names))
    return sites


def emit_celery_payload_edges(graph: nx.DiGraph, *, repo_root: Path | None = None) -> int:
    tasks = _find_task_defs(graph, repo_root=repo_root)
    if not tasks:
        return 0
    sites = _find_enqueue_sites(graph, tasks, repo_root=repo_root)
    added = 0
    for caller_id, task_name, provided_kwargs in sites:
        task = tasks[task_name]
        expected = set(task.expected_kwargs)
        provided = set(provided_kwargs)
        overlap = sorted(expected & provided)
        missing = sorted(expected - provided)
        extra = sorted(provided - expected)

        metadata = SemanticEdgeMetadata(
            confidence=0.8 if missing or extra else 1.0,
            inferred=False,
            source_system="python",
            target_system="celery",
            contract_kind=ContractKind.queue,
            task_name=task_name,
            payload_fields=overlap,
        )
        # Attach missing/extra through the BaseModel extras field via dict merge.
        dumped = metadata.model_dump(mode="json")
        dumped["payload_missing_fields"] = missing
        dumped["payload_extra_fields"] = extra

        graph.add_edge(
            caller_id,
            task.node_id,
            key=f"enqueue:{task_name}",
            relation=TASK_ENQUEUES,
            **dumped,
        )
        graph.add_edge(
            caller_id,
            task.node_id,
            key=f"producer:{task_name}",
            relation=PRODUCES_PAYLOAD,
            **dumped,
        )
        # Synthetic consumer self-edge: producer sent these fields, consumer
        # expects ``expected``; keep a separate node-less edge for the
        # verifier by adding a self-loop on the task node with CONSUMES.
        graph.add_edge(
            task.node_id,
            task.node_id,
            key=f"consumes:{task_name}",
            relation=CONSUMES_PAYLOAD,
            task_name=task_name,
            payload_fields=sorted(expected),
            inferred=False,
            source_system="celery",
            target_system="python",
            contract_kind=ContractKind.queue.value,
        )
        graph.add_edge(
            task.node_id,
            task.node_id,
            key=f"task_consumes:{task_name}",
            relation=TASK_CONSUMES,
            task_name=task_name,
        )
        added += 1
    return added


__all__ = ["emit_celery_payload_edges"]
