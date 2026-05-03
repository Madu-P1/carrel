from __future__ import annotations

import os
import secrets

from fastapi import Request


HEADER_NAME = "X-Carrel-Local-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_LOCAL_API_TOKEN = os.getenv("CARREL_LOCAL_API_TOKEN") or secrets.token_urlsafe(32)


def get_local_api_token() -> str:
    return _LOCAL_API_TOKEN


def is_mutating_api_request(request: Request) -> bool:
    return request.url.path.startswith("/api/") and request.method.upper() not in SAFE_METHODS


def has_valid_local_api_token(request: Request) -> bool:
    supplied = request.headers.get(HEADER_NAME)
    return bool(supplied) and secrets.compare_digest(supplied, _LOCAL_API_TOKEN)
