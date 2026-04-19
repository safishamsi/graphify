from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="cors-origin-omits-known-client-origin",
    universe=Universe.env,
    verifier_checks=["negation_witness", "cross_universe_edge_exists"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    client_origins = set()
    for _, attrs in iter_nodes_by_kind(graph, "config_key"):
        if str(attrs.get("key") or "").endswith("NEXT_PUBLIC_DEPOS_API_URL"):
            client_origins.add(str(attrs.get("origin") or attrs.get("value") or ""))
    for node_id, attrs in iter_nodes_by_kind(graph, "config_key"):
        key = str(attrs.get("key") or "")
        if "CORS" not in key.upper():
            continue
        allowed = set(str(v) for v in attrs.get("origins", []) if str(v).strip())
        missing = sorted(origin for origin in client_origins if origin and origin not in allowed)
        if missing:
            out.append(
                make_candidate(
                    scope_id=f"env:cors-omits-origin:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.79,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={"missing_origins": missing, "config_key": key},
                )
            )
    return out


register(SPEC, run)
