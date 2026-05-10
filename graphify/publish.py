"""Opt-in registry publish for understand-quickly.

Stamps `metadata.{tool, tool_version, generated_at, commit}` into the emitted
graph.json and, when `UNDERSTAND_QUICKLY_TOKEN` is set, fires a
`repository_dispatch` event at `looptech-ai/understand-quickly`.

Stdlib-only — works on the same Python versions as the rest of graphify (>=3.10).

Spec: https://github.com/looptech-ai/understand-quickly/blob/main/docs/spec/code-graph-protocol.md
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess  # nosec B404 — used only to read git rev-parse HEAD/remote
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from importlib.metadata import version as _pkg_version
    _TOOL_VERSION = _pkg_version("graphifyy")
except Exception:  # pragma: no cover
    _TOOL_VERSION = "unknown"

TOOL_NAME = "graphify"
REGISTRY_REPO = "looptech-ai/understand-quickly"
TOKEN_ENV = "UNDERSTAND_QUICKLY_TOKEN"
DISPATCH_EVENT_TYPE = "uq-publish"


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(  # nosec B603 — fixed argv, no shell
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _git_head(repo_dir: Path) -> str | None:
    sha = _git(["rev-parse", "HEAD"], repo_dir)
    return sha if sha and len(sha) == 40 else None


def _detect_repo_slug(repo_dir: Path) -> str | None:
    url = _git(["remote", "get-url", "origin"], repo_dir) or ""
    for prefix in ("https://github.com/", "git@github.com:"):
        if url.startswith(prefix):
            slug = url[len(prefix):].removesuffix(".git")
            return slug or None
    return None


def stamp_metadata(graph_path: Path, *, repo_dir: Path | None = None,
                   tool_version: str | None = None,
                   now: str | None = None) -> dict[str, Any]:
    """Merge metadata into the graph file in-place. Returns the metadata dict."""
    graph_path = Path(graph_path)
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    md: dict[str, Any] = dict(data.get("metadata") or {})
    md["tool"] = TOOL_NAME
    md["tool_version"] = tool_version or _TOOL_VERSION
    md["generated_at"] = now or _dt.datetime.now(_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    commit = _git_head(repo_dir or graph_path.parent.parent)
    if commit:
        md["commit"] = commit
    data["metadata"] = md
    graph_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return md


def dispatch(repo_slug: str, *, token: str, schema: str, graph_path: str,
             commit: str | None = None, timeout: float = 10.0) -> int:
    """POST `repository_dispatch` to the registry. Returns HTTP status."""
    payload = {
        "event_type": DISPATCH_EVENT_TYPE,
        "client_payload": {
            "repo": repo_slug, "schema": schema, "graph_path": graph_path,
            "tool": TOOL_NAME, "tool_version": _TOOL_VERSION,
            **({"commit": commit} if commit else {}),
        },
    }
    req = urllib.request.Request(  # nosec B310 — fixed https URL
        f"https://api.github.com/repos/{REGISTRY_REPO}/dispatches",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{TOOL_NAME}/{_TOOL_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return resp.status


def publish(graph_path: Path, *, repo_dir: Path | None = None,
            schema: str = "gitnexus@1", token_env: str = TOKEN_ENV,
            log: Any = None) -> dict[str, Any]:
    """Stamp metadata and (if token set) dispatch. Never raises on network errors."""
    log = log or sys.stderr
    graph_path = Path(graph_path).resolve()
    repo_dir = Path(repo_dir).resolve() if repo_dir else graph_path.parent.parent
    metadata = stamp_metadata(graph_path, repo_dir=repo_dir)

    token = os.environ.get(token_env, "").strip()
    if not token:
        print(
            f"[graphify publish] {graph_path} stamped; ${token_env} unset — "
            f"skipping registry dispatch (see "
            f"https://github.com/looptech-ai/uq-publish-action for CI use).",
            file=log,
        )
        return {"dispatched": False, "metadata": metadata}

    repo_slug = _detect_repo_slug(repo_dir)
    if not repo_slug:
        print("[graphify publish] no github 'origin' remote — skipping dispatch.",
              file=log)
        return {"dispatched": False, "metadata": metadata}

    # Registry fetches via raw.githubusercontent.com, so it needs a repo-relative
    # POSIX path. If the graph isn't inside the repo, we can stamp locally but
    # can't dispatch a fetchable path.
    try:
        rel_graph_path = graph_path.relative_to(repo_dir).as_posix()
    except ValueError:
        print(
            f"[graphify publish] {graph_path} is outside {repo_dir}; "
            f"skipping dispatch (graph must live inside the repo for the "
            f"registry to fetch it).",
            file=log,
        )
        return {"dispatched": False, "metadata": metadata,
                "error": "graph_path outside repo_dir"}

    try:
        status = dispatch(repo_slug, token=token, schema=schema,
                          graph_path=rel_graph_path, commit=metadata.get("commit"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"[graphify publish] {repo_slug} not in registry — register "
                  f"once with: npx @understand-quickly/cli add", file=log)
            return {"dispatched": False, "metadata": metadata, "registered": False}
        print(f"[graphify publish] dispatch failed ({exc.code}); local file stamped.",
              file=log)
        return {"dispatched": False, "metadata": metadata, "error": str(exc)}
    except (urllib.error.URLError, OSError) as exc:
        print(f"[graphify publish] dispatch failed ({exc}); local file stamped.",
              file=log)
        return {"dispatched": False, "metadata": metadata, "error": str(exc)}

    print(f"[graphify publish] dispatched to {REGISTRY_REPO} (HTTP {status}) "
          f"for {repo_slug}.", file=log)
    return {"dispatched": True, "metadata": metadata, "status": status}
