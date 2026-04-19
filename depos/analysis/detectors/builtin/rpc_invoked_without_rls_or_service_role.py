from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import outgoing_by_relation, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="rpc-invoked-without-rls-or-service-role",
    universe=Universe.code,
    verifier_checks=["rls_awareness", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="critical",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in graph.nodes(data=True):
        rpc_calls = outgoing_by_relation(graph, node_id, "ROUTE_CALLS_RPC")
        if not rpc_calls:
            continue
        has_rls = bool(attrs.get("rls_checked"))
        service_role = bool(attrs.get("uses_service_role"))
        if has_rls or service_role:
            continue
        out.append(
                make_candidate(
                    scope_id=f"auth:rpc-no-rls:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.9,
                    analysis_mode=mode,
                    diff_anchors=[node_id] + [target for target, _ in rpc_calls],
                    extra={
                        "rpc_targets": [target for target, _ in rpc_calls],
                        "oracle_hints": {"missing_guard_signals": 1},
                        "missing_guard_signals": 1,
                    },
                )
            )
    return out


register(SPEC, run)
