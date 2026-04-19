from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="peer-dep-unsatisfied",
    universe=Universe.deps,
    verifier_checks=["graph_path_exists", "version_satisfaction"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "package_dep"):
        if str(attrs.get("dep_type") or "") != "peer":
            continue
        if attrs.get("peer_unsatisfied") or attrs.get("unsatisfied"):
            out.append(
                make_candidate(
                    scope_id=f"deps:peer-unsatisfied:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.77,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={
                        "package_name": attrs.get("package_name"),
                        "declared_range": attrs.get("declared_range"),
                        "resolved_version": attrs.get("resolved_version"),
                    },
                )
            )
    return out


register(SPEC, run)
