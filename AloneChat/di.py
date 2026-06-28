"""
Dependency injection container for AloneChat.

Single source of truth for all singletons. Replaces ``core/server/container.py``
and all ``get_*()`` module-level singletons. Each service receives its
dependencies (repos, other services) via ``__init__``. Lazy initialization with
thread-safe double-check locking.

Usage::

    from AloneChat.di import container

    auth_svc   = container.auth_service
    user_svc   = container.user_service
    friend_svc = container.friend_service

The module-level ``container`` instance is created at import time (cheap — all
real work is deferred until a property is first accessed).  Use ``container.reset()``
to drop every cached instance for tests or after a config reload.
"""

import threading
from typing import Optional

from .server.database import Database, get_database
from .server.repositories.user_repo import UserRepository
from .server.repositories.message_repo import MessageRepository
from .server.repositories.friend_repo import FriendRepository
from .server.auth import AuthService
from .server.user import UserService
from .server.message import MessageService
from .server.chat import ChatService
from .server.friend import FriendService


class Container:
    """Thread-safe, lazy-loading dependency injection container.

    Every property returns the same singleton instance across all callers.
    Uses double-check locking so that lock acquisition only occurs during
    the first access or after a ``reset()``.

    Dependency graph::

        db
         ├── user_repo ──────┬── auth_service ──┐
         ├── message_repo ───┬── user_service ───┤
         └── friend_repo ────┼── message_service │
                             ├── chat_service ───┘
                             └── friend_service
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        # -- Database -----------------------------------------------------------
        self._db: Optional[Database] = None

        # -- Repositories -------------------------------------------------------
        self._user_repo: Optional[UserRepository] = None
        self._message_repo: Optional[MessageRepository] = None
        self._friend_repo: Optional[FriendRepository] = None

        # -- Services -----------------------------------------------------------
        self._auth_service: Optional[AuthService] = None
        self._user_service: Optional[UserService] = None
        self._message_service: Optional[MessageService] = None
        self._chat_service: Optional[ChatService] = None
        self._friend_service: Optional[FriendService] = None

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    @property
    def db(self) -> Database:
        """Return the process-wide Database singleton (lazy)."""
        if self._db is None:
            with self._lock:
                if self._db is None:
                    self._db = get_database()
        return self._db

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------

    @property
    def user_repo(self) -> UserRepository:
        """Return the UserRepository, injecting the current Database."""
        if self._user_repo is None:
            with self._lock:
                if self._user_repo is None:
                    self._user_repo = UserRepository(db=self.db)
        return self._user_repo

    @property
    def message_repo(self) -> MessageRepository:
        """Return the MessageRepository, injecting the current Database."""
        if self._message_repo is None:
            with self._lock:
                if self._message_repo is None:
                    self._message_repo = MessageRepository(db=self.db)
        return self._message_repo

    @property
    def friend_repo(self) -> FriendRepository:
        """Return the FriendRepository, injecting the current Database."""
        if self._friend_repo is None:
            with self._lock:
                if self._friend_repo is None:
                    self._friend_repo = FriendRepository(db=self.db)
        return self._friend_repo

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    @property
    def auth_service(self) -> AuthService:
        """Return the AuthService, injecting the UserRepository."""
        if self._auth_service is None:
            with self._lock:
                if self._auth_service is None:
                    self._auth_service = AuthService(user_repo=self.user_repo)
        return self._auth_service

    @property
    def user_service(self) -> UserService:
        """Return the UserService, injecting UserRepository and AuthService."""
        if self._user_service is None:
            with self._lock:
                if self._user_service is None:
                    self._user_service = UserService(
                        user_repo=self.user_repo,
                        auth_service=self.auth_service,
                    )
        return self._user_service

    @property
    def message_service(self) -> MessageService:
        """Return the MessageService, injecting the MessageRepository."""
        if self._message_service is None:
            with self._lock:
                if self._message_service is None:
                    self._message_service = MessageService(
                        message_repo=self.message_repo,
                    )
        return self._message_service

    @property
    def chat_service(self) -> ChatService:
        """Return the ChatService, injecting the MessageRepository."""
        if self._chat_service is None:
            with self._lock:
                if self._chat_service is None:
                    self._chat_service = ChatService(
                        message_repo=self.message_repo,
                    )
        return self._chat_service

    @property
    def friend_service(self) -> FriendService:
        """Return the FriendService, injecting FriendRepository and UserService."""
        if self._friend_service is None:
            with self._lock:
                if self._friend_service is None:
                    self._friend_service = FriendService(
                        friend_repo=self.friend_repo,
                        user_repo=self.user_repo,
                    )
        return self._friend_service

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Drop every cached instance.

        The next property access lazily re-creates each service.  This is
        useful in tests or when the process needs to reconfigure without
        restarting.
        """
        with self._lock:
            self._db = None
            self._user_repo = None
            self._message_repo = None
            self._friend_repo = None
            self._auth_service = None
            self._user_service = None
            self._message_service = None
            self._chat_service = None
            self._friend_service = None

    def shutdown(self) -> None:
        """Perform orderly shutdown of services.

        Flushes status buffers and releases resources before dropping all
        cached instances.
        """
        if self._user_service is not None:
            try:
                self._user_service.shutdown()
            except Exception:
                pass
        self.reset()


# ---------------------------------------------------------------------------
# Module-level container instance
# ---------------------------------------------------------------------------

container = Container()
