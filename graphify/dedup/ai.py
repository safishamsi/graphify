from __future__ import annotations
from rapidfuzz.distance import JaroWinkler
from .metrics import _norm, _is_variant_pair, _short_label_blocked
from .core import _UF, _pick_winner, _COMMUNITY_BOOST
def _llm_tiebreak(
    candidates: list[dict],
    uf: _UF,
    communities: dict[str, int],
    *,
    backend: str,
    batch_size: int = 30,
    low: float = 75.0,
    high: float = 92.0,
) -> None:
    """Batch-resolve ambiguous pairs (score in [low, high)) via LLM."""
    try:
        from graphify.llm.core import BACKENDS, _format_backend_env_keys, _get_backend_api_key
        if backend not in BACKENDS:
            print(f"[graphify] --dedup-llm: unknown backend {backend!r}, skipping LLM tiebreaker.", flush=True)
            return
        if not _get_backend_api_key(backend):
            env_keys = _format_backend_env_keys(backend)
            print(f"[graphify] --dedup-llm: {env_keys} not set, skipping LLM tiebreaker.", flush=True)
            return
    except ImportError:
        return

    ambiguous: list[tuple[dict, dict, float]] = []
    for i, node in enumerate(candidates):
        norm_i = _norm(node.get("label", node.get("id", "")))
        for j in range(i + 1, len(candidates)):
            neighbor = candidates[j]
            if uf.find(node["id"]) == uf.find(neighbor["id"]):
                continue
            norm_j = _norm(neighbor.get("label", neighbor.get("id", "")))
            score = JaroWinkler.normalized_similarity(norm_i, norm_j) * 100
            if _is_variant_pair(norm_i, norm_j):
                continue
            if _short_label_blocked(norm_i, norm_j, score):
                continue
            c1 = communities.get(node["id"])
            c2 = communities.get(neighbor["id"])
            if (c1 is not None and c2 is not None and c1 == c2
                    and min(len(norm_i), len(norm_j)) >= 12):
                score += _COMMUNITY_BOOST
            if low <= score < high:
                ambiguous.append((node, neighbor, score))

    if not ambiguous:
        return

    try:
        from graphify.llm.core import _call_llm
    except ImportError as exc:
        # F-038: previously this silent fallback hid the fact that `_call_llm`
        # didn't exist in `graphify.llm` at all, so `--dedup-llm` was a no-op.
        # Surface the import failure so future regressions are visible.
        print(
            f"[graphify] --dedup-llm: cannot import _call_llm ({exc}); skipping LLM tiebreaker.",
            flush=True,
        )
        return

    for batch_start in range(0, len(ambiguous), batch_size):
        batch = ambiguous[batch_start : batch_start + batch_size]
        pairs_text = "\n".join(
            f"{i+1}. \"{a['label']}\" vs \"{b['label']}\""
            for i, (a, b, _) in enumerate(batch)
        )
        prompt = (
            "For each pair below, answer only 'yes' or 'no': are they the same real-world concept?\n\n"
            f"{pairs_text}\n\n"
            "Reply with one line per pair: '1. yes', '2. no', etc."
        )
        try:
            response = _call_llm(prompt, backend=backend, max_tokens=200)
            lines = response.strip().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(".", 1)
                if len(parts) != 2:
                    continue
                try:
                    idx = int(parts[0].strip()) - 1
                except ValueError:
                    continue
                if 0 <= idx < len(batch):
                    answer = parts[1].strip().lower()
                    if answer.startswith("yes"):
                        a, b, _ = batch[idx]
                        winner = _pick_winner([a, b])
                        uf.union(winner["id"], a["id"])
                        uf.union(winner["id"], b["id"])
        except Exception as exc:
            print(f"[graphify] --dedup-llm batch failed: {exc}", flush=True)
