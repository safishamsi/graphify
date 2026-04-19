from __future__ import annotations

from collections import defaultdict

from depos.analysis.detectors import register
from depos.analysis.detectors.builtin.common import iter_nodes_by_kind, make_candidate, simple_spec
from depos.analysis.schemas import SeedType, Universe


SPEC = simple_spec(
    name="transitive-pin-conflict",
    universe=Universe.deps,
    verifier_checks=["version_satisfaction", "external_oracle_lookup"],
    requires_reasoner=False,
    severity="high",
)


def run(graph, manifest, mode, config, ctx):
    groups: dict[str, set[str]] = defaultdict(set)
    anchors: dict[str, list[str]] = defaultdict(list)
    for node_id, attrs in iter_nodes_by_kind(graph, "lockfile_resolution"):
        package_name = str(attrs.get("package_name") or "")
        version = str(attrs.get("resolved_version") or "")
        if not package_name or not version:
            continue
        groups[package_name].add(version)
        anchors[package_name].append(node_id)
    out = []
    for package_name, versions in groups.items():
        if len(versions) <= 1:
            continue
        out.append(
            make_candidate(
                scope_id=f"deps:transitive-pin-conflict:{package_name}",
                seed_type=SeedType.graph_anomaly,
                priority_score=0.79,
                analysis_mode=mode,
                diff_anchors=anchors[package_name],
                extra={"package_name": package_name, "versions": sorted(versions)},
            )
        )
    return out


register(SPEC, run)
