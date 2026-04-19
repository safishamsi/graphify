from __future__ import annotations

from depos.analysis.candidate_identifier import _ai_driven_candidates
from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import simple_spec
from depos.analysis.schemas import Universe


SPEC = simple_spec(
    name="lexical-keyword-seed",
    universe=Universe.code,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=True,
    severity="low",
)


def run(graph, manifest, mode, config, ctx):
    return _ai_driven_candidates(graph, config, mode)


register(SPEC, run)
