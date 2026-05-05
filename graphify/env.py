"""Environment loading helpers for graphify CLI and direct LLM use."""
from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from collections.abc import MutableMapping


_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WINDOWS_USER_ENV_KEYS = (
    "MOONSHOT_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OLLAMA_API_KEY",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "GRAPHIFY_FORCE",
    "GRAPHIFY_MAX_OUTPUT_TOKENS",
    "GRAPHIFY_NO_TIPS",
    "GRAPHIFY_OUT",
    "GRAPHIFY_VIZ_NODE_LIMIT",
    "GRAPHIFY_WHISPER_MODEL",
    "GRAPHIFY_WHISPER_PROMPT",
)


def _unquote_dotenv_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values

    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export "):].lstrip()
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            continue
        values[key] = _unquote_dotenv_value(value)
    return values


def _windows_user_env() -> dict[str, str]:
    if platform.system() != "Windows":
        return {}
    try:
        import winreg
    except Exception:
        return {}

    values: dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for name in _WINDOWS_USER_ENV_KEYS:
                try:
                    value, _kind = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                if value:
                    values[name] = str(value)
    except OSError:
        return {}
    return values


def _wsl_windows_users_root() -> Path | None:
    root = Path("/mnt/c/Users")
    return root if root.exists() else None


def _candidate_dotenv_paths(cwd: Path, home: Path) -> list[Path]:
    paths: list[Path] = []

    def add(path: Path) -> None:
        if path not in paths:
            paths.append(path)

    try:
        cwd = cwd.resolve()
    except OSError:
        cwd = cwd.absolute()
    try:
        home = home.resolve()
    except OSError:
        home = home.absolute()

    current = cwd
    chain: list[Path] = []
    while True:
        chain.append(current / ".env")
        if current == home or current.parent == current:
            break
        current = current.parent

    # WSL does not inherit Windows user environment. If a matching Windows home
    # exists, load its .env as a fallback for shared API keys.
    if platform.system() != "Windows":
        users_root = _wsl_windows_users_root()
        if users_root is not None:
            add(users_root / home.name / ".env")

    add(home / ".env")

    # Load broader .env files first, then let closer project files override them.
    for path in reversed(chain):
        add(path)

    return paths


def load_env(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Load env vars from user/project .env files without overriding process env."""
    env = environ if environ is not None else os.environ
    protected = {key for key, value in env.items() if value}
    pending: dict[str, str] = {}

    for key, value in _windows_user_env().items():
        if key not in protected:
            pending[key] = value

    cwd = cwd or Path.cwd()
    home = home or Path.home()
    for path in _candidate_dotenv_paths(cwd, home):
        if not path.exists():
            continue
        for key, value in _read_dotenv(path).items():
            if key not in protected:
                pending[key] = value

    env.update(pending)
