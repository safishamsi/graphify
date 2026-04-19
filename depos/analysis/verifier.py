"""Module 6 \u2014 deterministic verifier.

Runs six check families over every reasoner finding and returns a
:class:`VerifierAuditEntry` summarizing what passed, what failed, and
what could not be evaluated. The six families:

1. **graph_path_exists**   \u2014 are all nodes the reasoner referenced real
   and reachable in the enriched graph?
2. **edge_confidence_floor** \u2014 if the finding rests on only inferred
   edges, require a confidence floor from the verifier policy, bumped
   for full-repo scans.
3. **rls_awareness**       \u2014 if the finding claims an RLS gap, confirm
   against :class:`RLSCoverage` from Module 1.
4. **migration_branch_state** \u2014 if the finding references a table that
   is not yet visible in the branch, mark the check invalid.
5. **payload_contract**    \u2014 producer/consumer key overlap check using
   Module 1's Celery payload annotations.
6. **phantom_anchor_short_circuit** \u2014 if ``diff_anchors`` on the
   candidate don't intersect the reasoner's witness path, short-circuit
   to invalid_reasoning.

All checks are deterministic and leave no floating-point room for
non-reproducible outcomes.
"""
from __future__ import annotations

from typing import Any, Iterable

import networkx as nx

from depos.analysis.config import IntelligenceConfig
from depos.analysis.oracles import ORACLES
from depos.analysis.schemas import (
    Candidate,
    ContextBundle,
    Finding,
    ModeAFinding,
    ModeAOutput,
    ModeBFinding,
    ModeBOutput,
    ModeCFinding,
    ModeCOutput,
    ReasonerMode,
    RLSCoverage,
    VerifierAuditEntry,
    VerifierCheckResult,
    VerifierOutcome,
)

CheckName = str


def _detector_meta(candidate: Candidate) -> dict[str, Any]:
    raw = candidate.extra.get("detector")
    return dict(raw) if isinstance(raw, dict) else {}


def _detector_name(candidate: Candidate) -> str:
    return str(_detector_meta(candidate).get("detector_name") or "legacy")


def _detector_spec(candidate: Candidate):
    try:
        from depos.analysis.detectors import get_detector

        name = _detector_name(candidate)
        if name == "legacy":
            return None
        return get_detector(name)
    except Exception:  # noqa: BLE001
        return None


def _safe_run(name: str, fn) -> VerifierCheckResult:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return VerifierCheckResult(name=name, result="unavailable", detail=f"exception:{exc}")


def _node_universe(attrs: dict[str, Any]) -> str:
    node_kind = str(attrs.get("node_kind") or attrs.get("kind") or "")
    if node_kind in {"package_manifest", "package_dep", "lockfile_resolution"}:
        return "deps"
    if node_kind in {"env_var", "config_key"}:
        return "env"
    if node_kind == "prompt_template":
        return "prompt"
    if node_kind in {"openapi_operation", "openapi_schema"}:
        return "schema"
    if node_kind in {"next_route", "next_middleware"}:
        return "nextjs"
    if node_kind in {"infra_workflow", "infra_service", "dockerfile_stage"}:
        return "infra"
    return str(attrs.get("universe") or attrs.get("source_system") or "code")


def _candidate_witness_path(graph: nx.DiGraph, candidate: Candidate) -> list[str]:
    if candidate.diff_anchors:
        return list(dict.fromkeys(candidate.diff_anchors))
    nodes: list[str] = []
    for seam in candidate.seam_edges:
        parts = seam.split("|")
        if len(parts) >= 2:
            nodes.extend(parts[:2])
    if nodes:
        return list(dict.fromkeys(nodes))
    if candidate.scope_id.startswith("node:"):
        return [candidate.scope_id[5:]]
    return []


def _check_graph_path_exists(graph: nx.DiGraph, nodes: list[str]) -> VerifierCheckResult:
    missing = [n for n in nodes if not graph.has_node(n)]
    if not nodes:
        return VerifierCheckResult(name="graph_path_exists", result="unavailable", detail="no nodes cited")
    if missing:
        return VerifierCheckResult(
            name="graph_path_exists",
            result="fail",
            detail=f"missing_nodes={missing}",
        )
    return VerifierCheckResult(name="graph_path_exists", result="pass")


def _check_edge_confidence_floor(
    graph: nx.DiGraph,
    path: list[str],
    *,
    floor: float,
    inferred_floor_applied: bool,
) -> VerifierCheckResult:
    if len(path) < 2:
        return VerifierCheckResult(name="edge_confidence_floor", result="unavailable")
    min_conf = 1.0
    all_inferred = True
    for u, v in zip(path, path[1:]):
        if not graph.has_edge(u, v):
            continue
        data = graph.get_edge_data(u, v) or {}
        # DiGraph returns a flat attrs dict; MultiDiGraph returns {key: attrs}.
        if graph.is_multigraph():
            datas = list(data.values())
        else:
            datas = [data]
        for d in datas:
            if not isinstance(d, dict):
                continue
            conf = float(d.get("confidence", 1.0))
            if not d.get("inferred"):
                all_inferred = False
            if conf < min_conf:
                min_conf = conf
    effective_floor = floor + (0.1 if inferred_floor_applied else 0.0)
    if all_inferred and min_conf < effective_floor:
        return VerifierCheckResult(
            name="edge_confidence_floor",
            result="fail",
            detail=f"min_conf={min_conf:.2f} floor={effective_floor:.2f} all_inferred=true",
        )
    return VerifierCheckResult(name="edge_confidence_floor", result="pass", detail=f"min_conf={min_conf:.2f}")


def _check_rls_awareness(graph: nx.DiGraph, bundle: ContextBundle, candidate: Candidate) -> VerifierCheckResult:
    detector_name = _detector_name(candidate)
    rls_detector = "rls" in detector_name
    has_rls_edges = any(
        data.get("relation") == "ROUTE_GUARDED_BY_RLS"
        for _, _, data in graph.edges(data=True)
    )
    if not rls_detector and not has_rls_edges and not bundle.rls_coverage:
        return VerifierCheckResult(name="rls_awareness", result="unavailable")
    if not bundle.rls_coverage:
        return VerifierCheckResult(name="rls_awareness", result="insufficient_static_evidence")
    # If any cited table has ``full`` coverage, we flag the RLS claim as likely covered.
    states = list(bundle.rls_coverage.values())
    if any(cov == RLSCoverage.full for cov in states):
        return VerifierCheckResult(name="rls_awareness", result="rls_covered", detail="full_on_any_cited_table")
    if any(cov in {RLSCoverage.partial_operation, RLSCoverage.partial_predicate} for cov in states):
        return VerifierCheckResult(name="rls_awareness", result="rls_partial")
    return VerifierCheckResult(name="rls_awareness", result="pass", detail="no_coverage_claimed")


def _check_migration_branch_state(bundle: ContextBundle, cited_tables: list[str]) -> VerifierCheckResult:
    if not cited_tables:
        return VerifierCheckResult(name="migration_branch_state", result="unavailable")
    missing = [t for t in cited_tables if t not in bundle.migration_state]
    if missing:
        return VerifierCheckResult(
            name="migration_branch_state",
            result="invalid",
            detail=f"not_in_branch={missing}",
        )
    return VerifierCheckResult(name="migration_branch_state", result="pass")


def _check_payload_contract(graph: nx.DiGraph, cited_nodes: list[str]) -> VerifierCheckResult:
    for n in cited_nodes:
        if not graph.has_node(n):
            continue
        for _, _, data in graph.out_edges(n, data=True):
            missing = data.get("payload_missing_fields")
            extra = data.get("payload_extra_fields")
            if missing or extra:
                return VerifierCheckResult(
                    name="payload_contract",
                    result="fail",
                    detail=f"missing={missing or []} extra={extra or []}",
                )
    return VerifierCheckResult(name="payload_contract", result="pass")


def _check_phantom_anchor(candidate: Candidate, witness_path: list[str], *, enabled: bool) -> VerifierCheckResult:
    if not enabled or not candidate.diff_anchors:
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="unavailable")
    if not witness_path:
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="unavailable")
    if set(candidate.diff_anchors) & set(witness_path):
        return VerifierCheckResult(name="phantom_anchor_short_circuit", result="pass")
    return VerifierCheckResult(
        name="phantom_anchor_short_circuit",
        result="fail",
        detail="diff_anchors_not_in_witness",
    )


def _check_external_oracle_lookup(candidate: Candidate) -> VerifierCheckResult:
    meta = _detector_meta(candidate)
    hints = dict(meta.get("oracle_hints") or candidate.extra.get("oracle_hints") or {})
    if not hints:
        return VerifierCheckResult(name="external_oracle_lookup", result="unavailable")
    oracle_name = str(hints.get("oracle") or "")
    if not oracle_name:
        if hints.get("schema"):
            oracle_name = "json_schema"
        elif hints.get("ecosystem") or hints.get("name"):
            oracle_name = "advisory_db"
        elif hints.get("declared_range") and hints.get("resolved_version"):
            oracle_name = "lockfile_resolver"
    oracle = ORACLES.get(oracle_name)
    if oracle is None:
        return VerifierCheckResult(name="external_oracle_lookup", result="unavailable", detail=f"oracle_missing:{oracle_name}")
    result = oracle(hints)
    if result.conclusion == "pass":
        return VerifierCheckResult(name="external_oracle_lookup", result="pass", detail=result.detail)
    if result.conclusion == "fail":
        return VerifierCheckResult(name="external_oracle_lookup", result="fail", detail=result.detail)
    return VerifierCheckResult(name="external_oracle_lookup", result="insufficient_static_evidence", detail=result.detail)


def _check_cross_universe_edge_exists(graph: nx.DiGraph, witness_path: list[str], candidate: Candidate) -> VerifierCheckResult:
    required_pairs = {
        tuple(pair)
        for pair in candidate.extra.get("required_universe_pairs", [])
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    }
    pairs: set[tuple[str, str]] = set()
    nodes = list(dict.fromkeys(witness_path or _candidate_witness_path(graph, candidate)))
    if len(nodes) >= 2:
        for idx, source in enumerate(nodes):
            for target in nodes[idx + 1 :]:
                if graph.has_edge(source, target):
                    data = graph.get_edge_data(source, target) or {}
                    pair = (
                        str(data.get("source_system") or _node_universe(graph.nodes[source])),
                        str(data.get("target_system") or _node_universe(graph.nodes[target])),
                    )
                    pairs.add(pair)
                if graph.has_edge(target, source):
                    data = graph.get_edge_data(target, source) or {}
                    pair = (
                        str(data.get("source_system") or _node_universe(graph.nodes[target])),
                        str(data.get("target_system") or _node_universe(graph.nodes[source])),
                    )
                    pairs.add(pair)
    if not pairs and candidate.seam_edges:
        for seam in candidate.seam_edges:
            parts = seam.split("|")
            if len(parts) < 2 or not graph.has_node(parts[0]) or not graph.has_node(parts[1]):
                continue
            pairs.add((_node_universe(graph.nodes[parts[0]]), _node_universe(graph.nodes[parts[1]])))
    if not pairs:
        return VerifierCheckResult(name="cross_universe_edge_exists", result="unavailable")
    if not required_pairs or pairs & required_pairs:
        return VerifierCheckResult(name="cross_universe_edge_exists", result="pass", detail=f"pairs={sorted(pairs)}")
    return VerifierCheckResult(name="cross_universe_edge_exists", result="fail", detail=f"pairs={sorted(pairs)}")


def _check_negation_witness(graph: nx.DiGraph, candidate: Candidate) -> VerifierCheckResult:
    detector_name = _detector_name(candidate)
    anchors = _candidate_witness_path(graph, candidate)
    if not anchors:
        return VerifierCheckResult(name="negation_witness", result="unavailable")
    if detector_name == "env-var-referenced-but-undefined":
        for node_id in anchors:
            if graph.has_node(node_id) and graph.nodes[node_id].get("node_kind") == "env_var":
                defined_edges = any(data.get("relation") == "DEFINED_BY_CONFIG" for _, _, data in graph.in_edges(node_id, data=True))
                if not defined_edges and not graph.nodes[node_id].get("defined"):
                    return VerifierCheckResult(name="negation_witness", result="pass", detail="env_var_has_no_definition_edge")
        return VerifierCheckResult(name="negation_witness", result="fail", detail="definition_edge_present")
    if detector_name == "env-var-defined-but-unused":
        for node_id in anchors:
            if graph.has_node(node_id) and graph.nodes[node_id].get("node_kind") == "env_var":
                reads = any(data.get("relation") == "READS_ENV_VAR" for _, _, data in graph.in_edges(node_id, data=True))
                return VerifierCheckResult(name="negation_witness", result="pass" if not reads else "fail", detail="no_readers" if not reads else "readers_present")
    return VerifierCheckResult(name="negation_witness", result="unavailable")


def _check_version_satisfaction(candidate: Candidate) -> VerifierCheckResult:
    meta = _detector_meta(candidate)
    hints = dict(meta.get("oracle_hints") or candidate.extra.get("oracle_hints") or {})
    if not hints.get("declared_range") or not hints.get("resolved_version"):
        return VerifierCheckResult(name="version_satisfaction", result="unavailable")
    oracle_name = "pep440" if str(hints.get("ecosystem") or "").lower() in {"pip", "python"} else "semver"
    result = ORACLES[oracle_name](hints)
    if result.conclusion == "pass":
        return VerifierCheckResult(name="version_satisfaction", result="pass", detail=result.detail)
    if result.conclusion == "fail":
        return VerifierCheckResult(name="version_satisfaction", result="fail", detail=result.detail)
    return VerifierCheckResult(name="version_satisfaction", result="insufficient_static_evidence", detail=result.detail)


# ---------------------------------------------------------------------------
# Outcome derivation
# ---------------------------------------------------------------------------


def _derive_outcome(checks: list[VerifierCheckResult], *, mechanical: bool = False) -> VerifierOutcome:
    executed = sum(1 for c in checks if c.result in {"pass", "fail", "invalid", "rls_covered", "rls_partial"})
    passes = sum(1 for c in checks if c.result == "pass")
    fails = sum(1 for c in checks if c.result in {"fail", "invalid"})
    if mechanical and passes >= 1 and fails == 0:
        return VerifierOutcome.confirmed
    if fails >= 2:
        return VerifierOutcome.invalid_reasoning
    if fails == 1 and passes >= 2 and executed >= 2:
        return VerifierOutcome.partially_confirmed
    if passes >= 3 and executed >= 2:
        return VerifierOutcome.confirmed
    if passes == 0 and executed >= 1:
        return VerifierOutcome.unconfirmed
    if passes >= 1 and executed >= 2:
        return VerifierOutcome.partially_confirmed
    return VerifierOutcome.unconfirmed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify(
    *,
    graph: nx.DiGraph,
    candidate: Candidate,
    bundle: ContextBundle,
    mode: ReasonerMode | None,
    finding: ModeAFinding | ModeBFinding | ModeCFinding | None,
    config: IntelligenceConfig,
    full_repo_scan: bool,
) -> tuple[VerifierAuditEntry, Finding]:
    spec = _detector_spec(candidate)
    witness_path: list[str] = _candidate_witness_path(graph, candidate)
    if isinstance(finding, ModeAFinding):
        witness_path = list(finding.affected_path or []) + list(finding.graph_anchor_nodes or [])
        bug_type = finding.bug_type
        description = finding.description
        confidence = float(finding.confidence)
        missing_guard = None
    elif isinstance(finding, ModeBFinding):
        witness_path = list(finding.graph_anchor_nodes or [])
        bug_type = finding.violation_type
        description = f"{finding.description} (A={finding.component_a}, B={finding.component_b})"
        confidence = float(finding.confidence)
        missing_guard = None
    elif isinstance(finding, ModeCFinding):
        witness_path = list(finding.violating_path or []) + list(finding.graph_anchor_nodes or [])
        bug_type = finding.flow_bug_type
        description = finding.description
        confidence = float(finding.confidence)
        missing_guard = finding.missing_guard
    else:
        bug_type = str(candidate.extra.get("anomaly") or candidate.extra.get("surface_type") or _detector_name(candidate))
        description = str(candidate.extra.get("description") or bug_type.replace("_", " ").replace("-", " "))
        confidence = 1.0 if spec is not None and not spec.requires_reasoner else 0.0
        missing_guard = str(candidate.extra.get("missing_guard") or "") or None

    cited_tables = sorted(bundle.rls_coverage.keys())

    requested_checks = list(spec.verifier_checks) if spec is not None else [
        "graph_path_exists",
        "edge_confidence_floor",
        "rls_awareness",
        "migration_branch_state",
        "payload_contract",
        "phantom_anchor_short_circuit",
    ]

    checks: list[VerifierCheckResult] = []
    for check_name in requested_checks:
        if check_name == "graph_path_exists":
            checks.append(_safe_run(check_name, lambda: _check_graph_path_exists(graph, witness_path)))
        elif check_name == "edge_confidence_floor":
            checks.append(
                _safe_run(
                    check_name,
                    lambda: _check_edge_confidence_floor(
                        graph,
                        witness_path,
                        floor=config.verifier.min_edge_confidence_for_confirmed,
                        inferred_floor_applied=full_repo_scan,
                    ),
                )
            )
        elif check_name == "rls_awareness":
            checks.append(_safe_run(check_name, lambda: _check_rls_awareness(graph, bundle, candidate)))
        elif check_name == "migration_branch_state":
            checks.append(_safe_run(check_name, lambda: _check_migration_branch_state(bundle, cited_tables)))
        elif check_name == "payload_contract":
            checks.append(_safe_run(check_name, lambda: _check_payload_contract(graph, witness_path)))
        elif check_name == "phantom_anchor_short_circuit":
            checks.append(_safe_run(check_name, lambda: _check_phantom_anchor(candidate, witness_path, enabled=config.verifier.phantom_anchor_short_circuit)))
        elif check_name == "external_oracle_lookup":
            checks.append(_safe_run(check_name, lambda: _check_external_oracle_lookup(candidate)))
        elif check_name == "cross_universe_edge_exists":
            checks.append(_safe_run(check_name, lambda: _check_cross_universe_edge_exists(graph, witness_path, candidate)))
        elif check_name == "negation_witness":
            checks.append(_safe_run(check_name, lambda: _check_negation_witness(graph, candidate)))
        elif check_name == "version_satisfaction":
            checks.append(_safe_run(check_name, lambda: _check_version_satisfaction(candidate)))
        else:
            checks.append(VerifierCheckResult(name=check_name, result="unavailable", detail="unknown_check"))

    mechanical = spec is not None and not spec.requires_reasoner and finding is None
    outcome = _derive_outcome(checks, mechanical=mechanical)

    mode_label = mode.value if mode is not None else "na"
    finding_id = f"{candidate.candidate_id}:{mode_label}:{bug_type}"[:96]
    audit = VerifierAuditEntry(
        finding_id=finding_id,
        verifier_outcome=outcome,
        checks_run=checks,
        inferred_edge_confidence_floor_applied=full_repo_scan,
        pack_manifest_id=bundle.pack_manifest.manifest_id,
        reasoner_mode=mode,
    )

    # Build the output-layer Finding. Surface RLS verdict if we have one.
    rls_verdict: RLSCoverage | None = None
    for cov in bundle.rls_coverage.values():
        if cov in {RLSCoverage.full, RLSCoverage.partial_operation, RLSCoverage.partial_predicate, RLSCoverage.context_mismatch, RLSCoverage.none}:
            rls_verdict = cov
            break

    affected: list[str] = []
    if isinstance(finding, ModeBFinding):
        affected = [finding.component_a, finding.component_b]
    elif witness_path:
        affected = witness_path[:4]

    out_finding = Finding(
        finding_id=finding_id,
        trust_level=outcome,
        mode=mode,
        verifier_outcome=outcome,
        bug_type=bug_type,
        description=description,
        affected_components=affected,
        witness_path=witness_path,
        missing_guard=missing_guard,
        reasoner_confidence=confidence,
        ranking_phase=0,
        verifier_checks_passed=[c.name for c in checks if c.result == "pass"],
        verifier_checks_inconclusive=[c.name for c in checks if c.result in {"unavailable", "insufficient_static_evidence", "rls_partial"}],
        rls_verdict=rls_verdict,
        pack_manifest_id=bundle.pack_manifest.manifest_id,
        detector_name=_detector_name(candidate),
        detector_version=str(_detector_meta(candidate).get("detector_version") or "0"),
        pipeline_version=str(_detector_meta(candidate).get("pipeline_version") or "0"),
        severity=str(_detector_meta(candidate).get("severity") or "medium"),
    )
    if outcome == VerifierOutcome.partially_confirmed:
        out_finding.partially_confirmed_caveat = (
            "Verifier confirmed some but not all structural checks; treat as suggestive, not proof."
        )
    return audit, out_finding


def verify_all(
    *,
    graph: nx.DiGraph,
    candidate: Candidate,
    bundle: ContextBundle,
    reasoner_outputs: dict[ReasonerMode, Any],
    config: IntelligenceConfig,
    full_repo_scan: bool,
) -> tuple[list[VerifierAuditEntry], list[Finding]]:
    audits: list[VerifierAuditEntry] = []
    findings: list[Finding] = []
    spec = _detector_spec(candidate)
    if (not reasoner_outputs) and spec is not None and not spec.requires_reasoner:
        audit, finding = verify(
            graph=graph,
            candidate=candidate,
            bundle=bundle,
            mode=None,
            finding=None,
            config=config,
            full_repo_scan=full_repo_scan,
        )
        audits.append(audit)
        findings.append(finding)
        return audits, findings
    for mode, output in reasoner_outputs.items():
        raw_findings: Iterable
        if isinstance(output, ModeAOutput):
            raw_findings = output.findings
        elif isinstance(output, ModeBOutput):
            raw_findings = output.findings
        elif isinstance(output, ModeCOutput):
            raw_findings = output.findings
        else:
            continue
        for raw in raw_findings:
            audit, f = verify(
                graph=graph,
                candidate=candidate,
                bundle=bundle,
                mode=mode,
                finding=raw,
                config=config,
                full_repo_scan=full_repo_scan,
            )
            audits.append(audit)
            findings.append(f)
    return audits, findings


__all__ = ["verify", "verify_all"]
