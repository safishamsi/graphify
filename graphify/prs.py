"""graphify prs — graph-aware PR dashboard.

Fast terminal overview of open PRs with CI/review state, worktree mapping,
and optional graph-impact analysis (which communities a PR touches) and
Opus-powered triage ranking.

Usage:
  graphify prs                   # dashboard of all open PRs
  graphify prs <number>          # deep dive on one PR
  graphify prs --triage          # Opus ranks your review queue
  graphify prs --worktrees       # show worktree → branch → PR mapping
  graphify prs --conflicts       # PRs sharing graph communities (merge-order risk)
  graphify prs --base <branch>   # filter to PRs targeting this base (default: v8)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── ANSI colours ─────────────────────────────────────────────────────────────

_NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")

def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t: str) -> str:   return _c("32", t)
def red(t: str) -> str:     return _c("31", t)
def yellow(t: str) -> str:  return _c("33", t)
def cyan(t: str) -> str:    return _c("36", t)
def bold(t: str) -> str:    return _c("1",  t)
def dim(t: str) -> str:     return _c("2",  t)
def magenta(t: str) -> str: return _c("35", t)

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def _pad(s: str, width: int) -> str:
    """Pad an ANSI-colored string to visible width (strips escape codes for length calc)."""
    visible_len = len(_ANSI_RE.sub("", s))
    return s + " " * max(0, width - visible_len)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PRInfo:
    number: int
    title: str
    branch: str
    base_branch: str
    author: str
    is_draft: bool
    review_decision: str        # APPROVED | CHANGES_REQUESTED | ""
    ci_status: str              # SUCCESS | FAILURE | PENDING | NONE
    updated_at: datetime
    expected_base: str = "main"  # set by fetch_prs via _detect_default_branch
    worktree_path: str | None = None
    # Graph impact — populated when graph.json exists
    communities_touched: list[int] = field(default_factory=list)
    nodes_affected: int = 0
    files_changed: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return _classify(self, self.expected_base)

    @property
    def days_old(self) -> int:
        return (datetime.now(timezone.utc) - self.updated_at).days

    @property
    def blast_radius(self) -> str:
        if not self.nodes_affected:
            return ""
        n = self.nodes_affected
        c = len(self.communities_touched)
        return f"{n} node{'s' if n != 1 else ''} / {c} communit{'ies' if c != 1 else 'y'}"


# ── Classification ────────────────────────────────────────────────────────────

_STATUS_ORDER = ["WRONG-BASE", "CI-FAIL", "CHANGES-REQ", "DRAFT", "STALE", "PENDING", "APPROVED", "READY"]
_STALE_DAYS = 14


def _classify(pr: "PRInfo", base: str = "v8") -> str:
    if pr.base_branch != base:
        return "WRONG-BASE"
    if pr.ci_status == "FAILURE":
        return "CI-FAIL"
    if pr.review_decision == "CHANGES_REQUESTED":
        return "CHANGES-REQ"
    if pr.is_draft:
        return "DRAFT"
    if pr.days_old >= _STALE_DAYS:
        return "STALE"
    if pr.review_decision == "APPROVED":
        return "APPROVED"
    if pr.ci_status == "PENDING":
        return "PENDING"
    return "READY"


def _status_color(status: str) -> str:
    return {
        "READY":       green(status),
        "APPROVED":    bold(green(status)),
        "CI-FAIL":     red(status),
        "CHANGES-REQ": red(status),
        "WRONG-BASE":  dim(status),
        "STALE":       dim(status),
        "DRAFT":       yellow(status),
        "PENDING":     yellow(status),
    }.get(status, status)


def _ci_icon(status: str) -> str:
    return {"SUCCESS": green("✓"), "FAILURE": red("✗"), "PENDING": yellow("…"), "NONE": dim("–")}.get(status, "?")


# ── GitHub data fetching ──────────────────────────────────────────────────────

def _gh(*args: str) -> list | dict | None:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def _detect_default_branch(repo: str | None = None) -> str:
    """Auto-detect the repo's default branch via gh, then git, then fall back to 'main'."""
    # Try gh first — works for any repo, not just the current directory
    args = ["repo", "view", "--json", "defaultBranchRef"]
    if repo:
        args += ["--repo", repo]
    data = _gh(*args)
    if data and data.get("defaultBranchRef", {}).get("name"):
        return data["defaultBranchRef"]["name"]
    # Fall back to git symbolic-ref for the current repo
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            # refs/remotes/origin/main → main
            ref = result.stdout.strip()
            return ref.split("/")[-1] if ref else "main"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"


_CI_FAILURE_CONCLUSIONS = frozenset({"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"})


def _parse_ci(rollup: list) -> str:
    if not rollup:
        return "NONE"
    conclusions = {r.get("conclusion") for r in rollup if r.get("conclusion")}
    if conclusions & _CI_FAILURE_CONCLUSIONS:
        return "FAILURE"
    statuses = {r.get("status") for r in rollup}
    if "IN_PROGRESS" in statuses or "QUEUED" in statuses:
        return "PENDING"
    if "SUCCESS" in conclusions:
        return "SUCCESS"
    return "NONE"


def fetch_prs(repo: str | None = None, base: str | None = None, limit: int = 50) -> list[PRInfo]:
    resolved_base = base or _detect_default_branch(repo)
    args = [
        "pr", "list", "--state", "open", "--limit", str(limit),
        "--json", "number,title,headRefName,baseRefName,author,isDraft,"
                  "reviewDecision,statusCheckRollup,updatedAt",
    ]
    if repo:
        args += ["--repo", repo]

    raw = _gh(*args)
    if raw is None:
        raise RuntimeError("gh CLI not found or not authenticated. Run: gh auth login")

    prs = []
    for item in raw:
        updated = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))
        prs.append(PRInfo(
            number=item["number"],
            title=item["title"],
            branch=item["headRefName"],
            base_branch=item["baseRefName"],
            author=item["author"]["login"] if item.get("author") else "?",
            is_draft=item.get("isDraft", False),
            review_decision=item.get("reviewDecision") or "",
            ci_status=_parse_ci(item.get("statusCheckRollup") or []),
            updated_at=updated,
            expected_base=resolved_base,
        ))
    return prs


def fetch_pr_files(number: int, repo: str | None = None) -> list[str]:
    args = ["pr", "diff", str(number), "--name-only"]
    if repo:
        args += ["--repo", repo]
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        return [l.strip() for l in result.stdout.splitlines() if l.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ── Graph-native impact (used by MCP tools — works on nx.Graph directly) ─────

def _path_match(graph_src: str, pr_file: str) -> bool:
    """True if graph_src and pr_file refer to the same file (path-boundary safe)."""
    if graph_src == pr_file:
        return True
    return graph_src.endswith("/" + pr_file) or pr_file.endswith("/" + graph_src)


def compute_pr_impact(files: list[str], G: "nx.Graph") -> tuple[list[int], int]:
    """Return (communities_touched, nodes_affected) for a set of changed files.

    Builds a file→(communities, count) index first so lookup is O(nodes + files)
    rather than O(nodes × files).
    """
    # Build index once
    file_comms: dict[str, set[int]] = {}
    file_count: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        src = data.get("source_file") or ""
        if not src:
            continue
        if src not in file_comms:
            file_comms[src] = set()
            file_count[src] = 0
        c = data.get("community")
        if c is not None:
            file_comms[src].add(int(c))
        file_count[src] += 1

    comms: set[int] = set()
    nodes = 0
    matched: set[str] = set()
    for f in files:
        for src, src_comms in file_comms.items():
            if src not in matched and _path_match(src, f):
                comms |= src_comms
                nodes += file_count[src]
                matched.add(src)
    return sorted(comms), nodes


def format_prs_text(prs: list["PRInfo"], base: str) -> str:
    """Plain-text PR summary for MCP output (no ANSI)."""
    actionable = [p for p in prs if p.base_branch == base]
    wrong = len(prs) - len(actionable)
    lines = [f"Open PRs targeting {base}: {len(actionable)}  ({wrong} on wrong base, not shown)\n"]
    for p in sorted(actionable, key=lambda x: (_STATUS_ORDER.index(x.status) if x.status in _STATUS_ORDER else 99, x.days_old)):
        impact = f"  blast_radius={p.blast_radius}" if p.blast_radius else ""
        lines.append(
            f"#{p.number} [{p.status}] CI={p.ci_status} review={p.review_decision or 'none'} "
            f"age={p.days_old}d author={p.author}{impact}\n  {p.title}"
        )
    return "\n\n".join(lines)


# ── Worktree mapping ──────────────────────────────────────────────────────────

def fetch_worktrees() -> dict[str, str]:
    """Returns {branch: worktree_path}."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    mapping: dict[str, str] = {}
    current_path = None
    for line in result.stdout.splitlines():
        if not line:
            current_path = None  # blank line = record separator; reset to avoid leaking across detached HEADs
        elif line.startswith("worktree "):
            current_path = line[9:]
        elif line.startswith("branch refs/heads/") and current_path:
            mapping[line[18:]] = current_path
    return mapping


# ── Graph impact analysis ─────────────────────────────────────────────────────

def _load_graph_json(graph_path: Path) -> dict | None:
    if not graph_path.exists():
        return None
    from graphify.security import check_graph_file_size_cap
    try:
        check_graph_file_size_cap(graph_path)
        return json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def build_community_labels(data: dict, top_n: int = 4) -> dict[int, list[str]]:
    """Return {community_id: [top_labels]} extracted from graph node data."""
    comm_labels: dict[int, list[str]] = defaultdict(list)
    for node in data.get("nodes", []):
        c = node.get("community")
        if c is None:
            continue
        label = node.get("label") or node.get("id") or ""
        if label:
            comm_labels[int(c)].append(label)
    return {c: labels[:top_n] for c, labels in comm_labels.items()}


def attach_graph_impact(
    prs: list[PRInfo], graph_path: Path, repo: str | None = None
) -> dict[int, list[str]]:
    """Fetch PR file lists concurrently, compute graph impact, return community labels."""
    data = _load_graph_json(graph_path)
    if not data:
        return {}

    # Build file → {community, node_count} index
    file_to_communities: dict[str, set[int]] = {}
    file_to_nodes: dict[str, int] = {}
    for node in data.get("nodes", []):
        src = node.get("source_file") or ""
        if not src:
            continue
        comm = node.get("community")
        if src not in file_to_communities:
            file_to_communities[src] = set()
            file_to_nodes[src] = 0
        if comm is not None:
            file_to_communities[src].add(int(comm))
        file_to_nodes[src] += 1

    # Fetch diffs concurrently — gh pr diff is the bottleneck (network I/O)
    actionable = [pr for pr in prs if pr.status != "WRONG-BASE"]
    workers = min(8, len(actionable)) if actionable else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_pr = {
            pool.submit(fetch_pr_files, pr.number, repo): pr
            for pr in actionable
        }
        for fut in as_completed(future_to_pr):
            pr = future_to_pr[fut]
            try:
                files = fut.result()
            except Exception:
                files = []
            pr.files_changed = files

            comms: set[int] = set()
            nodes = 0
            matched: set[str] = set()
            for f in files:
                for gf, gcomms in file_to_communities.items():
                    if gf not in matched and _path_match(gf, f):
                        comms |= gcomms
                        nodes += file_to_nodes.get(gf, 0)
                        matched.add(gf)
            pr.communities_touched = sorted(comms)
            pr.nodes_affected = nodes

    return build_community_labels(data)


# ── Dashboard rendering ───────────────────────────────────────────────────────

def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def render_dashboard(prs: list[PRInfo], base: str = "v8", show_wrong_base: bool = False) -> None:
    actionable = [p for p in prs if p.base_branch == base]
    wrong_base = [p for p in prs if p.base_branch != base]

    # Sort: READY first, then by status order, then by recency
    actionable.sort(key=lambda p: (_STATUS_ORDER.index(p.status) if p.status in _STATUS_ORDER else 99, p.days_old))

    print()
    print(bold(f"  graphify prs  ·  base: {base}  ·  {len(actionable)} PRs"))
    print()

    if not actionable:
        print(dim("  No open PRs targeting this base branch."))
    else:
        # Header
        print(f"  {'#':>4}  {'CI':2}  {'STATUS':13}  {'UPDATED':8}  {'IMPACT':22}  TITLE")
        print(f"  {'─'*4}  {'─'*2}  {'─'*13}  {'─'*8}  {'─'*22}  {'─'*40}")

        for pr in actionable:
            status_str = _pad(_status_color(pr.status), 13)
            ci_str = _ci_icon(pr.ci_status)
            age = f"{pr.days_old}d" if pr.days_old > 0 else "today"
            impact = _pad(dim(_truncate(pr.blast_radius, 22)), 22) if pr.blast_radius else _pad(dim("–"), 22)
            wt = f" {cyan('⬡')}" if pr.worktree_path else "  "
            draft = dim(" [draft]") if pr.is_draft else ""
            title = _truncate(pr.title, 52)
            num = _pad(bold(f"#{pr.number}"), 6)
            print(f"  {num}{wt}  {ci_str}  {status_str}  {age:>6}   {impact}  {title}{draft}")

    # Summary line
    by_status: dict[str, int] = {}
    for p in actionable:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    parts = []
    if by_status.get("READY"):      parts.append(green(f"{by_status['READY']} ready"))
    if by_status.get("APPROVED"):   parts.append(bold(green(f"{by_status['APPROVED']} approved")))
    if by_status.get("PENDING"):    parts.append(yellow(f"{by_status['PENDING']} pending CI"))
    if by_status.get("CI-FAIL"):    parts.append(red(f"{by_status['CI-FAIL']} CI failing"))
    if by_status.get("CHANGES-REQ"):parts.append(red(f"{by_status['CHANGES-REQ']} changes requested"))
    if by_status.get("DRAFT"):      parts.append(yellow(f"{by_status['DRAFT']} draft"))
    if by_status.get("STALE"):      parts.append(dim(f"{by_status['STALE']} stale"))

    if wrong_base:
        parts.append(dim(f"{len(wrong_base)} wrong base"))

    print()
    print(f"  {' · '.join(parts)}")
    print()

    if wrong_base and show_wrong_base:
        print(dim(f"  ── {len(wrong_base)} PRs targeting wrong base ──"))
        for pr in sorted(wrong_base, key=lambda p: p.number, reverse=True):
            print(dim(f"  #{pr.number:4}  base={pr.base_branch:12}  {_truncate(pr.title, 60)}"))
        print()


def render_worktrees(prs: list[PRInfo], worktrees: dict[str, str]) -> None:
    print()
    print(bold("  Worktrees"))
    print()
    if not worktrees:
        print(dim("  No active worktrees found."))
        print()
        return

    pr_by_branch = {p.branch: p for p in prs}
    for branch, path in sorted(worktrees.items()):
        pr = pr_by_branch.get(branch)
        if pr:
            status = _status_color(pr.status)
            print(f"  {cyan(path)}")
            print(f"    {dim('branch:')} {branch}  →  PR {bold(f'#{pr.number}')}  [{status}]  {_truncate(pr.title, 50)}")
        else:
            print(f"  {cyan(path)}")
            print(f"    {dim('branch:')} {branch}  {dim('(no open PR)')}")
        print()


def render_conflicts(
    prs: list[PRInfo],
    base: str = "v8",
    community_labels: dict[int, list[str]] | None = None,
) -> None:
    actionable = [p for p in prs if p.base_branch == base and p.communities_touched]
    if not actionable:
        print(dim("\n  No graph impact data — run with a valid graph.json to detect conflicts.\n"))
        return

    # Build community → [PRs] map
    comm_to_prs: dict[int, list[PRInfo]] = {}
    for pr in actionable:
        for c in pr.communities_touched:
            comm_to_prs.setdefault(c, []).append(pr)

    conflicts = {c: ps for c, ps in comm_to_prs.items() if len(ps) > 1}
    if not conflicts:
        print(green("\n  No community overlap between open PRs — safe to merge in any order.\n"))
        return

    print()
    print(bold("  Community conflicts (PRs sharing the same graph community)"))
    print()
    labels = community_labels or {}
    for comm, ps in sorted(conflicts.items(), key=lambda x: -len(x[1])):
        comm_label_str = ""
        if comm in labels and labels[comm]:
            comm_label_str = dim("  — " + ", ".join(labels[comm]))
        print(f"  {yellow(f'Community {comm}')}{comm_label_str}  ({len(ps)} PRs overlap)")
        for pr in ps:
            print(f"    #{pr.number:4}  {_pad(_status_color(pr.status), 13)}  {_truncate(pr.title, 55)}")
        print()


def render_pr_detail(pr: PRInfo, repo: str | None = None) -> None:
    print()
    print(bold(f"  PR #{pr.number}  ·  {_status_color(pr.status)}"))
    print(f"  {pr.title}")
    print()
    print(f"  {dim('branch:')}  {pr.branch}  →  {pr.base_branch}")
    print(f"  {dim('author:')}  {pr.author}")
    print(f"  {dim('updated:')} {pr.days_old}d ago")
    print(f"  {dim('CI:')}      {_ci_icon(pr.ci_status)} {pr.ci_status}")
    if pr.review_decision:
        print(f"  {dim('review:')} {pr.review_decision}")
    if pr.worktree_path:
        print(f"  {dim('worktree:')} {cyan(pr.worktree_path)}")
    if pr.blast_radius:
        print()
        print(f"  {bold('Graph impact:')}  {pr.blast_radius}")
        print(f"  {dim('communities:')} {pr.communities_touched}")
        if pr.files_changed:
            print(f"  {dim('files changed:')} {len(pr.files_changed)}")
            for f in pr.files_changed[:10]:
                print(f"    {dim(f)}")
            if len(pr.files_changed) > 10:
                print(dim(f"    … and {len(pr.files_changed) - 10} more"))
    print()


# ── Triage (multi-backend) ────────────────────────────────────────────────────

# Best model per backend for reasoning tasks (different from extraction defaults)
_TRIAGE_MODEL_DEFAULTS: dict[str, str] = {
    "claude": "claude-opus-4-7",
    "kimi":   "kimi-k2.6",
    "openai": "gpt-4.1-mini",
    "gemini": "gemini-3-flash-preview",
}


def _resolve_triage_backend() -> tuple[str, str]:
    """Return (backend, model) using GRAPHIFY_TRIAGE_BACKEND or first available key."""
    from graphify.llm import BACKENDS, _get_backend_api_key, _default_model_for_backend

    explicit = os.environ.get("GRAPHIFY_TRIAGE_BACKEND", "").strip()
    if explicit in BACKENDS:
        model = (os.environ.get("GRAPHIFY_TRIAGE_MODEL")
                 or _TRIAGE_MODEL_DEFAULTS.get(explicit)
                 or _default_model_for_backend(explicit))
        return explicit, model

    for b in ("claude", "kimi", "openai", "gemini"):
        if _get_backend_api_key(b):
            model = (os.environ.get("GRAPHIFY_TRIAGE_MODEL")
                     or _TRIAGE_MODEL_DEFAULTS.get(b)
                     or _default_model_for_backend(b))
            return b, model

    import shutil
    if shutil.which("claude"):
        return "claude-cli", "claude-code-plan"

    return "ollama", _default_model_for_backend("ollama")


def triage_with_opus(prs: list[PRInfo], base: str) -> None:
    try:
        from graphify.llm import BACKENDS, _get_backend_api_key
    except ImportError:
        print(red("  graphify.llm not available — cannot run triage."), file=sys.stderr)
        sys.exit(1)

    candidates = [p for p in prs if p.base_branch == base and p.status not in ("WRONG-BASE", "STALE")]
    if not candidates:
        print(dim("  No actionable PRs to triage."))
        return

    lines = []
    for pr in candidates:
        impact = f", blast_radius={pr.blast_radius}" if pr.blast_radius else ""
        lines.append(
            f"PR #{pr.number} [{pr.status}] CI={pr.ci_status} review={pr.review_decision or 'none'} "
            f"age={pr.days_old}d author={pr.author}{impact}\n  title: {pr.title}"
        )

    prompt = (
        "You are a senior engineer helping triage a PR review queue. "
        "Given these open PRs, rank them by review priority for the repo maintainer. "
        "For each PR give: priority number, one sentence on what action to take and why. "
        "Be direct and specific. Format each as: #<number> — <action>.\n\n"
        + "\n\n".join(lines)
    )

    try:
        backend, model = _resolve_triage_backend()
    except Exception as e:
        print(red(f"  Could not resolve triage backend: {e}"), file=sys.stderr)
        sys.exit(1)

    print()
    print(bold("  Triage") + dim(f" ({backend} / {model})"))
    print()

    try:
        if backend == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=_get_backend_api_key("claude"))
            with client.messages.stream(
                model=model, max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                print("  ", end="", flush=True)
                for text in stream.text_stream:
                    print(text.replace("\n", "\n  "), end="", flush=True)
            print("\n")

        elif backend in ("kimi", "openai", "gemini", "ollama"):
            from openai import OpenAI
            cfg = BACKENDS[backend]
            api_key = _get_backend_api_key(backend) or "ollama"
            client = OpenAI(api_key=api_key, base_url=cfg.get("base_url", ""))
            with client.chat.completions.create(
                model=model, max_tokens=1024, stream=True,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                print("  ", end="", flush=True)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        print(delta.replace("\n", "\n  "), end="", flush=True)
            print("\n")

        elif backend == "claude-cli":
            import subprocess as _sp
            proc = _sp.run(
                ["claude", "-p", "--no-session-persistence"],
                input=prompt, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode != 0:
                print(red(f"  claude -p failed: {proc.stderr.strip()[:300]}"), file=sys.stderr)
            else:
                try:
                    result = json.loads(proc.stdout).get("result") or proc.stdout
                except json.JSONDecodeError:
                    result = proc.stdout
                for line in result.splitlines():
                    print(f"  {line}")
                print()

    except Exception as e:
        print(f"\n\n  {red(f'Triage failed: {e}')}", file=sys.stderr)


# ── Entry point ───────────────────────────────────────────────────────────────

def cmd_prs(argv: list[str]) -> None:
    base: str | None = None  # auto-detected from repo if not given
    repo: str | None = None
    do_triage = False
    do_worktrees = False
    do_conflicts = False
    show_wrong_base = False
    pr_number: int | None = None
    graph_path = Path("graphify-out/graph.json")

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--triage":
            do_triage = True
        elif arg == "--worktrees":
            do_worktrees = True
        elif arg == "--conflicts":
            do_conflicts = True
        elif arg == "--wrong-base":
            show_wrong_base = True
        elif arg in ("--base", "-b") and i + 1 < len(argv):
            base = argv[i + 1]; i += 1
        elif arg.startswith("--base="):
            base = arg.split("=", 1)[1]
        elif arg in ("--repo", "-R") and i + 1 < len(argv):
            repo = argv[i + 1]; i += 1
        elif arg.startswith("--graph="):
            graph_path = Path(arg.split("=", 1)[1])
        elif arg == "--graph" and i + 1 < len(argv):
            graph_path = Path(argv[i + 1]); i += 1
        elif arg.lstrip("#").isdigit():
            pr_number = int(arg.lstrip("#"))
        elif arg in ("-h", "--help"):
            print(__doc__)
            return
        i += 1

    if base is None:
        base = _detect_default_branch(repo)

    try:
        prs = fetch_prs(repo=repo, base=base)
    except RuntimeError as e:
        print(red(f"  Error: {e}"), file=sys.stderr)
        sys.exit(1)

    worktrees = fetch_worktrees()
    for pr in prs:
        pr.worktree_path = worktrees.get(pr.branch)

    # Graph impact is expensive (concurrent gh pr diff calls) — only fetch when
    # the user actually needs it: deep dive, triage, and conflict detection.
    community_labels: dict[int, list[str]] = {}
    needs_impact = graph_path.exists() and (pr_number is not None or do_triage or do_conflicts)
    if needs_impact:
        community_labels = attach_graph_impact(prs, graph_path, repo)

    if pr_number is not None:
        match = next((p for p in prs if p.number == pr_number), None)
        if not match:
            print(red(f"  PR #{pr_number} not found in open PRs."), file=sys.stderr)
            sys.exit(1)
        render_pr_detail(match, repo)
        return

    if do_triage:
        render_dashboard(prs, base, show_wrong_base)
        triage_with_opus(prs, base)
        return

    if do_worktrees:
        render_worktrees(prs, worktrees)
        return

    if do_conflicts:
        render_dashboard(prs, base, show_wrong_base)
        render_conflicts(prs, base, community_labels)
        return

    render_dashboard(prs, base, show_wrong_base)
