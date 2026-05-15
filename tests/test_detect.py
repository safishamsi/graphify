from pathlib import Path
from graphify.detect import classify_file, count_words, detect, detect_incremental, save_manifest, FileType, _looks_like_paper, _is_ignored, _load_graphifyignore

FIXTURES = Path(__file__).parent / "fixtures"

def test_classify_python():
    assert classify_file(Path("foo.py")) == FileType.CODE

def test_classify_typescript():
    assert classify_file(Path("bar.ts")) == FileType.CODE

def test_classify_markdown():
    assert classify_file(Path("README.md")) == FileType.DOCUMENT

def test_classify_pdf():
    assert classify_file(Path("paper.pdf")) == FileType.PAPER

def test_classify_pdf_in_xcassets_skipped():
    # PDFs inside Xcode asset catalogs are vector icons, not papers
    asset_pdf = Path("MyApp/Images.xcassets/icon.imageset/icon.pdf")
    assert classify_file(asset_pdf) is None

def test_classify_pdf_in_xcassets_root_skipped():
    asset_pdf = Path("Pods/HXPHPicker/Assets.xcassets/photo.pdf")
    assert classify_file(asset_pdf) is None

def test_classify_unknown_returns_none():
    assert classify_file(Path("archive.zip")) is None

def test_classify_image():
    assert classify_file(Path("screenshot.png")) == FileType.IMAGE
    assert classify_file(Path("design.jpg")) == FileType.IMAGE
    assert classify_file(Path("diagram.webp")) == FileType.IMAGE

def test_count_words_sample_md():
    words = count_words(FIXTURES / "sample.md")
    assert words > 5

def test_detect_finds_fixtures():
    result = detect(FIXTURES)
    assert result["total_files"] >= 2
    assert "code" in result["files"]
    assert "document" in result["files"]

def test_detect_warns_small_corpus():
    result = detect(FIXTURES)
    assert result["needs_graph"] is False
    assert result["warning"] is not None

def test_detect_skips_dotfiles():
    result = detect(FIXTURES)
    for files in result["files"].values():
        for f in files:
            assert "/." not in f


def test_classify_md_paper_by_signals(tmp_path):
    """A .md file with enough paper signals should classify as PAPER."""
    paper = tmp_path / "paper.md"
    paper.write_text(
        "# Abstract\n\nWe propose a new method. See [1] and [23].\n"
        "This work was published in the Journal of AI. ArXiv preprint.\n"
        "See Equation 3 for details. \\cite{vaswani2017}.\n"
    )
    assert classify_file(paper) == FileType.PAPER


def test_classify_md_doc_without_signals(tmp_path):
    """A plain .md file without paper signals should stay DOCUMENT."""
    doc = tmp_path / "notes.md"
    doc.write_text("# My Notes\n\nHere are some notes about the project.\n")
    assert classify_file(doc) == FileType.DOCUMENT


def test_classify_attention_paper():
    """The real attention paper file should be classified as PAPER."""
    paper_path = Path("/home/safi/graphify_eval/papers/attention_is_all_you_need.md")
    if paper_path.exists():
        result = classify_file(paper_path)
        assert result == FileType.PAPER


def test_graphifyignore_excludes_file(tmp_path):
    """Files matching .graphifyignore patterns are excluded from detect()."""
    (tmp_path / ".graphifyignore").write_text("vendor/\n*.generated.py\n")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "lib.py").write_text("x = 1")
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "schema.generated.py").write_text("x = 1")

    result = detect(tmp_path)
    file_list = result["files"]["code"]
    assert any("main.py" in f for f in file_list)
    assert not any("vendor" in f for f in file_list)
    assert not any("generated" in f for f in file_list)
    assert result["graphifyignore_patterns"] == 2


def test_graphifyignore_missing_is_fine(tmp_path):
    """No .graphifyignore is not an error."""
    (tmp_path / "main.py").write_text("x = 1")
    result = detect(tmp_path)
    assert result["graphifyignore_patterns"] == 0


def test_graphifyignore_comments_ignored(tmp_path):
    """Comment lines in .graphifyignore are not treated as patterns."""
    (tmp_path / ".graphifyignore").write_text("# this is a comment\n\nmain.py\n")
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "other.py").write_text("x = 2")
    result = detect(tmp_path)
    assert not any("main.py" in f for f in result["files"]["code"])
    assert any("other.py" in f for f in result["files"]["code"])


def test_detect_follows_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real_lib"
    real_dir.mkdir()
    (real_dir / "util.py").write_text("x = 1")
    (tmp_path / "linked_lib").symlink_to(real_dir)

    result_no = detect(tmp_path, follow_symlinks=False)
    result_yes = detect(tmp_path, follow_symlinks=True)

    assert any("real_lib" in f for f in result_no["files"]["code"])
    assert not any("linked_lib" in f for f in result_no["files"]["code"])
    assert any("linked_lib" in f for f in result_yes["files"]["code"])


def test_detect_follows_symlinked_file(tmp_path):
    (tmp_path / "real.py").write_text("x = 1")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")

    result = detect(tmp_path, follow_symlinks=True)
    code = result["files"]["code"]
    assert any("real.py" in f for f in code)
    assert any("link.py" in f for f in code)


def test_graphifyignore_hermetic_without_vcs(tmp_path):
    """Without a VCS root, parent .graphifyignore does NOT apply (hermetic)."""
    (tmp_path / ".graphifyignore").write_text("vendor/\n")
    sub = tmp_path / "packages" / "mylib"
    sub.mkdir(parents=True)
    (sub / "main.py").write_text("x = 1")
    vendor = sub / "vendor"
    vendor.mkdir()
    (vendor / "dep.py").write_text("y = 2")

    result = detect(sub)
    code_files = result["files"]["code"]
    assert any("main.py" in f for f in code_files)
    # parent .graphifyignore must NOT leak into a non-VCS scan
    assert any("vendor" in f for f in code_files)
    assert result["graphifyignore_patterns"] == 0


def test_graphifyignore_discovered_from_parent_in_vcs(tmp_path):
    """Inside a VCS repo, parent .graphifyignore applies to subdirectory scans."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".graphifyignore").write_text("vendor/\n")
    sub = tmp_path / "packages" / "mylib"
    sub.mkdir(parents=True)
    (sub / "main.py").write_text("x = 1")
    vendor = sub / "vendor"
    vendor.mkdir()
    (vendor / "dep.py").write_text("y = 2")

    result = detect(sub)
    code_files = result["files"]["code"]
    assert any("main.py" in f for f in code_files)
    assert not any("vendor" in f for f in code_files)
    assert result["graphifyignore_patterns"] >= 1


def test_graphifyignore_stops_at_git_boundary(tmp_path):
    """Upward search stops at the git repo root (.git directory)."""
    (tmp_path / ".graphifyignore").write_text("main.py\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    sub = repo / "sub"
    sub.mkdir()
    (sub / "main.py").write_text("x = 1")

    result = detect(sub)
    code_files = result["files"]["code"]
    assert any("main.py" in f for f in code_files)
    assert result["graphifyignore_patterns"] == 0


def test_graphifyignore_at_git_root_is_included(tmp_path):
    """A .graphifyignore at the git repo root is included when scanning a subdir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".graphifyignore").write_text("vendor/\n")
    sub = repo / "packages" / "mylib"
    sub.mkdir(parents=True)
    (sub / "main.py").write_text("x = 1")
    vendor = sub / "vendor"
    vendor.mkdir()
    (vendor / "dep.py").write_text("y = 2")

    result = detect(sub)
    code_files = result["files"]["code"]
    assert any("main.py" in f for f in code_files)
    assert not any("vendor" in f for f in code_files)
    assert result["graphifyignore_patterns"] == 1


def test_detect_handles_circular_symlinks(tmp_path):
    sub = tmp_path / "a"
    sub.mkdir()
    (sub / "main.py").write_text("x = 1")
    (sub / "loop").symlink_to(tmp_path)

    result = detect(tmp_path, follow_symlinks=True)
    assert any("main.py" in f for f in result["files"]["code"])


def test_detect_incremental_propagates_follow_symlinks(tmp_path, monkeypatch):
    """detect_incremental must forward follow_symlinks so symlinked sub-trees
    appear in incremental scans the same way they appear in full scans."""
    monkeypatch.chdir(tmp_path)

    real_dir = tmp_path / "real_corpus"
    real_dir.mkdir()
    (real_dir / "note.md").write_text("# real note\n\nsome content")
    (tmp_path / "linked_corpus").symlink_to(real_dir)

    manifest_path = str(tmp_path / "manifest.json")

    # Without following symlinks, the symlinked dir contents are invisible.
    no_link = detect_incremental(tmp_path, manifest_path, follow_symlinks=False)
    assert not any("linked_corpus" in f for f in no_link["files"]["document"])

    # With follow_symlinks=True, the symlinked dir contents appear and are new.
    yes_link = detect_incremental(tmp_path, manifest_path, follow_symlinks=True)
    assert any("linked_corpus" in f for f in yes_link["files"]["document"])
    assert yes_link["new_total"] >= 2  # real + linked

    # After saving manifest, a second incremental scan should see no changes.
    save_manifest(yes_link["files"], manifest_path)
    second = detect_incremental(tmp_path, manifest_path, follow_symlinks=True)
    assert second["new_total"] == 0


def test_classify_video_extensions():
    """Video and audio file extensions should classify as VIDEO."""
    from graphify.detect import FileType
    assert classify_file(Path("lecture.mp4")) == FileType.VIDEO
    assert classify_file(Path("podcast.mp3")) == FileType.VIDEO
    assert classify_file(Path("talk.mov")) == FileType.VIDEO
    assert classify_file(Path("recording.wav")) == FileType.VIDEO
    assert classify_file(Path("webinar.webm")) == FileType.VIDEO
    assert classify_file(Path("audio.m4a")) == FileType.VIDEO


def test_classify_google_workspace_shortcuts():
    assert classify_file(Path("notes.gdoc")) == FileType.DOCUMENT
    assert classify_file(Path("budget.gsheet")) == FileType.DOCUMENT
    assert classify_file(Path("deck.gslides")) == FileType.DOCUMENT


def test_detect_skips_google_workspace_shortcuts_by_default(tmp_path):
    (tmp_path / "notes.gdoc").write_text('{"doc_id":"doc-1"}', encoding="utf-8")

    result = detect(tmp_path)

    assert not result["files"]["document"]
    assert any("Google Workspace shortcut skipped" in item for item in result["skipped_sensitive"])


def test_detect_converts_google_workspace_shortcuts_when_enabled(tmp_path, monkeypatch):
    shortcut = tmp_path / "notes.gdoc"
    shortcut.write_text('{"doc_id":"doc-1"}', encoding="utf-8")

    def fake_convert(path, out_dir, *, xlsx_to_markdown=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "notes_converted.md"
        out.write_text("# Notes\n\nA converted Google Doc.", encoding="utf-8")
        return out

    monkeypatch.setattr("graphify.detect.convert_google_workspace_file", fake_convert)

    result = detect(tmp_path, google_workspace=True)

    assert len(result["files"]["document"]) == 1
    assert result["files"]["document"][0].endswith("notes_converted.md")
    assert result["total_words"] > 0


def test_detect_includes_video_key(tmp_path):
    """detect() result always includes a 'video' key even with no video files."""
    (tmp_path / "main.py").write_text("x = 1")
    result = detect(tmp_path)
    assert "video" in result["files"]


def test_detect_finds_video_files(tmp_path):
    """detect() correctly counts video files and does not add them to word count."""
    (tmp_path / "lecture.mp4").write_bytes(b"fake video data")
    (tmp_path / "notes.md").write_text("# Notes\nSome content here.")
    result = detect(tmp_path)
    assert len(result["files"]["video"]) == 1
    assert any("lecture.mp4" in f for f in result["files"]["video"])
    # total_words should not include video files (they have no readable text)
    assert result["total_words"] >= 0  # won't crash


def test_detect_video_not_in_words(tmp_path):
    """Video files do not contribute to total_words."""
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 100)
    result = detect(tmp_path)
    # Only video file present — total_words should be 0
    assert result["total_words"] == 0


def test_detect_skips_coverage_dir(tmp_path):
    """coverage/ and lcov-report/ are noise dirs — HTML reports inside must be excluded (#870)."""
    cov = tmp_path / "coverage" / "lcov-report"
    cov.mkdir(parents=True)
    (cov / "index.html").write_text("<html>coverage report</html>")
    (cov / "src.ts.html").write_text("<html>file coverage</html>")
    (tmp_path / "main.py").write_text("def hello(): pass")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    cov_prefix = str(tmp_path / "coverage")
    assert not any(f.startswith(cov_prefix) for f in all_files)
    assert any("main.py" in f for f in all_files)


def test_detect_skips_visual_tests_dir(tmp_path):
    """visual-tests/ bundles and snapshots are noise — must be excluded (#869)."""
    vt = tmp_path / "visual-tests"
    vt.mkdir()
    (vt / "bundle.js").write_text("var u3=function(){};var d2=function(){}")
    (vt / "screens.tsx").write_text("export const Screen = () => <div/>")
    (tmp_path / "app.py").write_text("def main(): pass")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert not any("visual-tests" in f for f in all_files)
    assert any("app.py" in f for f in all_files)


def test_detect_skips_snapshots_dir(tmp_path):
    """__snapshots__/ and snapshots/ are jest/vitest artefacts — must be excluded."""
    (tmp_path / "__snapshots__").mkdir()
    (tmp_path / "__snapshots__" / "app.test.ts.snap").write_text("// Jest Snapshot\nexports[`test 1`] = `<div/>`")
    (tmp_path / "app.ts").write_text("export function greet() { return 'hi'; }")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert not any("__snapshots__" in f for f in all_files)
    assert any("app.ts" in f for f in all_files)


def test_detect_skips_storybook_static_dir(tmp_path):
    """storybook-static/ is a build artefact — must be excluded."""
    sb = tmp_path / "storybook-static"
    sb.mkdir()
    (sb / "index.html").write_text("<html>storybook</html>")
    (sb / "main.js").write_text("(function(){var s=1;})()")
    (tmp_path / "Button.tsx").write_text("export const Button = () => <button/>")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert not any("storybook-static" in f for f in all_files)
    assert any("Button.tsx" in f for f in all_files)
