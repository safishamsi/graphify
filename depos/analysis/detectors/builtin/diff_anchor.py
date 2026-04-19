from __future__ import annotations

from depos.analysis.candidate_identifier import _diff_anchor_candidates
from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import simple_spec
from depos.analysis.schemas import Universe


SPEC = simple_spec(
    name="diff-anchor",
    universe=Universe.code,
    verifier_checks=["graph_path_exists", "phantom_anchor_short_circuit"],
    requires_reasoner=True,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    return _diff_anchor_candidates(graph, manifest, mode)


register(SPEC, run)
