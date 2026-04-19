from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="compose-service-depends-on-service-with-different-network",
    universe=Universe.infra,
    verifier_checks=["graph_path_exists", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "infra_service"):
        conflicts = list(attrs.get("network_conflicts", []) or [])
        if conflicts:
            out.append(
                make_candidate(
                    scope_id=f"infra:compose-network-conflict:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.66,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"network_conflicts": conflicts},
                )
            )
    return out


register(SPEC, run)
