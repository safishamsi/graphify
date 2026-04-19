from __future__ import annotations

from collections import defaultdict

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import make_candidate, package_groups, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="dep-version-mismatch-across-workspaces",
    universe=Universe.deps,
    verifier_checks=["graph_path_exists", "version_satisfaction", "external_oracle_lookup"],
    requires_reasoner=False,
    severity="medium",
    applies_when="node.kind == 'package_dep'",
)


def run(graph, manifest, mode, config, ctx):
    out = []
    for package_name, nodes in package_groups(graph).items():
        by_range: dict[str, list[str]] = defaultdict(list)
        manifests: set[str] = set()
        for node_id, attrs in nodes:
            manifests.add(str(attrs.get("manifest_id") or attrs.get("source_file") or node_id))
            by_range[str(attrs.get("declared_range") or "").strip()].append(node_id)
        ranges = [value for value in by_range if value]
        if len(manifests) > 1 and len(set(ranges)) > 1:
            anchors = sorted({node_id for node_ids in by_range.values() for node_id in node_ids})
            out.append(
                make_candidate(
                    scope_id=f"deps:range-drift:{package_name}",
                    seed_type=SeedType.graph_anomaly,
                    priority_score=0.78,
                    analysis_mode=mode,
                    diff_anchors=anchors,
                    extra={
                        "package_name": package_name,
                        "declared_ranges": sorted(ranges),
                        "oracle_hints": {"package_name": package_name, "ranges": sorted(ranges)},
                    },
                )
            )
    return out


register(SPEC, run)
