"""
Auth middleware extracted from app.py.

Contains TokenCache class, decode_token(), _get_user() dependency,
and AuthMiddleware class.
"""

import logging
import time
from typing import Dict, Optional

import jwt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from AloneChat.config import config

logger = logging.getLogger(__name__)

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


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token, with LRU caching."""
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


def _get_user(request: Request) -> str:
    """FastAPI dependency: extract authenticated username from request.state.

    Raises HTTPException(401) when the user is not set on the request.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _get_token_user(request: Request) -> Optional[str]:
    """Extract username from Authorization header or authToken cookie.

    Returns None when no valid token is present (does not raise).
    Useful for endpoints that serve both authenticated and anonymous paths.
    """
    token = None
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]

    if not token:
        token = request.cookies.get("authToken")

    if not token:
        return None

    payload = decode_token(token)
    return payload.get("sub") if payload else None


class AuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces JWT authentication on every request.

    Whitelisted paths (login, register, static, SSE, legacy recv) are passed
    through without a token.  Other requests are redirected to /login.html
    when the token is missing, expired, or invalid.
    """

    async def dispatch(self, request: Request, call_next):
        whitelist = [
            "/api/auth/login", "/api/auth/register", "/api/get_default_server",
            "/static/", "/login.html", "/events", "/api/chat/events", "/recv", "/recv/batch"
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
