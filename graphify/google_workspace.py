"""Optional Google Workspace shortcut export support.

Google Drive for desktop stores native Docs, Sheets, and Slides as small JSON
shortcut files (.gdoc, .gsheet, .gslides). Those files are pointers, not the
document content. This module exports them to Markdown sidecars via the
googleworkspace CLI (`gws`) so Graphify can extract their actual contents.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Callable, Any


GOOGLE_WORKSPACE_EXTENSIONS = {".gdoc", ".gsheet", ".gslides"}


def google_workspace_enabled(value: str | None = None) -> bool:
    """Return True when Google Workspace shortcut export is enabled."""
    raw = value if value is not None else os.environ.get("GRAPHIFY_GOOGLE_WORKSPACE", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _safe_yaml_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def _extract_file_id_from_url(url: str) -> str | None:
    """Extract a Drive file ID from common Google Docs/Drive URL shapes."""
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("id"):
        return query["id"][0]
    match = re.search(r"/(?:document|spreadsheets|presentation|file)/d/([^/?#]+)", parsed.path)
    if match:
        return match.group(1)
    return None


def _extract_resource_key(url: str, data: dict[str, Any]) -> str | None:
    for key in ("resource_key", "resourceKey"):
        value = data.get(key)
        if value:
            return str(value)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("resourcekey"):
        return query["resourcekey"][0]
    return None


def read_google_shortcut(path: Path) -> dict[str, str | None]:
    """Read a .gdoc/.gsheet/.gslides shortcut and return export metadata."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"could not read Google Workspace shortcut {path}: {exc}") from exc

    url = str(data.get("url") or "")
    file_id = (
        data.get("doc_id")
        or data.get("file_id")
        or data.get("fileId")
        or data.get("id")
        or _extract_file_id_from_url(url)
    )
    if not file_id:
        resource_id = str(data.get("resource_id") or "")
        if ":" in resource_id:
            file_id = resource_id.split(":", 1)[1]

    if not file_id:
        raise RuntimeError(f"Google Workspace shortcut {path} does not include a Drive file ID")

    return {
        "file_id": str(file_id),
        "url": url or None,
        "resource_key": _extract_resource_key(url, data),
        "account": str(data.get("email")) if data.get("email") else None,
    }


def _run_gws_export(file_id: str, mime_type: str, output: Path, resource_key: str | None = None) -> None:
    exe = shutil.which("gws")
    if not exe:
        raise RuntimeError(
            "gws is required for Google Workspace export. Install it from "
            "https://github.com/googleworkspace/cli and run `gws auth login -s drive`."
        )

    params: dict[str, str] = {"fileId": file_id, "mimeType": mime_type}
    # Drive resource keys are sent via X-Goog-Drive-Resource-Keys. The current
    # gws export command has no custom-header flag, so do not pass resourceKey
    # as an unsupported query parameter.
    _ = resource_key
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    timeout = int(os.environ.get("GRAPHIFY_GOOGLE_WORKSPACE_TIMEOUT", "120"))
    result = subprocess.run(
        [exe, "drive", "files", "export", "--params", json.dumps(params), "-o", output.name],
        capture_output=True,
        cwd=output.parent,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        if len(stderr) > 1200:
            stderr = stderr[:1200] + "..."
        raise RuntimeError(f"gws export failed for {file_id}: {stderr}")


def _sidecar_path(path: Path, out_dir: Path) -> Path:
    name_hash = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    return out_dir / f"{path.stem}_{name_hash}.md"


def _with_frontmatter(path: Path, shortcut: dict[str, str | None], body: str, exported_mime_type: str) -> str:
    source_url = shortcut.get("url") or ""
    account = shortcut.get("account") or ""
    account_line = ""
    if account:
        account_hash = hashlib.sha256(account.encode()).hexdigest()[:12]
        account_line = f'google_account_hash: "{account_hash}"\n'
    return (
        "---\n"
        f'source_file: "{_safe_yaml_str(str(path))}"\n'
        'source_type: "google_workspace"\n'
        f'google_file_id: "{_safe_yaml_str(shortcut["file_id"] or "")}"\n'
        f'google_export_mime_type: "{_safe_yaml_str(exported_mime_type)}"\n'
        f'source_url: "{_safe_yaml_str(source_url)}"\n'
        f"{account_line}"
        "---\n\n"
        f"<!-- converted from Google Workspace shortcut: {path.name} -->\n\n"
        f"{body.strip()}\n"
    )


def convert_google_workspace_file(
    path: Path,
    out_dir: Path,
    *,
    xlsx_to_markdown: Callable[[Path], str] | None = None,
) -> Path | None:
    """Export a Google Workspace shortcut to a Markdown sidecar.

    Returns the converted Markdown path, or None when conversion is unsupported
    or produced no readable content.
    """
    ext = path.suffix.lower()
    if ext not in GOOGLE_WORKSPACE_EXTENSIONS:
        return None

    shortcut = read_google_shortcut(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _sidecar_path(path, out_dir)

    if ext == ".gdoc":
        with tempfile.NamedTemporaryFile("w+b", suffix=".md", delete=False, dir=out_dir) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_gws_export(shortcut["file_id"] or "", "text/markdown", tmp_path, shortcut.get("resource_key"))
            body = tmp_path.read_text(encoding="utf-8", errors="replace")
        finally:
            tmp_path.unlink(missing_ok=True)
        if not body.strip():
            return None
        out_path.write_text(_with_frontmatter(path, shortcut, body, "text/markdown"), encoding="utf-8")
        return out_path

    if ext == ".gslides":
        with tempfile.NamedTemporaryFile("w+b", suffix=".txt", delete=False, dir=out_dir) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_gws_export(shortcut["file_id"] or "", "text/plain", tmp_path, shortcut.get("resource_key"))
            body = tmp_path.read_text(encoding="utf-8", errors="replace")
        finally:
            tmp_path.unlink(missing_ok=True)
        if not body.strip():
            return None
        out_path.write_text(_with_frontmatter(path, shortcut, body, "text/plain"), encoding="utf-8")
        return out_path

    if ext == ".gsheet":
        if xlsx_to_markdown is None:
            raise RuntimeError("Google Sheets export requires the office extra: pip install graphifyy[office,google]")
        with tempfile.NamedTemporaryFile("w+b", suffix=".xlsx", delete=False, dir=out_dir) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_gws_export(
                shortcut["file_id"] or "",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                tmp_path,
                shortcut.get("resource_key"),
            )
            body = xlsx_to_markdown(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        if not body.strip():
            return None
        out_path.write_text(
            _with_frontmatter(
                path,
                shortcut,
                body,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            encoding="utf-8",
        )
        return out_path

    return None
