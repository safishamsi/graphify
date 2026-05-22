"""Synthesis layer — LLM reasoning over graph substructures.

Goes beyond pattern-matching analyzers by extracting ego subgraphs around
high-risk entities and asking an LLM to identify systemic risks that emerge
from the combination of connected facts.

Usage:
    from graphify.synthesize import synthesize_risks
    narratives = synthesize_risks(G, red_flags, key_persons, backend="gemini")
"""
from __future__ import annotations

import os
from typing import Any

import networkx as nx


def _call_synthesis_llm(prompt: str, *, max_tokens: int = 300) -> str:
    """Call LLM for synthesis. Uses Vertex REST API if GOOGLE_GEMINI_BASE_URL is set,
    otherwise falls back to graphify.llm._call_llm."""
    base_url = os.environ.get("GOOGLE_GEMINI_BASE_URL", "").rstrip("/")
    if base_url:
        # Native Vertex AI REST call
        import httpx
        api_ver = os.environ.get("GOOGLE_GENAI_API_VERSION", "")
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        model = os.environ.get("GRAPHIFY_GEMINI_MODEL", "gemini-2.5-flash")
        url = f"{base_url}/{api_ver}/models/{model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
        }
        resp = httpx.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    return p["text"]
        return ""
    else:
        from graphify.llm import _call_llm, detect_backend
        backend = detect_backend()
        if not backend:
            raise ValueError("No LLM backend available.")
        return _call_llm(prompt, backend=backend, max_tokens=max_tokens)


def _ego_subgraph_text(G: nx.Graph, center: str, hops: int = 2) -> str:
    """Serialize a node's ego subgraph as readable text for LLM consumption."""
    ego_nodes = {center}
    frontier = {center}
    for _ in range(hops):
        next_frontier: set = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in ego_nodes:
                    next_frontier.add(neighbor)
                    ego_nodes.add(neighbor)
        frontier = next_frontier

    center_label = G.nodes[center].get("label", center)
    lines = [f"CENTER: {center_label}"]
    lines.append(f"  type: {G.nodes[center].get('type', 'unknown')}")
    lines.append(f"  degree: {G.degree(center)}")
    lines.append("")
    lines.append("CONNECTIONS:")

    # Sort by relevance (direct connections first, then 2-hop)
    direct = set(G.neighbors(center))
    for neighbor in sorted(ego_nodes - {center}, key=lambda n: (n not in direct, G.nodes[n].get("label", ""))):
        nd = G.nodes[neighbor]
        label = nd.get("label", neighbor)
        # Get edge data if directly connected
        if neighbor in direct:
            try:
                ed = G[center][neighbor]
            except KeyError:
                ed = {}
            rel = ed.get("relation", "connected_to")
            conf = ed.get("confidence_score", ed.get("confidence", ""))
            lines.append(f"  --{rel}--> {label}" + (f" [{conf}]" if conf else ""))
        else:
            # 2-hop: find the intermediary
            for mid in direct:
                if G.has_edge(mid, neighbor):
                    try:
                        ed = G[mid][neighbor]
                    except KeyError:
                        ed = {}
                    mid_label = G.nodes[mid].get("label", mid)
                    rel = ed.get("relation", "connected_to")
                    lines.append(f"  ({mid_label}) --{rel}--> {label}")
                    break

    return "\n".join(lines[:60])  # Cap at 60 lines to stay within token budget


def _group_findings_by_theme(
    G: nx.Graph,
    red_flags: list[dict],
    key_persons: list[dict],
) -> dict[str, dict]:
    """Group red flags into thematic clusters for synthesis.

    Rather than grouping by exact node (which scatters findings), we cluster
    by risk theme: related-party, governance/control, financial, structural.

    Returns {theme_id: {"label": str, "center_node": str, "findings": list}}.
    """
    themes: dict[str, dict] = {
        "governance_control": {"label": "Governance & Control", "center_node": "", "findings": []},
        "related_party": {"label": "Related-Party Exposure", "center_node": "", "findings": []},
        "financial_risk": {"label": "Financial Risk", "center_node": "", "findings": []},
        "structural_complexity": {"label": "Structural Complexity", "center_node": "", "findings": []},
    }

    _governance_keywords = {"control", "voting", "dependence", "key_person", "ceo", "director", "officer"}
    _related_keywords = {"related_party", "self_deal", "loan", "officer_loan", "conflict"}
    _financial_keywords = {"loss", "profitab", "revenue", "compensation", "lease"}
    _structural_keywords = {"vie", "consolidat", "subsidiary", "variable interest"}

    for f in red_flags:
        ftype = f.get("type", "").lower()
        label = f.get("label", "").lower()
        combined = ftype + " " + label

        if any(k in combined for k in _governance_keywords):
            themes["governance_control"]["findings"].append(f)
        elif any(k in combined for k in _related_keywords):
            themes["related_party"]["findings"].append(f)
        elif any(k in combined for k in _structural_keywords):
            themes["structural_complexity"]["findings"].append(f)
        elif any(k in combined for k in _financial_keywords):
            themes["financial_risk"]["findings"].append(f)
        else:
            # Default: put in financial
            themes["financial_risk"]["findings"].append(f)

    for kp in key_persons:
        themes["governance_control"]["findings"].append({"type": "key_person_risk", **kp})

    # Assign center_node: pick the highest-degree node referenced in findings
    for theme in themes.values():
        nodes_in_theme = []
        for f in theme["findings"]:
            nid = f.get("node", f.get("person", ""))
            if nid and nid in G:
                nodes_in_theme.append(nid)
        if nodes_in_theme:
            theme["center_node"] = max(nodes_in_theme, key=lambda n: G.degree(n))

    # Filter to themes with ≥2 findings
    return {k: v for k, v in themes.items() if len(v["findings"]) >= 2}


_SYNTHESIS_PROMPT = """\
You are an investigative analyst writing for a non-expert board member who needs to understand risks in plain language.

Below is a subgraph from a corporate filing's knowledge graph, plus the red flags detected in it.

SUBGRAPH:
{subgraph}

RED FLAGS:
{findings}

Your job: look at how these facts CONNECT and explain what the pattern means. Follow this structure:

## What's happening (2-3 sentences)
Explain the mechanism in plain English. Use concrete numbers from the subgraph. A smart 16-year-old should understand this.

## Who benefits, who loses
Name specific entities from the subgraph. Follow the money — who gets paid, who bears the risk, who gets diluted.

## Why this is worse than it looks
What would a short-seller or activist investor highlight? What does the COMBINATION reveal that reading each fact alone would miss? Connect at least 2 findings together to show the compounding effect.

## What to investigate next
One specific question that would confirm or kill this thesis. Not generic "more info needed" — a precise data request.

Rules:
- Use the actual entity names and dollar amounts from the subgraph.
- Never say "systemic risk" or "non-arm's-length" — use plain words.
- Never hedge with "potentially" or "may indicate" — state what the pattern shows, then say what's uncertain.
- Be direct and blunt. If it looks bad, say so.
"""


def synthesize_risks(
    G: nx.Graph,
    red_flags: list[dict],
    key_persons: list[dict],
    *,
    backend: str | None = None,
    max_entities: int = 5,
    max_tokens: int = 8192,
) -> list[dict]:
    """Synthesize risk narratives by running LLM on ego subgraphs of high-risk entities.

    Args:
        G: The knowledge graph.
        red_flags: Output of red_flag_analyzer(G).
        key_persons: Output of key_person_risk_analyzer(G).
        backend: LLM backend (auto-detected if None).
        max_entities: Max number of entities to synthesize (most findings first).
        max_tokens: Max tokens per LLM response.

    Returns:
        List of dicts: [{entity, label, narrative, finding_count, findings_summary}]
    """
    # Check that some LLM is available
    has_vertex = bool(os.environ.get("GOOGLE_GEMINI_BASE_URL"))
    if not has_vertex:
        from graphify.llm import detect_backend as _detect
        if backend is None:
            backend = _detect()
        if not backend:
            return [{"error": "No LLM backend available. Set GEMINI_API_KEY, ANTHROPIC_API_KEY, or similar."}]

    # Group findings into thematic clusters
    themes = _group_findings_by_theme(G, red_flags, key_persons)
    if not themes:
        return []

    # Sort by finding count, take top N
    ranked = sorted(themes.items(), key=lambda x: len(x[1]["findings"]), reverse=True)[:max_entities]

    results = []
    for theme_id, info in ranked:
        center = info["center_node"]
        if not center or center not in G:
            # Use highest-degree node in graph as context anchor
            center = max(G.nodes(), key=lambda n: G.degree(n))

        subgraph_text = _ego_subgraph_text(G, center)
        findings_text = "\n".join(
            f"- [{f.get('severity', 'medium').upper()}] {f.get('type', '')}: {f.get('label', f.get('person', ''))}"
            for f in info["findings"]
        )

        prompt = _SYNTHESIS_PROMPT.format(subgraph=subgraph_text, findings=findings_text)

        try:
            narrative = _call_synthesis_llm(prompt, max_tokens=max_tokens)
        except Exception as e:
            narrative = f"[Synthesis failed: {e}]"

        results.append({
            "theme": theme_id,
            "label": info["label"],
            "center_entity": G.nodes[center].get("label", center),
            "narrative": narrative,
            "finding_count": len(info["findings"]),
            "findings_summary": [f.get("type", "") for f in info["findings"]],
        })

    return results


def synthesize_risks_offline(
    G: nx.Graph,
    red_flags: list[dict],
    key_persons: list[dict],
    *,
    max_entities: int = 5,
) -> list[dict]:
    """Generate synthesis prompts WITHOUT calling the LLM.

    Useful for testing, debugging, or feeding into an external LLM session.
    Returns the same structure as synthesize_risks but with 'prompt' instead of 'narrative'.
    """
    themes = _group_findings_by_theme(G, red_flags, key_persons)
    if not themes:
        return []

    ranked = sorted(themes.items(), key=lambda x: len(x[1]["findings"]), reverse=True)[:max_entities]

    results = []
    for theme_id, info in ranked:
        center = info["center_node"]
        if not center or center not in G:
            center = max(G.nodes(), key=lambda n: G.degree(n))

        subgraph_text = _ego_subgraph_text(G, center)
        findings_text = "\n".join(
            f"- [{f.get('severity', 'medium').upper()}] {f.get('type', '')}: {f.get('label', f.get('person', ''))}"
            for f in info["findings"]
        )

        prompt = _SYNTHESIS_PROMPT.format(subgraph=subgraph_text, findings=findings_text)

        results.append({
            "theme": theme_id,
            "label": info["label"],
            "center_entity": G.nodes[center].get("label", center),
            "prompt": prompt,
            "finding_count": len(info["findings"]),
            "findings_summary": [f.get("type", "") for f in info["findings"]],
        })

    return results
