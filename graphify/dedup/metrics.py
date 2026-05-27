from __future__ import annotations
import math
import re
import unicodedata
from collections import defaultdict
from datasketch import MinHash
def _norm(label: str) -> str:
    """Lowercase + collapse non-alphanumeric runs to space (Unicode-aware)."""
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_]+", " ", label.casefold(), flags=re.UNICODE).strip()


def _entropy(label: str) -> float:
    """Shannon entropy in bits/char of the normalised label."""
    s = _norm(label)
    if not s:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in s:
        freq[ch] += 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _shingles(text: str, k: int = 3) -> set[str]:
    """Return k-gram character shingles of text."""
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str, num_perm: int = 128) -> MinHash:
    # Strip spaces so "graph extractor" and "graphextractor" share shingles
    m = MinHash(num_perm=num_perm)
    for shingle in _shingles(text.replace(" ", "")):
        m.update(shingle.encode("utf-8"))
    return m


# Matches labels whose trailing token is a version/variant suffix:
# digits optionally followed by letters (chip SKUs: ASR1603, M1, Cortex-A55)
# or 2+ letters (codename revisions: cranelr vs cranel).
# Requires the stem to end in a letter so plain words don't accidentally match.
_VARIANT_SUFFIX = re.compile(r"^(.*[a-z])([0-9]+[a-z]*|[a-z]{2,})$")


def _is_variant_pair(a: str, b: str) -> bool:
    """True if a and b are sibling model/SKU variants (same stem, different suffix).

    Only applied to short labels (< 12 chars); long labels go through JW normally.
    """
    if a == b:
        return False
    if max(len(a), len(b)) >= 12:
        return False
    ma, mb = _VARIANT_SUFFIX.match(a), _VARIANT_SUFFIX.match(b)
    if not (ma and mb):
        return False
    return ma.group(1) == mb.group(1) and ma.group(2) != mb.group(2)


def _short_label_blocked(a: str, b: str, jw_score: float) -> bool:
    """Block fuzzy merge for short labels unless it's a same-length single-char substitution.

    Insertions/deletions on short strings (cranel/cranelr, M1/M1 Pro) produce
    high Jaro-Winkler scores due to the prefix bonus but are almost never true
    duplicates — they're abbreviations or variants.
    """
    if max(len(a), len(b)) >= 12:
        return False
    from rapidfuzz.distance import DamerauLevenshtein
    # Allow only same-length single-char substitutions (true typos like "Extractor"/"Extractar").
    # Block length-differing pairs regardless of score.
    if jw_score >= 97.0 and len(a) == len(b) and DamerauLevenshtein.distance(a, b) <= 1:
        return False
    return True

