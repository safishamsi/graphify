"""
Core data models: URL, Headers, Cookies, Request, Response.
These are the central data types that everything else in the library references.
"""

import json as _json
from exceptions import HTTPStatusError


class URL:
    def __init__(self, url: str):
        self.raw = url
        self.scheme, _, rest = url.partition("://")
        self.host, _, self.path = rest.partition("/")
        self.path = "/" + self.path

    def copy_with(self, **kwargs) -> "URL":
        return URL(kwargs.get("url", self.raw))

    def __str__(self):
        return self.raw

    def __repr__(self):
        return f"URL({self.raw!r})"


class Headers:
    def __init__(self, headers=None):
        self._store = {}
        for k, v in (headers or {}).items():
            self._store[k.lower()] = v

    def get(self, key: str, default=None):
        return self._store.get(key.lower(), default)

    def items(self):
        return self._store.items()

    def __setitem__(self, key, value):
        self._store[key.lower()] = value

    def __getitem__(self, key):
        return self._store[key.lower()]

    def __contains__(self, key):
        return key.lower() in self._store


class Cookies:
    def __init__(self, cookies=None):
        self._jar = dict(cookies or {})

    def set(self, name: str, value: str, domain: str = "") -> None:
        self._jar[name] = value

    def get(self, name: str, default=None):
        return self._jar.get(name, default)

    def delete(self, name: str) -> None:
        self._jar.pop(name, None)

    def clear(self) -> None:
        self._jar.clear()

    def items(self):
        return self._jar.items()


class Request:
    def __init__(self, method: str, url, *, headers=None, content=None, cookies=None):
        self.method = method.upper()
        self.url = URL(url) if isinstance(url, str) else url
        self.headers = Headers(headers)
        self.content = content or b""
        self.cookies = Cookies(cookies)

    def __repr__(self):
        return f"<Request [{self.method}]>"


class Response:
    def __init__(self, status_code: int, *, headers=None, content=None, request=None):
        self.status_code = status_code
        self.headers = Headers(headers)
        self.content = content or b""
        self.request = request

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return _json.loads(self.content)

    def read(self) -> bytes:
        return self.content

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def raise_for_status(self) -> None:
        if self.is_error:
            message = f"{self.status_code} Error"
            raise HTTPStatusError(message, request=self.request, response=self)

    @property
    def cookies(self) -> Cookies:
        jar = Cookies()
        for header in self.headers.get("set-cookie", "").split(","):
            if "=" in header:
                name, _, value = header.strip().partition("=")
                jar.set(name.strip(), value.split(";")[0].strip())
        return jar

    def __repr__(self):
        return f"<Response [{self.status_code}]>"
