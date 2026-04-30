"""Tests for token-aware chunking and parallel chunk execution in graphify.llm."""
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=False)
def no_tokenizer():
    """Force the chars/4 fallback so packing math is deterministic regardless
    of whether tiktoken is installed in the test environment. tiktoken's BPE
    compresses repeated/synthetic content heavily, which would make pack-size
    assertions tied to specific input sizes flaky."""
    from graphify import llm
    with patch.object(llm, "_TOKENIZER", None):
        yield


# ---- Token-aware packing -----------------------------------------------------

def test_pack_chunks_packs_small_files_together(tmp_path):
    """Many small files should land in a single chunk, not one chunk per file."""
    from graphify.llm import _pack_chunks_by_tokens

    files = []
    for i in range(20):
        f = tmp_path / f"small_{i}.py"
        f.write_text("x = 1\n")  # ~6 bytes => ~1 token
        files.append(f)

    chunks = _pack_chunks_by_tokens(files, token_budget=10_000)
    assert len(chunks) == 1
    assert sorted(chunks[0]) == sorted(files)


def test_pack_chunks_starts_new_chunk_when_budget_would_overflow(tmp_path, no_tokenizer):
    """When the next file would push the chunk past the budget, start a new chunk.

    With chars/4 fallback: each 10,000-char file = (10000+80)/4 = 2520 tokens.
    Budget 6000 fits two (5040 < 6000) but not three (7560 > 6000).
    Five files → 2/2/1 = three chunks.
    """
    from graphify.llm import _pack_chunks_by_tokens

    files = []
    for i in range(5):
        f = tmp_path / f"file_{i}.py"
        f.write_text("x" * 10_000)
        files.append(f)

    chunks = _pack_chunks_by_tokens(files, token_budget=6_000)
    sizes = [len(c) for c in chunks]
    assert sizes == [2, 2, 1], f"expected [2, 2, 1], got {sizes}"
    assert sum(sizes) == 5  # all files accounted for


def test_pack_chunks_groups_by_directory(tmp_path):
    """Files in the same directory should land in the same chunk when they fit."""
    from graphify.llm import _pack_chunks_by_tokens

    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    a1 = dir_a / "x.py"; a1.write_text("a")
    a2 = dir_a / "y.py"; a2.write_text("a")
    b1 = dir_b / "x.py"; b1.write_text("b")
    b2 = dir_b / "y.py"; b2.write_text("b")

    # Big budget — everything fits in one chunk in principle, but the order
    # within the chunk should keep dir_a's files contiguous and dir_b's
    # contiguous (not interleaved).
    chunks = _pack_chunks_by_tokens([a1, b1, a2, b2], token_budget=1_000_000)
    assert len(chunks) == 1
    chunk = chunks[0]
    a_indices = [i for i, p in enumerate(chunk) if p.parent == dir_a]
    b_indices = [i for i, p in enumerate(chunk) if p.parent == dir_b]
    assert a_indices == sorted(a_indices)
    assert b_indices == sorted(b_indices)
    # all of one directory comes before all of the other
    assert max(a_indices) < min(b_indices) or max(b_indices) < min(a_indices)


def test_pack_chunks_oversized_file_gets_its_own_chunk(tmp_path, no_tokenizer):
    """A file larger than the budget can't be split — it goes alone in a chunk."""
    from graphify.llm import _pack_chunks_by_tokens

    big = tmp_path / "big.py"; big.write_text("x" * 200_000)  # ~50k tokens (cap-bound)
    small = tmp_path / "small.py"; small.write_text("x")

    chunks = _pack_chunks_by_tokens([big, small], token_budget=1_000)
    sizes = [len(c) for c in chunks]
    # big should be alone in its own chunk; small in its own (no other file
    # to share with)
    assert sizes == [1, 1]


def test_pack_chunks_rejects_non_positive_budget(tmp_path):
    from graphify.llm import _pack_chunks_by_tokens

    f = tmp_path / "x.py"; f.write_text("a")
    with pytest.raises(ValueError):
        _pack_chunks_by_tokens([f], token_budget=0)


# ---- Tokenizer fallback ------------------------------------------------------

def test_estimate_file_tokens_uses_tiktoken_when_available(tmp_path):
    """When tiktoken is installed, the estimator should call into it for
    accurate counts rather than the chars/4 heuristic."""
    from graphify import llm

    f = tmp_path / "sample.py"
    text = "def hello():\n    return 'world'\n" * 50  # ~1500 chars
    f.write_text(text)

    # Force the tokenizer to be a mock that records calls and returns a known
    # token list, so we can assert the tiktoken path is taken.
    fake_encoder = type("E", (), {"encode": staticmethod(lambda s: [0] * 999)})()
    with patch.object(llm, "_TOKENIZER", fake_encoder):
        n = llm._estimate_file_tokens(f)
    assert n == 999 + (llm._PER_FILE_OVERHEAD_CHARS // llm._CHARS_PER_TOKEN)


def test_estimate_file_tokens_falls_back_to_chars_when_no_tokenizer(tmp_path):
    """Without tiktoken installed, the estimator falls back to chars/4."""
    from graphify import llm

    f = tmp_path / "sample.py"
    f.write_text("x" * 1_000)  # 1000 bytes

    with patch.object(llm, "_TOKENIZER", None):
        n = llm._estimate_file_tokens(f)
    # 1000 chars + 80 overhead = 1080 / 4 = 270 tokens
    assert n == (1000 + llm._PER_FILE_OVERHEAD_CHARS) // llm._CHARS_PER_TOKEN


# ---- Parallel execution ------------------------------------------------------

def _stub_chunk_result(file_count: int, idx: int) -> dict:
    """Build a deterministic fake extraction result for a chunk."""
    return {
        "nodes": [{"id": f"chunk_{idx}_node_{i}"} for i in range(file_count)],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 100 * file_count,
        "output_tokens": 50 * file_count,
    }


def test_corpus_parallel_runs_chunks_concurrently(tmp_path):
    """With max_concurrency > 1, total wall time should be ~max(chunk times),
    not the sum. Each stub extraction sleeps; we assert wall time."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(8):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    def slow_extract(chunk, **kwargs):
        time.sleep(0.3)
        return _stub_chunk_result(len(chunk), 0)

    with patch("graphify.llm.extract_files_direct", side_effect=slow_extract):
        t0 = time.time()
        # Force 4 chunks of 2 files each by setting a tight token budget.
        result = extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=2, max_concurrency=4
        )
        elapsed = time.time() - t0

    # 4 chunks × 0.3s sequential = 1.2s. Parallel with 4 workers should land near 0.3-0.5s.
    assert elapsed < 1.0, f"expected parallel speedup, took {elapsed:.2f}s"
    assert len(result["nodes"]) == 8


def test_corpus_parallel_sequential_when_max_concurrency_is_one(tmp_path):
    """max_concurrency=1 should run sequentially (no thread pool)."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(3):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    call_order = []

    def record(chunk, **kwargs):
        call_order.append(tuple(p.name for p in chunk))
        return _stub_chunk_result(len(chunk), len(call_order))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=1, max_concurrency=1
        )

    # Sequential => we see calls in submission order
    assert call_order == [("f0.py",), ("f1.py",), ("f2.py",)]


def test_corpus_parallel_continues_after_chunk_failure(tmp_path, capsys):
    """A single chunk raising should be logged but not abort the run.
    Other chunks' results should still be merged."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(4):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    call_count = {"n": 0}

    def maybe_fail(chunk, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated API error")
        return _stub_chunk_result(len(chunk), call_count["n"])

    with patch("graphify.llm.extract_files_direct", side_effect=maybe_fail):
        result = extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=1, max_concurrency=1
        )

    # 4 chunks dispatched, 1 failed → 3 chunks contributed nodes
    assert len(result["nodes"]) == 3
    err = capsys.readouterr().err
    assert "failed" in err and "simulated API error" in err


def test_corpus_parallel_legacy_mode_when_token_budget_is_none(tmp_path):
    """token_budget=None should fall back to legacy fixed-count chunking."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(45):
        f = tmp_path / f"f{i}.py"; f.write_text("x")
        files.append(f)

    chunks_seen = []

    def record(chunk, **kwargs):
        chunks_seen.append(len(chunk))
        return _stub_chunk_result(len(chunk), len(chunks_seen))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(
            files, backend="kimi", token_budget=None, chunk_size=20, max_concurrency=1
        )

    # 45 files / chunk_size=20 = 3 chunks of 20, 20, 5
    assert chunks_seen == [20, 20, 5]


def test_corpus_parallel_token_budget_default_packs_files(tmp_path):
    """With the default token_budget, many tiny files pack into one chunk."""
    from graphify.llm import extract_corpus_parallel

    files = []
    for i in range(50):
        f = tmp_path / f"f{i}.py"; f.write_text("x = 1\n")
        files.append(f)

    chunks_seen = []

    def record(chunk, **kwargs):
        chunks_seen.append(len(chunk))
        return _stub_chunk_result(len(chunk), len(chunks_seen))

    with patch("graphify.llm.extract_files_direct", side_effect=record):
        extract_corpus_parallel(files, backend="kimi", max_concurrency=1)

    # 50 tiny files at default 60k token budget should pack into 1 chunk
    assert len(chunks_seen) == 1
    assert chunks_seen[0] == 50


# ---- Adaptive retry on truncation -------------------------------------------

def _stub_with_finish(file_count: int, finish_reason: str = "stop") -> dict:
    """Build a stub extraction result with a controllable finish_reason."""
    return {
        "nodes": [{"id": f"n_{i}"} for i in range(file_count)],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 100 * file_count,
        "output_tokens": 50 * file_count,
        "finish_reason": finish_reason,
    }


def test_adaptive_retry_returns_directly_when_not_truncated(tmp_path):
    """No retry when finish_reason='stop' — single call, result passes through."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="stop")

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [4], f"expected 1 call of 4 files, got {calls}"
    assert len(result["nodes"]) == 4


def test_adaptive_retry_splits_when_finish_reason_length(tmp_path):
    """finish_reason='length' triggers split-in-half. Both halves succeed
    on the second try (mocked) and results merge."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) == 4 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [4, 2, 2], f"expected [4, 2, 2], got {calls}"
    assert len(result["nodes"]) == 4
    assert result["finish_reason"] == "stop"


def test_adaptive_retry_recurses_for_persistent_truncation(tmp_path):
    """When even the half-chunk truncates, split again. With 8 files and a
    truncation cutoff at >2 files, splits 8 → 4 → 2 (4 leaves of 2)."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(8)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) > 2 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    # Tree: 8 (trunc) → 4 + 4 (both trunc) → 2+2+2+2 (all stop)
    # Total calls: 1 + 2 + 4 = 7
    assert sorted(calls) == [2, 2, 2, 2, 4, 4, 8]
    assert len(result["nodes"]) == 8


def test_adaptive_retry_caps_at_max_depth(tmp_path, capsys):
    """If everything truncates, retries stop at max_depth — partial result
    kept with a warning, no infinite loop."""
    from graphify.llm import _extract_with_adaptive_retry

    files = [tmp_path / f"f{i}.py" for i in range(8)]
    for f in files:
        f.write_text("x")

    calls = []

    def always_truncate(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="length")

    with patch("graphify.llm.extract_files_direct", side_effect=always_truncate):
        _extract_with_adaptive_retry(
            files, backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=2
        )

    # max_depth=2 bounds the tree: root + 2 + 4 = 7 calls maximum
    assert len(calls) <= 7, f"recursion not bounded — {len(calls)} calls"
    err = capsys.readouterr().err
    assert "still truncated" in err


def test_adaptive_retry_single_file_truncation_does_not_recurse(tmp_path, capsys):
    """A single file that truncates can't be split further — surface a
    warning and return what we got. No infinite loop."""
    from graphify.llm import _extract_with_adaptive_retry

    f = tmp_path / "huge.py"; f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        return _stub_with_finish(len(chunk), finish_reason="length")

    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        _extract_with_adaptive_retry(
            [f], backend="kimi", api_key=None, model=None, root=tmp_path, max_depth=3
        )

    assert calls == [1], f"single-file chunk recursed; calls = {calls}"
    err = capsys.readouterr().err
    assert "single-file chunk" in err and "truncated" in err


def test_corpus_parallel_uses_adaptive_retry(tmp_path):
    """End-to-end: extract_corpus_parallel routes through adaptive retry,
    so a chunk that truncates gets split and merged transparently before
    on_chunk_done fires."""
    from graphify.llm import extract_corpus_parallel

    files = [tmp_path / f"f{i}.py" for i in range(4)]
    for f in files:
        f.write_text("x")

    calls = []

    def stub(chunk, **kwargs):
        calls.append(len(chunk))
        finish = "length" if len(chunk) == 4 else "stop"
        return _stub_with_finish(len(chunk), finish_reason=finish)

    chunk_done_args = []
    with patch("graphify.llm.extract_files_direct", side_effect=stub):
        result = extract_corpus_parallel(
            files,
            backend="kimi",
            token_budget=None,
            chunk_size=4,
            max_concurrency=1,
            on_chunk_done=lambda i, t, r: chunk_done_args.append((i, t, len(r["nodes"]))),
        )

    # Adaptive retry runs INSIDE _run_one: 4 → 2 + 2 = 3 underlying API calls
    assert calls == [4, 2, 2]
    # User-visible: 1 chunk completion (the merged result)
    assert len(chunk_done_args) == 1
    assert chunk_done_args[0] == (0, 1, 4)
    assert len(result["nodes"]) == 4
