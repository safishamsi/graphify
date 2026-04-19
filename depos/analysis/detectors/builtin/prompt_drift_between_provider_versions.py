from __future__ import annotations

from collections import defaultdict

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="prompt-drift-between-provider-versions",
    universe=Universe.prompt,
    verifier_checks=["graph_path_exists", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    groups = defaultdict(list)
    for node_id, attrs in iter_nodes_by_kind(graph, "prompt_template"):
        logical_name = str(attrs.get("logical_name") or attrs.get("name") or node_id)
        groups[logical_name].append((node_id, attrs))
    out = []
    for logical_name, nodes in groups.items():
        schemas = {str(attrs.get("schema_id") or "") for _, attrs in nodes}
        vars_sets = {tuple(sorted(str(v) for v in attrs.get("declared_vars", []))) for _, attrs in nodes}
        if len(nodes) > 1 and (len(schemas) > 1 or len(vars_sets) > 1):
            out.append(
                make_candidate(
                    scope_id=f"prompt:drift:{logical_name}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.66,
                    analysis_mode=mode,
                    diff_anchors=[node_id for node_id, _ in nodes],
                    extra={"logical_name": logical_name},
                )
            )
    return out


register(SPEC, run)
