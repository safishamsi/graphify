"""Pipeline that orchestrates Modules 2\u20137 against a Module 1 enriched graph.

Kept as a thin composition layer so each module is independently
testable. The CLI layer is responsible for writing outputs; this module
only returns :class:`Finding` instances plus the side-effects of writing
module-specific audit files (reasoner queue, gray-zone audit).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import networkx as nx

from depos.analysis.candidate_identifier import identify_candidates
from depos.analysis.config import IntelligenceConfig
from depos.analysis.context_bundle import build_bundle
from depos.analysis.gray_zone_evaluator import evaluate as evaluate_gray_zone
from depos.analysis.gray_zone_evaluator import persist as persist_gray_zone
from depos.analysis.ranker import rank, serialize_examples
from depos.analysis.reasoning_engine import run_all_modes
from depos.analysis.schemas import (
    AnalysisMode,
    Finding,
    RankerDiffFeatures,
    RankerInput,
    RunMetadata,
    VerifierOutcome,
)
from depos.analysis.verifier import verify_all


def _build_ranker_input(candidate, bundle) -> RankerInput:
    cross_lang = len(bundle.cross_language_seams)
    changed_nodes = len(candidate.diff_anchors) + len([c for c in bundle.call_chain_in if c.get("depth", 0) == 1])
    features = RankerDiffFeatures(
        changed_nodes_on_path=changed_nodes,
        cross_lang_seams_on_path=cross_lang,
        unresolved_symbols=0,
        removed_entities_referenced=0,
    )
    return RankerInput(
        candidate_id=candidate.candidate_id,
        candidate_path=candidate.diff_anchors,
        edge_sequence=[s.relation for s in bundle.cross_language_seams],
        node_attrs={},
        diff_features=features,
    )


def run_modules_2_through_7(
    graph: nx.DiGraph,
    *,
    config: IntelligenceConfig,
    run_meta: RunMetadata,
    diff_path: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> list[Finding]:
    mode = run_meta.analysis_mode

    # Module 2 \u2014 candidates
    candidates, manifest = identify_candidates(
        graph,
        config=config,
        mode=mode,
        diff_path=diff_path,
        repo_root=repo_root,
    )
    if not candidates:
        return []

    all_findings: list[Finding] = []
    all_audits = []
    ranker_inputs: list[RankerInput] = []
    labels: dict[str, tuple[str, str]] = {}
    full_repo_scan = mode == AnalysisMode.full_repo_scan

    # Modules 3 \u2192 6 per-candidate.
    for candidate in candidates:
        bundle = build_bundle(graph, candidate, config=config)
        reasoner_out = run_all_modes(bundle, config=config, run_id=run_meta.run_id)
        audits, findings = verify_all(
            graph=graph,
            candidate=candidate,
            bundle=bundle,
            reasoner_outputs=reasoner_out,
            config=config,
            full_repo_scan=full_repo_scan,
        )
        all_findings.extend(findings)
        all_audits.extend(audits)
        ranker_inputs.append(_build_ranker_input(candidate, bundle))
        # Derive label for ranker training data.
        if any(a.verifier_outcome == VerifierOutcome.confirmed for a in audits):
            labels[candidate.candidate_id] = ("suspicious", "verifier_confirmed")
        elif all(a.verifier_outcome == VerifierOutcome.invalid_reasoning for a in audits):
            labels[candidate.candidate_id] = ("not_suspicious", "verifier_contradicted")

    # Module 5 \u2014 rank and serialize phase-0 training rows.
    scores = rank(ranker_inputs, config=config)
    score_map = {s.candidate_id: s for s in scores}
    for f in all_findings:
        candidate_id = f.finding_id.split(":", 1)[0]
        s = score_map.get(candidate_id)
        if s is not None:
            f.ranking_phase = s.ranking_phase
    serialize_examples(
        ranker_inputs,
        labels,
        config=config,
        run_id=run_meta.run_id,
        repo_id=run_meta.repo_id,
        base_ref=run_meta.base_ref,
        head_ref=run_meta.head_ref,
    )

    # Module 7 \u2014 gray-zone evaluator.
    gray_rows = evaluate_gray_zone(
        zip(all_findings, all_audits),
        config=config,
        run_id=run_meta.run_id,
        run_low_stitcher_coverage=run_meta.low_stitcher_coverage,
    )
    persist_gray_zone(gray_rows, config=config, run_id=run_meta.run_id)

    return all_findings


__all__ = ["run_modules_2_through_7"]
