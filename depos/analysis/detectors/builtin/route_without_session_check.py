from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="route-without-session-check",
    universe=Universe.nextjs,
    verifier_checks=["negation_witness", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "next_route"):
        public = bool(attrs.get("public", False))
        guarded = bool(incoming_by_relation(graph, node_id, "NEXT_ROUTE_GUARDED_BY_MIDDLEWARE")) or bool(attrs.get("session_checked"))
        if public and not guarded:
            out.append(
                make_candidate(
                    scope_id=f"auth:route-no-session:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.84,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={
                        "route_path": attrs.get("path"),
                        "oracle_hints": {"missing_guard_signals": 1},
                        "missing_guard_signals": 1,
                    },
                )
            )
    return out


register(SPEC, run)
