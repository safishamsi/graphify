"""mcp_ingest.py — Extract MCP (Model Context Protocol) server configuration files.

Reads `.mcp.json` / `claude_desktop_config.json` / `mcp.json` / `mcp_servers.json`
and turns the `mcpServers` map into Graphify nodes and edges.

Symmetry with `serve.py`: Graphify exposes itself AS an MCP server. This module
indexes MCP servers AS a corpus type, completing the loop — an agent that runs
graphify with `--mcp` can now query its own configured MCP layer.

Entry point:
  extract_mcp_config(path: Path) -> dict[str, list[dict]]

  Returns `{"nodes": [...], "edges": [...]}` compatible with Graphify's
  extraction-result format. Returns `{"nodes": [...], "edges": [...], "error": "..."}`
  when the file is malformed, too large, or has no `mcpServers` map — the empty
  result keeps it indistinguishable from "no MCP config here" for downstream
  callers.

Detected filenames (case-sensitive, matched on basename):
  - .mcp.json                       (Claude Code project config)
  - claude_desktop_config.json      (Claude Desktop)
  - mcp.json                        (generic / per-tool)
  - mcp_servers.json                (alternate naming)

Schema emitted:
  Node kinds:
    - file              the config file itself (label = filename)
    - mcp_server        one per entry under mcpServers
    - mcp_command       executable (npx, uvx, node, python, ...) — global ID
    - mcp_package       npm / pypi package id parsed from args — global ID
    - env_var           env variable NAME only — global ID. VALUES ARE NEVER READ.

  Edge relations:
    - contains          file -> mcp_server
    - references        mcp_server -> mcp_command
    - references        mcp_server -> mcp_package
    - requires_env      mcp_server -> env_var   (new relation; distinguishes
                                                  env dependencies from generic refs)

Security:
  - Env var VALUES are never read, persisted, labelled, or surfaced. Only env
    var NAMES become nodes. (`env: {"API_KEY": "sk-..."}` -> node "API_KEY" only.)
  - File size capped at 1 MiB (matches extract_json).
  - All labels go through `sanitize_label` (control characters stripped, length
    capped) before emission.
  - Args are NOT persisted as nodes/edges to avoid leaking paths or secrets that
    some servers embed as positional args.

Cross-config emergent edges:
  Because `mcp_command`, `mcp_package`, and `env_var` nodes use global IDs (no
  per-file stem prefix), the same package or env var across two MCP configs
  produces shared nodes — naturally surfacing "what configs depend on this
  thing?" via graph traversal. Server nodes ARE stem-scoped so two configs
  declaring different servers under the same key (e.g., both have "filesystem")
  do not collide.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from graphify.security import sanitize_label


MCP_CONFIG_FILENAMES: frozenset[str] = frozenset({
    ".mcp.json",
    "claude_desktop_config.json",
    "mcp.json",
    "mcp_servers.json",
})

_MAX_BYTES = 1_048_576  # 1 MiB — same cap as extract_json
_MAX_SERVERS_PER_FILE = 200  # generous; flags pathological configs


def is_mcp_config_path(path: Path) -> bool:
    """Return True when ``path`` is a recognised MCP config filename."""
    return path.name in MCP_CONFIG_FILENAMES


def extract_mcp_config(path: Path) -> dict[str, Any]:
    """Parse an MCP config file into Graphify nodes and edges.

    Behaviour matches other extractors in `extract.py`:
      - returns ``{"nodes": [...], "edges": [...]}`` on success
      - returns ``{"nodes": [], "edges": [], "error": "<reason>"}`` on parse
        failure, oversize file, or missing ``mcpServers`` map
    """
    try:
        with path.open("rb") as fh:
            raw = fh.read(_MAX_BYTES + 1)
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"mcp_ingest read error: {exc}"}

    if len(raw) > _MAX_BYTES:
        return {"nodes": [], "edges": [], "error": "mcp config too large to index"}

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return {"nodes": [], "edges": [], "error": f"mcp_ingest decode error: {exc}"}

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"nodes": [], "edges": [], "error": f"mcp_ingest json error: {exc}"}

    if not isinstance(doc, dict):
        return {"nodes": [], "edges": [], "error": "mcp_ingest: root is not an object"}

    servers = doc.get("mcpServers")
    if not isinstance(servers, dict):
        # Some tools nest the map (e.g., {"mcp": {"servers": {...}}}). Try one
        # well-known alternate shape but do not search exhaustively.
        nested = doc.get("mcp")
        if isinstance(nested, dict):
            servers = nested.get("servers")
        if not isinstance(servers, dict):
            return {"nodes": [], "edges": [], "error": "mcp_ingest: no mcpServers map"}

    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    seen_edge_keys: set[tuple[str, str, str]] = set()

    _add_node(
        nodes, seen_node_ids,
        nid=file_nid,
        label=path.name,
        kind="mcp_config_file",
        source_file=str_path,
        line=1,
    )

    file_stem = _file_stem(path)
    server_count = 0
    for server_name, spec in servers.items():
        if not isinstance(server_name, str) or not server_name:
            continue
        if not isinstance(spec, dict):
            # Skip non-object server entries silently — the broken entry is
            # the user's, not ours.
            continue
        if server_count >= _MAX_SERVERS_PER_FILE:
            break
        server_count += 1
        _emit_server(
            server_name=server_name,
            spec=spec,
            file_nid=file_nid,
            file_stem=file_stem,
            source_file=str_path,
            nodes=nodes,
            edges=edges,
            seen_node_ids=seen_node_ids,
            seen_edge_keys=seen_edge_keys,
        )

    return {"nodes": nodes, "edges": edges}


def _emit_server(
    *,
    server_name: str,
    spec: dict[str, Any],
    file_nid: str,
    file_stem: str,
    source_file: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    seen_node_ids: set[str],
    seen_edge_keys: set[tuple[str, str, str]],
) -> None:
    """Emit nodes/edges for one entry under ``mcpServers``."""
    server_nid = _make_id(file_stem, "mcp_server", server_name)
    _add_node(
        nodes, seen_node_ids,
        nid=server_nid,
        label=server_name,
        kind="mcp_server",
        source_file=source_file,
        line=1,  # JSON doesn't expose line numbers without a parser pass
    )
    _add_edge(
        edges, seen_edge_keys,
        source=file_nid,
        target=server_nid,
        relation="contains",
        source_file=source_file,
        line=1,
    )

    command = spec.get("command")
    if isinstance(command, str) and command.strip():
        cmd_label = command.strip()
        cmd_nid = _make_id("mcp_command", cmd_label)
        _add_node(
            nodes, seen_node_ids,
            nid=cmd_nid,
            label=cmd_label,
            kind="mcp_command",
            source_file=source_file,
            line=1,
        )
        _add_edge(
            edges, seen_edge_keys,
            source=server_nid,
            target=cmd_nid,
            relation="references",
            source_file=source_file,
            line=1,
            context="command",
        )

    args = spec.get("args")
    if isinstance(args, list):
        package = _detect_package_from_args(args)
        if package:
            pkg_nid = _make_id("mcp_package", package)
            _add_node(
                nodes, seen_node_ids,
                nid=pkg_nid,
                label=package,
                kind="mcp_package",
                source_file=source_file,
                line=1,
            )
            _add_edge(
                edges, seen_edge_keys,
                source=server_nid,
                target=pkg_nid,
                relation="references",
                source_file=source_file,
                line=1,
                context="package",
            )

    env = spec.get("env")
    if isinstance(env, dict):
        # ONLY KEYS. Values may contain secrets and are never read here.
        for env_name in env.keys():
            if not isinstance(env_name, str) or not env_name:
                continue
            env_nid = _make_id("env_var", env_name)
            _add_node(
                nodes, seen_node_ids,
                nid=env_nid,
                label=env_name,
                kind="env_var",
                source_file=source_file,
                line=1,
            )
            _add_edge(
                edges, seen_edge_keys,
                source=server_nid,
                target=env_nid,
                relation="requires_env",
                source_file=source_file,
                line=1,
            )


# ── Package detection from args ───────────────────────────────────────────────

# Patterns observed in real MCP server configs:
#   ["-y", "@modelcontextprotocol/server-filesystem", "/data"]   (npx)
#   ["-y", "@org/pkg@1.2.3"]
#   ["mcp-server-fetch"]                                          (uvx / python)
#   ["mcp-server-time", "--local-timezone=UTC"]
#   ["@scoped/some-mcp"]                                          (pnpx)
#   ["mcp-server-fetch"]                                          (uvx direct)
_NPM_PKG_RE = re.compile(r"^@[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*(?:@[\w.\-+]+)?$")
_PY_MCP_PKG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*-mcp(?:-[a-z0-9._-]+)?$|^mcp-[a-z0-9][a-z0-9._-]*$")
_ARG_FLAG_RE = re.compile(r"^-{1,2}\w")


def _detect_package_from_args(args: list[Any]) -> str | None:
    """Return the first arg that looks like an npm or pypi package id, else None.

    Skips short flags (-y, --yes) and option arguments (--local-timezone=UTC).
    """
    for raw in args:
        if not isinstance(raw, str):
            continue
        arg = raw.strip()
        if not arg or _ARG_FLAG_RE.match(arg):
            continue
        if _NPM_PKG_RE.match(arg):
            return _strip_version(arg)
        if _PY_MCP_PKG_RE.match(arg):
            return arg
    return None


def _strip_version(pkg: str) -> str:
    """Drop the ``@version`` suffix from an npm package id, preserving the scope.

    Scoped:   ``@scope/name`` or ``@scope/name@1.2.3`` — there are at most two
              ``@`` chars; the second is the version separator.
    Unscoped: ``name`` or ``name@1.2.3``.
    """
    if pkg.startswith("@"):
        version_at = pkg.find("@", 1)
        return pkg if version_at == -1 else pkg[:version_at]
    version_at = pkg.find("@")
    return pkg if version_at == -1 else pkg[:version_at]


# ── Node / edge construction (Graphify schema) ────────────────────────────────


def _add_node(
    nodes: list[dict[str, Any]],
    seen: set[str],
    *,
    nid: str,
    label: str,
    kind: str,
    source_file: str,
    line: int,
) -> None:
    """Append a node if not already present. ``kind`` is metadata, not file_type."""
    if not nid or nid in seen:
        return
    seen.add(nid)
    nodes.append({
        "id": nid,
        "label": sanitize_label(label),
        "file_type": "code",
        "source_file": source_file,
        "source_location": f"L{line}",
        "metadata": {"mcp_kind": kind},
    })


def _add_edge(
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    *,
    source: str,
    target: str,
    relation: str,
    source_file: str,
    line: int,
    context: str | None = None,
) -> None:
    """Append an edge if (source, target, relation) is not already present."""
    if not source or not target or source == target:
        return
    key = (source, target, relation)
    if key in seen:
        return
    seen.add(key)
    edge: dict[str, Any] = {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": source_file,
        "source_location": f"L{line}",
        "weight": 1.0,
    }
    if context:
        edge["context"] = context
    edges.append(edge)


# ── ID helpers (kept local; mirror extract.py shape) ──────────────────────────


def _make_id(*parts: str) -> str:
    """Build a stable node ID. Must match extract._make_id's normalisation rules."""
    combined = "_".join(p.strip("_.") for p in parts if p)
    combined = unicodedata.normalize("NFKC", combined)
    cleaned = re.sub(r"[^\w]+", "_", combined, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").casefold()


def _file_stem(path: Path) -> str:
    """Mirror extract._file_stem: include parent dir name to disambiguate."""
    parent = path.parent.name
    if parent and parent not in (".", ""):
        return f"{parent}.{path.stem}"
    return path.stem
