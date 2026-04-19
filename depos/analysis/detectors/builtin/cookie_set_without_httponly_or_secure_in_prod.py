from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="cookie-set-without-httponly-or-secure-in-prod",
    universe=Universe.code,
    verifier_checks=["graph_path_exists"],
    requires_reasoner=False,
    severity="critical",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in graph.nodes(data=True):
        cookie = attrs.get("cookie_settings")
        if not isinstance(cookie, dict):
            continue
        if cookie.get("httponly") and cookie.get("secure"):
            continue
        if str(attrs.get("environment") or "").lower() not in {"production", "prod"} and not attrs.get("prod_only"):
            continue
        out.append(
                make_candidate(
                    scope_id=f"auth:insecure-cookie:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.91,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={
                        "cookie_settings": cookie,
                        "oracle_hints": {"missing_guard_signals": 1},
                        "missing_guard_signals": 1,
                    },
                )
            )
    return out


register(SPEC, run)
