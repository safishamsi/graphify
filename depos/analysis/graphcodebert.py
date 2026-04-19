"""GraphCodeBERT bundle scoring.

Scores Module 3 context bundles against a small library of structural bug
patterns. The scorer is intentionally retrieval-style: it does not try to
replace the reasoner. Instead it produces a ranking prior and an attached
pattern hint for Gemma / replay prioritization.

Output rows are plain dicts so they can be written directly to JSON or fed
into later pipeline stages without introducing new schema coupling.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


_PATTERN_LIBRARY: list[dict[str, str]] = [
    {
        "label": "auth_guard_drift",
        "text": (
            "Missing authentication or authorization guard on a public route, "
            "handler, middleware, or privileged operation."
        ),
    },
    {
        "label": "rls_policy_gap",
        "text": (
            "Database access path where row level security is missing, partially "
            "applied, or context dependent."
        ),
    },
    {
        "label": "schema_migration_drift",
        "text": (
            "Application code still references schema entities that may have been "
            "created, dropped, or reordered by migrations."
        ),
    },
    {
        "label": "queue_payload_drift",
        "text": (
            "Producer and consumer disagree about task payload fields, missing "
            "keys, extra keys, or argument contract."
        ),
    },
    {
        "label": "http_contract_mismatch",
        "text": (
            "Client call and server route disagree on path, method, shape, or "
            "wiring, causing missing endpoint or broken request flow."
        ),
    },
    {
        "label": "missing_error_handling",
        "text": (
            "Control flow lacks validation, exception handling, or defensive "
            "guarding around risky operations."
        ),
    },
]


def _bundle_text(bundle: dict[str, Any]) -> str:
    snippets = bundle.get("code_snippets", []) or []
    snippet_text = "\n\n".join(
        [
            f"FILE: {snippet.get('source_file', '')}\n"
            f"NODE: {snippet.get('node_id', '')}\n"
            f"{snippet.get('text', '')[:2500]}"
            for snippet in snippets[:4]
        ]
    )
    seams = bundle.get("cross_language_seams", []) or []
    seam_text = "\n".join(
        [
            f"{seam.get('relation', '')}: {seam.get('source', '')} -> {seam.get('target', '')}"
            for seam in seams[:10]
        ]
    )
    anchors = ", ".join(anchor.get("node_id", "") for anchor in (bundle.get("diff_anchors", []) or [])[:10])
    reads = ", ".join((bundle.get("data_reads", []) or [])[:10])
    writes = ", ".join((bundle.get("data_writes", []) or [])[:10])
    rls = ", ".join(f"{k}:{v}" for k, v in sorted((bundle.get("rls_coverage", {}) or {}).items()))
    migrations = ", ".join(f"{k}:{v}" for k, v in sorted((bundle.get("migration_state", {}) or {}).items())[:10])
    call_in = ", ".join(entry.get("node_id", "") for entry in (bundle.get("call_chain_in", []) or [])[:10])
    call_out = ", ".join(entry.get("node_id", "") for entry in (bundle.get("call_chain_out", []) or [])[:10])

    parts = [
        f"CANDIDATE_ID: {bundle.get('candidate_id', '')}",
        f"SCOPE_ID: {bundle.get('scope_id', '')}",
        f"DIFF_ANCHORS: {anchors}",
        f"CALL_CHAIN_IN: {call_in}",
        f"CALL_CHAIN_OUT: {call_out}",
        f"DATA_READS: {reads}",
        f"DATA_WRITES: {writes}",
        f"RLS: {rls}",
        f"MIGRATION_STATE: {migrations}",
        f"SEAMS:\n{seam_text}",
        f"SNIPPETS:\n{snippet_text}",
    ]
    return "\n\n".join(part for part in parts if part.strip())


def _mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    masked = last_hidden_state * mask
    denom = mask.sum(dim=1).clamp(min=1e-9)
    return masked.sum(dim=1) / denom


class GraphCodeBERTScorer:
    def __init__(
        self,
        *,
        model_name: str = "microsoft/graphcodebert-base",
        cache_dir: str | None = None,
        device: str | None = None,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.local_files_only = local_files_only
        self.device = device or self._default_device()
        self._tokenizer = None
        self._model = None
        self._pattern_rows: list[dict[str, Any]] | None = None

    def _torch(self):
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - runtime env
            raise RuntimeError(
                "GraphCodeBERT scoring requires torch/transformers. "
                'Install with: pip install -e ".[intelligence]"'
            ) from exc
        return torch

    def _default_device(self) -> str:
        try:
            torch = self._torch()
            return "cuda" if torch.cuda.is_available() else "cpu"
        except RuntimeError:
            return "cpu"

    def _load(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return
        try:
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised in runtime envs
            raise RuntimeError(
                "GraphCodeBERT scoring requires the intelligence extras. "
                'Install with: pip install -e ".[intelligence]"'
            ) from exc
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            cache_dir=self.cache_dir,
            local_files_only=self.local_files_only,
        )
        self._model = AutoModel.from_pretrained(
            self.model_name,
            cache_dir=self.cache_dir,
            local_files_only=self.local_files_only,
        )
        self._model.to(self.device)
        self._model.eval()

    def _embed(self, texts: list[str]) -> torch.Tensor:
        torch = self._torch()
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        with torch.no_grad():
            out = self._model(**encoded)
            pooled = _mean_pool(out.last_hidden_state, encoded["attention_mask"])
            return torch.nn.functional.normalize(pooled, p=2, dim=1).cpu()

    def _pattern_matrix(self) -> tuple[list[dict[str, str]], torch.Tensor]:
        torch = self._torch()
        if self._pattern_rows is not None:
            labels = [{"label": row["label"], "text": row["text"]} for row in self._pattern_rows]
            matrix = torch.tensor([row["embedding"] for row in self._pattern_rows], dtype=torch.float32)
            return labels, matrix
        labels = list(_PATTERN_LIBRARY)
        embeddings = self._embed([row["text"] for row in labels])
        self._pattern_rows = [
            {"label": row["label"], "text": row["text"], "embedding": embeddings[idx].tolist()}
            for idx, row in enumerate(labels)
        ]
        return labels, embeddings

    def score_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        torch = self._torch()
        labels, pattern_matrix = self._pattern_matrix()
        bundle_text = _bundle_text(bundle)
        bundle_embedding = self._embed([bundle_text])[0]
        sims = torch.mv(pattern_matrix, bundle_embedding)
        ordered = sorted(
            [
                {
                    "label": labels[idx]["label"],
                    "score": round(float(score), 6),
                }
                for idx, score in enumerate(sims.tolist())
            ],
            key=lambda row: (-row["score"], row["label"]),
        )
        top = ordered[0] if ordered else {"label": "", "score": 0.0}
        return {
            "bundle_id": bundle.get("bundle_id", ""),
            "candidate_id": bundle.get("candidate_id", ""),
            "scope_id": bundle.get("scope_id", ""),
            "graphcodebert_score": top["score"],
            "graphcodebert_pattern": top["label"],
            "top_patterns": ordered[:3],
            "bundle_fingerprint": hashlib.sha1(bundle_text.encode("utf-8")).hexdigest(),
        }


def score_bundles(
    bundles: Iterable[dict[str, Any]],
    *,
    model_name: str = "microsoft/graphcodebert-base",
    cache_dir: str | None = None,
    device: str | None = None,
    local_files_only: bool = False,
) -> list[dict[str, Any]]:
    scorer = GraphCodeBERTScorer(
        model_name=model_name,
        cache_dir=cache_dir,
        device=device,
        local_files_only=local_files_only,
    )
    rows = [scorer.score_bundle(bundle) for bundle in bundles]
    rows.sort(key=lambda row: (-row["graphcodebert_score"], row["bundle_id"]))
    return rows


def load_bundles(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"expected bundle list in {path}")
    return [row for row in data if isinstance(row, dict)]


def persist_scores(rows: Iterable[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(rows), indent=2), encoding="utf-8")
    return path


__all__ = ["GraphCodeBERTScorer", "load_bundles", "persist_scores", "score_bundles"]
