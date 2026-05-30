"""
Utility functions shared across the library.
Small helpers that don't belong in any one module.
"""

import re
from models import Cookies


SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization"}


def primitive_value_to_str(value) -> str:
    """Convert a primitive value to its string representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def normalize_header_key(key: str) -> str:
    """Convert a header key to its canonical Title-Case form."""
    return "-".join(word.capitalize() for word in key.split("-"))


def flatten_queryparams(params: dict) -> list:
    """
    Expand a params dict into a flat list of (key, value) pairs.
    List values become multiple pairs with the same key.
    """
    result = []
    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                result.append((key, primitive_value_to_str(item)))
        else:
            result.append((key, primitive_value_to_str(value)))
    return result


def parse_content_type(content_type: str) -> tuple:
    """
    Parse a Content-Type header value.
    Returns (media_type, params_dict).
    Example: 'application/json; charset=utf-8' -> ('application/json', {'charset': 'utf-8'})
    """
    parts = [p.strip() for p in content_type.split(";")]
    media_type = parts[0]
    params = {}
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            params[key.strip()] = value.strip()
    return media_type, params


def obfuscate_sensitive_headers(headers: dict) -> dict:
    """Return a copy of headers with sensitive values replaced by [obfuscated]."""
    return {k: "[obfuscated]" if k.lower() in SENSITIVE_HEADERS else v for k, v in headers.items()}


def unset_all_cookies(cookies: Cookies) -> None:
    """Clear all cookies from a cookie jar in place."""
    cookies.clear()


def is_known_encoding(encoding: str) -> bool:
    """Check if a character encoding label is recognized by Python's codec system."""
    import codecs

    try:
        codecs.lookup(encoding)
        return True
    except LookupError:
        return False


def build_url_with_params(base_url: str, params: dict) -> str:
    """Append query parameters to a URL string."""
    if not params:
        return base_url
    pairs = flatten_queryparams(params)
    query = "&".join(f"{k}={v}" for k, v in pairs)
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{query}"
