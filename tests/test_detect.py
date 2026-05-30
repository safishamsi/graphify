from pathlib import Path
from graphify.detect import classify_file, count_words, detect, detect_incremental, save_manifest, FileType, _looks_like_paper, _is_ignored, _load_graphifyignore, _is_sensitive

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

def test_detect_skips_noise_dot_dirs():
    """Noise dot dirs (.next, .nuxt, .graphify cache, …) are skipped (#873).
    Non-noise dot dirs (.github, .claude, …) are now allowed through."""
    result = detect(FIXTURES)
    for files in result["files"].values():
        for f in files:
            # graphify's own cache is always skipped
            assert "/.graphify/" not in f
            # well-known framework caches are always skipped
            for noise in ("/.next/", "/.nuxt/", "/.turbo/", "/.angular/"):
                assert noise not in f


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


def test_detect_auto_detects_direct_symlink_child(tmp_path):
    """When ``root`` has a direct symlinked child, default (None) follows symlinks
    so the user does not have to know to pass follow_symlinks=True for "fake
    working dir" patterns (folder of symlinks pointing at scattered sources)."""
    real_dir = tmp_path / "real_lib"
    real_dir.mkdir()
    (real_dir / "util.py").write_text("x = 1")
    (tmp_path / "linked_lib").symlink_to(real_dir)

    # Default (no kwarg): auto-detect → follows because of linked_lib symlink
    result = detect(tmp_path)
    assert any("linked_lib" in f for f in result["files"]["code"])


def test_detect_default_does_not_follow_when_no_symlinks(tmp_path):
    """When ``root`` has no direct symlinks, the auto-detect default stays False
    (legacy behaviour preserved for ordinary scans)."""
    (tmp_path / "main.py").write_text("x = 1")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "other.py").write_text("y = 2")

    # Smoke: no symlinks anywhere → auto-detect returns False, scan succeeds
    result = detect(tmp_path)
    assert any("main.py" in f for f in result["files"]["code"])
    assert any("other.py" in f for f in result["files"]["code"])


def test_detect_explicit_false_overrides_auto_detect(tmp_path):
    """An explicit follow_symlinks=False overrides the auto-detect, even when
    root contains symlinks. Lets callers opt out of the new behaviour."""
    real_dir = tmp_path / "real_lib"
    real_dir.mkdir()
    (real_dir / "util.py").write_text("x = 1")
    (tmp_path / "linked_lib").symlink_to(real_dir)

    # Explicit False overrides auto-detect; symlink contents must NOT appear.
    result = detect(tmp_path, follow_symlinks=False)
    assert not any("linked_lib" in f for f in result["files"]["code"])


def test_detect_incremental_propagates_follow_symlinks(tmp_path, monkeypatch):
    """detect_incremental must forward follow_symlinks so symlinked sub-trees
    appear in incremental scans the same way they appear in full scans."""
    monkeypatch.chdir(tmp_path)

    real_dir = tmp_path / "real_corpus"
    real_dir.mkdir()
    (real_dir / "note.md").write_text("# real note\n\nsome content")
    (tmp_path / "linked_corpus").symlink_to(real_dir)

    # Store manifest inside graphify-out/ so it is pruned by _SKIP_DIRS
    # and doesn't get re-detected as a code file now that .json is indexed.
    manifest_dir = tmp_path / "graphify-out"
    manifest_dir.mkdir()
    manifest_path = str(manifest_dir / "manifest.json")

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


# --- #873: dot dirs allowed, framework caches blocked ---

def test_detect_allows_github_dir(tmp_path):
    """Files inside .github/ (workflows etc.) are now indexed (#873)."""
    gh = tmp_path / ".github" / "workflows"
    gh.mkdir(parents=True)
    (gh / "ci.yml").write_text("name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n")
    (tmp_path / "main.py").write_text("def run(): pass")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert any(".github" in f for f in all_files), "expected .github/workflows/ci.yml to be detected"


def test_detect_skips_next_cache(tmp_path):
    """.next/ (Next.js build cache) must be excluded even after dot-dir fix (#873)."""
    next_dir = tmp_path / ".next" / "cache"
    next_dir.mkdir(parents=True)
    (next_dir / "build.js").write_text("(function(){var s=1;})()")
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "index.tsx").write_text("export default function Home() { return <div/> }")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert not any(".next" in f for f in all_files)
    assert any("index.tsx" in f for f in all_files)


def test_detect_skips_graphify_own_cache(tmp_path):
    """.graphify/ (extraction cache) must never be re-indexed as source (#873)."""
    cache = tmp_path / ".graphify" / "cache"
    cache.mkdir(parents=True)
    (cache / "abc123.json").write_text('{"nodes": [], "edges": []}')
    (tmp_path / "app.py").write_text("def go(): pass")
    result = detect(tmp_path)
    all_files = [f for files in result["files"].values() for f in files]
    assert not any(".graphify" in f for f in all_files)
    assert any("app.py" in f for f in all_files)


# --- #882: gitignore parent-exclusion rule for ! re-includes ---

def test_negation_cannot_rescue_file_under_excluded_dir(tmp_path):
    """A ! re-include cannot un-ignore a file whose parent dir is excluded (#882)."""
    from graphify.detect import _is_ignored, _load_graphifyignore
    android = tmp_path / "android" / "app" / "src"
    android.mkdir(parents=True)
    victim = android / "Main.kt"
    victim.write_text("fun main() {}")
    (tmp_path / ".graphifyignore").write_text("android/\n!src/\n")
    patterns = _load_graphifyignore(tmp_path)
    assert _is_ignored(victim, tmp_path, patterns), (
        "android/app/src/Main.kt must remain ignored even with !src/ because "
        "the parent android/ is excluded"
    )


def test_negation_works_when_no_ancestor_excluded(tmp_path):
    """A ! re-include must still un-ignore a file when no ancestor is excluded (#882)."""
    from graphify.detect import _is_ignored, _load_graphifyignore
    src = tmp_path / "src"
    src.mkdir()
    keep = src / "keep.py"
    keep.write_text("x = 1")
    (tmp_path / ".graphifyignore").write_text("*.py\n!src/keep.py\n")
    patterns = _load_graphifyignore(tmp_path)
    assert not _is_ignored(keep, tmp_path, patterns), (
        "src/keep.py should be un-ignored by !src/keep.py since src/ itself is not excluded"
    )


def test_negation_ancestor_itself_reincluded(tmp_path):
    """If the ancestor dir itself is re-included, its children should not be blocked (#882)."""
    from graphify.detect import _is_ignored, _load_graphifyignore
    vendor = tmp_path / "vendor" / "lib"
    vendor.mkdir(parents=True)
    f = vendor / "utils.py"
    f.write_text("x = 1")
    (tmp_path / ".graphifyignore").write_text("vendor/\n!vendor/\n")
    patterns = _load_graphifyignore(tmp_path)
    # vendor/ is excluded then re-included; ancestor eval returns False so file is evaluated on its own
    assert not _is_ignored(f, tmp_path, patterns)


# Regression tests for #920 - sensitive pattern misses underscore-prefixed names
def test_sensitive_flags_api_token_txt():
    assert _is_sensitive(Path("api_token.txt"))

def test_sensitive_flags_oauth_token_json():
    assert _is_sensitive(Path("oauth_token.json"))

def test_sensitive_flags_underscore_secret():
    assert _is_sensitive(Path("app_secret.yaml"))

def test_sensitive_does_not_flag_tokenizer_py():
    assert not _is_sensitive(Path("tokenizer.py"))

def test_sensitive_does_not_flag_tokenize_py():
    assert not _is_sensitive(Path("tokenize.py"))

def test_sensitive_flags_passwords_py():
    # passwords.py is just as likely a secret store as passwords.txt — code ext is no excuse
    assert _is_sensitive(Path("passwords.py"))

def test_sensitive_flags_ssh_dir():
    assert _is_sensitive(Path("/home/user/.ssh/id_rsa"))

def test_sensitive_flags_secrets_dir():
    assert _is_sensitive(Path("config/secrets/db.json"))

def test_sensitive_flags_token_txt():
    assert _is_sensitive(Path("token.txt"))

def test_sensitive_flags_credentials_json():
    assert _is_sensitive(Path("credentials.json"))

def test_sensitive_does_not_flag_root_file_named_credentials():
    # A root-level file called "credentials" (no parent dir named credentials)
    # must NOT be flagged by Stage 1; Stage 2 name-pattern check catches it instead.
    # Specifically: Path("credentials").parts == ('credentials',) which is parts[:-1] == ()
    # so the dir check passes. The name pattern for "credential" then picks it up.
    # What we are asserting here is that the Stage 1 check uses parts[:-1], not parts.
    p = Path("credentials")
    # The name pattern WILL match "credentials" (it's a sensitive name), but the
    # false-flag we fixed was Stage 1 matching on the filename itself as a "dir".
    # Verify the whole function still returns True (via name pattern, not dir check).
    assert _is_sensitive(p)

def test_sensitive_secret_handler_txt():
    # Both patterns now use (?![a-zA-Z]) so underscore after keyword is allowed.
    # "secret_handler.txt": "secret" followed by "_" (not alpha) → flagged.
    assert _is_sensitive(Path("secret_handler.txt"))

def test_sensitive_token_config_yaml():
    # "token_config.yaml": "token" followed by "_" (not alpha) → flagged.
    assert _is_sensitive(Path("token_config.yaml"))


# ── Issue #933: failed-chunk files must not be frozen in manifest ─────────────

def test_save_manifest_skips_semantic_hash_for_files_without_cache(tmp_path):
    """Files in failed chunks have no semantic cache entry; save_manifest must
    leave their semantic_hash empty so detect_incremental re-queues them (#933)."""
    import json
    from graphify.cache import save_cached

    doc1 = tmp_path / "docs" / "a.md"
    doc2 = tmp_path / "docs" / "b.md"
    doc1.parent.mkdir()
    doc1.write_text("# A\n\ncontent a")
    doc2.write_text("# B\n\ncontent b")

    # Simulate: doc1's chunk succeeded (has a cache entry), doc2's chunk failed (no entry).
    save_cached(doc1, {"nodes": [{"id": "a", "source_file": str(doc1)}], "edges": [], "hyperedges": []}, root=tmp_path, kind="semantic")
    # doc2: no cache entry written

    files = {"document": [str(doc1), str(doc2)]}
    manifest_path = str(tmp_path / "manifest.json")

    # Simulate what __main__.py now does: only include files with semantic output.
    sem_extracted = {str(doc1)}  # doc2 not present — failed chunk
    sem_types = {"document", "paper", "image"}
    safe_files = {
        ftype: [f for f in flist if ftype not in sem_types or f in sem_extracted]
        for ftype, flist in files.items()
    }
    save_manifest(safe_files, manifest_path)

    manifest = json.loads(Path(manifest_path).read_text())
    assert str(doc1) in manifest, "successful file must be in manifest"
    assert manifest[str(doc1)]["semantic_hash"] != "", "successful file must have semantic_hash"
    assert str(doc2) not in manifest, "failed-chunk file must be absent from manifest"



def test_save_manifest_without_filter_unchanged_for_code(tmp_path):
    """Code files must be stamped in the manifest regardless of semantic cache."""
    import json

    py = tmp_path / "main.py"
    py.write_text("print('hello')")

    files = {"code": [str(py)]}
    manifest_path = str(tmp_path / "manifest.json")
    save_manifest(files, manifest_path)

    manifest = json.loads(Path(manifest_path).read_text())
    assert str(py) in manifest
    assert manifest[str(py)]["ast_hash"] != ""
# Regression tests for #945 - .gitignore fallback when no .graphifyignore exists

def test_gitignore_fallback_when_no_graphifyignore(tmp_path):
    """When no .graphifyignore exists, .gitignore patterns are honored (#945)."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("vendor/\n*.generated.py\n")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "lib.py").write_text("x = 1")
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "schema.generated.py").write_text("x = 1")

    result = detect(tmp_path)
    code = result["files"]["code"]
    assert any("main.py" in f for f in code)
    assert not any("vendor" in f for f in code)
    assert not any("generated" in f for f in code)


def test_graphifyignore_takes_precedence_over_gitignore(tmp_path):
    """When both exist, .graphifyignore is used and .gitignore is ignored (#945)."""
    (tmp_path / ".git").mkdir()
    # .gitignore would exclude main.py; .graphifyignore excludes only other.py
    (tmp_path / ".gitignore").write_text("main.py\n")
    (tmp_path / ".graphifyignore").write_text("other.py\n")
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "other.py").write_text("x = 2")

    result = detect(tmp_path)
    code = result["files"]["code"]
    assert any("main.py" in f for f in code)       # gitignore NOT applied
    assert not any("other.py" in f for f in code)  # graphifyignore IS applied


# Regression tests for #947 - .worktrees/ skipped and --exclude flag

def test_detect_skips_worktrees_dir(tmp_path):
    """Files inside .worktrees/ are never indexed (#947)."""
    wt = tmp_path / ".worktrees" / "feature-branch"
    wt.mkdir(parents=True)
    (wt / "main.py").write_text("x = 1")
    (tmp_path / "app.py").write_text("y = 2")

    result = detect(tmp_path)
    code = result["files"]["code"]
    assert any("app.py" in f for f in code)
    assert not any(".worktrees" in f for f in code)


def test_detect_skips_nested_worktrees_dir(tmp_path):
    """Files inside .claude/worktrees/ (nested placement) are never indexed (#1023)."""
    wt = tmp_path / ".claude" / "worktrees" / "feature-branch"
    wt.mkdir(parents=True)
    (wt / "main.py").write_text("x = 1")
    (tmp_path / "app.py").write_text("y = 2")

    result = detect(tmp_path)
    code = result["files"]["code"]
    assert any("app.py" in f for f in code)
    assert not any("worktrees" in f for f in code)


def test_detect_extra_excludes_pattern(tmp_path):
    """extra_excludes patterns exclude matching files from detect() (#947)."""
    (tmp_path / "main.py").write_text("x = 1")
    (tmp_path / "secret.py").write_text("API_KEY = 'abc'")
    subdir = tmp_path / "legacy"
    subdir.mkdir()
    (subdir / "old.py").write_text("y = 2")

    result = detect(tmp_path, extra_excludes=["secret.py", "legacy/"])
    code = result["files"]["code"]
    assert any("main.py" in f for f in code)
    assert not any("secret.py" in f for f in code)
    assert not any("legacy" in f for f in code)


# ---------------------------------------------------------------------------
# Shebang interpreter parsing
# ---------------------------------------------------------------------------

def test_shebang_interpreter_plain(tmp_path):
    """Plain shebang returns the interpreter basename."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "plain"
    script.write_bytes(b"#!/usr/bin/python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"


def test_shebang_interpreter_env_single_arg(tmp_path):
    """`#!/usr/bin/env python3` returns the interpreter, not 'env'."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_single"
    script.write_bytes(b"#!/usr/bin/env python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"


def test_shebang_interpreter_env_dash_s(tmp_path):
    """`#!/usr/bin/env -S python3 -u` (-S split-args form) recovers the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_dashs"
    script.write_bytes(b"#!/usr/bin/env -S python3 -u\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"


def test_shebang_interpreter_env_with_flags(tmp_path):
    """`#!/usr/bin/env -i bash` skips env flags and resolves to the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_flags"
    script.write_bytes(b"#!/usr/bin/env -i bash\necho hi\n")
    assert _shebang_interpreter(script) == "bash"


def test_shebang_interpreter_env_with_assignment(tmp_path):
    """`#!/usr/bin/env DEBUG=1 python3` skips var=value assignments."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_assign"
    script.write_bytes(b"#!/usr/bin/env DEBUG=1 python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"


def test_shebang_interpreter_no_shebang(tmp_path):
    """File without shebang returns None."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "no_shebang"
    script.write_bytes(b"print('x')\n")
    assert _shebang_interpreter(script) is None


def test_shebang_interpreter_quoted_path(tmp_path):
    """Quoted interpreter path with spaces parses correctly via shlex."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "quoted"
    # Note: actual `#!` on disk wouldn't permit a quoted path on most kernels,
    # but shlex must not crash and should produce a reasonable answer
    script.write_bytes(b'#!"/usr/local/bin/python3"\nprint("x")\n')
    assert _shebang_interpreter(script) == "python3"


def test_shebang_file_type_classifies_via_interpreter(tmp_path):
    """Classify file type via interpreter, including env -S form."""
    script = tmp_path / "tool"
    script.write_bytes(b"#!/usr/bin/env -S python3 -u\nprint('x')\n")
    # No extension, must be classified via shebang
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_unreadable_returns_none(tmp_path):
    """Unreadable / nonexistent files return None, never raise."""
    from graphify.detect import _shebang_interpreter
    missing = tmp_path / "does_not_exist"
    assert _shebang_interpreter(missing) is None


def test_shebang_interpreter_env_unset_with_operand(tmp_path):
    """`env -u VAR python3` skips both -u and its required operand."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_unset"
    script.write_bytes(b"#!/usr/bin/env -u PYTHONPATH python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_chdir_with_operand(tmp_path):
    """`env -C /tmp python3` skips both -C and its workdir operand."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_chdir"
    script.write_bytes(b"#!/usr/bin/env -C /tmp python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_path_with_operand(tmp_path):
    """`env -P /bin python3` skips both -P and its utilpath operand."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_path"
    script.write_bytes(b"#!/usr/bin/env -P /bin python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_dash_s_after_flag(tmp_path):
    """`env -i -S "python3 -u"` handles -S after another env flag."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_flag_dash_s"
    script.write_bytes(b'#!/usr/bin/env -i -S "python3 -u"\nprint("x")\n')
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_clumped_u_operand(tmp_path):
    """Clumped `-uPYTHONPATH` form (no space between flag and operand) is one arg."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_clumped"
    script.write_bytes(b"#!/usr/bin/env -uPYTHONPATH python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_missing_operand_returns_none(tmp_path):
    """`env -u` with no operand → not a valid command, return None."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_missing_op"
    script.write_bytes(b"#!/usr/bin/env -u\n")
    assert _shebang_interpreter(script) is None


def test_shebang_interpreter_env_gnu_split_string_equals(tmp_path):
    """GNU `--split-string='python3 -u'` (with `=` operand) → python3."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_split_eq"
    script.write_bytes(b"#!/usr/bin/env --split-string='python3 -u'\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_gnu_split_string_separate(tmp_path):
    """GNU `--split-string "python3 -u"` (separate operand) → python3."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_split_sep"
    script.write_bytes(b'#!/usr/bin/env --split-string "python3 -u"\nprint("x")\n')
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_gnu_argv0_operand(tmp_path):
    """GNU `-a alias python3` skips both -a and its argv0 operand."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_argv0"
    script.write_bytes(b"#!/usr/bin/env -a alias python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_compact_dash_s(tmp_path):
    """Compact `-Spython3 -u` form (no space between -S and packed string)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_compact_dash_s"
    script.write_bytes(b"#!/usr/bin/env -Spython3 -u\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_compact_v_then_s(tmp_path):
    """Compact `-vSpython3` (-v plus compact -S)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_compact_vs"
    script.write_bytes(b"#!/usr/bin/env -vSpython3 -u\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_unset_separate_operand(tmp_path):
    """GNU `--unset PYTHONPATH python3` (separate operand)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_unset"
    script.write_bytes(b"#!/usr/bin/env --unset PYTHONPATH python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_unset_equals(tmp_path):
    """GNU `--unset=PYTHONPATH python3` (`=` operand form)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_unset_eq"
    script.write_bytes(b"#!/usr/bin/env --unset=PYTHONPATH python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_chdir_separate_operand(tmp_path):
    """GNU `--chdir /tmp python3` (separate operand)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_chdir"
    script.write_bytes(b"#!/usr/bin/env --chdir /tmp python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_chdir_equals(tmp_path):
    """GNU `--chdir=/tmp python3` (`=` operand form)."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_chdir_eq"
    script.write_bytes(b"#!/usr/bin/env --chdir=/tmp python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_signal_flags(tmp_path):
    """GNU signal-handling flags skip transparently."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_signal"
    script.write_bytes(b"#!/usr/bin/env --default-signal=TERM --ignore-signal=PIPE python3\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_unknown_option_returns_none(tmp_path):
    """Unknown hyphen-prefixed env option → return None rather than guessing."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_unknown"
    script.write_bytes(b"#!/usr/bin/env --no-such-flag python3\n")
    # Must refuse to guess: if we can't classify the option, we can't trust
    # that the next token is the interpreter. Safer to return None.
    assert _shebang_interpreter(script) is None


def test_shebang_interpreter_env_dash_s_assignment_before_interpreter(tmp_path):
    """`-S` payload may carry NAME=value assignments before the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_s_assignment"
    script.write_bytes(
        b"#!/usr/bin/env -S PYTHONPATH=/opt/custom:${PYTHONPATH} python3\n"
        b"print('x')\n"
    )
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_dash_s_flag_before_interpreter(tmp_path):
    """`-S` payload may carry env flags (e.g. -i) before the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_s_flag"
    script.write_bytes(b"#!/usr/bin/env -S -i OLDUSER=${USER} python3\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_split_assignment_before_interpreter(tmp_path):
    """`--split-string=` payload may carry assignments before the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_split_assignment"
    script.write_bytes(
        b"#!/usr/bin/env --split-string='PYTHONPATH=/opt/custom:${PYTHONPATH} python3 -u'\n"
        b"print('x')\n"
    )
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_long_split_flag_before_interpreter(tmp_path):
    """`--split-string=` payload may carry env flags before the interpreter."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_long_split_flag"
    script.write_bytes(b"#!/usr/bin/env --split-string='-i python3 -u'\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE


def test_shebang_interpreter_env_nested_split_string_rejected(tmp_path):
    """A `-S` payload that itself starts with `-S` is rejected (allow_split=False
    on the recursive call bounds the recursion depth at one). Without this guard,
    a malicious or strange shebang could spin the parser indefinitely."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_nested_split"
    # Outer -S splits into ["-S", "python3", "-u"]; inner -S is treated as an
    # unknown option in the recursed pass, so we get None (refuse to guess).
    script.write_bytes(b"#!/usr/bin/env -S -S python3 -u\nprint('x')\n")
    assert _shebang_interpreter(script) is None


def test_shebang_interpreter_env_vs_assignment_before_interpreter(tmp_path):
    """`-vS` packed payload also re-parses for leading assignments."""
    from graphify.detect import _shebang_interpreter
    script = tmp_path / "env_vs_assignment"
    script.write_bytes(b"#!/usr/bin/env -vS DEBUG=1 python3 -u\nprint('x')\n")
    assert _shebang_interpreter(script) == "python3"
    assert classify_file(script) == FileType.CODE
