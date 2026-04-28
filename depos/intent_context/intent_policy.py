"""Load and validate ``.depos/intent.yaml`` tier policy (policy-as-code).

``tier_rules`` are evaluated in array order — first matching ``glob`` wins.

Path matching supports ``/``-separated POSIX paths and ``**`` (multi-segment), in
addition to single-segment ``*`` / ``?`` per ``fnmatch``.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from depos.intent_context.schemas import IntentTier, TierSource


_VALID_TIERS = frozenset({"P0", "P1", "P2"})


def _coerce_tier(raw: Any, *, where: str) -> IntentTier:
    if raw is None:
        raise ValueError(f"{where}: tier is required")
    s = str(raw).strip().upper()
    if s not in _VALID_TIERS:
        raise ValueError(f"{where}: invalid tier {raw!r}; expected P0, P1, or P2")
    return s  # type: ignore[return-value]


@dataclass
class IntentTierRuleRow:
    glob: str
    tier: IntentTier


@dataclass
class IntentPolicy:
    default_tier: IntentTier
    tier_rules: list[IntentTierRuleRow]
    binding_globs: list[str]
    intent_schema_policy: int | None = None


def match_path_glob(relpath_posix: str, pattern: str) -> bool:
    """Match ``relpath_posix`` against ``pattern`` (POSIX, ``**`` crosses ``/``)."""
    r = (relpath_posix.replace("\\", "/")).removeprefix("./")
    pat = pattern.replace("\\", "/").removeprefix("./")
    if "**" not in pat:
        return fnmatch(r, pat)

    pa = [x for x in r.split("/") if x != ""]
    segs = [x for x in pat.split("/") if x != ""]

    def rec(pi: int, si: int) -> bool:
        if si >= len(segs):
            return pi >= len(pa)
        seg = segs[si]
        if seg == "**":
            # Zero path segments consumed
            if rec(pi, si + 1):
                return True
            # Or consume one segment and recurse with same **
            return pi < len(pa) and rec(pi + 1, si)
        if pi >= len(pa):
            return False
        if not fnmatch(pa[pi], seg):
            return False
        return rec(pi + 1, si + 1)

    return rec(0, 0)


def load_intent_policy(repo_root: Path) -> tuple[IntentPolicy, list[str]]:
    """Parse ``intent.yaml``. Missing file → default Tier P2, empty rules."""
    warnings: list[str] = []
    path = repo_root / ".depos" / "intent.yaml"
    if not path.is_file():
        return (
            IntentPolicy(
                default_tier="P2",
                tier_rules=[],
                binding_globs=[],
                intent_schema_policy=None,
            ),
            warnings,
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    data: dict[str, Any] = {}
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            data = loaded
    except Exception as e:
        warnings.append(f"intent.yaml: parse error ({e}); using defaults")
        return (
            IntentPolicy(
                default_tier="P2",
                tier_rules=[],
                binding_globs=[],
                intent_schema_policy=None,
            ),
            warnings,
        )

    isp = data.get("intent_schema_policy")
    intent_schema_policy = int(isp) if isinstance(isp, int) else None

    try:
        default_tier = _coerce_tier(data.get("default_tier", "P2"), where="default_tier")
    except ValueError as e:
        warnings.append(str(e))
        default_tier = "P2"

    tier_rules: list[IntentTierRuleRow] = []
    rules_raw = data.get("tier_rules") or []
    if rules_raw is not None and not isinstance(rules_raw, list):
        warnings.append("tier_rules: must be a list; ignoring")
        rules_raw = []
    if isinstance(rules_raw, list):
        for i, row in enumerate(rules_raw):
            if not isinstance(row, dict):
                warnings.append(f"tier_rules[{i}]: must be an object; skipping entry")
                continue
            glo = row.get("glob")
            if not glo or not isinstance(glo, str):
                warnings.append(f"tier_rules[{i}]: missing or invalid glob")
                continue
            try:
                tt = _coerce_tier(row.get("tier"), where=f"tier_rules[{i}].tier")
            except ValueError as e:
                warnings.append(str(e))
                continue
            tier_rules.append(IntentTierRuleRow(glob=glo.strip(), tier=tt))

    binding_raw = data.get("binding_globs") or []
    binding_globs: list[str] = []
    if isinstance(binding_raw, list):
        binding_globs = [str(x).strip() for x in binding_raw if x]
    elif binding_raw:
        warnings.append("binding_globs: must be a list; ignoring")

    return (
        IntentPolicy(
            default_tier=default_tier,
            tier_rules=tier_rules,
            binding_globs=binding_globs,
            intent_schema_policy=intent_schema_policy,
        ),
        warnings,
    )


def policy_tier_for_path(relpath_posix: str, policy: IntentPolicy) -> tuple[IntentTier, TierSource]:
    """First matching ``tier_rules`` wins; otherwise ``default_tier``."""
    for rule in policy.tier_rules:
        if match_path_glob(relpath_posix, rule.glob):
            return rule.tier, "policy_glob"
    return policy.default_tier, "default"
