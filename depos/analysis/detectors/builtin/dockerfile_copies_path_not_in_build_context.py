from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="dockerfile-copies-path-not-in-build-context",
    universe=Universe.infra,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "dockerfile_stage"):
        missing = list(attrs.get("missing_copy_sources", []) or [])
        if missing:
            out.append(
                make_candidate(
                    scope_id=f"infra:docker-copy-missing:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.81,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"missing_copy_sources": missing},
                )
            )
    return out


register(SPEC, run)
