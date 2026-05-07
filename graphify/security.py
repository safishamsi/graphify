# Security helpers - URL validation, safe fetch, path guards, label sanitisation
from __future__ import annotations

import contextlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import ipaddress
import socket

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_FETCH_BYTES = 52_428_800   # 50 MB hard cap for binary downloads
_MAX_TEXT_BYTES  = 10_485_760   # 10 MB hard cap for HTML / text

# AWS metadata, link-local, and common cloud metadata endpoints
_BLOCKED_HOSTS = {"metadata.google.internal", "metadata.google.com"}

# RFC 6598 Shared Address Space (CGN) -- is_private misses this on Python <3.11
_CGN_NETWORK = ipaddress.ip_network("100.64.0.0/10")


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """Raise ValueError if *url* is not http or https, or targets a private/internal IP.

    Blocks file://, ftp://, data:, and any other scheme that could be used
    for SSRF or local file access. Also blocks requests to private/reserved
    IP ranges (127.x, 10.x, 169.254.x, etc.) and cloud metadata endpoints
    to prevent SSRF in cloud environments.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Blocked URL scheme '{parsed.scheme}' - only http and https are allowed. "
            f"Got: {url!r}"
        )

    hostname = parsed.hostname
    if hostname:
        # Block known cloud metadata hostnames
        if hostname.lower() in _BLOCKED_HOSTS:
            raise ValueError(
                f"Blocked cloud metadata endpoint '{hostname}'. "
                f"Got: {url!r}"
            )

        # Resolve hostname and block private/reserved IP ranges
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for info in infos:
                addr = info[4][0]
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip in _CGN_NETWORK:
                    raise ValueError(
                        f"Blocked private/internal IP {addr} (resolved from '{hostname}'). "
                        f"Got: {url!r}"
                    )
        except socket.gaierror as exc:
            raise ValueError(
                f"DNS resolution failed for '{hostname}': {exc}. Got: {url!r}"
            ) from exc

    return url


@contextlib.contextmanager
def _ssrf_guarded_socket():
    """Patch socket.getaddrinfo for the duration of a fetch to catch DNS rebinding.

    Validates every IP that urllib resolves so a DNS server cannot return a public IP
    for validate_url and swap to a private IP for the actual connection (TOCTOU fix).
    Not thread-safe, but graphify is a single-threaded CLI tool.
    """
    original = socket.getaddrinfo

    def _guarded(host, port, *args, **kwargs):
        results = original(host, port, *args, **kwargs)
        for info in results:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip in _CGN_NETWORK:
                raise OSError(
                    f"SSRF blocked: IP {addr} resolved from '{host}' is private/reserved"
                )
        return results

    socket.getaddrinfo = _guarded
    try:
        yield
    finally:
        socket.getaddrinfo = original


class _NoFileRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that re-validates every redirect target.

    Prevents open-redirect SSRF attacks where an http:// URL redirects
    to file:// or an internal address.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)          # raises ValueError if scheme is wrong
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoFileRedirectHandler)


# ---------------------------------------------------------------------------
# Safe fetch
# ---------------------------------------------------------------------------

def safe_fetch(url: str, max_bytes: int = _MAX_FETCH_BYTES, timeout: int = 30) -> bytes:
    """Fetch *url* and return raw bytes.

    Protections applied:
    - URL scheme validated (http / https only)
    - Redirects re-validated via _NoFileRedirectHandler
    - Response body capped at *max_bytes* (streaming read)
    - Non-2xx status raises urllib.error.HTTPError
    - Network errors propagate as urllib.error.URLError / OSError

    Raises:
        ValueError        - disallowed scheme or redirect target
        urllib.error.HTTPError  - non-2xx HTTP status
        urllib.error.URLError   - DNS / connection failure
        OSError               - size cap exceeded
    """
    validate_url(url)
    opener = _build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 graphify/1.0"})

    with _ssrf_guarded_socket(), opener.open(req, timeout=timeout) as resp:
        # urllib raises HTTPError for non-2xx when using urlopen directly;
        # with a custom opener we check manually to be safe.
        status = getattr(resp, "status", None) or getattr(resp, "code", None)
        if status is not None and not (200 <= status < 300):
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", {}, None)

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(65_536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise OSError(
                    f"Response from {url!r} exceeds size limit "
                    f"({max_bytes // 1_048_576} MB). Aborting download."
                )
            chunks.append(chunk)

    return b"".join(chunks)


def safe_fetch_text(url: str, max_bytes: int = _MAX_TEXT_BYTES, timeout: int = 15) -> str:
    """Fetch *url* and return decoded text (UTF-8, replacing bad bytes).

    Wraps safe_fetch with tighter defaults for HTML / text content.
    """
    raw = safe_fetch(url, max_bytes=max_bytes, timeout=timeout)
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def validate_graph_path(path: str | Path, base: Path | None = None) -> Path:
    """Resolve *path* and verify it stays inside *base*.

    *base* defaults to the `graphify-out` directory relative to CWD.
    Also requires the base directory to exist, so a caller cannot
    trick graphify into reading files before any graph has been built.

    Raises:
        ValueError  - path escapes base, or base does not exist
        FileNotFoundError - resolved path does not exist
    """
    if base is None:
        resolved_hint = Path(path).resolve()
        for candidate in [resolved_hint, *resolved_hint.parents]:
            if candidate.name == "graphify-out":
                base = candidate
                break
        if base is None:
            base = Path("graphify-out").resolve()

    base = base.resolve()
    if not base.exists():
        raise ValueError(
            f"Graph base directory does not exist: {base}. "
            "Run /graphify first to build the graph."
        )

    resolved = Path(path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(
            f"Path {path!r} escapes the allowed directory {base}. "
            "Only paths inside graphify-out/ are permitted."
        )

    if not resolved.exists():
        raise FileNotFoundError(f"Graph file not found: {resolved}")

    return resolved


# ---------------------------------------------------------------------------
# Label sanitisation (mirrors code-review-graph's _sanitize_name pattern)
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_LABEL_LEN = 256


def sanitize_label(text: str | None) -> str:
    """Strip control characters and cap length.

    Safe for embedding in JSON data (inside <script> tags) and plain text.
    For direct HTML injection, wrap the result with html.escape().
    """
    if text is None:
        return ""
    text = _CONTROL_CHAR_RE.sub("", str(text))
    if len(text) > _MAX_LABEL_LEN:
        text = text[:_MAX_LABEL_LEN]
    return text
