"""Errors the user can fix, with a stable code the UI translates (errors.<code>).

The web server turns any CodedError into a 400 `{"detail": {"code", "message"}}`, so an endpoint
can just call the function; the English message is the fallback when a code has no translation.
"""
from __future__ import annotations


class CodedError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
