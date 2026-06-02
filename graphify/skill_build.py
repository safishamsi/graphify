"""Generate the per-platform skill files from the canonical ``skill.md``.

``skill.md`` is the single source of truth. This module slices it by markdown
heading and recomposes the slices two ways:

* **split mode** (true skill loaders that follow sibling-file references, e.g.
  Claude Code) -> a lean ``SKILL.md`` plus on-demand ``reference/<command>.md``
  files. A ``/graphify query`` then loads ``SKILL.md`` + ``reference/query.md``
  instead of the full ~1,150-line document.
* **flatten mode** (loaders not verified to follow sibling references) -> one
  self-contained file, the slices re-inlined in their original order. This is a
  lossless round-trip of ``skill.md`` (see :func:`flatten`).

The load-bearing node-ID rule and JSON extraction contract live in Step 3 and
are moved as **verbatim slices** (substring copies, never re-typed), so the
byte-accuracy constraint from issue #1106 is satisfied structurally rather than
by being careful. ``--check`` regenerates and diffs the committed artifacts so
CI catches any drift.

Run ``python -m graphify.skill_build`` to regenerate, or ``--check`` to verify
the committed tree is in sync.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Manifest: which skill.md section goes where. Encoded as data, not a separate
# .toml, to avoid a tomllib backport dependency on Python 3.10 and to keep the
# routing testable in-process.
# ---------------------------------------------------------------------------

# H2 section title -> destination reference file (without the .md). Titles are
# matched exactly against the heading text. Any H2 not listed here raises, so a
# new section added to skill.md can never be silently dropped from the split.
H2_DESTINATION: dict[str, str] = {
    "Usage": "core",
    "What graphify is for": "core",
    "What You Must Do When Invoked": "core",  # intro only; its Step children route to extract
    "Honesty Rules": "core",
    "Interpreter guard for subcommands": "shared",  # prepended to update/query/add
    "For --update (incremental re-extraction)": "update",
    "For --cluster-only": "update",
    "For /graphify query": "query",
    "For /graphify path": "query",
    "For /graphify explain": "query",
    "For /graphify add": "add",
    "For --watch": "watch",
    "For git commit hook": "watch",
    "For native CLAUDE.md integration": "watch",
}

# Order of the on-demand reference files and the shared interpreter-guard
# preamble that each one carries (the guard's own text lists which subcommands
# need it: --update, --cluster-only, query, path, explain, add — not watch).
REFERENCE_FILES = ("extract", "update", "query", "add", "watch")
NEEDS_INTERPRETER_GUARD = {"update", "query", "add"}

# Per-reference H1 + one-line lede the generator prepends to each slice file.
REFERENCE_HEADERS: dict[str, str] = {
    "extract": (
        "# graphify build pipeline\n\n"
        "Loaded on demand by `SKILL.md` for a fresh build "
        "(a bare path, a GitHub URL, or any flag that implies extraction). "
        "Follow the steps in order; do not skip steps.\n\n"
    ),
    "update": (
        "# graphify incremental update\n\n"
        "Loaded on demand by `SKILL.md` for `--update` and `--cluster-only`. "
        "Steps 3-9 referenced below live in `reference/extract.md`.\n\n"
    ),
    "query": (
        "# graphify query / path / explain\n\n"
        "Loaded on demand by `SKILL.md` to answer questions against an "
        "existing graph.\n\n"
    ),
    "add": (
        "# graphify add\n\n"
        "Loaded on demand by `SKILL.md` for `/graphify add <url>`.\n\n"
    ),
    "watch": (
        "# graphify watch / hooks / native integration\n\n"
        "Loaded on demand by `SKILL.md` for `--watch`, the git commit hook, "
        "and native CLAUDE.md integration.\n\n"
    ),
}

# The routing table injected into the lean SKILL.md (split mode only — it is a
# generated addition, never part of skill.md, so it must not appear in flatten
# output). Placed immediately after the "What You Must Do When Invoked" intro.
ROUTING_TABLE = """\
**Where each flow lives.** Load only the reference file for the task at hand — \
do not read the others.

| If the request is… | Read and follow |
|---|---|
| a fresh build: a bare path, a GitHub URL, or any flag that implies extraction | `reference/extract.md` |
| `--update` or `--cluster-only` | `reference/update.md` |
| `/graphify query`, `path`, `explain`, or a natural-language question when a graph already exists | `reference/query.md` |
| `/graphify add <url>` | `reference/add.md` |
| `--watch`, the git commit hook, or native CLAUDE.md integration | `reference/watch.md` |

"""

# Minimal in-place adaptations applied ONLY to core segments so the lean
# SKILL.md points at reference files instead of moved sections. Kept tiny and
# explicit; --check enforces them deterministically.
CORE_REPLACEMENTS: list[tuple[str, str]] = [
    (
        "**skip Steps 1–5 entirely and jump straight to `## For /graphify query`.**",
        "**skip the build pipeline entirely and follow `reference/query.md`.**",
    ),
    (
        "run Step 0 before anything else, then continue with the resolved local path.",
        "run Step 0 in `reference/extract.md` before anything else, then continue "
        "with the resolved local path.",
    ),
    (
        "Follow these steps in order. Do not skip steps.",
        "Determine the flow from the request, then read and follow the matching "
        "reference file below. Within a reference file, follow its steps in order — "
        "do not skip steps.",
    ),
]

PACKAGE_DIR = Path(__file__).parent
SOURCE = PACKAGE_DIR / "skill.md"
CLAUDE_DIR = PACKAGE_DIR / "skill_claude"

_HEADING_RE = re.compile(r"^(#{1,6}) +(.*)$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


class Segment:
    """One heading and the text from it up to the next heading (verbatim)."""

    __slots__ = ("level", "title", "text")

    def __init__(self, level: int, title: str, text: str):
        self.level = level
        self.title = title
        self.text = text


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_body, rest) splitting a leading ``---`` block.

    The frontmatter body excludes the ``---`` fences. Reconstruct the original
    with ``"---\\n" + fm + "\\n---\\n" + rest``.
    """
    if not text.startswith("---\n"):
        return "", text
    end = text.index("\n---\n", 4)
    return text[4:end], text[end + 5:]


def parse_segments(body: str) -> list[Segment]:
    """Split ``body`` at every heading line, losslessly.

    Headings inside fenced code blocks (```` ``` ```` / ``~~~``) are ignored, so
    ``#``-comments inside bash snippets are not mistaken for markdown headings.
    Concatenating every segment's ``.text`` reproduces ``body`` byte-for-byte. A
    leading region before the first heading (e.g. a blank line) is returned as a
    level-0 segment with an empty title.
    """
    heads: list[tuple[int, int, str]] = []  # (char offset, level, title)
    in_fence = False
    fence = ""
    offset = 0
    for line in body.splitlines(keepends=True):
        stripped = line.lstrip()
        fm = _FENCE_RE.match(stripped)
        if fm:
            marker = fm.group(1)[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence = False
        elif not in_fence:
            hm = _HEADING_RE.match(line)
            if hm:
                heads.append((offset, len(hm.group(1)), hm.group(2).strip()))
        offset += len(line)

    if not heads:
        return [Segment(0, "", body)]
    segments: list[Segment] = []
    if heads[0][0] > 0:
        segments.append(Segment(0, "", body[: heads[0][0]]))
    for i, (start, level, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(body)
        segments.append(Segment(level, title, body[start:end]))
    return segments


# The one H2 whose intro stays in core but whose nested steps are the build
# pipeline and route to extract.
_INVOCATION_SECTION = "What You Must Do When Invoked"


def _route_all(segments: list[Segment]) -> list[str]:
    """Assign every segment a destination, in document order.

    H1/preamble -> core. H2 -> its mapped destination (unmapped raises). Deeper
    headings inherit the destination context of their anchor section, so the
    ``#### Part A/B/C`` blocks under Step 3 follow extract, and the ``### Step``
    blocks under ``## For /graphify query`` follow query — without relying on
    the heading text.
    """
    dests: list[str] = []
    context = "core"  # destination inherited by headings deeper than H2
    for seg in segments:
        if seg.level <= 1:
            dest = context = "core"
        elif seg.level == 2:
            try:
                mapped = H2_DESTINATION[seg.title]
            except KeyError:
                raise SystemExit(
                    f"skill_build: unmapped H2 section '## {seg.title}'. Add it to "
                    f"H2_DESTINATION in graphify/skill_build.py so the split stays complete."
                )
            if seg.title == _INVOCATION_SECTION:
                dest, context = "core", "extract"  # intro is core; steps are extract
            else:
                dest = context = mapped
        else:
            dest = context  # H3/H4 inherit their anchor section
        dests.append(dest)
    return dests


def build_artifacts() -> dict[str, str]:
    """Parse skill.md and return {relative_path: content} for the Claude split.

    Keys are POSIX-relative paths under the skill directory: ``SKILL.md`` and
    ``reference/<command>.md``.
    """
    text = SOURCE.read_text(encoding="utf-8")
    # Fail loudly if a core adaptation no longer matches skill.md: otherwise a
    # reworded source would silently leave stale "jump to ## For ..." text in the
    # lean SKILL.md pointing at sections that moved into reference files.
    for old, _ in CORE_REPLACEMENTS:
        if old not in text:
            raise SystemExit(
                "skill_build: CORE_REPLACEMENTS target not found in skill.md "
                f"(did the wording change?): {old!r}"
            )
    frontmatter, body = split_frontmatter(text)
    segments = parse_segments(body)

    buckets: dict[str, list[str]] = {k: [] for k in ("core", "shared", *REFERENCE_FILES)}
    for seg, dest in zip(segments, _route_all(segments)):
        chunk = seg.text
        if dest == "core":
            for old, new in CORE_REPLACEMENTS:
                chunk = chunk.replace(old, new)
            # Inject the routing table right after the routing intro.
            if seg.level == 2 and seg.title == "What You Must Do When Invoked":
                chunk = chunk.rstrip("\n") + "\n\n" + ROUTING_TABLE
        buckets[dest].append(chunk)

    shared_preamble = "".join(buckets["shared"])

    artifacts: dict[str, str] = {}
    artifacts["SKILL.md"] = "---\n" + frontmatter + "\n---\n" + "".join(buckets["core"])
    for name in REFERENCE_FILES:
        parts = [REFERENCE_HEADERS[name]]
        if name in NEEDS_INTERPRETER_GUARD and shared_preamble:
            parts.append(shared_preamble.rstrip("\n") + "\n\n")
        parts.append("".join(buckets[name]))
        artifacts[f"reference/{name}.md"] = "".join(parts)
    return artifacts


def flatten() -> str:
    """Reconstruct skill.md from its parsed segments (lossless round-trip).

    Used by the parity test to prove the slicer drops nothing, and as the basis
    for regenerating flatten-mode platform files in a later rollout.
    """
    text = SOURCE.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    return "---\n" + frontmatter + "\n---\n" + "".join(s.text for s in parse_segments(body))


def write_artifacts() -> list[Path]:
    """Regenerate the committed Claude split tree. Returns paths written."""
    artifacts = build_artifacts()
    written: list[Path] = []
    for rel, content in artifacts.items():
        dst = CLAUDE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
        written.append(dst)
    return written


def check() -> int:
    """Verify the committed tree matches a fresh generation. 0 ok, 1 drift."""
    if flatten() != SOURCE.read_text(encoding="utf-8"):
        print("skill_build: FAIL — flatten() is not a lossless round-trip of skill.md.", file=sys.stderr)
        return 1
    drift: list[str] = []
    for rel, content in build_artifacts().items():
        dst = CLAUDE_DIR / rel
        if not dst.exists() or dst.read_text(encoding="utf-8") != content:
            drift.append(rel)
    if drift:
        print(
            "skill_build: FAIL — these generated files are out of sync with skill.md:\n  "
            + "\n  ".join(drift)
            + "\nRun `python -m graphify.skill_build` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print("skill_build: OK — generated skill tree is in sync with skill.md.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        return check()
    written = write_artifacts()
    for p in written:
        print(f"  wrote {p.relative_to(PACKAGE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
