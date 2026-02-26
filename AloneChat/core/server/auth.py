"""
Authentication service for AloneChat server.

Pure authentication logic without any HTTP/transport concerns.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Set

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


class TokenBlacklist:
    """Thread-safe token blacklist with automatic expiration cleanup."""
    
    def __init__(self, cleanup_interval: int = 300):
        self._blacklist: dict[str, float] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
    
    def add(self, token: str, expiry: float) -> None:
        with self._lock:
            self._blacklist[token] = expiry
            self._maybe_cleanup()
    
    def is_revoked(self, token: str) -> bool:
        with self._lock:
            expiry = self._blacklist.get(token)
            if expiry is None:
                return False
            if time.time() > expiry:
                del self._blacklist[token]
                return False
            return True
    
    def _maybe_cleanup(self) -> None:
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = time.time()
    
    def _cleanup(self) -> None:
        now = time.time()
        expired = [t for t, exp in self._blacklist.items() if now > exp]
        for t in expired:
            del self._blacklist[t]
        if expired:
            logger.debug("Cleaned up %d expired tokens from blacklist", len(expired))
    
    def size(self) -> int:
        with self._lock:
            return len(self._blacklist)


_token_blacklist = TokenBlacklist()


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
        if _token_blacklist.is_revoked(token):
            return None
        
        try:
            payload = jwt.decode(token, self._secret, algorithms=[self._algorithm])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def revoke_token(self, token: str) -> bool:
        try:
            payload = jwt.decode(
                token, 
                self._secret, 
                algorithms=[self._algorithm],
                options={"verify_exp": False}
            )
            expiry = payload.get("exp", 0)
            _token_blacklist.add(token, expiry)
            logger.info("Token revoked for user: %s", payload.get("sub"))
            return True
        except jwt.InvalidTokenError:
            return False
    
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
