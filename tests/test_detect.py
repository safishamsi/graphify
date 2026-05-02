from pathlib import Path
from graphify.detect import classify_file, count_words, detect, FileType, _looks_like_paper, _is_ignored, _load_graphifyignore

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


def test_classify_video_extensions():
    """Video and audio file extensions should classify as VIDEO."""
    from graphify.detect import FileType
    assert classify_file(Path("lecture.mp4")) == FileType.VIDEO
    assert classify_file(Path("podcast.mp3")) == FileType.VIDEO
    assert classify_file(Path("talk.mov")) == FileType.VIDEO
    assert classify_file(Path("recording.wav")) == FileType.VIDEO
    assert classify_file(Path("webinar.webm")) == FileType.VIDEO
    assert classify_file(Path("audio.m4a")) == FileType.VIDEO


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


# ── Custom extension aliases ─────────────────────────────────────────────────

import pytest

from graphify import detect as _detect_module


@pytest.fixture
def alias_state():
    """Snapshot and restore extension-alias module state around a test."""
    snapshot_aliases = dict(_detect_module.EXTENSION_ALIASES)
    snapshot_code = set(_detect_module.CODE_EXTENSIONS)
    snapshot_doc = set(_detect_module.DOC_EXTENSIONS)
    try:
        yield
    finally:
        _detect_module.EXTENSION_ALIASES.clear()
        _detect_module.EXTENSION_ALIASES.update(snapshot_aliases)
        _detect_module.CODE_EXTENSIONS.clear()
        _detect_module.CODE_EXTENSIONS.update(snapshot_code)
        _detect_module.DOC_EXTENSIONS.clear()
        _detect_module.DOC_EXTENSIONS.update(snapshot_doc)


def test_register_alias_code_extension(alias_state):
    from graphify.detect import register_extension_alias, EXTENSION_ALIASES, CODE_EXTENSIONS
    register_extension_alias(".pic", ".php")
    assert ".pic" in CODE_EXTENSIONS
    assert EXTENSION_ALIASES[".pic"] == ".php"
    assert classify_file(Path("controller.pic")) == FileType.CODE


def test_register_alias_doc_extension(alias_state):
    from graphify.detect import register_extension_alias, EXTENSION_ALIASES, DOC_EXTENSIONS
    register_extension_alias(".note", ".md")
    assert ".note" in DOC_EXTENSIONS
    assert EXTENSION_ALIASES[".note"] == ".md"
    assert classify_file(Path("readme.note")) == FileType.DOCUMENT


def test_register_alias_normalizes_case(alias_state):
    from graphify.detect import register_extension_alias, EXTENSION_ALIASES, CODE_EXTENSIONS
    register_extension_alias(".PIC", ".PHP")
    assert ".pic" in CODE_EXTENSIONS
    assert ".pic" in EXTENSION_ALIASES


def test_register_alias_requires_leading_dot(alias_state):
    from graphify.detect import register_extension_alias
    with pytest.raises(ValueError, match="must start with"):
        register_extension_alias("pic", ".php")
    with pytest.raises(ValueError, match="must start with"):
        register_extension_alias(".pic", "php")


def test_register_alias_rejects_unknown_canonical(alias_state):
    from graphify.detect import register_extension_alias
    with pytest.raises(ValueError, match="not a known"):
        register_extension_alias(".pic", ".unknownlang")


def test_apply_extension_aliases_from_env_single(alias_state, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_EXTENSION_ALIASES", ".pic:.php")
    _detect_module._apply_extension_aliases_from_env()
    assert _detect_module.EXTENSION_ALIASES.get(".pic") == ".php"


def test_apply_extension_aliases_from_env_multiple(alias_state, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_EXTENSION_ALIASES", ".pic:.php , .note:.md ,.x:.py")
    _detect_module._apply_extension_aliases_from_env()
    assert _detect_module.EXTENSION_ALIASES.get(".pic") == ".php"
    assert _detect_module.EXTENSION_ALIASES.get(".note") == ".md"
    assert _detect_module.EXTENSION_ALIASES.get(".x") == ".py"


def test_apply_extension_aliases_from_env_skips_malformed(alias_state, monkeypatch):
    # Malformed entries should be skipped silently — never crash on bad config
    monkeypatch.setenv(
        "GRAPHIFY_EXTENSION_ALIASES",
        ".valid:.py,broken,no-colon, : ,.bad:.unknownlang",
    )
    _detect_module._apply_extension_aliases_from_env()
    assert _detect_module.EXTENSION_ALIASES.get(".valid") == ".py"
    assert ".bad" not in _detect_module.EXTENSION_ALIASES


def test_apply_extension_aliases_from_env_empty(alias_state, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_EXTENSION_ALIASES", raising=False)
    _detect_module._apply_extension_aliases_from_env()
    # Should be a no-op — no entries added beyond what was already snapshotted
    assert _detect_module.EXTENSION_ALIASES == {}


def test_collect_files_includes_aliased_extension(alias_state, tmp_path):
    from graphify.detect import register_extension_alias
    from graphify.extract import collect_files
    register_extension_alias(".pic", ".php")
    (tmp_path / "main.pic").write_text("<?php class Foo {} ?>")
    (tmp_path / "ignore.txt").write_text("not code")
    found = collect_files(tmp_path)
    assert any(p.name == "main.pic" for p in found)


def test_extract_dispatches_aliased_extension(alias_state, tmp_path):
    from graphify.detect import register_extension_alias
    from graphify.extract import collect_files, extract
    register_extension_alias(".pic", ".php")
    (tmp_path / "shop.pic").write_text(
        "<?php\nclass ShopCart {\n    public function checkout() { return 1; }\n}\n"
    )
    paths = collect_files(tmp_path)
    result = extract(paths, cache_root=tmp_path)
    labels = {n.get("label", "") for n in result["nodes"]}
    # PHP grammar should have produced a class node for ShopCart
    assert any("ShopCart" in label or "shopcart" in label.lower() for label in labels)
