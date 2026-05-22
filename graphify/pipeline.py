"""End-to-end orchestrator: extraction dict → all outputs.

Provides a single function `run()` that wires build→cluster→analyze→report→save→viz
with correct API signatures. Callers (skill.md, CLI, tests) use this instead of
manually importing 6 modules and guessing parameter order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx


@dataclass
class PipelineResult:
    """Everything produced by a pipeline run."""

    G: nx.Graph
    communities: dict[int, list[str]]
    cohesion: dict[int, float]
    labels: dict[int, str]
    god_node_list: list[dict]
    surprise_list: list[dict]
    questions: list[dict]
    report: str
    domain_analysis: dict[str, Any] = field(default_factory=dict)


def run(
    out_dir: str | Path,
    extraction: dict,
    detection: dict,
    *,
    domain_names: list[str] | None = None,
    community_labels: dict[int, str] | None = None,
    use_db: bool = False,
    skip_save: bool = False,
    skip_html: bool = False,
    skip_wiki: bool = False,
    built_at_commit: str | None = None,
) -> PipelineResult:
    """Run Steps 4-6 of the pipeline: build → cluster → hooks → analyze → save → report → viz.

    Parameters
    ----------
    out_dir : path to the graphify-out directory
    extraction : merged dict with keys "nodes", "edges", "hyperedges"
    detection : result of detect() (used for report header)
    domain_names : list of domain plugin names to activate (e.g. ["finance", "diligence"])
    community_labels : optional pre-computed labels {community_id: "label"}
    use_db : if True, persist as graph.db; otherwise graph.json
    skip_save / skip_html / skip_wiki : skip respective outputs
    built_at_commit : git commit hash to stamp on the graph
    """
    from .analyze import god_nodes, suggest_questions, surprising_connections
    from .build import build_from_json
    from .cluster import cluster, score_all
    from .domain import run_hooks
    from .report import generate

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # --- Hook 3: domain post_extract (modifies extraction in-place) ---
    domain_analysis: dict[str, Any] = {}
    if domain_names:
        extraction, _ = run_hooks(
            {"domains": domain_names},
            extraction,
            G=None,
            hooks=["post_extract"],
        )

    # --- Build ---
    G = build_from_json(extraction)

    # --- Cluster ---
    communities = cluster(G)
    cohesion = score_all(G, communities)

    # --- Hook 4 & 5: domain post_build + analyzers ---
    if domain_names:
        _, domain_analysis = run_hooks(
            {"domains": domain_names},
            extraction,
            G=G,
            hooks=["post_build", "analyzers"],
        )

    # --- Analyze ---
    god = god_nodes(G, communities, top_n=10)
    surprises = surprising_connections(G, communities, top_n=5)
    labels = community_labels or {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels, top_n=7)

    # --- Save ---
    if not skip_save:
        from .store import save

        backend = "db" if use_db else "json"
        save(out, G, communities, backend=backend, built_at_commit=built_at_commit)

    # --- Report ---
    report = generate(
        G,
        communities,
        community_labels=labels,
        god_node_list=god,
        surprise_list=surprises,
        detection_result=detection,
        token_cost={"input_tokens": 0, "output_tokens": 0},
        root=str(out),
        cohesion_scores=cohesion,
        suggested_questions=questions,
        built_at_commit=built_at_commit,
    )

    # Append domain analysis to report
    if domain_analysis:
        report += "\n\n## Domain Analysis\n"
        for key, findings in domain_analysis.items():
            dom_name, analyzer_name = key.split(".", 1)
            title = analyzer_name.replace("_", " ").title()
            report += f"\n### {title} ({dom_name})\n\n"
            if not findings:
                report += "_No findings._\n"
            else:
                for f in findings[:20]:
                    severity = f.get("severity", "")
                    label = f.get("label", f.get("node", f.get("person", "")))
                    detail = f.get("detail", "") or f.get("reason", "")
                    if not detail:
                        detail = f.get("type", "").replace("_", " ")
                        if "roles" in f:
                            detail += f' (roles: {", ".join(f["roles"])})'
                        if "degree" in f:
                            detail += f' — degree: {f["degree"]}'
                        if "fragments_into" in f:
                            detail += f' — fragments into: {f["fragments_into"]}'
                    sev_icon = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(severity, "\u26aa")
                    report += f"- {sev_icon} **{label}** — {detail}\n"

    (out / "GRAPH_REPORT.md").write_text(report)

    # --- HTML ---
    if not skip_html:
        from .tree_html import write_tree_html

        write_tree_html(out, out / "graph.html")

    # --- Wiki ---
    if not skip_wiki:
        from .wiki import to_wiki

        to_wiki(G, communities, out / "wiki", god_nodes_data=god)

    return PipelineResult(
        G=G,
        communities=communities,
        cohesion=cohesion,
        labels=labels,
        god_node_list=god,
        surprise_list=surprises,
        questions=questions,
        report=report,
        domain_analysis=domain_analysis,
    )
