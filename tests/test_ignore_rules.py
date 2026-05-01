import os
from pathlib import Path
from graphify.detect import detect, _pattern_to_regex

def test_ignore_trailing_slash(tmp_path):
    """A pattern with a trailing slash only matches directories."""
    (tmp_path / ".graphifyignore").write_text("vendor/\n")
    (tmp_path / "vendor.py").write_text("x = 1") # file named vendor.py
    (tmp_path / "vendor").mkdir() # dir named vendor
    (tmp_path / "vendor" / "lib.py").write_text("y = 2")
    
    result = detect(tmp_path)
    code_files = [f.replace(os.sep, "/") for f in result["files"]["code"]]
    
    # File named 'vendor.py' should be included because pattern 'vendor/' only matches dirs
    assert any("vendor.py" in f for f in code_files)
    # Dir named 'vendor' should be ignored
    assert not any("vendor/lib.py" in f for f in code_files)

def test_negation_parent_ignored(tmp_path):
    """Standard ignore semantics: cannot re-include a file if a parent directory is excluded."""
    (tmp_path / ".graphifyignore").write_text("ignored/\n!ignored/keep.py\n")
    
    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "keep.py").write_text("print('keep')")
    
    result = detect(tmp_path)
    code_files = result["files"]["code"]
    
    # keep.py should be IGNORED because its parent 'ignored/' is excluded
    assert not any("keep.py" in f for f in code_files)

def test_negation_with_wildcard(tmp_path):
    """To re-include a file, the parent dir must not be fully excluded (e.g. use dir/*)."""
    (tmp_path / ".graphifyignore").write_text("ignored/*\n!ignored/keep.py\n")
    
    ignored_dir = tmp_path / "ignored"
    ignored_dir.mkdir()
    (ignored_dir / "skip.py").write_text("print('skip')")
    (ignored_dir / "keep.py").write_text("print('keep')")
    
    result = detect(tmp_path)
    code_files = result["files"]["code"]
    
    # keep.py should be INCLUDED
    assert any("keep.py" in f for f in code_files)
    # skip.py should be IGNORED
    assert not any("skip.py" in f for f in code_files)

def test_anchored_pattern(tmp_path):
    """A leading slash anchors the pattern to the root."""
    (tmp_path / ".graphifyignore").write_text("/root_only.py\n")
    (tmp_path / "root_only.py").write_text("x = 1")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "root_only.py").write_text("y = 2")
    
    result = detect(tmp_path)
    code_files = [f.replace(os.sep, "/") for f in result["files"]["code"]]
    
    assert not any(f.endswith("/root_only.py") and not "/sub/" in f for f in code_files)
    assert any("/sub/root_only.py" in f for f in code_files)

def test_exact_prefix_no_partial_match(tmp_path):
    """'git/' matches a/git/foo but NOT a/git-foo.py"""
    (tmp_path / ".graphifyignore").write_text("git/\n")
    git_dir = tmp_path / "git"
    git_dir.mkdir()
    (git_dir / "foo.py").write_text("x=1")
    (tmp_path / "git-foo.py").write_text("y=2")
    
    result = detect(tmp_path)
    code_files = [f.replace(os.sep, "/") for f in result["files"]["code"]]
    
    assert not any("git/foo.py" in f for f in code_files)
    assert any("git-foo.py" in f for f in code_files)

def test_complex_negation_chain(tmp_path):
    """data/** + !data/**/ + !data/**/*.txt"""
    (tmp_path / ".graphifyignore").write_text("data/**\n!data/**/\n!data/**/*.txt\n")
    data_dir = tmp_path / "data" / "nested" / "deep"
    data_dir.mkdir(parents=True)
    (tmp_path / "data" / "nested" / "skip.py").write_text("x=1")
    (data_dir / "keep.txt").write_text("y=2")
    
    result = detect(tmp_path)
    code_files = [f.replace(os.sep, "/") for f in result["files"]["code"]]
    doc_files = [f.replace(os.sep, "/") for f in result["files"]["document"]]
    
    assert not any("skip.py" in f for f in code_files)
    assert any("keep.txt" in f for f in doc_files)

def test_trailing_whitespace_stripped(tmp_path):
    """Unescaped trailing whitespace is stripped."""
    (tmp_path / ".graphifyignore").write_text("vendor/   \n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("y = 2")
    
    result = detect(tmp_path)
    code_files = [f.replace(os.sep, "/") for f in result["files"]["code"]]
    assert not any("vendor/lib.py" in f for f in code_files)

def test_trailing_whitespace_escaped(tmp_path):
    """Escaped trailing whitespace is preserved."""
    (tmp_path / ".graphifyignore").write_text("vendor\\ \n")
    # Due to Windows limitations on paths with trailing spaces, we test this logic
    # using the direct _match_ignore_pattern function rather than filesystem creation.
    from graphify.detect import _match_ignore_pattern, _load_graphifyignore
    patterns = _load_graphifyignore(tmp_path)
    pattern_str = patterns[0][1]
    
    assert pattern_str == "vendor\\ "  # The backslash is preserved and compiled to match a space
    assert _match_ignore_pattern("vendor ", pattern_str, is_dir=False)
    assert not _match_ignore_pattern("vendor", pattern_str, is_dir=False)

def test_posix_character_classes():
    """POSIX character classes are correctly mapped to Python regex."""
    assert _pattern_to_regex("[[:alpha:]].py").fullmatch("a.py")
    assert _pattern_to_regex("[[:alpha:]].py").fullmatch("Z.py")
    assert not _pattern_to_regex("[[:alpha:]].py").fullmatch("1.py")
    
    assert _pattern_to_regex("[[:digit:]].py").fullmatch("5.py")
    assert not _pattern_to_regex("[[:digit:]].py").fullmatch("a.py")
