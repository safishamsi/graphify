from pathlib import Path
from graphify.detect import classify_file, count_words, detect, FileType, _looks_like_paper, _is_path_ignored, _load_graphifyignore, _match_ignore_pattern

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


def test_graphifyignore_negation(tmp_path):
    """Support ! negation patterns in .graphifyignore."""
    (tmp_path / ".graphifyignore").write_text("*.py\n!important.py\n")
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "important.py").write_text("print('important')")
    (tmp_path / "other.py").write_text("print('other')")

    result = detect(tmp_path)
    file_list = result["files"]["code"]

    # important.py should be included because of !important.py
    assert any("important.py" in f for f in file_list)
    # main.py and other.py should be ignored because of *.py
    assert not any("main.py" in f for f in file_list)
    assert not any("other.py" in f for f in file_list)


def test_graphifyignore_trailing_slash_directory_only(tmp_path):
    """Trailing / means directory-only: ignored/ prunes the dir but does NOT match a file named ignored.py."""
    (tmp_path / ".graphifyignore").write_text("ignored/\n")

    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "skip.py").write_text("skip")
    (tmp_path / "ignored.py").write_text("this is a file named ignored.py")
    (tmp_path / "main.py").write_text("x = 1")

    result = detect(tmp_path)
    file_list = result["files"]["code"]

    # The directory and all its contents are pruned
    assert not any("skip.py" in f for f in file_list)
    # But a FILE named ignored.py is NOT excluded (trailing / means dirs only)
    assert any("ignored.py" in f for f in file_list)
    assert any("main.py" in f for f in file_list)


def test_graphifyignore_reinclude_requires_wildcard(tmp_path):
    """Per gitignore spec, re-including a file inside an excluded dir requires dir/* not dir/.

    ignored/ prunes the directory entirely — !ignored/keep.py has no effect.
    The correct pattern is ignored/* (exclude contents) + !ignored/keep.py.
    """
    (tmp_path / ".graphifyignore").write_text("ignored/*\n!ignored/keep.py\n")

    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "skip.py").write_text("skip")
    (ignored_dir / "keep.py").write_text("keep")

    result = detect(tmp_path)
    file_list = result["files"]["code"]

    # keep.py is re-included because ignored/* doesn't prune the directory itself
    assert any("keep.py" in f for f in file_list)
    assert not any("skip.py" in f for f in file_list)


def test_graphifyignore_negation_reproducer(tmp_path):
    """Issue #628 reproducer: broad glob excludes specific paths, ! re-includes vetted file."""    
    (tmp_path / ".graphifyignore").write_text("**/*vetted*\n!**/src/lib/vetted.ts\n")
    src_lib = tmp_path / "src" / "lib"
    src_lib.mkdir(parents=True)
    (src_lib / "vetted.ts").write_text("// SDK wrapper - no actual secrets")
    # Another file that also matches **/*vetted* but is NOT re-included
    (tmp_path / "src" / "my-vetted.ts").write_text("vetted=abc")

    result = detect(tmp_path)
    file_list = result["files"]["code"]

    # src/lib/vetted.ts is re-included by the ! pattern
    assert any("vetted.ts" in f and "lib" in f for f in file_list)
    # src/my-vetted.ts matches **/*vetted* and stays excluded
    assert not any("my-vetted.ts" in f for f in file_list)

def test_graphifyignore_parent_negation_reinclude(tmp_path):
    """Parent .graphifyignore wildcard + negation applies to subdirectory scans.

    Uses vendor/* (not vendor/) so the directory is traversed and keep.py can be re-included.
    A VCS root (.git) is present so the upward walk reaches the parent ignore file.
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".graphifyignore").write_text("vendor/*\n!vendor/keep.py\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    vendor = sub / "vendor"
    vendor.mkdir()
    (vendor / "dep.py").write_text("y = 2")
    (vendor / "keep.py").write_text("z = 3")
    (sub / "main.py").write_text("x = 1")

    result = detect(sub)
    code_files = result["files"]["code"]

    assert any("main.py" in f for f in code_files)
    assert any("keep.py" in f for f in code_files)
    assert not any("dep.py" in f for f in code_files)


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


def test_graphifyignore_discovered_from_parent(tmp_path):
    """A .graphifyignore in a VCS-rooted parent directory applies to subdirectory scans."""
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


def test_graphifyignore_stops_at_project_boundary(tmp_path):
    """Upward search stops at the first recognised project-root marker."""
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


def test_graphifyignore_stops_at_non_git_boundary(tmp_path):
    """Without a VCS root, scan root is the ceiling — outer ignore files are not loaded."""
    (tmp_path / ".graphifyignore").write_text("main.py\n")
    sub = tmp_path / "project" / "src"
    sub.mkdir(parents=True)
    (sub / "main.py").write_text("x = 1")

    result = detect(sub)
    code_files = result["files"]["code"]
    assert any("main.py" in f for f in code_files)
    assert result["graphifyignore_patterns"] == 0


def test_graphifyignore_monorepo_walks_past_package_json(tmp_path):
    """In a monorepo, package.json in a sub-package does not stop the walk;
    the .git root boundary is always honoured."""
    repo = tmp_path / "monorepo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".graphifyignore").write_text("*.log\n")
    pkg = repo / "packages" / "my-lib"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text("{}\n")
    src = pkg / "src"
    src.mkdir()
    (src / "index.ts").write_text("export default 1;")
    (src / "debug.log").write_text("log")

    result = detect(src)
    assert result["graphifyignore_patterns"] == 1


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


# ---------------------------------------------------------------------------
# _match_ignore_pattern unit tests — cover standard ignore categories
# ---------------------------------------------------------------------------

def test_ignore_pattern_double_star_leading():
    """`**/foo` matches foo at any depth including root."""
    assert _match_ignore_pattern("foo.py", "**/foo.py", is_dir=False)
    assert _match_ignore_pattern("src/foo.py", "**/foo.py", is_dir=False)
    assert _match_ignore_pattern("a/b/c/foo.py", "**/foo.py", is_dir=False)
    assert not _match_ignore_pattern("foo.ts", "**/foo.py", is_dir=False)


def test_ignore_pattern_double_star_trailing():
    """`logs/**` matches everything inside logs/."""
    assert _match_ignore_pattern("logs/app.log", "logs/**", is_dir=False)
    assert _match_ignore_pattern("logs/2024/app.log", "logs/**", is_dir=False)
    assert not _match_ignore_pattern("logs", "logs/**", is_dir=True)
    assert not _match_ignore_pattern("other/app.log", "logs/**", is_dir=False)


def test_ignore_pattern_double_star_middle():
    """`a/**/b` matches a/b, a/x/b, a/x/y/b — zero or more intermediate dirs."""
    assert _match_ignore_pattern("a/b", "a/**/b", is_dir=False)
    assert _match_ignore_pattern("a/x/b", "a/**/b", is_dir=False)
    assert _match_ignore_pattern("a/x/y/b", "a/**/b", is_dir=False)
    assert not _match_ignore_pattern("b", "a/**/b", is_dir=False)
    # a/b is matched by a/**/b, so any file inside a/b (like a/b/c) is ignored.
    assert _match_ignore_pattern("a/b/c", "a/**/b", is_dir=False)


def test_ignore_pattern_double_star_non_special():
    """`foo**/bar` — ** not after / is treated as *."""
    assert _match_ignore_pattern("foo/bar", "foo**/bar", is_dir=False)
    assert _match_ignore_pattern("fooxyz/bar", "foo**/bar", is_dir=False)
    # ** treated as *, so it cannot cross a second /
    assert not _match_ignore_pattern("foo/baz/bar", "foo**/bar", is_dir=False)


def test_ignore_pattern_leading_slash_anchored():
    """`/main.py` is anchored to root — does not match src/main.py."""
    assert _match_ignore_pattern("main.py", "/main.py", is_dir=False)
    assert not _match_ignore_pattern("src/main.py", "/main.py", is_dir=False)
    assert not _match_ignore_pattern("a/b/main.py", "/main.py", is_dir=False)


def test_ignore_pattern_trailing_slash_not_file():
    """`vendor/` must NOT match a file named vendor.py."""
    assert not _match_ignore_pattern("vendor.py", "vendor/", is_dir=False)
    assert not _match_ignore_pattern("vendors.py", "vendor/", is_dir=False)
    # But it does match the directory itself and files inside
    assert _match_ignore_pattern("vendor", "vendor/", is_dir=True)
    assert _match_ignore_pattern("vendor/lib.py", "vendor/", is_dir=False)


def test_ignore_pattern_question_mark_wildcard():
    """`?` matches exactly one character except /."""
    assert _match_ignore_pattern("a.py", "?.py", is_dir=False)
    assert not _match_ignore_pattern("ab.py", "?.py", is_dir=False)
    # ?.py is unanchored, so it matches any file whose basename matches ?.py.
    # a/b.py has basename b.py which matches ?.py.
    assert _match_ignore_pattern("a/b.py", "?.py", is_dir=False)
    assert _match_ignore_pattern("foo", "f?o", is_dir=False)
    assert not _match_ignore_pattern("fo", "f?o", is_dir=False)


def test_ignore_pattern_character_class():
    """`[abc].py` matches a.py, b.py, c.py but not d.py."""
    assert _match_ignore_pattern("a.py", "[abc].py", is_dir=False)
    assert _match_ignore_pattern("b.py", "[abc].py", is_dir=False)
    assert _match_ignore_pattern("c.py", "[abc].py", is_dir=False)
    assert not _match_ignore_pattern("d.py", "[abc].py", is_dir=False)
    assert not _match_ignore_pattern("ab.py", "[abc].py", is_dir=False)


def test_ignore_pattern_negated_character_class():
    """`[!abc].py` matches any single char except a, b, c before .py."""
    assert _match_ignore_pattern("d.py", "[!abc].py", is_dir=False)
    assert _match_ignore_pattern("z.py", "[!abc].py", is_dir=False)
    assert not _match_ignore_pattern("a.py", "[!abc].py", is_dir=False)
    assert not _match_ignore_pattern("b.py", "[!abc].py", is_dir=False)


def test_ignore_pattern_single_star_no_cross_slash():
    """`src/*.py` matches src/foo.py but NOT src/lib/foo.py (* can't cross /)."""
    assert _match_ignore_pattern("src/foo.py", "src/*.py", is_dir=False)
    assert not _match_ignore_pattern("src/lib/foo.py", "src/*.py", is_dir=False)
    assert not _match_ignore_pattern("foo.py", "src/*.py", is_dir=False)
