from __future__ import annotations

from urllib.parse import urlparse

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="redirect-target-not-safelisted",
    universe=Universe.env,
    verifier_checks=["graph_path_exists", "negation_witness"],
    requires_reasoner=False,
    severity="high",
)


def _external(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in list(iter_nodes_by_kind(graph, "config_key")) + list(iter_nodes_by_kind(graph, "next_route")):
        targets = list(attrs.get("redirect_targets") or [])
        safelist = set(str(v) for v in attrs.get("allowed_redirect_origins", []) if str(v).strip())
        for target in targets:
            if not _external(str(target)):
                continue
            origin = "{uri.scheme}://{uri.netloc}".format(uri=urlparse(str(target)))
            if origin not in safelist:
                out.append(
                    make_candidate(
                        scope_id=f"env:redirect-not-safelisted:{node_id}:{origin}",
                        seed_type=SeedType.graph_anomaly,
                        priority_score=0.84,
                        analysis_mode=mode,
                        diff_anchors=[node_id],
                        extra={"target": target, "origin": origin},
                    )
                )
    return out


register(SPEC, run)
