from __future__ import annotations

from depos.analysis.candidate_identifier import _graph_anomaly_candidates
from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import simple_spec
from depos.analysis.schemas import Universe


SPEC = simple_spec(
    name="graph-anomaly",
    universe=Universe.code,
    verifier_checks=["graph_path_exists", "negation_witness"],
    requires_reasoner=True,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    return _graph_anomaly_candidates(graph, mode)


register(SPEC, run)
