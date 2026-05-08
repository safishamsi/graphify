from pathlib import Path
import json

import pytest

import graphify.google_workspace as gw


def test_read_google_shortcut_doc_id(tmp_path):
    shortcut = tmp_path / "Planning.gdoc"
    shortcut.write_text(
        '{"url":"https://docs.google.com/document/d/doc-123/edit","doc_id":"doc-123","email":"me@example.com"}',
        encoding="utf-8",
    )

    metadata = gw.read_google_shortcut(shortcut)

    assert metadata["file_id"] == "doc-123"
    assert metadata["account"] == "me@example.com"


def test_read_google_shortcut_extracts_id_from_url(tmp_path):
    shortcut = tmp_path / "Budget.gsheet"
    shortcut.write_text(
        '{"url":"https://docs.google.com/spreadsheets/d/sheet-456/edit?resourcekey=key-1"}',
        encoding="utf-8",
    )

    metadata = gw.read_google_shortcut(shortcut)

    assert metadata["file_id"] == "sheet-456"
    assert metadata["resource_key"] == "key-1"


def test_convert_gdoc_to_markdown_sidecar(tmp_path, monkeypatch):
    shortcut = tmp_path / "Planning.gdoc"
    shortcut.write_text(
        '{"url":"https://docs.google.com/document/d/doc-123/edit","doc_id":"doc-123"}',
        encoding="utf-8",
    )

    def fake_export(file_id, mime_type, output, resource_key=None):
        assert file_id == "doc-123"
        assert mime_type == "text/markdown"
        output.write_text("# Planning\n\nExported doc text.", encoding="utf-8")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(shortcut, tmp_path / "converted")

    assert out is not None
    assert out.suffix == ".md"
    content = out.read_text(encoding="utf-8")
    assert 'source_type: "google_workspace"' in content
    assert "# Planning" in content


def test_convert_gsheet_uses_xlsx_markdown_callback(tmp_path, monkeypatch):
    shortcut = tmp_path / "Budget.gsheet"
    shortcut.write_text('{"doc_id":"sheet-456"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        assert file_id == "sheet-456"
        assert mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        output.write_bytes(b"xlsx")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(
        shortcut,
        tmp_path / "converted",
        xlsx_to_markdown=lambda path: "## Sheet: Main\n\n| A |\n| --- |\n| 1 |",
    )

    assert out is not None
    assert "## Sheet: Main" in out.read_text(encoding="utf-8")


def test_run_gws_export_uses_output_directory_as_cwd(tmp_path, monkeypatch):
    output = tmp_path / "converted" / "doc.md"
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Result()

    monkeypatch.setattr(gw.shutil, "which", lambda name: "/usr/local/bin/gws")
    monkeypatch.setattr(gw.subprocess, "run", fake_run)

    gw._run_gws_export("doc-123", "text/markdown", output)

    assert output.parent.exists()
    cmd, kwargs = calls[0]
    assert kwargs["cwd"] == output.parent.resolve()
    assert cmd[:4] == ["/usr/local/bin/gws", "drive", "files", "export"]
    assert cmd[-2:] == ["-o", "doc.md"]


def test_run_gws_export_does_not_send_resource_key_as_query_param(tmp_path, monkeypatch):
    output = tmp_path / "converted" / "doc.md"
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(gw.shutil, "which", lambda name: "/usr/local/bin/gws")
    monkeypatch.setattr(gw.subprocess, "run", fake_run)

    gw._run_gws_export("doc-123", "text/markdown", output, resource_key="rk-1")

    params = json.loads(calls[0][calls[0].index("--params") + 1])
    assert params == {"fileId": "doc-123", "mimeType": "text/markdown"}


def test_google_workspace_enabled_env(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_GOOGLE_WORKSPACE", "yes")
    assert gw.google_workspace_enabled()

    monkeypatch.setenv("GRAPHIFY_GOOGLE_WORKSPACE", "0")
    assert not gw.google_workspace_enabled()


# --- Additional edge-case / real-world tests ---


def test_google_workspace_enabled_true_variants(monkeypatch):
    """All truthy strings should return True."""
    for value in ("1", "true", "yes", "on", "TRUE", "YES", "ON"):
        monkeypatch.setenv("GRAPHIFY_GOOGLE_WORKSPACE", value)
        assert gw.google_workspace_enabled(), f"Expected True for {value!r}"


def test_google_workspace_enabled_false_variants(monkeypatch):
    """Falsy/unknown strings should return False."""
    for value in ("0", "false", "no", "off", "", "maybe", " "):
        monkeypatch.setenv("GRAPHIFY_GOOGLE_WORKSPACE", value)
        assert not gw.google_workspace_enabled(), f"Expected False for {value!r}"


def test_google_workspace_enabled_explicit_value():
    """When value is passed directly, env is ignored."""
    import os
    os.environ["GRAPHIFY_GOOGLE_WORKSPACE"] = "yes"
    # Explicit "0" overrides env "yes"
    assert not gw.google_workspace_enabled("0")
    # Explicit "true" overrides env "yes"
    assert gw.google_workspace_enabled("true")


def test_extract_file_id_from_url_empty():
    """Empty or None URL returns None."""
    assert gw._extract_file_id_from_url("") is None
    assert gw._extract_file_id_from_url(None) is None


def test_extract_file_id_from_url_query_param():
    """URL with ?id= param."""
    result = gw._extract_file_id_from_url("https://docs.google.com/open?id=doc-abc")
    assert result == "doc-abc"


def test_extract_file_id_from_url_path_document():
    """URL with /document/d/ style path."""
    result = gw._extract_file_id_from_url("https://docs.google.com/document/d/doc-xyz/preview")
    assert result == "doc-xyz"


def test_extract_file_id_from_url_path_spreadsheets():
    """URL with /spreadsheets/d/ style path."""
    result = gw._extract_file_id_from_url("https://docs.google.com/spreadsheets/d/sheet-abc/edit#gid=0")
    assert result == "sheet-abc"


def test_extract_file_id_from_url_path_file():
    """URL with /file/d/ style path."""
    result = gw._extract_file_id_from_url("https://drive.google.com/file/d/file-123/view")
    assert result == "file-123"


def test_extract_file_id_from_url_no_match():
    """URL with no recognizable Google Docs pattern returns None."""
    result = gw._extract_file_id_from_url("https://example.com/some/page")
    assert result is None


def test_extract_resource_key_from_data():
    """resource_key in the shortcut JSON data is picked up."""
    data = {"resource_key": "rk-value-1"}
    result = gw._extract_resource_key("https://example.com", data)
    assert result == "rk-value-1"


def test_extract_resource_key_from_data_camel_case():
    """resourceKey (camelCase) in the shortcut JSON data is picked up."""
    data = {"resourceKey": "rk-value-2"}
    result = gw._extract_resource_key("https://example.com", data)
    assert result == "rk-value-2"


def test_extract_resource_key_from_url():
    """When not in data, resourcekey is extracted from URL query."""
    data = {"other": "stuff"}
    url = "https://docs.google.com/spreadsheets/d/x/edit?resourcekey=rk-url"
    result = gw._extract_resource_key(url, data)
    assert result == "rk-url"


def test_extract_resource_key_none():
    """No resource key at all returns None."""
    data = {"other": "stuff"}
    result = gw._extract_resource_key("https://example.com", data)
    assert result is None


def test_extract_resource_key_none_with_empty_url():
    """Empty URL + no key in data = None."""
    data = {}
    result = gw._extract_resource_key("", data)
    assert result is None


def test_read_google_shortcut_invalid_json(tmp_path):
    """Invalid JSON raises RuntimeError."""
    shortcut = tmp_path / "bad.gdoc"
    shortcut.write_text("not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="could not read Google Workspace shortcut"):
        gw.read_google_shortcut(shortcut)


def test_read_google_shortcut_missing_file(tmp_path):
    """Non-existent shortcut file raises FileNotFoundError (or RuntimeError wrapped)."""
    shortcut = tmp_path / "gone.gdoc"
    with pytest.raises((RuntimeError, FileNotFoundError)):
        gw.read_google_shortcut(shortcut)


def test_read_google_shortcut_resource_id_colon(tmp_path):
    """When no doc_id/file_id/id, falls back to resource_id with colon split."""
    shortcut = tmp_path / "Planning.gdoc"
    shortcut.write_text(
        '{"resource_id":"document:doc-from-resource-id"}',
        encoding="utf-8",
    )
    metadata = gw.read_google_shortcut(shortcut)
    assert metadata["file_id"] == "doc-from-resource-id"


def test_read_google_shortcut_no_id_at_all(tmp_path):
    """Shortcut with no file id info raises RuntimeError."""
    shortcut = tmp_path / "empty.gdoc"
    shortcut.write_text('{"url":"https://example.com"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not include a Drive file ID"):
        gw.read_google_shortcut(shortcut)


def test_read_google_shortcut_uses_file_id_key(tmp_path):
    """file_id key in JSON data."""
    shortcut = tmp_path / "test.gdoc"
    shortcut.write_text('{"file_id":"fid-001", "doc_id":"d-002"}', encoding="utf-8")
    metadata = gw.read_google_shortcut(shortcut)
    # doc_id takes priority (checked first in source)
    assert metadata["file_id"] == "d-002"


def test_read_google_shortcut_uses_fileId_camel(tmp_path):
    """fileId (camelCase) key in JSON data."""
    shortcut = tmp_path / "test.gdoc"
    shortcut.write_text('{"fileId":"camel-id"}', encoding="utf-8")
    metadata = gw.read_google_shortcut(shortcut)
    assert metadata["file_id"] == "camel-id"


def test_read_google_shortcut_uses_id_key(tmp_path):
    """id key in JSON data."""
    shortcut = tmp_path / "test.gdoc"
    shortcut.write_text('{"id":"plain-id"}', encoding="utf-8")
    metadata = gw.read_google_shortcut(shortcut)
    assert metadata["file_id"] == "plain-id"


def test_run_gws_export_missing_gws_binary(tmp_path, monkeypatch):
    """When gws is not found, raises RuntimeError."""
    monkeypatch.setattr(gw.shutil, "which", lambda name: None)
    output = tmp_path / "converted" / "doc.md"

    with pytest.raises(RuntimeError, match="gws is required"):
        gw._run_gws_export("doc-123", "text/markdown", output)


def test_run_gws_export_subprocess_failure(tmp_path, monkeypatch):
    """When gws returns non-zero, raises RuntimeError with stderr."""
    output = tmp_path / "converted" / "doc.md"
    output.parent.mkdir(parents=True, exist_ok=True)

    class Result:
        returncode = 1
        stdout = ""
        stderr = "Access denied: insufficient permissions"

    monkeypatch.setattr(gw.shutil, "which", lambda name: "/usr/local/bin/gws")
    monkeypatch.setattr(gw.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="gws export failed"):
        gw._run_gws_export("doc-123", "text/markdown", output)


def test_run_gws_export_stderr_truncated(tmp_path, monkeypatch):
    """Very long stderr is truncated before inclusion in error message."""
    output = tmp_path / "converted" / "doc.md"
    output.parent.mkdir(parents=True, exist_ok=True)

    long_msg = "x" * 2000

    class Result:
        returncode = 1
        stdout = ""
        stderr = long_msg

    monkeypatch.setattr(gw.shutil, "which", lambda name: "/usr/local/bin/gws")
    monkeypatch.setattr(gw.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="..."):
        gw._run_gws_export("doc-123", "text/markdown", output)


def test_convert_unsupported_extension(tmp_path):
    """A file with .txt extension is not a Google Workspace shortcut."""
    path = tmp_path / "something.txt"
    path.write_text("hello", encoding="utf-8")
    result = gw.convert_google_workspace_file(path, tmp_path / "converted")
    assert result is None


def test_convert_gdoc_empty_body(tmp_path, monkeypatch):
    """When gws export returns empty body, return None."""
    shortcut = tmp_path / "empty.gdoc"
    shortcut.write_text('{"doc_id":"doc-empty"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        output.write_text("", encoding="utf-8")  # empty

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(shortcut, tmp_path / "converted")
    assert out is None


def test_convert_gslides_to_text(tmp_path, monkeypatch):
    """Google Slides shortcut exports to text/plain."""
    shortcut = tmp_path / "deck.gslides"
    shortcut.write_text('{"doc_id":"slide-789"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        assert mime_type == "text/plain"
        output.write_text("Slide 1 content\nSlide 2 content", encoding="utf-8")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(shortcut, tmp_path / "converted")
    assert out is not None
    content = out.read_text(encoding="utf-8")
    assert "Slide 1 content" in content
    assert 'source_type: "google_workspace"' in content


def test_convert_gslides_empty_body(tmp_path, monkeypatch):
    """Empty text from gslides export returns None."""
    shortcut = tmp_path / "empty.gslides"
    shortcut.write_text('{"doc_id":"slide-empty"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        output.write_text("", encoding="utf-8")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(shortcut, tmp_path / "converted")
    assert out is None


def test_convert_gsheet_no_callback(tmp_path, monkeypatch):
    """Google Sheets without xlsx_to_markdown callback raises RuntimeError."""
    shortcut = tmp_path / "sheet.gsheet"
    shortcut.write_text('{"doc_id":"sheet-111"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        output.write_bytes(b"xlsx")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    with pytest.raises(RuntimeError, match="requires the office extra"):
        gw.convert_google_workspace_file(shortcut, tmp_path / "converted")


def test_convert_gsheet_empty_body(tmp_path, monkeypatch):
    """Empty body from gsheet xlsx_to_markdown callback returns None."""
    shortcut = tmp_path / "empty.gsheet"
    shortcut.write_text('{"doc_id":"sheet-empty"}', encoding="utf-8")

    def fake_export(file_id, mime_type, output, resource_key=None):
        output.write_bytes(b"xlsx")

    monkeypatch.setattr(gw, "_run_gws_export", fake_export)

    out = gw.convert_google_workspace_file(
        shortcut,
        tmp_path / "converted",
        xlsx_to_markdown=lambda path: "",  # empty
    )
    assert out is None


def test_sidecar_path_deterministic():
    """_sidecar_path produces consistent hash-based filenames."""
    from pathlib import Path
    p = Path("/some/absolute/path/to/doc.gdoc")
    out_dir = Path("/tmp/output")

    result1 = gw._sidecar_path(p, out_dir)
    result2 = gw._sidecar_path(p, out_dir)
    # Same inputs -> same output
    assert result1 == result2
    # Uses stem + hash
    assert result1.stem.startswith("doc_")
    assert len(result1.stem) == len("doc_") + 8  # 8 hex chars
    assert result1.suffix == ".md"


def test_with_frontmatter_account_hash(tmp_path):
    """_with_frontmatter includes account hash when account is present."""
    shortcut = {
        "file_id": "f-001",
        "url": "https://docs.google.com/document/d/f-001",
        "account": "user@example.com",
    }
    result = gw._with_frontmatter(
        Path("/path/doc.gdoc"),
        shortcut,
        "# Some content",
        "text/markdown",
    )
    assert 'google_account_hash:' in result
    assert 'source_url: "https://docs.google.com/document/d/f-001"' in result


def test_with_frontmatter_no_account(tmp_path):
    """_with_frontmatter omits account hash when no account."""
    shortcut = {
        "file_id": "f-002",
        "url": "https://docs.google.com/document/d/f-002",
        "account": None,
    }
    result = gw._with_frontmatter(
        Path("/path/doc.gdoc"),
        shortcut,
        "# Content",
        "text/markdown",
    )
    assert "google_account_hash:" not in result
