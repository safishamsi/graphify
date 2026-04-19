"""Module 5 \u2014 ranker (Phase 0 heuristic).

We intentionally start with a deterministic heuristic scorer so findings
replay identically run-to-run. Phase 0 features match the plan's
``phase_0_weights`` contract:

- cross_language_seam_count
- changed_node_density
- unresolved_symbol_count
- removed_entity_references
- missing_guard_signals

The serialization layer writes Phase 0 training rows to
``<DEPOS_DATA>/intelligence/<run_id>/ranker_phase0_examples.jsonl``
after verifier labels are attached (see Module 6).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from depos.analysis.config import IntelligenceConfig
from depos.analysis.schemas import (
    RankerDiffFeatures,
    RankerExample,
    RankerInput,
    RankerScore,
)


def _score(features: RankerDiffFeatures, weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    components: dict[str, float] = {}
    # Normalize each feature to [0, 1] with saturating caps so one giant
    # diff does not blow out the scale.
    components["cross_language_seam_count"] = min(features.cross_lang_seams_on_path / 10.0, 1.0)
    components["changed_node_density"] = min(features.changed_nodes_on_path / 20.0, 1.0)
    components["unresolved_symbol_count"] = min(features.unresolved_symbols / 10.0, 1.0)
    components["removed_entity_references"] = min(features.removed_entities_referenced / 5.0, 1.0)
    components["missing_guard_signals"] = min(features.missing_guard_signals / 3.0, 1.0)
    components["graphcodebert_score"] = max(0.0, min(features.graphcodebert_score, 1.0))

    score = sum(weights.get(k, 0.0) * v for k, v in components.items())
    return score, components


def rank(inputs: Iterable[RankerInput], *, config: IntelligenceConfig) -> list[RankerScore]:
    weights = config.ranker.phase_0_weights
    phase = 0 if config.ranker.ranking_phase_override is None else config.ranker.ranking_phase_override
    scored: list[RankerScore] = []
    for ri in inputs:
        s, components = _score(ri.diff_features, weights)
        scored.append(
            RankerScore(
                candidate_id=ri.candidate_id,
                score=s,
                ranking_phase=phase,
                components=components,
            )
        )
    scored.sort(key=lambda r: (-r.score, r.candidate_id))
    return scored


def serialize_examples(
    inputs: Iterable[RankerInput],
    labels: dict[str, tuple[str, str]],  # candidate_id -> (label, label_source)
    *,
    config: IntelligenceConfig,
    run_id: str,
    repo_id: str = "",
    base_ref: str = "",
    head_ref: str = "",
) -> Path:
    out_dir = config.data_dir / config.run_output_subdir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ranker_phase0_examples.jsonl"
    phase = 0 if config.ranker.ranking_phase_override is None else config.ranker.ranking_phase_override
    with path.open("w", encoding="utf-8") as fp:
        for ri in sorted(inputs, key=lambda r: r.candidate_id):
            label = labels.get(ri.candidate_id)
            if label is None:
                continue
            example = RankerExample(
                example_id=ri.candidate_id,
                candidate_path=ri.candidate_path,
                edge_sequence=ri.edge_sequence,
                node_attrs=ri.node_attrs,
                diff_features=ri.diff_features,
                label=label[0],
                label_source=label[1],
                ranking_phase_at_creation=phase,
                repo_id=repo_id,
                base_ref=base_ref,
                head_ref=head_ref,
            )
            fp.write(example.model_dump_json() + "\n")
    return path


__all__ = ["rank", "serialize_examples"]
