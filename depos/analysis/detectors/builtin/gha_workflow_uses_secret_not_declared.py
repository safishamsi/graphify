from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="gha-workflow-uses-secret-not-declared",
    universe=Universe.infra,
    verifier_checks=["graph_path_exists", "negation_witness"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "infra_workflow"):
        undeclared = list(attrs.get("undeclared_secrets", []) or [])
        if undeclared:
            out.append(
                make_candidate(
                    scope_id=f"infra:gha-secret:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.78,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"undeclared_secrets": undeclared},
                )
            )
    return out


register(SPEC, run)
