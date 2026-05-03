"""Tests for the `graphify dry-run` CLI command."""
import sys
import pytest
from pathlib import Path
from unittest.mock import patch


def _run_main(argv):
    """Run graphify.__main__.main() with the given argv, capture stdout."""
    import io
    from graphify.__main__ import main
    buf = io.StringIO()
    exit_code = 0
    with patch("sys.argv", argv), patch("sys.stdout", buf):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code or 0
    return buf.getvalue(), exit_code


def test_dry_run_prints_summary(tmp_path):
    """dry-run on a directory with code files prints a file-count summary."""
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "utils.py").write_text("def f(): pass\n")
    out, code = _run_main(["graphify", "dry-run", str(tmp_path)])
    assert code == 0
    assert "Corpus scan" in out
    assert "Code files" in out
    assert "Total" in out


def test_dry_run_no_files_written(tmp_path):
    """dry-run must not create graphify-out/ or any output files."""
    (tmp_path / "readme.md").write_text("# hello\n")
    _run_main(["graphify", "dry-run", str(tmp_path)])
    assert not (tmp_path / "graphify-out").exists()


def test_dry_run_default_path(tmp_path, monkeypatch):
    """dry-run with no path argument defaults to the current directory."""
    (tmp_path / "main.py").write_text("print('hi')\n")
    monkeypatch.chdir(tmp_path)
    out, code = _run_main(["graphify", "dry-run"])
    assert code == 0
    assert "Corpus scan" in out


def test_dry_run_missing_path(tmp_path):
    """dry-run with a non-existent path exits non-zero."""
    with pytest.raises(SystemExit) as exc:
        with patch("sys.argv", ["graphify", "dry-run", str(tmp_path / "nonexistent")]):
            from graphify.__main__ import main
            main()
    assert exc.value.code != 0


def test_dry_run_no_graphify_out_written(tmp_path):
    """dry-run output says no files were written."""
    (tmp_path / "a.py").write_text("a = 1\n")
    out, _ = _run_main(["graphify", "dry-run", str(tmp_path)])
    assert "No files were written" in out


def test_dry_run_office_no_sidecar_written(tmp_path):
    """dry-run must not write office sidecars even when .docx/.xlsx files are present."""
    from unittest.mock import MagicMock, patch as mpatch

    # Create a fake .docx so detect sees it as an office file
    (tmp_path / "report.docx").write_bytes(b"PK\x03\x04")  # minimal docx magic bytes

    with mpatch("graphify.detect.convert_office_file") as mock_convert:
        _run_main(["graphify", "dry-run", str(tmp_path)])

    mock_convert.assert_not_called()


def test_dry_run_office_missing_deps_warns(tmp_path):
    """dry-run warns when office deps are missing and content would be empty in a real run."""
    from unittest.mock import patch as mpatch

    (tmp_path / "report.docx").write_bytes(b"PK\x03\x04")

    # Simulate missing python-docx: docx_to_markdown returns ""
    with mpatch("graphify.detect.docx_to_markdown", return_value=""):
        out, code = _run_main(["graphify", "dry-run", str(tmp_path)])

    assert code == 0
    assert "office deps missing" in out.lower() or "office" in out.lower()
    assert "pip install graphify[office]" in out
