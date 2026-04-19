from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="vulnerable-dep",
    universe=Universe.deps,
    verifier_checks=["external_oracle_lookup", "version_satisfaction"],
    requires_reasoner=False,
    severity="critical",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "lockfile_resolution"):
        advisories = list(attrs.get("advisory_ids") or [])
        if not advisories and not attrs.get("vulnerable"):
            continue
        out.append(
            make_candidate(
                scope_id=f"deps:vulnerable:{node_id}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.92,
                analysis_mode=mode,
                diff_anchors=[node_id],
                extra={
                    "package_name": attrs.get("package_name"),
                    "resolved_version": attrs.get("resolved_version"),
                    "advisory_ids": advisories,
                    "oracle_hints": {
                        "oracle": "advisory_db",
                        "ecosystem": attrs.get("ecosystem"),
                        "name": attrs.get("package_name"),
                        "version": attrs.get("resolved_version"),
                    },
                },
            )
        )
    return out


register(SPEC, run)
