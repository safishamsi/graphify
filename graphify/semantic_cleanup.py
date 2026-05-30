# Semantic fragment sanitizer — converts sentence-like rationale nodes into
# attributes on related nodes and removes invalid file_type values.
#
# Currently called from the skill merge scripts (skill-opencode.md,
# skill-codex.md) so that rationale text never leaks into the knowledge
# graph as standalone nodes. (Future: graphify.llm may wire this into
# _parse_llm_json / _merge_into for non-skill code paths; not done in
# this cycle.)
from __future__ import annotations

import json
import re
from pathlib import Path

# Labels longer than this many characters, or containing >= this many words,
# are candidates for being sentence-like rationale text rather than entity names.
_RATIONALE_MIN_CHARS = 80
_RATIONALE_MIN_WORDS = 8

# Validation limits for untrusted semantic-fragment payloads. See
# validate_semantic_fragment(). Issue #825: returned-JSON normalization for
# OpenCode and Codex agents requires a Python enforcement boundary so a
# malicious or runaway agent response cannot exhaust memory or escape the
# graphify-out chunk directory via crafted node/edge IDs.
MAX_SEMANTIC_FRAGMENT_BYTES = 25 * 1024 * 1024
MAX_SEMANTIC_FRAGMENT_NODES = 10_000
MAX_SEMANTIC_FRAGMENT_EDGES = 100_000
MAX_SEMANTIC_FRAGMENT_HYPEREDGES = 10_000
MAX_SEMANTIC_HYPEREDGE_NODES = 256
MAX_SEMANTIC_ID_LENGTH = 256
VALID_SEMANTIC_FILE_TYPES = frozenset({"code", "document", "paper", "image", "rationale", "concept"})
_SEMANTIC_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def validate_semantic_fragment(fragment: object) -> list[str]:
    """Return validation errors for an untrusted semantic extraction fragment.

    Empty list means valid. Called by skill merge code before
    sanitize_semantic_fragment() so malformed or malicious agent JSON is
    rejected before it touches the graph. Parameter is `object` (not `dict`)
    because we may be handed arbitrary deserialized JSON — the first check
    rejects anything that isn't a dict.
    """
    if not isinstance(fragment, dict):
        return ["fragment must be a JSON object"]

    errors: list[str] = []
    try:
        payload = json.dumps(fragment, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return [f"fragment is not JSON-serializable: {exc}"]

    if len(payload) > MAX_SEMANTIC_FRAGMENT_BYTES:
        errors.append(f"payload is {len(payload)} bytes; max is {MAX_SEMANTIC_FRAGMENT_BYTES}")

    nodes = fragment.get("nodes", [])
    edges = fragment.get("edges", [])
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        nodes = []
    elif len(nodes) > MAX_SEMANTIC_FRAGMENT_NODES:
        errors.append(f"nodes has {len(nodes)} entries; max is {MAX_SEMANTIC_FRAGMENT_NODES}")

    if not isinstance(edges, list):
        errors.append("edges must be a list")
        edges = []
    elif len(edges) > MAX_SEMANTIC_FRAGMENT_EDGES:
        errors.append(f"edges has {len(edges)} entries; max is {MAX_SEMANTIC_FRAGMENT_EDGES}")

    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] must be an object")
            continue
        _validate_semantic_id(errors, f"nodes[{i}].id", node.get("id"))
        file_type = node.get("file_type")
        if file_type is not None and file_type not in VALID_SEMANTIC_FILE_TYPES:
            errors.append(
                f"nodes[{i}].file_type {file_type!r} is not one of "
                f"{sorted(VALID_SEMANTIC_FILE_TYPES)}"
            )  # validate file_type before any sanitize path can run

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be an object")
            continue
        _validate_semantic_id(errors, f"edges[{i}].source", edge.get("source"))
        _validate_semantic_id(errors, f"edges[{i}].target", edge.get("target"))

    hyperedges = fragment.get("hyperedges", [])
    if hyperedges is None:
        hyperedges = []
    if not isinstance(hyperedges, list):
        errors.append("hyperedges must be a list")
    else:
        if len(hyperedges) > MAX_SEMANTIC_FRAGMENT_HYPEREDGES:
            errors.append(
                f"hyperedges has {len(hyperedges)} entries; "
                f"max is {MAX_SEMANTIC_FRAGMENT_HYPEREDGES}"
            )
        for i, he in enumerate(hyperedges):
            if not isinstance(he, dict):
                errors.append(f"hyperedges[{i}] must be an object")
                continue
            _validate_semantic_id(errors, f"hyperedges[{i}].id", he.get("id"))
            he_nodes = he.get("nodes")
            if not isinstance(he_nodes, list):
                errors.append(f"hyperedges[{i}].nodes must be a list")
                continue
            if len(he_nodes) > MAX_SEMANTIC_HYPEREDGE_NODES:
                errors.append(
                    f"hyperedges[{i}].nodes has {len(he_nodes)} entries; "
                    f"max is {MAX_SEMANTIC_HYPEREDGE_NODES}"
                )
            for j, ref in enumerate(he_nodes):
                _validate_semantic_id(errors, f"hyperedges[{i}].nodes[{j}]", ref)

    return errors


def load_validated_semantic_fragment(path: Path) -> tuple[dict | None, list[str]]:
    """Load and validate a semantic chunk, rejecting oversize files before parsing.

    The size guard runs against `path.stat().st_size` so an attacker-supplied
    multi-gigabyte chunk file cannot blow up memory at `read_text()` time.
    JSON decode errors are returned as validation errors rather than raised,
    so callers can `continue` past bad chunks without a try/except.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, [f"could not stat {path}: {exc}"]
    if size > MAX_SEMANTIC_FRAGMENT_BYTES:
        return None, [f"payload is {size} bytes; max is {MAX_SEMANTIC_FRAGMENT_BYTES}"]
    try:
        fragment = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"]
    except OSError as exc:
        return None, [f"could not read {path}: {exc}"]
    errors = validate_semantic_fragment(fragment)
    return (None, errors) if errors else (fragment, [])


def _validate_semantic_id(errors: list[str], field: str, value: object) -> None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return
    if not value:
        errors.append(f"{field} must not be empty")
        return
    if len(value) > MAX_SEMANTIC_ID_LENGTH:
        errors.append(f"{field} is {len(value)} chars; max is {MAX_SEMANTIC_ID_LENGTH}")
    if "/" in value or "\\" in value or ".." in value:
        errors.append(f"{field} must not contain path separators or '..'")
    if not _SEMANTIC_ID_RE.fullmatch(value):
        errors.append(f"{field} contains unsupported characters")


def sanitize_semantic_fragment(fragment: dict) -> dict:
    """Clean up a semantic extraction fragment in-place.

    Operations:
    1. Removes nodes with ``file_type: "rationale"`` or ``file_type: "concept"``
       that were emitted by an LLM (these are not valid semantic entity types).
    2. Detects nodes whose label reads like a sentence / rationale paragraph
       AND that participate in a ``rationale_for`` edge, then converts the
       label into a ``rationale`` attribute on the target node and removes
       the source-node + its edges. The ``rationale_for`` edge signal applies
       regardless of the source node's ``file_type`` — sentence-like nodes
       with allowed types (``document``, ``code``) are still cleaned up when
       they're explicitly marked as rationale.
    3. Strips nodes whose only distinguishing field is the label itself
       (empty id — likely LLM hallucination).
    4. Filters hyperedges so they cannot reference removed or unknown node
       IDs after the cleanup passes above. A hyperedge with fewer than two
       surviving members is dropped.

    Returns the same dict for convenience.
    """
    _invalid_ft = frozenset({"rationale", "concept"})

    nodes: list[dict] = fragment.get("nodes", [])
    edges: list[dict] = fragment.get("edges", [])
    hyperedges: list[dict] = fragment.get("hyperedges", []) or []

    # ---- build lookup maps --------------------------------------------------
    node_by_id: dict[str, dict] = {}
    for n in nodes:
        nid = n.get("id", "")
        if nid:
            node_by_id[nid] = n

    # Pre-collect node IDs that source a `rationale_for` edge — these are
    # candidates for sentence-like cleanup even when file_type is allowed.
    rationale_for_sources: set[str] = set()
    for e in edges:
        if e.get("relation") == "rationale_for":
            src = e.get("source", "")
            if src:
                rationale_for_sources.add(src)

    # ---- pass 1: identify nodes to remove + rationale candidates -----------
    rationale_candidates: list[dict] = []
    remove_ids: set[str] = set()
    keep_nodes: list[dict] = []
    for n in nodes:
        nid = n.get("id", "")
        if not nid:
            # Node without an id cannot be referenced — discard.
            continue
        ft = n.get("file_type", "")
        label = n.get("label", "")
        if ft in _invalid_ft:
            # Explicitly-invalid file_type ("rationale" or "concept"): if
            # the label looks like a sentence we may convert to attribute.
            if _is_sentence_like_rationale_label(label):
                rationale_candidates.append(n)
            remove_ids.add(nid)
            continue
        if nid in rationale_for_sources and _is_sentence_like_rationale_label(label):
            # Allowed file_type, but the node sources a `rationale_for` edge
            # AND its label is sentence-like prose. Treat it as rationale
            # cleanup material rather than a real graph entity.
            rationale_candidates.append(n)
            remove_ids.add(nid)
            continue
        keep_nodes.append(n)

    # ---- pass 2: convert sentence-nodes → rationale attributes --------------
    # Only `rationale_for` edges propagate the rationale text. Other outgoing
    # edges (e.g. references, conceptually_related_to) are NOT used as
    # attribute-propagation paths — that would corrupt unrelated nodes by
    # attaching rationale meant for a different target.
    rationale_attrs: dict[str, list[str]] = {}
    for rn in rationale_candidates:
        rn_id = rn.get("id", "")
        text = rn.get("label", "").strip()
        for e in edges:
            if e.get("relation") != "rationale_for":
                continue
            if e.get("source") != rn_id:
                continue
            target_id = e.get("target")
            if target_id not in node_by_id or target_id in remove_ids:
                continue
            rationale_attrs.setdefault(target_id, []).append(text)

    for target_id, texts in rationale_attrs.items():
        if target_id in node_by_id and target_id not in remove_ids:
            _append_rationale_attr(node_by_id[target_id], texts)

    # ---- pass 3: strip edges referencing removed nodes ----------------------
    keep_edges: list[dict] = []
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src in remove_ids or tgt in remove_ids:
            continue
        keep_edges.append(e)

    # ---- pass 4: filter hyperedges to surviving node IDs --------------------
    surviving_ids: set[str] = {n.get("id", "") for n in keep_nodes}
    surviving_ids.discard("")
    keep_hyperedges: list[dict] = []
    for he in hyperedges:
        if not isinstance(he, dict):
            continue
        he_nodes = he.get("nodes")
        if not isinstance(he_nodes, list):
            continue
        filtered = [ref for ref in he_nodes if isinstance(ref, str) and ref in surviving_ids]
        if len(filtered) < 2:
            # A hyperedge needs at least two surviving members to be meaningful.
            continue
        if len(filtered) != len(he_nodes):
            he = dict(he)
            he["nodes"] = filtered
        keep_hyperedges.append(he)

    fragment["nodes"] = keep_nodes
    fragment["edges"] = keep_edges
    fragment["hyperedges"] = keep_hyperedges
    return fragment


def _is_sentence_like_rationale_label(label: str) -> bool:
    """Return True if *label* looks like prose / rationale text rather than an
    entity or concept name.

    Heuristics (no false positives on short-concept-edge-cases):
    - Longer than *_RATIONALE_MIN_CHARS* chars, OR
    - At least *_RATIONALE_MIN_WORDS* whitespace-delimited tokens, AND
    - Contains at least one sentence-ending punctuation mark (``. ! ?``) or a
      colon (common in "Decision: ..." rationales).
    """
    if not label:
        return False
    label = label.strip()
    if len(label) < _RATIONALE_MIN_CHARS:
        word_count = len(label.split())
        if word_count < _RATIONALE_MIN_WORDS:
            return False
    # Must look like actual prose: has sentence-ending punctuation or a colon.
    return bool(re.search(r"[.!?:]", label))


def _append_rationale_attr(node: dict, texts: list[str]) -> None:
    """Append one or more rationale strings to *node*'s ``rationale`` attribute.

    If the attribute already exists the new texts are appended with a
    double-newline separator so downstream consumers can distinguish distinct
    rationale fragments.
    """
    existing = node.get("rationale", "")
    new_text = "\n\n".join(texts).strip()
    if existing:
        node["rationale"] = existing + "\n\n" + new_text
    else:
        node["rationale"] = new_text
