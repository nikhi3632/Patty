"""Sanitize secrets from HTTP error messages.

API keys leak when httpx includes full URLs (with query params) in exception
messages. This module provides a context manager that catches exceptions and
strips all known secret values before re-raising.
"""

import re
from contextlib import contextmanager

from src.config import get

SECRET_VARS = [
    "NASS_API_KEY",
    "MYMARKET_NEWS_API_KEY",
    "GOOGLE_PLACES_API_KEY",
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "HUNTER_API_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
]


def redact(text: str) -> str:
    """Replace any secret values found in text with '***'."""
    for var in SECRET_VARS:
        value = get(var)
        if value and value in text:
            text = text.replace(value, "***")
    # Also strip secrets from URL query params (key=VALUE patterns)
    text = re.sub(r"(key=|api_key=|apikey=)[^&\s'\"]+", r"\1***", text, flags=re.I)
    return text


@contextmanager
def safe_request():
    """Context manager that redacts secrets from any raised exceptions."""
    try:
        yield
    except Exception as exc:
        sanitized = redact(str(exc))
        raise type(exc)(sanitized) from None
