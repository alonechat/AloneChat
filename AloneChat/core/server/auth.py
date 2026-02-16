"""
Authentication service for AloneChat server.

Pure authentication logic without any HTTP/transport concerns.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import jwt

from AloneChat.config import config
from AloneChat.core.crypto import hash_password, verify_password
from .database import get_database, UserData

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    success: bool = False
    user_id: Optional[str] = None
    token: Optional[str] = None
    error: Optional[str] = None


@dataclass
class RegisterResult:
    success: bool = False
    user_id: Optional[str] = None
    error: Optional[str] = None


class AuthService:
    """Pure authentication service - no transport concerns."""
    
    def __init__(self):
        self._db = get_database()
        self._secret = config.JWT_SECRET
        self._algorithm = config.JWT_ALGORITHM
        self._expire_minutes = config.JWT_EXPIRE_MINUTES
    
    def register(self, username: str, password: str) -> RegisterResult:
        if not username or len(username) < 3 or len(username) > 20:
            return RegisterResult(error="Username must be 3-20 characters")
        
        if not password or len(password) < 6:
            return RegisterResult(error="Password must be at least 6 characters")
        
        if self._db.user_exists(username):
            return RegisterResult(error="Username already exists")
        
        password_hash = hash_password(password)
        
        if self._db.create_user(username, password_hash, username):
            logger.info("User registered: %s", username)
            return RegisterResult(success=True, user_id=username)
        
        return RegisterResult(error="Failed to create user")
    
    def authenticate(self, username: str, password: str) -> AuthResult:
        if not username or not password:
            return AuthResult(error="Username and password required")
        
        user = self._db.get_user(username)
        if not user:
            return AuthResult(error="Invalid credentials")
        
        if not verify_password(password, user.password_hash):
            return AuthResult(error="Invalid credentials")
        
        token = self._generate_token(username)
        logger.info("User authenticated: %s", username)
        return AuthResult(success=True, user_id=username, token=token)
    
    def validate_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def _generate_token(self, username: str) -> str:
        expiration = time.time() + self._expire_minutes * 60
        return jwt.encode(
            {"sub": username, "exp": expiration},
            self._secret,
            algorithm=self._algorithm
        )


_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
