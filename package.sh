#!/bin/bash
# Package graphify source files for distribution.
# Includes: src, tests, docs, config. Excludes: venv, dist, build, caches.

set -euo pipefail

VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')
OUTFILE="graphify-${VERSION}-src.tar.gz"

tar czf "$OUTFILE" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.so' \
    --exclude='*.egg' \
    --exclude='*.egg-info' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='env' \
    --exclude='dist' \
    --exclude='build' \
    --exclude='uv.lock' \
    --exclude='.pytest_cache' \
    --exclude='.mypy_cache' \
    --exclude='.ruff_cache' \
    --exclude='.claude' \
    --exclude='.graphify' \
    --exclude='worked/*/graphify-out' \
    --exclude='orig_skills' \
    --exclude='.vscode' \
    --exclude='.git' \
    --exclude='#*#' \
    --exclude='*~' \
    --exclude='*.tar.gz' \
    graphify/ \
    tests/ \
    examples/ \
    worked/ \
    docs/ \
    pyproject.toml \
    README.md \
    LICENSE \
    CLAUDE.md \
    ARCHITECTURE.md \
    CHANGELOG.md \
    SECURITY.md \
    AGENTS.md \
    ISSUES.md \
    graphify.spec \
    project_notes.md \
    package.sh

echo "Packaged: $OUTFILE ($(du -h "$OUTFILE" | cut -f1))"
echo "Contents:"
tar tzf "$OUTFILE" | wc -l | xargs -I{} echo "  {} files"
