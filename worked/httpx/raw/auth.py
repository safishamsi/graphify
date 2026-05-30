"""
Authentication handlers.
Auth objects are callables that modify a request before it is sent.
DigestAuth is the most interesting: it participates in a full request/response cycle,
reading the 401 response to build the challenge before re-sending.
"""

import hashlib
import time
from models import Request, Response


class Auth:
    """Base class for all authentication handlers."""

    def auth_flow(self, request: Request):
        """Modify the request. May yield to inspect the response."""
        raise NotImplementedError


class BasicAuth(Auth):
    """HTTP Basic Authentication."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def auth_flow(self, request: Request):
        import base64

        credentials = f"{self.username}:{self.password}".encode()
        encoded = base64.b64encode(credentials).decode()
        request.headers["Authorization"] = f"Basic {encoded}"
        yield request


class BearerAuth(Auth):
    """Bearer token authentication."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request: Request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class DigestAuth(Auth):
    """
    HTTP Digest Authentication.
    Requires a full request/response cycle: sends the initial request,
    reads the 401 WWW-Authenticate header, then re-sends with credentials.
    This is the only auth handler that reads from Response.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._nonce_count = 0

    def auth_flow(self, request: Request):
        yield request  # first attempt, no credentials

        # This handler must inspect the Response to continue
        response = yield

        if response.status_code == 401:
            challenge = self._parse_challenge(response)
            credentials = self._build_credentials(request, challenge)
            request.headers["Authorization"] = credentials
            yield request

    def _parse_challenge(self, response: Response) -> dict:
        """Extract digest parameters from the WWW-Authenticate header."""
        header = response.headers.get("www-authenticate", "")
        params = {}
        for part in header.replace("Digest ", "").split(","):
            if "=" in part:
                key, _, value = part.strip().partition("=")
                params[key.strip()] = value.strip().strip('"')
        return params

    def _build_credentials(self, request: Request, challenge: dict) -> str:
        """Compute the Authorization header value for a digest challenge."""
        self._nonce_count += 1
        nc = f"{self._nonce_count:08x}"
        cnonce = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        realm = challenge.get("realm", "")
        nonce = challenge.get("nonce", "")

        ha1 = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{request.method}:{request.url.path}".encode()).hexdigest()
        response_hash = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:auth:{ha2}".encode()).hexdigest()

        return (
            f'Digest username="{self.username}", realm="{realm}", '
            f'nonce="{nonce}", uri="{request.url.path}", '
            f'nc={nc}, cnonce="{cnonce}", response="{response_hash}"'
        )


class NetRCAuth(Auth):
    """Load credentials from ~/.netrc based on the request host."""

    def auth_flow(self, request: Request):
        import netrc

        try:
            credentials = netrc.netrc().authenticators(request.url.host)
            if credentials:
                username, _, password = credentials
                basic = BasicAuth(username, password)
                yield from basic.auth_flow(request)
                return
        except Exception:
            pass
        yield request
