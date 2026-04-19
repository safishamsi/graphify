from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="env-var-typed-drift",
    universe=Universe.env,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "env_var"):
        if not attrs.get("typed_drift"):
            continue
        out.append(
            make_candidate(
                scope_id=f"env:typed-drift:{attrs.get('name') or node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.67,
                analysis_mode=mode,
                diff_anchors=[node_id],
                extra={
                    "env_var": attrs.get("name"),
                    "expected_type": attrs.get("expected_type"),
                    "observed_value": attrs.get("value"),
                },
            )
        )
    return out


register(SPEC, run)
