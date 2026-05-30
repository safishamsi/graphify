"""
The main Client and AsyncClient classes.
BaseClient holds all shared logic. Client and AsyncClient extend it for sync/async.
This is the integration hub of the library - it imports from every other module.
"""

from models import Request, Response, URL, Headers, Cookies
from auth import Auth, BasicAuth
from transport import BaseTransport, HTTPTransport, AsyncHTTPTransport
from exceptions import TooManyRedirects, InvalidURL
from utils import build_url_with_params, obfuscate_sensitive_headers


DEFAULT_MAX_REDIRECTS = 20


class Timeout:
    def __init__(self, timeout=5.0, *, connect=None, read=None, write=None, pool=None):
        self.connect = connect or timeout
        self.read = read or timeout
        self.write = write or timeout
        self.pool = pool or timeout


class Limits:
    def __init__(self, max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0):
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry


class BaseClient:
    """
    Shared implementation for Client and AsyncClient.
    Handles auth, redirects, cookies, and header defaults.
    """

    def __init__(
        self,
        *,
        auth=None,
        headers=None,
        cookies=None,
        timeout=Timeout(),
        max_redirects=DEFAULT_MAX_REDIRECTS,
        base_url="",
    ):
        self._auth = auth
        self._headers = Headers(headers or {})
        self._cookies = Cookies(cookies or {})
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._base_url = URL(base_url) if base_url else None

    def _build_request(self, method: str, url: str, **kwargs) -> Request:
        if self._base_url:
            url = self._base_url.raw.rstrip("/") + "/" + url.lstrip("/")
        if kwargs.get("params"):
            url = build_url_with_params(url, kwargs.pop("params"))
        headers = Headers(kwargs.get("headers", {}))
        for k, v in self._headers.items():
            if k not in headers:
                headers[k] = v
        return Request(
            method, url, headers=headers, content=kwargs.get("content"), cookies=self._cookies
        )

    def _merge_cookies(self, response: Response) -> None:
        for name, value in response.cookies.items():
            self._cookies.set(name, value)


class Client(BaseClient):
    """Synchronous HTTP client."""

    def __init__(self, *, transport: BaseTransport = None, **kwargs):
        super().__init__(**kwargs)
        self._transport = transport or HTTPTransport()

    def request(self, method: str, url: str, **kwargs) -> Response:
        request = self._build_request(method, url, **kwargs)
        auth = kwargs.get("auth") or self._auth
        if auth:
            flow = auth.auth_flow(request)
            request = next(flow)
        response = self._transport.handle_request(request)
        self._merge_cookies(response)
        if auth:
            try:
                flow.send(response)
            except StopIteration:
                pass
        return response

    def get(self, url: str, **kwargs) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs) -> Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Response:
        return self.request("DELETE", url, **kwargs)

    def head(self, url: str, **kwargs) -> Response:
        return self.request("HEAD", url, **kwargs)

    def send(self, request: Request) -> Response:
        return self._transport.handle_request(request)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncClient(BaseClient):
    """Asynchronous HTTP client."""

    def __init__(self, *, transport=None, **kwargs):
        super().__init__(**kwargs)
        self._transport = transport or AsyncHTTPTransport()

    async def request(self, method: str, url: str, **kwargs) -> Response:
        request = self._build_request(method, url, **kwargs)
        response = await self._transport.handle_async_request(request)
        self._merge_cookies(response)
        return response

    async def get(self, url: str, **kwargs) -> Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Response:
        return await self.request("DELETE", url, **kwargs)

    async def send(self, request: Request) -> Response:
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()
