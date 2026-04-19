from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="env-var-referenced-but-undefined",
    universe=Universe.env,
    verifier_checks=["graph_path_exists", "negation_witness", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "env_var"):
        if attrs.get("defined"):
            continue
        readers = incoming_by_relation(graph, node_id, "READS_ENV_VAR")
        if not readers:
            continue
        out.append(
            make_candidate(
                scope_id=f"env:undefined:{attrs.get('name') or node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.82,
                analysis_mode=mode,
                diff_anchors=[node_id] + [source for source, _ in readers],
                extra={"env_var": attrs.get("name"), "readers": [source for source, _ in readers]},
            )
        )
    return out


register(SPEC, run)
