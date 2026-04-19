from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import incoming_by_relation, iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="phantom-dep",
    universe=Universe.deps,
    verifier_checks=["graph_path_exists", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "package_dep"):
        if attrs.get("declared", True):
            continue
        importers = incoming_by_relation(graph, node_id, "IMPORTS_PACKAGE")
        if not importers and not attrs.get("imported_by"):
            continue
        out.append(
            make_candidate(
                scope_id=f"deps:phantom:{node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.75,
                analysis_mode=mode,
                diff_anchors=[node_id] + [source for source, _ in importers],
                extra={"package_name": attrs.get("package_name")},
            )
        )
    return out


register(SPEC, run)
