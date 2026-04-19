from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="enum-value-used-but-not-in-schema",
    universe=Universe.schema,
    verifier_checks=["external_oracle_lookup"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "openapi_schema"):
        invalid = list(attrs.get("used_enum_values_not_in_schema", []) or [])
        if invalid:
            out.append(
                make_candidate(
                    scope_id=f"schema:enum-mismatch:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.72,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"invalid_enum_values": invalid, "schema_name": attrs.get("name")},
                )
            )
    return out


register(SPEC, run)
