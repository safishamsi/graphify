from pathlib import Path
import json

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
