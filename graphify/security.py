# Security helpers - URL validation, safe fetch, path guards, label sanitisation
from __future__ import annotations

import html
import http.client
import re
import ssl
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
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


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
                if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                    raise ValueError(
                        f"Blocked private/internal IP {addr} (resolved from '{hostname}'). "
                        f"Got: {url!r}"
                    )
        except socket.gaierror:
            pass  # DNS failure will surface later during fetch

    return url


def _assert_public_ip(addr: str, *, hostname: str, url: str) -> None:
    ip = ipaddress.ip_address(addr)
    if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
        raise ValueError(
            f"Blocked private/internal IP {addr} (resolved from '{hostname}'). "
            f"Got: {url!r}"
        )


def _resolve_public_ips(hostname: str, url: str) -> list[str]:
    """Resolve *hostname* and return vetted public IPs in lookup order."""
    if hostname.lower() in _BLOCKED_HOSTS:
        raise ValueError(
            f"Blocked cloud metadata endpoint '{hostname}'. "
            f"Got: {url!r}"
        )

    infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    addrs: list[str] = []
    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        _assert_public_ip(addr, hostname=hostname, url=url)
        if addr not in seen:
            addrs.append(addr)
            seen.add(addr)
    return addrs


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


class _DirectHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a vetted IP while verifying the original hostname."""

    def __init__(self, connect_host: str, server_hostname: str, *args, **kwargs):
        self._server_hostname = server_hostname
        super().__init__(connect_host, *args, **kwargs)

    def connect(self):
        http.client.HTTPConnection.connect(self)
        hostname = self._tunnel_host or self._server_hostname
        self.sock = self._context.wrap_socket(self.sock, server_hostname=hostname)


def _request_target(parsed: urllib.parse.ParseResult) -> str:
    target = parsed.path or "/"
    if parsed.params:
        target += f";{parsed.params}"
    if parsed.query:
        target += f"?{parsed.query}"
    return target


def _host_header(parsed: urllib.parse.ParseResult) -> str:
    hostname = parsed.hostname or ""
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    if parsed.port and parsed.port != default_port:
        return f"{hostname}:{parsed.port}"
    return hostname


def _open_direct(url: str, timeout: int) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    """Open *url* against a vetted IP, preserving Host/SNI for the original hostname."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise urllib.error.URLError(f"Missing hostname in URL: {url!r}")

    addresses = _resolve_public_ips(hostname, url)
    if not addresses:
        raise urllib.error.URLError(f"Could not resolve hostname: {hostname}")

    connect_host = addresses[0]
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    headers = {
        "User-Agent": "Mozilla/5.0 graphify/1.0",
        "Host": _host_header(parsed),
    }
    target = _request_target(parsed)

    if parsed.scheme.lower() == "https":
        conn = _DirectHTTPSConnection(
            connect_host,
            hostname,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    else:
        conn = http.client.HTTPConnection(connect_host, port=port, timeout=timeout)

    conn.request("GET", target, headers=headers)
    return conn, conn.getresponse()


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
    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        validate_url(current_url)
        conn = None
        try:
            conn, resp = _open_direct(current_url, timeout)
            status = getattr(resp, "status", None) or getattr(resp, "code", None)

            if status in _REDIRECT_STATUSES:
                location = resp.getheader("Location")
                if not location:
                    raise urllib.error.HTTPError(current_url, status, f"HTTP {status}", {}, None)
                current_url = urllib.parse.urljoin(current_url, location)
                continue

            if status is not None and not (200 <= status < 300):
                raise urllib.error.HTTPError(current_url, status, f"HTTP {status}", {}, None)

            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(65_536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise OSError(
                        f"Response from {current_url!r} exceeds size limit "
                        f"({max_bytes // 1_048_576} MB). Aborting download."
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            if conn is not None:
                conn.close()

    raise urllib.error.HTTPError(current_url, 310, "Too many redirects", {}, None)


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
