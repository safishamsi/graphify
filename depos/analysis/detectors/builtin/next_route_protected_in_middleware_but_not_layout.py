from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="next-route-protected-in-middleware-but-not-layout",
    universe=Universe.nextjs,
    verifier_checks=["graph_path_exists", "negation_witness", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "next_route"):
        guarded = bool(incoming_by_relation(graph, node_id, "NEXT_ROUTE_GUARDED_BY_MIDDLEWARE"))
        uses_layout = bool(incoming_by_relation(graph, node_id, "NEXT_ROUTE_USES_LAYOUT")) or bool(attrs.get("uses_auth_layout"))
        if guarded and not uses_layout:
            out.append(
                make_candidate(
                    scope_id=f"next:guarded-no-layout:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.69,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"route_path": attrs.get("path")},
                )
            )
    return out


register(SPEC, run)
