from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="request-body-missing-required-field",
    universe=Universe.schema,
    verifier_checks=["external_oracle_lookup", "graph_path_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "openapi_operation"):
        missing = list(attrs.get("missing_request_required_fields", []) or [])
        if missing:
            out.append(
                make_candidate(
                    scope_id=f"schema:req-missing:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.86,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"missing_fields": missing, "operation_id": attrs.get("operation_id")},
                )
            )
    return out


register(SPEC, run)
