# graphify/detect/constants.py — shared constants for the detect package.
# All submodules (core, ignore, languages, documents) import from here
# to avoid circular imports.
from __future__ import annotations
import re

# ─── Extension sets ──────────────────────────────────────────────────
CODE_EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.ejs', '.ets', '.go', '.rs', '.java', '.groovy', '.gradle', '.cpp', '.cc', '.cxx', '.c', '.h', '.hpp', '.rb', '.swift', '.kt', '.kts', '.cs', '.scala', '.php', '.lua', '.luau', '.toc', '.zig', '.ps1', '.ex', '.exs', '.m', '.mm', '.jl', '.vue', '.svelte', '.astro', '.dart', '.v', '.sv', '.sql', '.r', '.f', '.F', '.f90', '.F90', '.f95', '.F95', '.f03', '.F03', '.f08', '.F08', '.pas', '.pp', '.dpr', '.dpk', '.lpr', '.inc', '.dfm', '.lfm', '.lpk', '.sh', '.bash', '.json'}
DOC_EXTENSIONS = {'.md', '.mdx', '.qmd', '.txt', '.rst', '.html', '.yaml', '.yml'}
PAPER_EXTENSIONS = {'.pdf'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
OFFICE_EXTENSIONS = {'.docx', '.xlsx'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.mp3', '.wav', '.m4a', '.ogg'}

# ─── Corpus thresholds ──────────────────────────────────────────────
CORPUS_WARN_THRESHOLD = 50_000    # words - below this, warn "you may not need a graph"
CORPUS_UPPER_THRESHOLD = 500_000  # words - above this, warn about token cost
FILE_COUNT_UPPER = 500             # files - above this, warn about token cost

# ─── Manifest ────────────────────────────────────────────────────────
_MANIFEST_PATH = "graphify-out/manifest.json"

# ─── Sensitivity / security ─────────────────────────────────────────
_SENSITIVE_DIRS = frozenset({
    ".ssh", ".gnupg", ".aws", ".gcloud", "secrets", ".secrets", "credentials",
})

_SENSITIVE_PATTERNS = [
    re.compile(r'(^|[\\/])\.(env|envrc)(\.|$)', re.IGNORECASE),
    re.compile(r'\.(pem|key|p12|pfx|cert|crt|der|p8)$', re.IGNORECASE),
    re.compile(r'(?<![a-zA-Z0-9])(credential|secret|passwd|password|private_key)s?(?![a-zA-Z])', re.IGNORECASE),
    re.compile(r'(?<![a-zA-Z0-9])tokens?(?![a-zA-Z])', re.IGNORECASE),
    re.compile(r'(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$'),
    re.compile(r'(\.netrc|\.pgpass|\.htpasswd)$', re.IGNORECASE),
    re.compile(r'(aws_credentials|gcloud_credentials|service.account)', re.IGNORECASE),
]

# ─── Paper detection ────────────────────────────────────────────────
_PAPER_SIGNALS = [
    re.compile(r'\barxiv\b', re.IGNORECASE),
    re.compile(r'\bdoi\s*:', re.IGNORECASE),
    re.compile(r'\babstract\b', re.IGNORECASE),
    re.compile(r'\bproceedings\b', re.IGNORECASE),
    re.compile(r'\bjournal\b', re.IGNORECASE),
    re.compile(r'\bpreprint\b', re.IGNORECASE),
    re.compile(r'\\cite\{'),
    re.compile(r'\[\d+\]'),
    re.compile(r'\[\n\d+\n\]'),
    re.compile(r'eq\.\s*\d+|equation\s+\d+', re.IGNORECASE),
    re.compile(r'\d{4}\.\d{4,5}'),
    re.compile(r'\bwe propose\b', re.IGNORECASE),
    re.compile(r'\bliterature\b', re.IGNORECASE),
]
_PAPER_SIGNAL_THRESHOLD = 3

# ─── Xcode asset catalog markers ────────────────────────────────────
_ASSET_DIR_MARKERS = {".imageset", ".xcassets", ".appiconset", ".colorset", ".launchimage"}

# ─── Shebang interpreters ───────────────────────────────────────────
_SHEBANG_CODE_INTERPRETERS = {
    "python", "python3", "python2",
    "ruby", "perl", "node", "nodejs",
    "bash", "sh", "dash", "zsh", "fish", "ksh", "tcsh",
    "lua", "php", "julia", "Rscript",
}

# ─── Directory / file skip lists ────────────────────────────────────
_SKIP_DIRS = {
    "venv", ".venv", "env", ".env",
    "node_modules", "__pycache__", ".git",
    "dist", "build", "target", "out",
    "site-packages", "lib64",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".eggs", "*.egg-info",
    "graphify-out",
    "coverage", "lcov-report",
    "visual-tests", "visual-test",
    "__snapshots__", "snapshots",
    "storybook-static",
    "dist-protected",
    ".next", ".nuxt", ".turbo", ".angular",
    ".idea", ".cache", ".parcel-cache", ".svelte-kit", ".terraform", ".serverless",
    ".graphify",
    ".worktrees",
}

_SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Gemfile.lock",
    "composer.lock", "go.sum", "go.work.sum",
}

_VCS_MARKERS = (".git", ".hg", ".svn", "_darcs", ".fossil")
