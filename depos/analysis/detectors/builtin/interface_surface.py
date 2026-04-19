from __future__ import annotations

from depos.analysis.candidate_identifier import _interface_surface_candidates
from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import simple_spec
from depos.analysis.schemas import Universe


SPEC = simple_spec(
    name="interface-surface",
    universe=Universe.code,
    verifier_checks=["graph_path_exists", "cross_universe_edge_exists"],
    requires_reasoner=True,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    return _interface_surface_candidates(graph, mode)


register(SPEC, run)
