"""
httpx-like exception hierarchy.
All exceptions inherit from HTTPError at the top.
"""


class HTTPError(Exception):
    """Base class for all httpx exceptions."""

    def __init__(self, message, *, request=None):
        self.request = request
        super().__init__(message)


class RequestError(HTTPError):
    """An error occurred while issuing a request."""


class TransportError(RequestError):
    """An error occurred at the transport layer."""


class TimeoutException(TransportError):
    """A timeout occurred."""


class ConnectTimeout(TimeoutException):
    """Timed out while connecting to the host."""


class ReadTimeout(TimeoutException):
    """Timed out while receiving data from the host."""


class WriteTimeout(TimeoutException):
    """Timed out while sending data to the host."""


class PoolTimeout(TimeoutException):
    """Timed out waiting to acquire a connection from the pool."""


class NetworkError(TransportError):
    """A network error occurred."""


class ConnectError(NetworkError):
    """Failed to establish a connection."""


class ReadError(NetworkError):
    """Failed to receive data from the network."""


class WriteError(NetworkError):
    """Failed to send data through the network."""


class CloseError(NetworkError):
    """Failed to close a connection."""


class ProxyError(TransportError):
    """An error occurred while establishing a proxy connection."""


class ProtocolError(TransportError):
    """A protocol was violated."""


class DecodingError(RequestError):
    """Decoding of the response failed."""


class TooManyRedirects(RequestError):
    """Too many redirects."""


class HTTPStatusError(HTTPError):
    """A 4xx or 5xx response was received."""

    def __init__(self, message, *, request, response):
        self.response = response
        super().__init__(message, request=request)


class InvalidURL(Exception):
    """URL is improperly formed or cannot be parsed."""


class CookieConflict(Exception):
    """Attempted to look up a cookie by name but multiple cookies exist."""
