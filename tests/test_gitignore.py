"""Tests for .gitignore-aware detection in detect.py.

The implementation uses :mod:`pathspec` with the gitwildmatch flavor, so the
full git ignore syntax is supported: trailing-slash dir-only, leading-slash
anchored, ``**`` recursive globs, and ``!``-negation that re-includes
previously-ignored entries (last match wins, parent-first).

Note on git's documented limitation: a ``!`` rule cannot rescue a file from
an already-pruned parent directory. We follow git here — once a directory is
ignored, paths underneath cannot be re-included.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.detect import detect, _is_ignored, _load_gitignore, _load_graphifyignore


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_RESPECT_GITIGNORE", raising=False)
    yield


def _write(p: Path, content: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    """Make tmp_path look like a git repo so the loader anchors to it."""
    (tmp_path / ".git").mkdir()
    return tmp_path.resolve()


def _detected(root: Path) -> list[str]:
    """Return all detected file paths as posix strings relative to *root*."""
    result = detect(root)
    files = [f for files in result["files"].values() for f in files]
    return sorted(
        Path(f).resolve().relative_to(root.resolve()).as_posix()
        for f in files
    )


# ---------------------------------------------------------------------------
# Loader-level tests
# ---------------------------------------------------------------------------


def test_load_gitignore_returns_anchored_specs(tmp_path):
    """Loader returns (anchor_dir, PathSpec) pairs."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("dist/\n*.tmp\n# comment\n\n", encoding="utf-8")
    specs = _load_gitignore(root)
    assert len(specs) == 1
    anchor, spec = specs[0]
    assert anchor == root.resolve()
    # gitwildmatch keeps a Pattern object even for comments / blank lines, but
    # those have regex=None — count only real, matchable patterns.
    real = [p for p in spec.patterns if p.regex is not None]
    assert len(real) == 2


def test_no_gitignore_returns_empty(tmp_path):
    root = _project(tmp_path)
    assert _load_gitignore(root) == []


def test_env_opt_out(tmp_path, monkeypatch):
    """GRAPHIFY_RESPECT_GITIGNORE=0 disables gitignore loading entirely."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
    for falsy in ("0", "false", "no", "off"):
        monkeypatch.setenv("GRAPHIFY_RESPECT_GITIGNORE", falsy)
        assert _load_gitignore(root) == []
    monkeypatch.setenv("GRAPHIFY_RESPECT_GITIGNORE", "1")
    assert _load_gitignore(root) != []


def test_loader_walks_to_repo_root(tmp_path):
    """A .gitignore at the repo root is found even when scanning a subfolder."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    sub = root / "src"
    sub.mkdir()
    specs = _load_gitignore(sub)
    anchors = [a for a, _ in specs]
    assert root.resolve() in anchors


def test_nested_gitignore_loaded(tmp_path):
    """Nested .gitignore files inside the scan root are picked up too."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
    nested = root / "pkg" / ".gitignore"
    _write(nested, "*.cache\n")
    specs = _load_gitignore(root)
    anchors = {a for a, _ in specs}
    assert root.resolve() in anchors
    assert nested.parent.resolve() in anchors


# ---------------------------------------------------------------------------
# Full wildmatch syntax — these are the cases that fnmatch couldn't honor.
# ---------------------------------------------------------------------------


def test_negation_re_includes_file_at_same_level(tmp_path):
    """`!keep.py` re-includes a file that an earlier pattern would exclude.

    File-level negation works as long as the parent directory is not itself
    excluded (see :func:`test_negation_does_not_resurrect_pruned_directory`).
    """
    root = _project(tmp_path)
    (root / ".gitignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    _write(root / "noise.py")
    _write(root / "keep.py")
    _write(root / "doc.md")

    rel = _detected(root)
    assert "keep.py" in rel
    assert "doc.md" in rel
    assert "noise.py" not in rel


def test_double_star_glob(tmp_path):
    """`**/foo/` matches the directory at any depth."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("**/__generated__/\n", encoding="utf-8")
    _write(root / "a" / "__generated__" / "x.py")
    _write(root / "a" / "b" / "__generated__" / "y.py")
    _write(root / "a" / "b" / "real.py")

    rel = _detected(root)
    assert "a/b/real.py" in rel
    assert not any("__generated__" in f for f in rel)


def test_leading_slash_is_anchored(tmp_path):
    """`/build/` is anchored to the .gitignore's directory only."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("/build/\n", encoding="utf-8")
    _write(root / "build" / "out.py")
    # A nested directory named "build" must NOT be excluded.
    _write(root / "src" / "build" / "kept.py")

    rel = _detected(root)
    assert "src/build/kept.py" in rel
    assert not any(f.startswith("build/") for f in rel)


def test_trailing_slash_means_directory_only(tmp_path):
    """`foo/` matches a directory called foo, not a file called foo."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("logs/\n", encoding="utf-8")
    _write(root / "logs" / "app.py")
    # A file literally named "logs" must not be excluded.
    (root / "logs.md").write_text("# notes", encoding="utf-8")

    rel = _detected(root)
    assert "logs.md" in rel
    assert not any(f.startswith("logs/") for f in rel)


def test_nested_gitignore_overrides_parent(tmp_path):
    """A child .gitignore's negation re-includes a file the parent ignored.

    Both rules are file-level (`*.py`, `!important.py`), neither prunes a
    parent directory, so the negation actually fires.
    """
    root = _project(tmp_path)
    (root / ".gitignore").write_text("*.py\n", encoding="utf-8")
    sub = root / "deploy"
    sub.mkdir()
    (sub / ".gitignore").write_text("!important.py\n", encoding="utf-8")

    _write(root / "noise.py")
    _write(sub / "important.py")
    _write(sub / "trace.py")

    rel = _detected(root)
    assert "deploy/important.py" in rel
    assert "noise.py" not in rel
    assert "deploy/trace.py" not in rel


def test_negation_does_not_resurrect_pruned_directory(tmp_path):
    """Documented git limitation: !file inside an ignored dir cannot recover it.

    git's own docs spell this out — once the directory is excluded, paths
    inside it cannot be re-included. We honor the same rule because we
    prune ignored directories at os.walk time for performance.
    """
    root = _project(tmp_path)
    (root / ".gitignore").write_text("excluded/\n!excluded/keep.py\n", encoding="utf-8")
    _write(root / "excluded" / "keep.py")
    _write(root / "excluded" / "junk.py")
    _write(root / "src" / "main.py")

    rel = _detected(root)
    assert "src/main.py" in rel
    # excluded/ was pruned wholesale; this matches git's own behavior.
    assert not any(f.startswith("excluded/") for f in rel)


def test_user_negation_overrides_default_dotfile_skip(tmp_path):
    """A user `!.config/` rule re-includes a directory we'd otherwise skip."""
    # By default we prune dotfile directories. An explicit !-rule re-includes.
    root = _project(tmp_path)
    (root / ".gitignore").write_text("!.config/\n", encoding="utf-8")
    _write(root / ".config" / "settings.py")
    _write(root / "main.py")

    rel = _detected(root)
    assert "main.py" in rel
    assert ".config/settings.py" in rel


# ---------------------------------------------------------------------------
# Integration with detect()
# ---------------------------------------------------------------------------


def test_detect_excludes_gitignored_files(tmp_path):
    root = _project(tmp_path)
    (root / ".gitignore").write_text("ignored/\n*.secret\n", encoding="utf-8")

    _write(root / "kept.py", "print('hi')")
    _write(root / "kept.md", "# Kept")
    _write(root / "ignored" / "junk.py", "x = 1")
    _write(root / "leak.secret", "topsecret")

    rel = _detected(root)
    assert "kept.py" in rel
    assert "kept.md" in rel
    assert not any(f.startswith("ignored/") for f in rel)
    assert "leak.secret" not in rel


def test_detect_respects_opt_out(tmp_path, monkeypatch):
    root = _project(tmp_path)
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _write(root / "kept.py")
    _write(root / "ignored" / "junk.py")

    monkeypatch.setenv("GRAPHIFY_RESPECT_GITIGNORE", "0")
    rel = _detected(root)
    assert "kept.py" in rel
    assert any(f.startswith("ignored/") for f in rel)


def test_detect_combines_gitignore_and_graphifyignore(tmp_path):
    root = _project(tmp_path)
    (root / ".gitignore").write_text("from-git/\n", encoding="utf-8")
    (root / ".graphifyignore").write_text("from-graphify/\n", encoding="utf-8")

    _write(root / "kept.py")
    _write(root / "from-git" / "a.py")
    _write(root / "from-graphify" / "b.py")

    rel = _detected(root)
    assert "kept.py" in rel
    assert not any(f.startswith("from-git/") for f in rel)
    assert not any(f.startswith("from-graphify/") for f in rel)


def test_graphifyignore_supports_full_syntax(tmp_path):
    """The new pathspec backend lifts .graphifyignore to full gitwildmatch too.

    Uses file-level patterns (no dir-level pruning) so the negation actually
    fires within the same directory.
    """
    root = _project(tmp_path)
    (root / ".graphifyignore").write_text(
        "*.py\n"
        "!keep.py\n"
        "**/__cache__/\n",
        encoding="utf-8",
    )
    _write(root / "noise.py")
    _write(root / "keep.py")
    _write(root / "src" / "__cache__" / "x.py")
    _write(root / "src" / "kept.md")

    rel = _detected(root)
    assert "keep.py" in rel
    assert "src/kept.md" in rel
    assert "noise.py" not in rel
    assert not any("__cache__" in f for f in rel)


# ---------------------------------------------------------------------------
# Direct _is_ignored unit checks (without going through detect())
# ---------------------------------------------------------------------------


def test_is_ignored_returns_false_for_no_specs(tmp_path):
    """Empty spec list means no opinion — file is kept."""
    assert _is_ignored(tmp_path / "foo.py", []) is False


def test_is_ignored_outside_anchor_subtree(tmp_path):
    """A spec under subdir/ must not affect paths outside subdir/."""
    root = _project(tmp_path)
    (root / "subdir").mkdir()
    (root / "subdir" / ".gitignore").write_text("*.bin\n", encoding="utf-8")
    specs = _load_gitignore(root)

    inside = root / "subdir" / "blob.bin"
    outside = root / "blob.bin"
    _write(inside)
    _write(outside)

    assert _is_ignored(inside, specs) is True
    # Outside the anchor subtree no spec applies — file is kept.
    assert _is_ignored(outside, specs) is False


def test_is_ignored_dir_flag(tmp_path):
    """Passing is_dir=True lets dir-only patterns (`build/`) match the bare path."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("build/\n", encoding="utf-8")
    specs = _load_gitignore(root)
    build = root / "build"
    build.mkdir()

    # Without is_dir the trailing-slash pattern can't match the bare name.
    assert _is_ignored(build, specs, is_dir=False) is False
    # With is_dir the helper appends the slash so the pattern matches.
    assert _is_ignored(build, specs, is_dir=True) is True


def test_is_ignored_returns_false_on_negation(tmp_path):
    """A `!`-rule that fires last keeps the file (returns False)."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    specs = _load_gitignore(root)
    f = root / "keep.py"
    _write(f)
    assert _is_ignored(f, specs) is False


# ---------------------------------------------------------------------------
# Unified .gitignore + .graphifyignore handling.
#
# A .graphifyignore is just a renamed .gitignore for graphify-specific rules.
# Both files are loaded by the same discovery walk and feed the same matcher;
# the only ordering rule is that within a single directory, .gitignore is
# evaluated first and .graphifyignore second, so graphify-specific rules can
# override their co-located git rule via last-match-wins.
# ---------------------------------------------------------------------------


def test_graphifyignore_can_override_gitignore_at_same_anchor(tmp_path):
    """A `!` in .graphifyignore re-includes a path .gitignore tried to exclude.

    Both files live in the same directory; `.graphifyignore` is evaluated
    second, so its negation wins.
    """
    root = _project(tmp_path)
    (root / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (root / ".graphifyignore").write_text("!analytics.py\n", encoding="utf-8")
    _write(root / "noise.py")
    _write(root / "analytics.py")

    rel = _detected(root)
    assert "analytics.py" in rel
    assert "noise.py" not in rel


def test_graphifyignore_supports_nested_files(tmp_path):
    """Nested .graphifyignore files are picked up just like nested .gitignore."""
    root = _project(tmp_path)
    sub = root / "pkg"
    sub.mkdir()
    (sub / ".graphifyignore").write_text("*.py\n!keep.py\n", encoding="utf-8")
    _write(root / "top.py")
    _write(sub / "noise.py")
    _write(sub / "keep.py")

    rel = _detected(root)
    assert "top.py" in rel
    assert "pkg/keep.py" in rel
    assert "pkg/noise.py" not in rel


def test_gitignore_opt_out_does_not_disable_graphifyignore(tmp_path, monkeypatch):
    """Setting GRAPHIFY_RESPECT_GITIGNORE=0 only silences .gitignore."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("kept.py\n", encoding="utf-8")
    (root / ".graphifyignore").write_text("dropped.py\n", encoding="utf-8")
    _write(root / "kept.py")
    _write(root / "dropped.py")
    _write(root / "main.py")

    monkeypatch.setenv("GRAPHIFY_RESPECT_GITIGNORE", "0")
    rel = _detected(root)
    # .gitignore is silenced -> kept.py comes back.
    assert "kept.py" in rel
    # .graphifyignore is unaffected -> dropped.py stays excluded.
    assert "dropped.py" not in rel
    assert "main.py" in rel


# ---------------------------------------------------------------------------
# Built-in noise spec — the noise-prune rules are now expressed as a
# GitIgnoreSpec prepended to the user's chain. This means user `!`-rules
# naturally override built-in noise via last-match-wins, and the same
# matcher handles every kind of pruning (no parallel _SKIP_DIRS list).
# ---------------------------------------------------------------------------


def test_noise_spec_prunes_dotfiles_and_dotdirs(tmp_path):
    """Dotfiles + dotdirs anywhere are pruned by the built-in noise spec."""
    root = _project(tmp_path)
    _write(root / ".eslintrc")
    _write(root / "src" / ".gitkeep")
    _write(root / "src" / "main.py")
    _write(root / ".pytest_cache" / "v" / "cache" / "data.txt")
    rel = _detected(root)
    assert ".eslintrc" not in rel
    assert "src/.gitkeep" not in rel
    assert "src/main.py" in rel
    assert all(not f.startswith(".pytest_cache/") for f in rel)


def test_noise_spec_prunes_lockfiles_anywhere(tmp_path):
    """Lockfiles like package-lock.json match anywhere via basename."""
    root = _project(tmp_path)
    _write(root / "package-lock.json")
    _write(root / "Cargo.lock")
    _write(root / "subdir" / "yarn.lock")
    _write(root / "main.py")
    rel = _detected(root)
    assert "package-lock.json" not in rel
    assert "Cargo.lock" not in rel
    assert "subdir/yarn.lock" not in rel
    assert "main.py" in rel


def test_noise_spec_prunes_venv_suffix_dirs(tmp_path):
    """*_venv and *_env wildcard dir patterns prune custom-named virtualenvs."""
    root = _project(tmp_path)
    _write(root / "myproj_venv" / "lib" / "site.py")
    _write(root / "tools_env" / "bin" / "tool.py")
    _write(root / "venv" / "lib" / "x.py")
    _write(root / "node_modules" / "pkg" / "index.js")
    _write(root / "src" / "main.py")
    rel = _detected(root)
    assert all(not f.startswith("myproj_venv/") for f in rel)
    assert all(not f.startswith("tools_env/") for f in rel)
    assert all(not f.startswith("venv/") for f in rel)
    assert all(not f.startswith("node_modules/") for f in rel)
    assert "src/main.py" in rel


def test_noise_spec_prunes_egg_info(tmp_path):
    """*.egg-info/ wildcard dir pattern prunes packaging metadata dirs."""
    root = _project(tmp_path)
    _write(root / "mypackage.egg-info" / "PKG-INFO")
    _write(root / "src" / "main.py")
    rel = _detected(root)
    assert all(not f.startswith("mypackage.egg-info/") for f in rel)
    assert "src/main.py" in rel


def test_noise_spec_prunes_graphify_home(tmp_path):
    """The configured graphify home dir is treated as noise."""
    root = _project(tmp_path)
    _write(root / ".graphify" / "graph.json")
    _write(root / "src" / "main.py")
    rel = _detected(root)
    assert all(not f.startswith(".graphify/") for f in rel)
    assert "src/main.py" in rel


def test_user_negation_overrides_builtin_noise_dotdir(tmp_path):
    """A user `!`-rule on a dotdir rescues it from the built-in noise spec."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("!.config/\n", encoding="utf-8")
    _write(root / ".config" / "settings.py")
    rel = _detected(root)
    assert ".config/settings.py" in rel


def test_user_negation_overrides_builtin_noise_venv(tmp_path):
    """A user `!`-rule rescues a recognized file inside a built-in-noise dir."""
    root = _project(tmp_path)
    (root / ".gitignore").write_text("!venv/\n", encoding="utf-8")
    _write(root / "venv" / "kept.py")
    rel = _detected(root)
    assert "venv/kept.py" in rel
