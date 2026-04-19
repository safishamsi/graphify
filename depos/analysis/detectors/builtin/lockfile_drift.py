from __future__ import annotations

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="lockfile-drift",
    universe=Universe.deps,
    verifier_checks=["graph_path_exists", "version_satisfaction", "external_oracle_lookup"],
    requires_reasoner=False,
    severity="medium",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for node_id, attrs in iter_nodes_by_kind(graph, "package_dep"):
        declared = str(attrs.get("declared_range") or "").strip()
        resolved = str(attrs.get("resolved_version") or "").strip()
        has_resolution = bool(attrs.get("lockfile_match", resolved))
        if declared and (not has_resolution or attrs.get("lockfile_drift")):
            out.append(
                make_candidate(
                    scope_id=f"deps:lockfile-drift:{node_id}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.74,
                    analysis_mode=mode,
                    diff_anchors=[node_id],
                    extra={
                        "package_name": attrs.get("package_name"),
                        "declared_range": declared,
                        "resolved_version": resolved,
                        "oracle_hints": {"declared_range": declared, "resolved_version": resolved},
                    },
                )
            )
    return out


register(SPEC, run)
