# Standard library imports
import datetime
import json
import os
import sys
import time
from typing import Dict

# Third-party imports
import bcrypt
import jwt
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Local imports
from AloneChat import __version__ as __main_version__
from AloneChat.config import config

# Default server address configuration file
SERVER_CONFIG_FILE = "server_config.json"
# Feedback file path
FEEDBACK_FILE = "feedback.json"
USER_DB_FILE = config.USER_DB_FILE


# Load saved user credentials
def load_user_credentials():
    user_credentials = {}
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r') as f:
                user_credentials = json.load(f)
        except (json.JSONDecodeError, IOError):
            user_credentials = {}
    # Initial users with hashed passwords
    # Check if admin user exists
    if "admin" not in user_credentials:
        # Generate random 12-character password
        import secrets
        import string
        password_chars = string.ascii_letters + string.digits + string.punctuation
        admin_password = ''.join(secrets.choice(password_chars) for _ in range(12))
        print(f"\n=== Auto-generated admin password (displayed once): {admin_password} ===\n")
        user_credentials["admin"] = {
            "password": hash_password(admin_password),
            "is_online": False
        }
        # Save to file
        save_user_credentials(user_credentials)
    return user_credentials


# Save user credentials to file
def save_user_credentials(credentials):
    # noinspection PyShadowingNames
    try:
        with open(USER_DB_FILE, 'w') as f:
            json.dump(credentials, f, indent=2)
    except IOError as e:
        print(f"Error saving user credentials: {e}")


# Update user online status
def update_user_online_status(username, is_online):
    if username in USER_CREDENTIALS:
        USER_CREDENTIALS[username]['is_online'] = is_online
        save_user_credentials(USER_CREDENTIALS)
        return True
    return False


# Load default server address configuration
def load_server_config():
    if os.path.exists(SERVER_CONFIG_FILE):
        try:
            with open(SERVER_CONFIG_FILE, 'r') as f:
                config_data = json.load(f)
                return config_data.get('default_server_address', config.DEFAULT_SERVER_ADDRESS)
        except (json.JSONDecodeError, IOError):
            return config.DEFAULT_SERVER_ADDRESS
    return config.DEFAULT_SERVER_ADDRESS


# 加载反馈数据
def load_feedbacks():
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('feedbacks', [])
        except (json.JSONDecodeError, IOError) as e:
            print(f"加载反馈数据失败: {e}")
            return []
    return []


# 保存反馈数据
def save_feedback(feedback):
    feedbacks = load_feedbacks()
    feedbacks.append(feedback)
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump({'feedbacks': feedbacks}, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"保存反馈数据失败: {e}")
        return False


# 更新反馈状态
def update_feedback_status(feedback_id, status, reply=''):
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
                print(f"更新反馈数据失败: {e}")
                return False
    return False


# Save default server address configuration
def save_server_config(server_address):
    # noinspection PyShadowingNames
    try:
        with open(SERVER_CONFIG_FILE, 'w') as f:
            json.dump({'default_server_address': server_address}, f, indent=2)
        return True
    except IOError as e:
        print(f"Error saving server config: {e}")
        return False


# Hash password function
def hash_password(password):
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


# Verify password function
def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


# Initialize user credentials
USER_CREDENTIALS: Dict[str, dict] = load_user_credentials()

# JWT configuration
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


class FeedbackReplyRequest(BaseModel):
    feedback_id: str
    status: str
    reply: str


class TokenResponse(BaseModel):
    success: bool
    token: str | None = None
    message: str | None = None


# Load server address and port from configuration
SERVER_CONFIG = load_server_config()
# Parse server address, handle complete URL format
if SERVER_CONFIG.startswith('ws://'):
    # Remove ws:// prefix
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
    print(f"Error connecting to server at {SERVER_ADDR}:{SERVER_PORT}: {e}")
    print("Ensure the server is running and accessible.")
    sys.exit(1)

app = FastAPI(
    title="AloneChat web",
    version=__main_version__,
    description="web for AloneChat, a simple chat application.",
    contact={
        "name": "AloneChat Team"
    }
)

# Add response header middleware to control static file caching
# Allow all CORS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enable GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Custom middleware to add cache control headers for static files
class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add cache control headers for static files
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response


app.add_middleware(CacheControlMiddleware)


# Authentication middleware - ensure all accesses except refresh require login
class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Whitelist paths - accessible without login
        whitelist = [
            "/login.html",
            "/api/login",
            "/api/register",
            "/static/",
            "/api/get_default_server"
        ]

        # Check if it's a whitelist path
        is_whitelisted = any(request.url.path.startswith(path) for path in whitelist)

        if is_whitelisted:
            return await call_next(request)

        # Check if it's a refresh operation (judged by Referer)
        referer = request.headers.get("referer")
        is_refresh = bool(referer)  # Simplified judgment:只要有referer就认为是刷新操作

        # If it's a new access (non-refresh) and not a whitelist path, check JWT token
        if not is_refresh:
            # Get token from request header or cookie
            token = None

            # Try to get from request header
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

            # If not in request header, try to get from cookie
            if not token:
                cookies = request.cookies
                token = cookies.get("authToken")

            if not token:
                # No valid token, redirect to login page
                return Response(
                    status_code=307,
                    headers={"Location": "/login.html"}
                )

            # Verify JWT token
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                # Check if token has expired
                if payload.get("exp") < time.time():
                    return Response(
                        status_code=307,
                        headers={"Location": "/login.html"}
                    )
                # Token is valid, add user information to request state
                request.state.user = payload.get("sub")
            except jwt.PyJWTError:
                # Token is invalid, redirect to login page
                return Response(
                    status_code=307,
                    headers={"Location": "/login.html"}
                )

        return await call_next(request)


app.add_middleware(AuthenticationMiddleware)
