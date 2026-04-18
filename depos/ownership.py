"""CODEOWNERS → path → owner; cross-owner warnings for blast subgraph."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


def parse_codeowners(content: str) -> list[tuple[re.Pattern, str]]:
    """Return list of (compiled glob pattern, owner line)."""
    rules: list[tuple[re.Pattern, str]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        owners = " ".join(parts[1:])
        # Very small glob: * and ** only
        regex = (
            pattern.replace("**", "___DOUBLESTAR___")
            .replace("*", "[^/]*")
            .replace("___DOUBLESTAR___", ".*")
        )
        regex = "^" + regex.replace("/", "\\/") + "$"
        try:
            rules.append((re.compile(regex), owners))
        except re.error:
            continue
    return rules


def owner_for_path(rules: list[tuple[re.Pattern, str]], rel_path: str) -> str | None:
    posix = PurePosixPath(rel_path.replace("\\", "/")).as_posix()
    for pat, own in reversed(rules):
        if pat.search(posix):
            return own
    return None


def cross_owner_warnings(
    impacted_files: list[str],
    rules: list[tuple[re.Pattern, str]],
    *,
    root: Path | None = None,
) -> list[str]:
    owners: set[str] = set()
    for f in impacted_files:
        rel = f
        if root:
            try:
                rel = str(Path(f).resolve().relative_to(root.resolve()))
            except ValueError:
                rel = f
        o = owner_for_path(rules, rel)
        if o:
            owners.add(o)
    if len(owners) > 1:
        return [f"Multiple CODEOWNERS hits: {', '.join(sorted(owners))}"]
    return []
