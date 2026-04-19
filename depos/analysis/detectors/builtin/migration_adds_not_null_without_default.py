from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="migration-adds-not-null-without-default",
    universe=Universe.schema,
    verifier_checks=["migration_branch_state", "graph_path_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "config_key"):
        if not attrs.get("migration_not_null_without_default"):
            continue
        out.append(
            make_candidate(
                scope_id=f"schema:not-null-no-default:{node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.88,
                analysis_mode=mode,
                diff_anchors=[node_id],
                extra={"migration_id": attrs.get("migration_id"), "table_name": attrs.get("table_name")},
            )
        )
    return out


register(SPEC, run)
