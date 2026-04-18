"""URL normalizer unit tests (PR 1 acceptance gate)."""
from __future__ import annotations

from depos.enrichment.url_normalize import (
    DYNAMIC_URL_MAX_CONFIDENCE,
    INFERRED_METHOD_PENALTY,
    INFERRED_THRESHOLD,
    MIN_EMIT_CONFIDENCE,
    normalize_path,
    normalize_route,
    score_match,
    strip_api_prefix,
)


def test_strip_api_prefix_only_once():
    assert strip_api_prefix("/api/repos/42") == "/repos/42"
    assert strip_api_prefix("/repos/42") == "/repos/42"
    assert strip_api_prefix("/api") == "/"
    assert strip_api_prefix("") == ""


def test_normalize_path_collapses_all_dynamic_segment_styles():
    assert normalize_path("/repos/{id}") == "/repos/{*}"
    assert normalize_path("/repos/:id") == "/repos/{*}"
    assert normalize_path("/repos/[id]") == "/repos/{*}"
    assert normalize_path("/repos/{repo_id:int}") == "/repos/{*}"


def test_normalize_path_strips_query_and_trailing_slash():
    assert normalize_path("/repos/42/?foo=bar") == "/repos/42"
    assert normalize_path("/") == "/"


def test_exact_match_scores_1_0_and_emits_confirmed():
    client = normalize_route("/api/repos/{id}", method="GET", strip_api=True)
    server = normalize_route("/repos/{repo_id}", method="GET")
    result = score_match(client, server)
    assert result.score == 1.0
    assert result.match_kind == "exact"
    assert result.emit is True
    assert result.inferred is False


def test_method_inferred_applies_penalty_but_still_emits():
    client = normalize_route("/api/repos/{id}", method="GET", strip_api=True)
    server = normalize_route("/repos/{repo_id}", method="GET")
    result = score_match(client, server, client_method_inferred=True)
    assert result.score == round(1.0 - INFERRED_METHOD_PENALTY, 4)
    assert result.emit is True
    # 0.9 >= INFERRED_THRESHOLD (0.8) -> NOT inferred
    assert result.inferred is False


def test_dynamic_url_construction_capped_at_0_4_does_not_emit():
    client = normalize_route("/api/repos/{id}", method="GET", strip_api=True)
    server = normalize_route("/repos/{repo_id}", method="GET")
    result = score_match(client, server, client_is_dynamic_url=True)
    assert result.score == DYNAMIC_URL_MAX_CONFIDENCE
    assert result.match_kind == "dynamic_url"
    # 0.4 < 0.6 emit threshold
    assert result.emit is False


def test_mismatched_methods_score_zero():
    client = normalize_route("/api/repos/{id}", method="GET", strip_api=True)
    server = normalize_route("/repos/{repo_id}", method="POST")
    result = score_match(client, server)
    assert result.score == 0.0
    assert result.emit is False


def test_mismatched_segment_counts_score_zero():
    client = normalize_route("/api/repos", method="GET", strip_api=True)
    server = normalize_route("/repos/{repo_id}", method="GET")
    result = score_match(client, server)
    assert result.score == 0.0


def test_thresholds_are_consistent():
    assert MIN_EMIT_CONFIDENCE < INFERRED_THRESHOLD
    assert DYNAMIC_URL_MAX_CONFIDENCE < MIN_EMIT_CONFIDENCE


def test_root_path_normalizes_cleanly():
    assert normalize_path("/") == "/"
    client = normalize_route("/api", method="GET", strip_api=True)
    server = normalize_route("/", method="GET")
    result = score_match(client, server)
    assert result.score == 1.0
