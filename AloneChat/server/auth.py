"""
Authentication service for AloneChat.

Pure authentication logic without any HTTP/transport concerns.
MIGRATED from core/server/auth.py — receives UserRepository via __init__
instead of calling module-level get_*() singletons.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import jwt

from AloneChat.config import config
from AloneChat.crypto import hash_password, verify_password
from AloneChat.server.repositories.user_repo import UserRepository

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
    """Pure authentication service — no transport concerns.

    Receives ``UserRepository`` via ``__init__`` instead of reaching for
    module-level singletons.  All database access goes through the injected
    repository.
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo
        self._secret = config.JWT_SECRET
        self._algorithm = config.JWT_ALGORITHM
        self._expire_minutes = config.JWT_EXPIRE_MINUTES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def register(self, username: str, password: str) -> RegisterResult:
        """Register a new user account.

        Returns a :class:`RegisterResult` whose ``success`` flag indicates
        whether the account was created.
        """
        if not username or len(username) < 3 or len(username) > 20:
            return RegisterResult(error="Username must be 3-20 characters")

        if not password or len(password) < 6:
            return RegisterResult(error="Password must be at least 6 characters")

        if self._user_repo.user_exists(username):
            return RegisterResult(error="Username already exists")

        password_hash = hash_password(password)

        if self._user_repo.create_user(username, password_hash, username):
            logger.info("User registered: %s", username)
            return RegisterResult(success=True, user_id=username)

        return RegisterResult(error="Failed to create user")

    async def login(self, username: str, password: str) -> AuthResult:
        """Authenticate a user and return a JWT token on success.

        Returns an :class:`AuthResult` whose ``token`` field carries the
        signed JWT when authentication succeeds.
        """
        if not username or not password:
            return AuthResult(error="Username and password required")

        user = self._user_repo.get_user(username)
        if not user:
            return AuthResult(error="Invalid credentials")

        if not verify_password(password, user.password_hash):
            return AuthResult(error="Invalid credentials")

        token = self._generate_token(username)
        logger.info("User authenticated: %s", username)
        return AuthResult(success=True, user_id=username, token=token)

    async def validate_token(self, token: str) -> Optional[str]:
        """Decode and validate a JWT token.

        Returns the ``sub`` claim (username) when the token is valid, or
        ``None`` when it has expired or is otherwise invalid.
        """
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._algorithm]
            )
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_token(self, username: str) -> str:
        """Create a signed JWT for *username* with the configured expiry."""
        expiration = time.time() + self._expire_minutes * 60
        return jwt.encode(
            {"sub": username, "exp": expiration},
            self._secret,
            algorithm=self._algorithm,
        )
