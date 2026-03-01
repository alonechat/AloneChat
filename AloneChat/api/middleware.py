"""
Middleware and authentication utilities for AloneChat API.
"""

import time
from typing import Dict, Optional, Set

import jwt
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from AloneChat.config import config


JWT_SECRET = config.JWT_SECRET
JWT_ALGORITHM = config.JWT_ALGORITHM


class TokenCache:
    """LRU cache for decoded JWT tokens."""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, token: str) -> Optional[dict]:
        if token in self._cache:
            payload, expiry = self._cache[token]
            if time.time() < expiry:
                return payload
            del self._cache[token]
        return None

    def set(self, token: str, payload: dict) -> None:
        if len(self._cache) >= self._max_size:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
        self._cache[token] = (payload, time.time() + self._ttl)

    def invalidate(self, token: str) -> None:
        self._cache.pop(token, None)


_token_cache = TokenCache()


def get_token_cache() -> TokenCache:
    return _token_cache


def decode_token(token: str) -> Optional[dict]:
    cached = _token_cache.get(token)
    if cached:
        if cached.get("exp", 0) > time.time():
            return cached
        _token_cache.invalidate(token)

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        _token_cache.set(token, payload)
        return payload
    except jwt.PyJWTError:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        whitelist = [
            "/api/login", "/api/register", "/api/get_default_server",
            "/static/", "/login.html", "/events", "/recv", "/recv/batch",
            "/", "/index.html", "/ping"
        ]

        if any(request.url.path.startswith(p) for p in whitelist):
            return await call_next(request)

        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

        if not token:
            token = request.cookies.get("authToken")

        if not token:
            return Response(status_code=307, headers={"Location": "/login.html"})

        payload = decode_token(token)
        if not payload or payload.get("exp", 0) < time.time():
            _token_cache.invalidate(token)
            return Response(status_code=307, headers={"Location": "/login.html"})

        request.state.user = payload.get("sub")
        return await call_next(request)


__all__ = ["TokenCache", "_token_cache", "get_token_cache", "decode_token", "AuthMiddleware"]
