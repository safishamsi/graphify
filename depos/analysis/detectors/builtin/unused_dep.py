from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="unused-dep",
    universe=Universe.deps,
    verifier_checks=["negation_witness"],
    requires_reasoner=False,
    severity="low",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "package_dep"):
        if attrs.get("dep_type") == "peer":
            continue
        if incoming_by_relation(graph, node_id, "IMPORTS_PACKAGE"):
            continue
        if attrs.get("used", False):
            continue
        out.append(
            make_candidate(
                scope_id=f"deps:unused:{node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.44,
                analysis_mode=mode,
                diff_anchors=[node_id],
                extra={"package_name": attrs.get("package_name")},
            )
        )
    return out


register(SPEC, run)
