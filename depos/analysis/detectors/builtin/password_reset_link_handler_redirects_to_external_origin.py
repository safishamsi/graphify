from __future__ import annotations

from urllib.parse import urlparse

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="password-reset-link-handler-redirects-to-external-origin",
    universe=Universe.nextjs,
    verifier_checks=["negation_witness"],
    requires_reasoner=False,
    severity="critical",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "next_route"):
        if "reset" not in str(attrs.get("path") or "").lower():
            continue
        for target in attrs.get("redirect_targets", []) or []:
            parsed = urlparse(str(target))
            if parsed.scheme and parsed.netloc:
                out.append(
                    make_candidate(
                        scope_id=f"auth:reset-external-redirect:{node_id}",
                        seed_type=SeedType.graph_anomaly,
                        priority_score=0.95,
                        analysis_mode=mode,
                        diff_anchors=[node_id],
                        extra={
                            "target": target,
                            "oracle_hints": {"missing_guard_signals": 1},
                            "missing_guard_signals": 1,
                        },
                    )
                )
    return out


register(SPEC, run)
