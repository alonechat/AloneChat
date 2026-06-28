"""
Authentication routes for AloneChat API.

Extracted from app.py. All endpoints use ``container.auth_service`` and
``container.user_service`` from the DI container for business logic.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from AloneChat.di import container

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth helper (mirrors the middleware helper in app.py)
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> str:
    """Extract the authenticated username from ``request.state.user``.

    Raises 401 when the request has not passed through the auth middleware.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@auth_router.post("/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    """Register a new user account."""
    result = await container.auth_service.register(
        credentials.username, credentials.password
    )
    if not result.success:
        return TokenResponse(success=False, message=result.error)
    return TokenResponse(success=True, message="Registration successful")


@auth_router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    """Authenticate a user and return a JWT token."""
    result = await container.auth_service.login(
        credentials.username, credentials.password
    )
    if not result.success:
        return TokenResponse(success=False, message=result.error)

    await container.user_service.set_online(result.user_id)
    return TokenResponse(success=True, token=result.token, message="Login successful")


@auth_router.post("/logout")
async def logout(request: Request):
    """Log out the current user (requires auth middleware)."""
    username = _get_user(request)
    await container.user_service.set_offline(username)
    return {"success": True, "message": "Logout successful"}
