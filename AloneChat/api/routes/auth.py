"""
Authentication routes for AloneChat API.
"""

from fastapi import APIRouter, HTTPException, Request

from AloneChat.api.models import LoginRequest, RegisterRequest, TokenResponse
from AloneChat.api.middleware import get_token_cache, decode_token
from AloneChat.core.server import get_auth_service, get_user_service


router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    result = get_auth_service().register(credentials.username, credentials.password)
    if not result.success:
        return TokenResponse(success=False, message=result.error)
    return TokenResponse(success=True, message="Registration successful")


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    result = get_auth_service().authenticate(credentials.username, credentials.password)
    if not result.success:
        return TokenResponse(success=False, message=result.error)

    get_user_service().set_online(result.user_id)
    return TokenResponse(success=True, token=result.token, message="Login successful")


@router.post("/logout")
async def logout(request: Request):
    from AloneChat.api.middleware import _token_cache
    from AloneChat.core.server import get_user_service

    username = request.state.user
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        _token_cache.invalidate(token)
        get_auth_service().revoke_token(token)

    get_user_service().set_offline(username)
    return {"success": True, "message": "Logout successful"}


@router.get("/get_default_server")
async def get_default_server():
    from AloneChat.config import config
    return {"success": True, "default_server_address": config.DEFAULT_SERVER_ADDRESS}
