from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="env-var-defined-but-unused",
    universe=Universe.env,
    verifier_checks=["negation_witness"],
    requires_reasoner=False,
    severity="low",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "env_var"):
        if not attrs.get("defined"):
            continue
        if incoming_by_relation(graph, node_id, "READS_ENV_VAR"):
            continue
        out.append(
            make_candidate(
                scope_id=f"env:unused:{attrs.get('name') or node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.38,
                analysis_mode=mode,
                diff_anchors=[node_id],
                extra={"env_var": attrs.get("name")},
            )
        )
    return out


register(SPEC, run)
