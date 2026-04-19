from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="error-swallowed-in-async-handler",
    universe=Universe.code,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in graph.nodes(data=True):
        if not attrs.get("async_handler"):
            continue
        if attrs.get("swallowed_error") or "except Exception:\n        pass" in str(attrs.get("embedded_text") or ""):
            out.append(
                make_candidate(
                    scope_id=f"flow:swallowed-error:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.8,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"source_file": attrs.get("source_file")},
                )
            )
    return out


register(SPEC, run)
