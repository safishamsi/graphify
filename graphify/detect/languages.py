from enum import Enum
import shlex
from pathlib import Path

from graphify.detect.constants import (
    CODE_EXTENSIONS, DOC_EXTENSIONS, PAPER_EXTENSIONS,
    IMAGE_EXTENSIONS, OFFICE_EXTENSIONS, VIDEO_EXTENSIONS,
    _SENSITIVE_DIRS, _SENSITIVE_PATTERNS,
    _PAPER_SIGNALS, _PAPER_SIGNAL_THRESHOLD,
    _ASSET_DIR_MARKERS, _SHEBANG_CODE_INTERPRETERS,
)

from graphify.google_workspace import GOOGLE_WORKSPACE_EXTENSIONS

class FileType(str, Enum):
    CODE = "code"
    DOCUMENT = "document"
    PAPER = "paper"
    IMAGE = "image"
    VIDEO = "video"

def _is_sensitive(path: Path) -> bool:
    """Return True if this file likely contains secrets and should be skipped."""
    # Stage 1: any PARENT directory is a known secrets dir (parts[:-1] excludes
    # the filename itself so a root-level file named "credentials" is not falsely
    # skipped — the name patterns in Stage 2 handle the filename).
    if any(part in _SENSITIVE_DIRS for part in path.parts[:-1]):
        return True
    # Stage 2: filename pattern match
    name = path.name
    return any(p.search(name) for p in _SENSITIVE_PATTERNS)

def _looks_like_paper(path: Path) -> bool:
    """Heuristic: does this text file read like an academic paper?"""
    try:
        # Only scan first 3000 chars for speed
        text = path.read_text(encoding="utf-8", errors="ignore")[:3000]
        hits = sum(1 for pattern in _PAPER_SIGNALS if pattern.search(text))
        return hits >= _PAPER_SIGNAL_THRESHOLD
    except Exception:
        return False

def _split_env_s(value: str, rest: list[str]) -> list[str]:
    """Re-tokenize an `env -S`/`--split-string` packed command, prepending the
    operand to any trailing args. Returns the unpacked argv."""
    packed = " ".join([value, *rest]).strip()
    return shlex.split(packed)

def _env_command_args(args: list[str], *, allow_split: bool = True) -> list[str]:
    """Strip leading env(1) options and var assignments, return the trailing
    command argv. Covers macOS/BSD and GNU coreutils env documented spellings.

    POSIX/macOS short forms:
        env [-0iv] [-C workdir] [-P utilpath] [-S string]
            [-u name] [name=value ...] [utility [argument ...]]

    GNU coreutils long/compact forms additionally supported:
        --argv0=ARG / -a ARG / -aARG
        --unset=NAME / --unset NAME / -u NAME / -uNAME
        --chdir=DIR / --chdir DIR / -C DIR / -CDIR
        --split-string=STRING / --split-string STRING
        -S STRING / -SSTRING / -vS STRING / -vSSTRING
        --ignore-environment / --null / --debug / --list-signal-handling
        --default-signal[=SIG] / --ignore-signal[=SIG] / --block-signal[=SIG]

    `-S` / `--split-string` payloads are themselves env-style argument lists
    per the GNU shebang synopsis:
        #!/usr/bin/env -[v]S[option]... [name=value]... command [args]...
    so after splitting the payload we recursively re-parse it with
    `allow_split=False` (a nested -S inside a split payload is rejected to
    bound recursion).

    Unknown hyphen-prefixed args yield [] (we refuse to guess whether
    their next token is an interpreter or an operand).
    """
    i = 0
    while i < len(args):
        arg = args[i]

        if arg == "--":
            return args[i + 1:]

        # Split-string forms: tokenize the packed payload, then re-parse it
        # as env args (so leading assignments/flags inside the payload are
        # skipped before the interpreter is identified).
        if allow_split:
            if arg == "-S":
                if i + 1 >= len(args):
                    return []
                return _env_command_args(
                    _split_env_s(" ".join(args[i + 1:]), []),
                    allow_split=False,
                )
            if arg.startswith("-S") and len(arg) > 2:
                return _env_command_args(
                    _split_env_s(arg[2:], args[i + 1:]),
                    allow_split=False,
                )
            if arg == "-vS":
                if i + 1 >= len(args):
                    return []
                return _env_command_args(
                    _split_env_s(" ".join(args[i + 1:]), []),
                    allow_split=False,
                )
            if arg.startswith("-vS") and len(arg) > 3:
                return _env_command_args(
                    _split_env_s(arg[3:], args[i + 1:]),
                    allow_split=False,
                )
            if arg.startswith("--split-string="):
                return _env_command_args(
                    _split_env_s(arg.split("=", 1)[1], args[i + 1:]),
                    allow_split=False,
                )
            if arg == "--split-string":
                if i + 1 >= len(args):
                    return []
                return _env_command_args(
                    _split_env_s(args[i + 1], args[i + 2:]),
                    allow_split=False,
                )

        # Options with separate required operand
        if arg in {"-u", "-C", "-P", "-a", "--unset", "--chdir", "--argv0"}:
            if i + 2 > len(args):
                return []
            i += 2
            continue

        # Clumped short option + operand
        if (
            arg.startswith(("-u", "-C", "-P", "-a"))
            and len(arg) > 2
            and not arg.startswith("--")
        ):
            i += 1
            continue

        # Long option with `=` operand
        if arg.startswith(("--unset=", "--chdir=", "--argv0=")):
            i += 1
            continue

        # No-operand flags
        if arg in {"-", "-i", "-0", "-v", "--ignore-environment", "--null",
                   "--debug", "--list-signal-handling"}:
            i += 1
            continue

        # Signal-handling long flags (with or without =SIG operand — we treat
        # them as no-effect for interpreter-resolution purposes)
        if arg.startswith(("--default-signal", "--ignore-signal", "--block-signal")):
            i += 1
            continue

        # Unknown hyphen-prefixed: refuse to guess
        if arg.startswith("-"):
            return []

        # Inline NAME=value assignment
        if "=" in arg:
            i += 1
            continue

        # First non-option, non-assignment token starts the command argv
        return args[i:]

    return []

def _shebang_interpreter(path: Path) -> str | None:
    """Return the interpreter name from a shebang line.

    Handles forms that a naive parser misses:
      - `#!/usr/bin/env -S python3 -u`     (env -S split-args form, anywhere)
      - `#!/usr/bin/env -i bash`           (no-operand env flags)
      - `#!/usr/bin/env -u VAR python3`    (env options with operands)
      - `#!/usr/bin/env -C /tmp python3`   (env -C workdir)
      - `#!/usr/bin/env -P /bin python3`   (env -P utilpath)
      - `#!/usr/bin/env DEBUG=1 python3`   (inline var assignment)
      - `#!"/usr/local/bin/python with spaces"`  (shlex handles quotes)

    Returns the basename of the resolved interpreter, or None if there is
    no shebang / the file is unreadable / parsing fails.
    """
    try:
        with path.open("rb") as f:
            first = f.read(256)
        if not first.startswith(b"#!"):
            return None
        line = first.split(b"\n")[0].decode(errors="replace")[2:].strip()
        parts = shlex.split(line)
        if not parts:
            return None
        interp = Path(parts[0]).name
        if interp == "env":
            env_args = _env_command_args(parts[1:])
            if not env_args:
                return None
            interp = Path(env_args[0]).name
        return interp
    except (OSError, ValueError):
        return None

def _shebang_file_type(path: Path) -> FileType | None:
    """Peek at the first line of an extensionless file for a shebang."""
    interp = _shebang_interpreter(path)
    if interp in _SHEBANG_CODE_INTERPRETERS:
        return FileType.CODE
    return None

def classify_file(path: Path) -> FileType | None:
    # Compound extensions must be checked before simple suffix lookup
    if path.name.lower().endswith(".blade.php"):
        return FileType.CODE
    ext = path.suffix.lower()
    if not ext:
        return _shebang_file_type(path)
    if ext in CODE_EXTENSIONS:
        return FileType.CODE
    if ext in PAPER_EXTENSIONS:
        # PDFs inside Xcode asset catalogs are vector icons, not papers
        if any(part.endswith(tuple(_ASSET_DIR_MARKERS)) for part in path.parts):
            return None
        return FileType.PAPER
    if ext in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if ext in DOC_EXTENSIONS:
        # Check if it's a converted paper
        if _looks_like_paper(path):
            return FileType.PAPER
        return FileType.DOCUMENT
    if ext in OFFICE_EXTENSIONS:
        return FileType.DOCUMENT
    if ext in GOOGLE_WORKSPACE_EXTENSIONS:
        return FileType.DOCUMENT
    if ext in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    return None
