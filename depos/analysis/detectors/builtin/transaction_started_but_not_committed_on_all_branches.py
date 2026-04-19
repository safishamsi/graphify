from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="transaction-started-but-not-committed-on-all-branches",
    universe=Universe.code,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=False,
    severity="critical",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("transaction_started") and attrs.get("transaction_missing_commit"):
            out.append(
                make_candidate(
                    scope_id=f"flow:txn-missing-commit:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.9,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"source_file": attrs.get("source_file")},
                )
            )
    return out


register(SPEC, run)
