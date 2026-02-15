# Standard library imports
import asyncio
import datetime
import json
import logging
import os
import sys
import threading
import time
from typing import Dict, Optional, Set

import bcrypt
import jwt
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from AloneChat import __version__ as __main_version__
from AloneChat.config import config

logger = logging.getLogger(__name__)

FEEDBACK_FILE = "feedback.json"
USER_DB_FILE = config.USER_DB_FILE


def hash_password(password: str) -> str:
    """Hash password with bcrypt (rounds=10 for performance)."""
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


class UserStatusManager:
    """
    Manages user online status with batched file persistence.
    
    Reduces file I/O by batching status updates and writing
    them periodically instead of on every status change.
    """
    
    _instance: Optional['UserStatusManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'UserStatusManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self._credentials: Dict[str, dict] = {}
        self._pending_status: Dict[str, bool] = {}
        self._dirty = False
        self._last_save = time.time()
        self._save_interval = 5.0
        self._save_lock = threading.Lock()
        
        self._load_credentials()
    
    def _load_credentials(self) -> None:
        """Load user credentials from file."""
        if os.path.exists(USER_DB_FILE):
            try:
                with open(USER_DB_FILE, 'r') as f:
                    self._credentials = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._credentials = {}
    
    def get_credentials(self) -> Dict[str, dict]:
        """Get user credentials dictionary."""
        return self._credentials
    
    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        return username in self._credentials
    
    def get_user(self, username: str) -> Optional[dict]:
        """Get user data."""
        return self._credentials.get(username)
    
    def add_user(self, username: str, password_hash: str) -> None:
        """Add a new user."""
        self._credentials[username] = {
            "password": password_hash,
            "is_online": False
        }
        self._dirty = True
        self._maybe_save()
    
    def update_online_status(self, username: str, is_online: bool) -> bool:
        """Update user online status (batched)."""
        if username not in self._credentials:
            return False
        
        self._credentials[username]['is_online'] = is_online
        self._pending_status[username] = is_online
        self._dirty = True
        self._maybe_save()
        return True
    
    def _maybe_save(self) -> None:
        """Save if enough time has passed or forced."""
        now = time.time()
        if self._dirty and (now - self._last_save) >= self._save_interval:
            self._save_credentials_sync()
    
    def _save_credentials_sync(self) -> None:
        """Synchronously save credentials to file."""
        with self._save_lock:
            try:
                with open(USER_DB_FILE, 'w') as f:
                    json.dump(self._credentials, f, indent=2)
                self._dirty = False
                self._last_save = time.time()
                self._pending_status.clear()
            except IOError as e:
                logger.error(f"Error saving user credentials: {e}")
    
    def force_save(self) -> None:
        """Force immediate save of pending changes."""
        if self._dirty:
            self._save_credentials_sync()
    
    def is_online(self, username: str) -> bool:
        """Check if user is online."""
        user = self._credentials.get(username)
        return user.get('is_online', False) if user else False


_user_manager = UserStatusManager()


def load_user_credentials() -> Dict[str, dict]:
    """Load user credentials (compatibility wrapper)."""
    return _user_manager.get_credentials()


def save_user_credentials(credentials) -> None:
    """Save user credentials (compatibility wrapper)."""
    global USER_CREDENTIALS
    USER_CREDENTIALS = credentials
    _user_manager.force_save()


def update_user_online_status(username: str, is_online: bool) -> bool:
    """Update user online status (optimized with batching)."""
    return _user_manager.update_online_status(username, is_online)


def load_feedbacks() -> list:
    """Load feedback data."""
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('feedbacks', [])
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load feedback: {e}")
    return []


def save_feedback(feedback: dict) -> bool:
    """Save feedback data."""
    feedbacks = load_feedbacks()
    feedbacks.append(feedback)
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump({'feedbacks': feedbacks}, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        logger.error(f"Failed to save feedback: {e}")
        return False


def update_feedback_status(feedback_id: str, status: str, reply: str = '') -> bool:
    """Update feedback status."""
    feedbacks = load_feedbacks()
    for i, feedback in enumerate(feedbacks):
        if feedback.get('id') == feedback_id:
            feedbacks[i]['status'] = status
            feedbacks[i]['reply'] = reply
            feedbacks[i]['reply_time'] = datetime.datetime.now().isoformat()
            try:
                with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'feedbacks': feedbacks}, f, ensure_ascii=False, indent=2)
                return True
            except IOError as e:
                logger.error(f"Failed to update feedback: {e}")
                return False
    return False


USER_CREDENTIALS: Dict[str, dict] = _user_manager.get_credentials()

JWT_SECRET = config.JWT_SECRET
JWT_ALGORITHM = config.JWT_ALGORITHM
JWT_EXPIRE_MINUTES = config.JWT_EXPIRE_MINUTES


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class FeedbackRequest(BaseModel):
    content: str


class TokenResponse(BaseModel):
    success: bool
    token: str | None = None
    message: str | None = None


SERVER_CONFIG = config.DEFAULT_SERVER_ADDRESS
if SERVER_CONFIG.startswith('ws://'):
    server_part = SERVER_CONFIG[5:]
    if ':' in server_part:
        SERVER_ADDR, SERVER_PORT = server_part.split(':')
        SERVER_PORT = int(SERVER_PORT)
    else:
        SERVER_ADDR = server_part
        SERVER_PORT = config.DEFAULT_SERVER_PORT
else:
    SERVER_ADDR = config.DEFAULT_HOST
    SERVER_PORT = config.DEFAULT_SERVER_PORT

try:
    SERVER = f"ws://{SERVER_ADDR}:{SERVER_PORT}"
except Exception as e:
    logger.error(f"Error connecting to server: {e}")
    sys.exit(1)

app = FastAPI(
    title="AloneChat api",
    version=__main_version__,
    description="api for AloneChat, a simple chat application.",
    contact={"name": "AloneChat Team"}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response


app.add_middleware(CacheControlMiddleware)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        whitelist = [
            "/login.html",
            "/api/login",
            "/api/register",
            "/static/",
            "/api/get_default_server"
        ]

        is_whitelisted = any(request.url.path.startswith(path) for path in whitelist)

        if is_whitelisted:
            return await call_next(request)

        referer = request.headers.get("referer")
        is_refresh = False

        if not is_refresh:
            token = None

            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

            if not token:
                cookies = request.cookies
                token = cookies.get("authToken")

            if not token:
                return Response(
                    status_code=307,
                    headers={"Location": "/login.html"}
                )

            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                if payload.get("exp") < time.time():
                    return Response(
                        status_code=307,
                        headers={"Location": "/login.html"}
                    )
                request.state.user = payload.get("sub")
            except jwt.PyJWTError:
                return Response(
                    status_code=307,
                    headers={"Location": "/login.html"}
                )

        return await call_next(request)


app.add_middleware(AuthenticationMiddleware)
