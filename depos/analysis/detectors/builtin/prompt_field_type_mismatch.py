from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="prompt-field-type-mismatch",
    universe=Universe.prompt,
    verifier_checks=["external_oracle_lookup"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "prompt_template"):
        mismatches = list(attrs.get("field_type_mismatches", []) or [])
        if mismatches:
            out.append(
                make_candidate(
                    scope_id=f"prompt:type-mismatch:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.7,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"field_type_mismatches": mismatches, "schema_id": attrs.get("schema_id")},
                )
            )
    return out


register(SPEC, run)
