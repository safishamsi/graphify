"""
Transport layer: connection management and low-level HTTP sending.
HTTPTransport wraps a connection pool. ProxyTransport sits in front of it.
MockTransport is used in tests.
"""

from models import Request, Response
from exceptions import TransportError, ConnectError, TimeoutException


class BaseTransport:
    """Sync transport interface."""

    def handle_request(self, request: Request) -> Response:
        raise NotImplementedError

    def close(self) -> None:
        pass


class AsyncBaseTransport:
    """Async transport interface."""

    async def handle_async_request(self, request: Request) -> Response:
        raise NotImplementedError

    async def aclose(self) -> None:
        pass


class ConnectionPool:
    """
    Manages a pool of persistent HTTP connections.
    Keys connections by (scheme, host, port).
    """

    def __init__(self, max_connections=100, max_keepalive_connections=20):
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self._pool = {}

    def _get_connection_key(self, request: Request) -> tuple:
        url = request.url
        port = 443 if url.scheme == "https" else 80
        return (url.scheme, url.host, port)

    def get_connection(self, request: Request):
        key = self._get_connection_key(request)
        return self._pool.get(key)

    def return_connection(self, request: Request, conn) -> None:
        key = self._get_connection_key(request)
        if len(self._pool) < self.max_keepalive_connections:
            self._pool[key] = conn

    def close(self) -> None:
        self._pool.clear()


class HTTPTransport(BaseTransport):
    """
    The main sync HTTP transport.
    Uses a ConnectionPool for connection reuse.
    """

    def __init__(self, verify=True, cert=None, limits=None):
        self.verify = verify
        self.cert = cert
        self._pool = ConnectionPool()

    def handle_request(self, request: Request) -> Response:
        conn = self._pool.get_connection(request)
        try:
            response = self._send(request, conn)
            self._pool.return_connection(request, conn)
            return response
        except TimeoutException:
            raise
        except Exception as exc:
            raise ConnectError(str(exc)) from exc

    def _send(self, request: Request, conn) -> Response:
        # Simplified: in real httpx this does the actual socket I/O
        return Response(200, headers={}, content=b"", request=request)

    def close(self) -> None:
        self._pool.close()


class AsyncHTTPTransport(AsyncBaseTransport):
    """The async variant of HTTPTransport."""

    def __init__(self, verify=True, cert=None):
        self.verify = verify
        self.cert = cert

    async def handle_async_request(self, request: Request) -> Response:
        return Response(200, headers={}, content=b"", request=request)

    async def aclose(self) -> None:
        pass


class MockTransport(BaseTransport):
    """
    A transport for testing that returns predefined responses.
    Pass a handler function that receives a Request and returns a Response.
    """

    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: Request) -> Response:
        return self.handler(request)


class ProxyTransport(BaseTransport):
    """
    Routes requests through an HTTP/HTTPS proxy.
    Wraps an inner transport and prepends proxy connection handling.
    """

    def __init__(self, proxy_url: str, *, inner: BaseTransport = None):
        self.proxy_url = proxy_url
        self._inner = inner or HTTPTransport()

    def handle_request(self, request: Request) -> Response:
        try:
            return self._inner.handle_request(request)
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"Proxy error: {exc}") from exc

    def close(self) -> None:
        self._inner.close()
