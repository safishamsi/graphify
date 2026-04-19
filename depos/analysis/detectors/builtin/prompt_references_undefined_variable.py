from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="prompt-references-undefined-variable",
    universe=Universe.prompt,
    verifier_checks=["negation_witness"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "prompt_template"):
        declared = set(str(v) for v in attrs.get("declared_vars", []) if str(v).strip())
        used = set(str(v) for v in attrs.get("used_vars", []) if str(v).strip())
        undefined = sorted(used - declared)
        if undefined:
            out.append(
                make_candidate(
                    scope_id=f"prompt:undefined-var:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.81,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"undefined_vars": undefined},
                )
            )
    return out


register(SPEC, run)
