"""Promotion rules for LSP resolver evidence.

External LSP hooks can return many definitions for dynamic calls. This module
keeps that evidence from becoming authoritative graph structure unless it is
specific enough to be useful.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Iterable


DEFAULT_PROMOTION_POLICY = {
    "allow_receiver_calls_without_type": False,
}


def _target_id(definition: dict) -> str | None:
    value = definition.get("target_id")
    if value:
        return str(value)
    target = definition.get("target")
    if isinstance(target, dict) and target.get("id"):
        return str(target["id"])
    return None


def _first_local_definition(definitions: Iterable[dict], target_id: str) -> dict:
    for definition in definitions:
        if _target_id(definition) == target_id:
            return definition
    return {}


def _receiver_is_explicit(evidence: dict) -> bool:
    receiver = evidence.get("receiver")
    if not receiver:
        return False
    if str(receiver) == "self":
        return False
    if evidence.get("receiver_node_type") == "implicit_receiver":
        return False
    return True


def _has_receiver_type_proof(evidence: dict) -> bool:
    """Return true when an external resolver supplied receiver type evidence."""
    if evidence.get("receiver_type"):
        return True
    try:
        return float(evidence.get("receiver_type_confidence", 0)) >= 0.75
    except (TypeError, ValueError):
        return False


def _edge_context(language: str | None, resolver: str | None) -> str:
    parts = ["lsp_definition"]
    if language:
        parts.append(str(language))
    if resolver:
        parts.append(str(resolver))
    return ":".join(parts)


def _resolver(data: dict) -> str | None:
    value = (
        data.get("lsp_resolver")
        or data.get("metadata", {}).get("resolver_name")
        or data.get("metadata", {}).get("hook_name")
    )
    return str(value) if value else None


def _language(data: dict) -> str | None:
    value = data.get("language") or data.get("metadata", {}).get("language")
    return str(value) if value else None


def _lsp_server(data: dict) -> str | None:
    value = data.get("lsp_server") or data.get("metadata", {}).get("lsp_server")
    return str(value) if value else None


def _promotion_key(edge: dict) -> tuple[str, str, str]:
    """Key promoted callsites by the graph edge they will become."""
    return (
        str(edge.get("source") or ""),
        str(edge.get("target") or ""),
        str(edge.get("relation") or ""),
    )


def _merge_list(existing: dict, key: str, values: Iterable[str]) -> None:
    merged = set()
    current = existing.get(key)
    if isinstance(current, list):
        merged.update(str(value) for value in current if value)
    elif current:
        merged.add(str(current))
    merged.update(str(value) for value in values if value)
    if merged:
        existing[key] = sorted(merged)


def _merge_promoted_edge(existing: dict, edge: dict) -> None:
    """Fold another callsite into an already-promoted graph edge."""
    existing["lsp_callsite_count"] = int(existing.get("lsp_callsite_count", 1)) + 1
    if existing.get("call_id") != edge.get("call_id"):
        existing.pop("call_id", None)
    _merge_list(existing, "lsp_resolvers", edge.get("lsp_resolvers", []))
    _merge_list(existing, "lsp_servers", edge.get("lsp_servers", []))
    existing["lsp_resolver_count"] = len(existing.get("lsp_resolvers", []))
    existing["lsp_server_count"] = len(existing.get("lsp_servers", []))
    if existing["lsp_resolver_count"] == 1:
        existing["lsp_resolver"] = existing["lsp_resolvers"][0]
    else:
        existing.pop("lsp_resolver", None)
    if existing["lsp_server_count"] == 1:
        existing["lsp_server"] = existing["lsp_servers"][0]
    else:
        existing.pop("lsp_server", None)
    existing["lsp_candidate_count"] = int(existing.get("lsp_candidate_count", 0)) + int(edge.get("lsp_candidate_count", 0))
    if existing.get("confidence") == "AMBIGUOUS" or edge.get("confidence") == "AMBIGUOUS":
        existing["confidence"] = "AMBIGUOUS"
        existing["confidence_score"] = min(
            float(existing.get("confidence_score", 0.2)),
            float(edge.get("confidence_score", 0.2)),
        )
        existing["lsp_promotion"] = "mixed_lsp_evidence"


def _callsite_key(evidence: dict) -> tuple:
    call_id = evidence.get("call_id")
    if call_id:
        return ("call_id", str(call_id))
    callee_range = evidence.get("callee_range")
    if isinstance(callee_range, dict):
        range_key = json.dumps(callee_range, sort_keys=True, separators=(",", ":"))
    else:
        range_key = ""
    return (
        "location",
        str(evidence.get("caller") or ""),
        str(evidence.get("source_file") or ""),
        str(evidence.get("source_location") or ""),
        range_key,
        str(evidence.get("callee") or ""),
        str(evidence.get("receiver") or ""),
    )


def _prepare_evidence(data: dict) -> list[dict]:
    evidence_items = data.get("lsp_evidence", [])
    if not isinstance(evidence_items, list):
        return []
    language = _language(data)
    resolver = _resolver(data)
    lsp_server = _lsp_server(data)
    prepared = []
    for evidence in evidence_items:
        if not isinstance(evidence, dict):
            continue
        item = dict(evidence)
        if language and not item.get("language"):
            item["language"] = language
        if resolver and not item.get("lsp_resolver"):
            item["lsp_resolver"] = resolver
        if lsp_server and not item.get("lsp_server"):
            item["lsp_server"] = lsp_server
        prepared.append(item)
    return prepared


def _definition_for_target(definitions: list[dict], target_id: str) -> dict:
    definition = _first_local_definition(definitions, target_id)
    return definition if isinstance(definition, dict) else {}


def _base_edge(callsite: dict, target_id: str, definition: dict) -> dict:
    sample = callsite["sample"]
    resolvers = sorted(callsite["resolvers_by_target"].get(target_id, set()))
    servers = sorted(callsite["servers_by_target"].get(target_id, set()))
    language = callsite["language"]
    resolver_for_context = resolvers[0] if len(resolvers) == 1 else None
    edge = {
        "source": sample.get("caller"),
        "target": target_id,
        "relation": "calls",
        "context": _edge_context(language, resolver_for_context),
        "source_file": sample.get("source_file"),
        "source_location": sample.get("source_location"),
        "callee": sample.get("callee"),
        "receiver": sample.get("receiver"),
        "call_shape": sample.get("call_shape"),
        "call_id": sample.get("call_id"),
        "definition_file": definition.get("definition_file"),
        "definition_range": definition.get("range") or definition.get("definition_range"),
        "lsp_resolvers": resolvers,
        "lsp_resolver_count": len(resolvers),
        "lsp_servers": servers,
        "lsp_server_count": len(servers),
        "lsp_candidate_count": callsite["definition_count"],
    }
    if len(resolvers) == 1:
        edge["lsp_resolver"] = resolvers[0]
    if len(servers) == 1:
        edge["lsp_server"] = servers[0]
    return edge


def _add_edge(edges_by_key: dict[tuple[str, str, str], dict], edge: dict, counts: Counter[str]) -> None:
    clean_edge = {k: v for k, v in edge.items() if v is not None}
    clean_edge["lsp_callsite_count"] = 1
    key = _promotion_key(clean_edge)
    if key in edges_by_key:
        _merge_promoted_edge(edges_by_key[key], clean_edge)
        counts["collapsed_promoted_callsites"] += 1
    else:
        edges_by_key[key] = clean_edge


def promote_lsp_evidence_documents(documents: Iterable[dict]) -> tuple[list[dict], dict]:
    """Promote LSP evidence after merging resolvers by callsite."""
    policy = dict(DEFAULT_PROMOTION_POLICY)
    evidence_items: list[dict] = []
    for data in documents:
        if not isinstance(data, dict):
            continue
        raw_policy = data.get("promotion_policy") or data.get("metadata", {}).get("promotion_policy")
        if isinstance(raw_policy, dict):
            policy.update(raw_policy)
        evidence_items.extend(_prepare_evidence(data))

    edges_by_key: dict[tuple[str, str, str], dict] = {}
    counts: Counter[str] = Counter()
    skipped_callees: Counter[str] = Counter()
    callsites: dict[tuple, dict] = {}

    for evidence in evidence_items:
        counts["evidence"] += 1
        definitions = [
            definition for definition in evidence.get("definitions", [])
            if isinstance(definition, dict)
        ]
        target_ids = sorted({
            target_id for definition in definitions
            for target_id in [_target_id(definition)]
            if target_id
        })
        callee = str(evidence.get("callee") or "")
        if not target_ids:
            counts["no_local_target"] += 1
            continue
        if (
            _receiver_is_explicit(evidence)
            and not policy.get("allow_receiver_calls_without_type", False)
            and not _has_receiver_type_proof(evidence)
        ):
            counts["receiver_without_type_skipped"] += 1
            skipped_callees[callee] += 1
            continue

        key = _callsite_key(evidence)
        callsite = callsites.setdefault(key, {
            "sample": evidence,
            "language": evidence.get("language"),
            "definitions_by_target": defaultdict(list),
            "resolvers_by_target": defaultdict(set),
            "servers_by_target": defaultdict(set),
            "definition_count": 0,
        })
        if not callsite.get("language") and evidence.get("language"):
            callsite["language"] = evidence.get("language")
        resolver = evidence.get("lsp_resolver")
        server = evidence.get("lsp_server")
        callsite["definition_count"] += len(definitions)
        for target_id in target_ids:
            callsite["definitions_by_target"][target_id].extend(
                definition for definition in definitions
                if _target_id(definition) == target_id
            )
            if resolver:
                callsite["resolvers_by_target"][target_id].add(str(resolver))
            if server:
                callsite["servers_by_target"][target_id].add(str(server))
        if len(target_ids) > 1:
            counts["ambiguous_resolver_results"] += 1

    for callsite in callsites.values():
        target_ids = sorted(callsite["definitions_by_target"].keys())
        if len(target_ids) == 1:
            target_id = target_ids[0]
            sample = callsite["sample"]
            if sample.get("caller") == target_id:
                counts["self_edge"] += 1
                continue
            definitions = callsite["definitions_by_target"][target_id]
            definition = _definition_for_target(definitions, target_id)
            edge = _base_edge(callsite, target_id, definition)
            resolver_count = edge["lsp_resolver_count"]
            edge.update({
                "confidence": "INFERRED",
                "confidence_score": 0.92 if resolver_count > 1 else 0.82,
                "lsp_local_target_count": 1,
                "lsp_promotion": (
                    "confirmed_unique_local_definition"
                    if resolver_count > 1
                    else "unique_local_definition"
                ),
            })
            if sample.get("receiver_type"):
                edge["receiver_type"] = sample.get("receiver_type")
            if sample.get("receiver_type_confidence") is not None:
                edge["receiver_type_confidence"] = sample.get("receiver_type_confidence")
            _add_edge(edges_by_key, edge, counts)
            counts["promoted_callsites"] += 1
            if resolver_count > 1:
                counts["confirmed_callsites"] += 1
            continue

        counts["ambiguous"] += 1
        counts["conflicting_callsites"] += 1
        for target_id in target_ids:
            definitions = callsite["definitions_by_target"][target_id]
            definition = _definition_for_target(definitions, target_id)
            edge = _base_edge(callsite, target_id, definition)
            edge.update({
                "confidence": "AMBIGUOUS",
                "confidence_score": 0.25,
                "lsp_local_target_count": len(target_ids),
                "lsp_promotion": "conflicting_definitions",
                "lsp_conflict_targets": target_ids,
            })
            _add_edge(edges_by_key, edge, counts)
            counts["ambiguous_edges"] += 1

    edges = list(edges_by_key.values())
    if edges:
        counts["promoted"] = len(edges)
    summary = dict(counts)
    if skipped_callees:
        summary["skipped_callees"] = [
            {"callee": callee, "count": count}
            for callee, count in skipped_callees.most_common(20)
        ]
    return edges, summary


def promote_lsp_evidence(data: dict) -> tuple[list[dict], dict]:
    """Return graph edges promoted from sidecar LSP evidence plus a summary.

    Default policy is conservative:
    - exactly one local target is required;
    - explicit receiver-bearing calls are not promoted without receiver type
      proof;
    - promoted LSP edges are INFERRED by default, not EXTRACTED.
    """
    return promote_lsp_evidence_documents([data])
