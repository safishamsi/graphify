"""Tests for graphify.edge_identity — schema constants and stable key helpers."""

from __future__ import annotations

from graphify.edge_identity import SCHEMA_KEY_FIELD, make_stable_key, strip_schema_key


def test_schema_key_field_constant():
    assert SCHEMA_KEY_FIELD == "key"


def test_make_stable_key_deterministic():
    k1 = make_stable_key("calls", "src/a.py", "L10")
    k2 = make_stable_key("calls", "src/a.py", "L10")
    assert k1 == k2
    assert isinstance(k1, str)
    assert k1  # non-empty


def test_make_stable_key_all_none():
    k = make_stable_key(None, None, None)
    assert isinstance(k, str)
    assert k  # non-empty — never crashes or returns empty string


def test_make_stable_key_differs_by_source_location():
    k1 = make_stable_key("calls", "src/a.py", "L10")
    k2 = make_stable_key("calls", "src/a.py", "L20")
    assert k1 != k2


def test_make_stable_key_identical_fields_match():
    k1 = make_stable_key("imports", "graphify/build.py", "L42")
    k2 = make_stable_key("imports", "graphify/build.py", "L42")
    assert k1 == k2


def test_strip_schema_key_removes_key_field():
    attrs = {"key": "calls:a.py:L1", "relation": "calls", "confidence": "EXTRACTED"}
    key_val, cleaned = strip_schema_key(attrs)
    assert key_val == "calls:a.py:L1"
    assert "key" not in cleaned
    assert cleaned["relation"] == "calls"
    assert cleaned["confidence"] == "EXTRACTED"


def test_strip_schema_key_no_key_present():
    attrs = {"relation": "imports", "confidence_score": 1.0}
    key_val, cleaned = strip_schema_key(attrs)
    assert key_val is None
    assert cleaned == attrs
    assert "key" not in cleaned


def test_strip_schema_key_does_not_mutate_input():
    attrs = {"key": "k1", "relation": "calls"}
    original = dict(attrs)
    strip_schema_key(attrs)
    assert attrs == original


# ---------------------------------------------------------------------------
# Blocker 1: delimiter-collision safety
# ---------------------------------------------------------------------------


def test_make_stable_key_no_delimiter_collision():
    # "a:b","c","d" must not hash the same as "a","b:c","d"
    k1 = make_stable_key("a:b", "c", "d")
    k2 = make_stable_key("a", "b:c", "d")
    assert k1 != k2


def test_make_stable_key_format_is_versioned():
    k = make_stable_key("calls", "a.py", "L1")
    assert k.startswith("edge:v1:")


def test_make_stable_key_none_differs_from_empty_and_unknown():
    # make_stable_key(None, None, None) must not collide with
    # make_stable_key("unknown", "", "") — None must serialize as JSON null,
    # not be normalised to "unknown"/"" before hashing.
    k_none = make_stable_key(None, None, None)
    k_defaults = make_stable_key("unknown", "", "")
    assert k_none != k_defaults
