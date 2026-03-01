"""
Pydantic models for AloneChat API.
"""

from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


class FeedbackRequest(BaseModel):
    content: str


class PrivateMessageRequest(BaseModel):
    recipient: str
    content: str


class UserStatusRequest(BaseModel):
    status: str


class FriendRequestModel(BaseModel):
    to_user: str
    message: str = ""


class FriendActionRequest(BaseModel):
    request_id: str


class SetRemarkRequest(BaseModel):
    friend_id: str
    remark: str


class SearchUserRequest(BaseModel):
    query: str
