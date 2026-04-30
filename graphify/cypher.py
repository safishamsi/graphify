# Cypher-subset query engine for graphify graphs.
# Supports: MATCH, WHERE, RETURN, LIMIT, ORDER BY
from __future__ import annotations

import re
from typing import Any

import networkx as nx


def _tokenize(query: str) -> list[str]:
    """Split a Cypher query into tokens, preserving quoted strings."""
    tokens: list[str] = []
    current = ""
    in_string = False
    string_char = ""
    for ch in query:
        if ch in ('"', "'") and not in_string:
            in_string = True
            string_char = ch
            if current:
                tokens.append(current)
                current = ""
            current += ch
        elif ch == string_char and in_string:
            current += ch
            tokens.append(current)
            current = ""
            in_string = False
            string_char = ""
        elif ch.isspace() and not in_string:
            if current:
                tokens.append(current)
                current = ""
        elif ch in "[](),-><>=!.:" and not in_string:
            if current:
                tokens.append(current)
                current = ""
            tokens.append(ch)
        else:
            current += ch
    if current:
        tokens.append(current)
    return tokens


def _parse_cypher(query: str) -> dict:
    """Parse a Cypher-like query into a structured dict.

    Supported patterns:
      MATCH (n) RETURN n
      MATCH (n:code) RETURN n.label
      MATCH (n)-[r:uses]->(m) RETURN n, m
      MATCH (n) WHERE n.community = 0 RETURN n LIMIT 10
    """
    tokens = _tokenize(query)
    result: dict[str, Any] = {
        "match_nodes": [],
        "match_edges": [],
        "where": [],
        "return_fields": [],
        "limit": None,
        "order_by": None,
        "order_desc": False,
    }

    i = 0
    while i < len(tokens):
        tok = tokens[i].upper()

        if tok == "MATCH":
            i += 1
            # Parse node or edge pattern
            while i < len(tokens) and tokens[i].upper() not in ("WHERE", "RETURN", "LIMIT", "ORDER"):
                if tokens[i] == "(":
                    i += 1
                    node_var = tokens[i]
                    i += 1
                    node_label = None
                    if i < len(tokens) and tokens[i] == ":":
                        i += 1
                        node_label = tokens[i].strip()
                        i += 1
                    result["match_nodes"].append({"var": node_var, "label": node_label})
                    if i < len(tokens) and tokens[i] == ")":
                        i += 1
                elif tokens[i] == "-":
                    # Edge pattern: -[r:rel]-> or <-[r:rel]-
                    direction = "both"
                    # Pre-bracket direction (uncommon): ->[r]-
                    if i + 1 < len(tokens) and tokens[i + 1] == ">":
                        direction = "out"
                        i += 2
                    elif i + 1 < len(tokens) and tokens[i + 1] == "-":
                        i += 2
                    else:
                        i += 1
                    if i < len(tokens) and tokens[i] == "[":
                        i += 1
                        edge_var = tokens[i]
                        i += 1
                        edge_type = None
                        if i < len(tokens) and tokens[i] == ":":
                            i += 1
                            edge_type = tokens[i].strip()
                            i += 1
                        if i < len(tokens) and tokens[i] == "]":
                            i += 1
                        # Post-bracket direction: ]-> (the standard form)
                        if i < len(tokens) and tokens[i] == "-":
                            if i + 1 < len(tokens) and tokens[i + 1] == ">":
                                direction = "out"
                                i += 2
                            elif i + 1 < len(tokens) and tokens[i + 1] == "-":
                                i += 2
                            else:
                                i += 1
                        result["match_edges"].append({"var": edge_var, "type": edge_type, "direction": direction})
                elif tokens[i] == "<":
                    if i + 1 < len(tokens) and tokens[i + 1] == "-":
                        direction = "in"
                        i += 2
                        if i < len(tokens) and tokens[i] == "[":
                            i += 1
                            edge_var = tokens[i]
                            i += 1
                            edge_type = None
                            if i < len(tokens) and tokens[i] == ":":
                                i += 1
                                edge_type = tokens[i].strip()
                                i += 1
                            result["match_edges"].append({"var": edge_var, "type": edge_type, "direction": direction})
                            if i < len(tokens) and tokens[i] == "]":
                                i += 1
                    else:
                        i += 1
                else:
                    i += 1

        elif tok == "WHERE":
            i += 1
            clause_tokens = []
            while i < len(tokens) and tokens[i].upper() not in ("RETURN", "LIMIT", "ORDER"):
                clause_tokens.append(tokens[i])
                i += 1
            result["where"] = _parse_where(clause_tokens)

        elif tok == "RETURN":
            i += 1
            fields = []
            while i < len(tokens) and tokens[i].upper() not in ("LIMIT", "ORDER"):
                if tokens[i] == ",":
                    i += 1
                    continue
                # Reassemble var.prop patterns
                if i + 2 < len(tokens) and tokens[i + 1] == ".":
                    fields.append(f"{tokens[i]}.{tokens[i + 2]}")
                    i += 3
                else:
                    fields.append(tokens[i])
                    i += 1
            result["return_fields"] = fields

        elif tok == "LIMIT":
            i += 1
            if i < len(tokens):
                try:
                    result["limit"] = int(tokens[i])
                except ValueError:
                    pass
                i += 1

        elif tok == "ORDER" and i + 1 < len(tokens) and tokens[i + 1].upper() == "BY":
            i += 2
            if i < len(tokens):
                result["order_by"] = tokens[i]
                i += 1
            if i < len(tokens) and tokens[i].upper() == "DESC":
                result["order_desc"] = True
                i += 1

        else:
            i += 1

    return result


def _parse_where(tokens: list[str]) -> list[dict]:
    """Parse WHERE clause tokens into predicate dicts.

    Supports: n.prop = value, n.prop != value, n.prop > value, n.prop CONTAINS 'str'
    """
    predicates: list[dict] = []
    i = 0
    while i < len(tokens):
        if i + 2 < len(tokens) and tokens[i + 1] == ".":
            var = tokens[i]
            prop = tokens[i + 2]
            i += 3
            op = tokens[i].upper() if i < len(tokens) else "="
            i += 1
            val = None
            if i < len(tokens):
                val = tokens[i]
                i += 1
            # Strip quotes
            if val and val[0] in ('"', "'"):
                val = val[1:-1]
            # Try numeric
            if val is not None:
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
            predicates.append({"var": var, "prop": prop, "op": op, "value": val})
        elif i + 1 < len(tokens) and tokens[i].upper() == "CONTAINS":
            # Handle: n.prop CONTAINS 'value'
            pass  # already handled above as op
            i += 1
        else:
            i += 1
    return predicates


def _eval_predicate(data: dict, pred: dict) -> bool:
    """Evaluate a single predicate against node/edge data."""
    prop_val = data.get(pred["prop"])
    target = pred["value"]
    op = pred["op"]

    if op == "=":
        return prop_val == target
    elif op in ("!=", "<>"):
        return prop_val != target
    elif op == ">":
        try:
            return float(prop_val or 0) > float(target or 0)
        except (TypeError, ValueError):
            return False
    elif op == "<":
        try:
            return float(prop_val or 0) < float(target or 0)
        except (TypeError, ValueError):
            return False
    elif op == ">=":
        try:
            return float(prop_val or 0) >= float(target or 0)
        except (TypeError, ValueError):
            return False
    elif op == "<=":
        try:
            return float(prop_val or 0) <= float(target or 0)
        except (TypeError, ValueError):
            return False
    elif op.upper() == "CONTAINS":
        return target in str(prop_val or "")
    return False


def _resolve_field(G: nx.Graph, obj, field: str) -> Any:
    """Resolve a RETURN field like 'n.label' or 'n.community'."""
    if field == "n" or field == "*":
        return dict(obj[1]) if hasattr(obj, "__iter__") and len(obj) == 2 else obj
    parts = field.split(".")
    if len(parts) == 2:
        var, prop = parts
        if isinstance(obj, tuple):
            data = obj[1]
        elif isinstance(obj, dict):
            data = obj
        else:
            data = G.nodes.get(obj, {})
        return data.get(prop)
    return obj


def execute_cypher(G: nx.Graph, query: str) -> list[dict]:
    """Execute a Cypher-subset query against a NetworkX graph.

    Returns a list of result rows (dicts keyed by RETURN field names).
    """
    parsed = _parse_cypher(query)
    results: list[dict] = []

    # Build candidate items based on MATCH
    match_nodes = parsed["match_nodes"]
    match_edges = parsed["match_edges"]
    where_preds = parsed["where"]
    return_fields = parsed["return_fields"]
    limit = parsed["limit"]

    if match_edges:
        # Edge-based query
        direction = match_edges[0]["direction"]
        edge_type = match_edges[0]["type"]

        for u, v, edata in G.edges(data=True):
            if edge_type and edata.get("relation") != edge_type:
                continue

            # Honor the directional intent encoded by build_from_json into
            # _src/_tgt. NetworkX's undirected iteration yields edges in
            # canonical (u, v) order which need not match the original
            # direction; without this, MATCH (n)-[r]->(m) silently returns
            # back-edges. If _src/_tgt are absent (e.g. compressed graphs),
            # fall back to (u, v) for "both" but skip the row for explicit
            # direction queries to avoid fake matches.
            src_id = edata.get("_src")
            tgt_id = edata.get("_tgt")
            if direction in ("out", "in"):
                if src_id is None or tgt_id is None or src_id not in G or tgt_id not in G:
                    continue
                if direction == "out":
                    n_id, m_id = src_id, tgt_id
                else:  # "in"
                    n_id, m_id = tgt_id, src_id
            else:
                n_id, m_id = u, v

            n_data = G.nodes[n_id]
            m_data = G.nodes[m_id]
            if match_nodes:
                if len(match_nodes) >= 1:
                    label_filter = match_nodes[0].get("label")
                    if label_filter and n_data.get("file_type") != label_filter and n_data.get("label") != label_filter:
                        continue
                if len(match_nodes) >= 2:
                    label_filter = match_nodes[1].get("label")
                    if label_filter and m_data.get("file_type") != label_filter and m_data.get("label") != label_filter:
                        continue

            # WHERE filtering
            row_bindings = {
                match_nodes[0]["var"]: (n_id, n_data) if match_nodes else (n_id, n_data),
            }
            if len(match_nodes) > 1:
                row_bindings[match_nodes[1]["var"]] = (m_id, m_data)
            if match_edges:
                row_bindings[match_edges[0]["var"]] = edata

            skip = False
            for pred in where_preds:
                binding = row_bindings.get(pred["var"])
                if binding is None:
                    skip = True
                    break
                data = binding[1] if isinstance(binding, tuple) else binding
                if not _eval_predicate(data, pred):
                    skip = True
                    break
            if skip:
                continue

            # Build result row
            row: dict[str, Any] = {}
            for field in return_fields:
                if "." in field:
                    var, prop = field.split(".", 1)
                    binding = row_bindings.get(var)
                    data = binding[1] if isinstance(binding, tuple) else binding
                    row[field] = data.get(prop)
                else:
                    binding = row_bindings.get(field)
                    row[field] = binding[1] if isinstance(binding, tuple) else binding
            results.append(row)
    else:
        # Node-only query
        for nid, data in G.nodes(data=True):
            if match_nodes:
                label_filter = match_nodes[0].get("label")
                if label_filter and data.get("file_type") != label_filter and data.get("label") != label_filter:
                    continue

            bindings = {match_nodes[0]["var"]: (nid, data)} if match_nodes else {"n": (nid, data)}

            skip = False
            for pred in where_preds:
                binding = bindings.get(pred["var"])
                if binding is None:
                    skip = True
                    break
                check_data = binding[1] if isinstance(binding, tuple) else binding
                if not _eval_predicate(check_data, pred):
                    skip = True
                    break
            if skip:
                continue

            row = {}
            for field in return_fields:
                if "." in field:
                    var, prop = field.split(".", 1)
                    binding = bindings.get(var)
                    check_data = binding[1] if isinstance(binding, tuple) else binding
                    row[field] = check_data.get(prop) if check_data else None
                elif field == "*":
                    row[field] = dict(data)
                else:
                    binding = bindings.get(field)
                    row[field] = binding[1] if isinstance(binding, tuple) else binding
            results.append(row)

    # ORDER BY
    order_by = parsed["order_by"]
    if order_by and results:
        def _sort_key(r):
            val = r.get(order_by)
            if val is None:
                return (1, "")
            try:
                return (0, float(val))
            except (TypeError, ValueError):
                return (0, str(val).lower())
        results.sort(key=_sort_key, reverse=parsed["order_desc"])

    # LIMIT
    if limit is not None:
        results = results[:limit]

    return results


def render_results(results: list[dict], format: str = "table") -> str:
    """Render query results as a human-readable string."""
    if not results:
        return "(no results)"
    if format == "json":
        import json
        return json.dumps(results, indent=2, default=str)

    # Table format
    keys = list(results[0].keys())
    lines = []
    header = " | ".join(str(k) for k in keys)
    lines.append(header)
    lines.append("-" * len(header))
    for row in results:
        lines.append(" | ".join(str(row.get(k, "")) for k in keys))
    return "\n".join(lines)
