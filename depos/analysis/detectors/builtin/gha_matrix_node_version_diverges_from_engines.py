from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="gha-matrix-node-version-diverges-from-engines",
    universe=Universe.infra,
    verifier_checks=["version_satisfaction"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "infra_workflow"):
        engine = str(attrs.get("engine_node_range") or "")
        versions = [str(v) for v in attrs.get("matrix_node_versions", []) if str(v).strip()]
        if engine and versions and attrs.get("matrix_engine_drift"):
            out.append(
                make_candidate(
                    scope_id=f"infra:gha-node-version-drift:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.71,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"engine_node_range": engine, "matrix_node_versions": versions},
                )
            )
    return out


register(SPEC, run)
