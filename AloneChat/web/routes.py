# Standard library imports
import datetime
import json
import os
import sys
import time
from typing import Dict, List

# 反馈数据文件路径
FEEDBACK_FILE = "feedback.json"

# Third-party imports
import bcrypt
import jwt
import psutil
import uvicorn
import getpass
import websockets
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Local imports
from AloneChat import __version__ as __main_version__
from AloneChat.config import config
from AloneChat.core.client.command import CommandSystem
from AloneChat.core.server.manager import WebSocketManager
from ..core.message.protocol import Message, MessageType

# Default server address configuration file
SERVER_CONFIG_FILE = "server_config.json"
USER_DB_FILE = config.USER_DB_FILE


# Load saved user credentials
def load_user_credentials():
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    # Initial users with hashed passwords
    return {
        "admin": {
            "password": hash_password(getpass.getpass("Admin user not found, set admin password: ")),
            "is_online": False
        }
    }


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
    token: str = None
    message: str = None


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


# Get default server address
@app.get("/api/get_default_server")
async def get_default_server():
    default_server = load_server_config()
    return {
        "success": True,
        "default_server_address": default_server
    }


# Set default server address
@app.post("/api/set_default_server")
async def set_default_server(server_address: str = Query(..., description="Default server address")):
    # Validate server address format
    if not server_address.startswith("ws://") and not server_address.startswith("wss://"):
        raise HTTPException(status_code=400, detail="Server address must start with ws:// or wss://")

    if save_server_config(server_address):
        return {
            "success": True,
            "message": "Default server address updated",
            "new_server_address": server_address
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save default server address")


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

app.mount("/static", StaticFiles(directory="AloneChat/web/static", html=False, check_dir=True, follow_symlink=False),
          name="static")


@app.get("/")
async def read_root():
    # Force redirect to specified login URL
    # Return local login page
    return FileResponse("AloneChat/web/static/login.html")


@app.get("/login.html")
async def read_login():
    # Force redirect to specified login URL
    # Return local login page
    return FileResponse("AloneChat/web/static/login.html")


@app.get("/index.html")
async def read_index():
    # Force redirect to specified login URL
    # Only accessible after login
    return FileResponse("AloneChat/web/static/index.html")


@app.get("/admin.html")
async def read_admin(request: Request):
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
        role = payload.get("role")
        if role != "admin":
            # Not an admin, redirect to regular user page
            return Response(
                status_code=307,
                headers={"Location": "/index.html"}
            )
    except jwt.PyJWTError:
        # Token is invalid, redirect to login page
        return Response(
            status_code=307,
            headers={"Location": "/login.html"}
        )

    # Is an admin, return admin page
    return FileResponse("AloneChat/web/static/admin.html")


@app.post("/api/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    # Check if username already exists
    if credentials.username in USER_CREDENTIALS:
        return TokenResponse(success=False, message="Username already exists")

    # Check password length
    if len(credentials.password) < 6:
        return TokenResponse(success=False, message="Password must be at least 6 characters")

    # Check username length
    if len(credentials.username) < 3 or len(credentials.username) > 20:
        return TokenResponse(success=False, message="Username must be between 3-20 characters")

    # Hash password and save
    USER_CREDENTIALS[credentials.username] = {
        "password": hash_password(credentials.password),
        "is_online": False
    }
    # Persist to file
    save_user_credentials(USER_CREDENTIALS)

    return TokenResponse(success=True, message="Registration successful")


@app.post("/api/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    # Verify user credentials
    print(f"Attempting login: username={credentials.username}")
    if credentials.username not in USER_CREDENTIALS:
        print(f"Login failed: User {credentials.username} does not exist")
        return TokenResponse(success=False, message="Incorrect username or password")

    if not verify_password(credentials.password, USER_CREDENTIALS[credentials.username]['password']):
        print(f"Login failed: Password mismatch for user {credentials.username}")
        return TokenResponse(success=False, message="Incorrect username or password")

    print(f"Login successful: User {credentials.username}")

    # Determine user role - supports multiple admin usernames
    admin_usernames = {"admin", "administrator"}
    role = "admin" if credentials.username.lower() in admin_usernames else "user"

    # Generate JWT token
    expiration = time.time() + JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": credentials.username, "exp": expiration, "role": role},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    # Update user online status
    update_user_online_status(credentials.username, True)

    # Return different messages based on role
    if role == "admin":
        return TokenResponse(success=True, token=token, message="Admin login successful")
    else:
        return TokenResponse(success=True, token=token, message="Login successful")


SERVER_ADDR = "localhost"


@app.post("/send")
async def send_message(sender: str, message: str, target: str | None = None):
    """
    Send a message to the connected WebSocket.

    Args:
        sender : The sender of the message.
        message (str): The message to send.
        target (str, optional): Target user for the message, if needed
    """
    # noinspection PyShadowingNames
    try:
        msg = CommandSystem.process(message, sender, target)
        async with websockets.connect(SERVER) as websocket:
            await websocket.send(msg.serialize())
    except Exception as e:
        print(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/recv")
async def recv_messages():
    """
    List all messages in the chat.

    Returns:
        List[Message]: List of all messages.
    """
    # noinspection PyShadowingNames
    try:
        async with websockets.connect(SERVER) as websocket:
            msg = await websocket.recv()
        return msg
    except Exception as e:
        print(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Admin permission verification dependency
async def admin_required(request: Request):
    # Get token from request header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token provided")

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        role = payload.get("role")
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Get singleton instance of WebSocketManager
ws_manager = WebSocketManager.get_instance()


@app.post("/api/admin/kick-user")
async def kick_user(username: str, user_data: dict = Depends(admin_required)):
    """
    Kick out specified user - real implementation
    """
    # Check if user is online
    if username not in ws_manager.sessions:
        raise HTTPException(status_code=404, detail=f"User {username} is not online")

    # Admin cannot kick themselves
    current_user = user_data.get("sub")
    if username == current_user:
        raise HTTPException(status_code=400, detail="Admin cannot kick themselves")

    # Get user's WebSocket connection and close it
    websocket = ws_manager.sessions[username]
    # noinspection PyShadowingNames
    try:
        # Send kick message
        kick_msg = Message(MessageType.TEXT, "SERVER", "You have been kicked from the chat room by an admin")
        await websocket.send(kick_msg.serialize())
        # Close connection
        await websocket.close(code=1008, reason="Kicked by admin")
        # Remove from session management
        del ws_manager.sessions[username]
        ws_manager.clients.discard(websocket)

        # Update user online status
        update_user_online_status(username, False)

        return {
            "success": True,
            "message": f"User {username} has been kicked"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error kicking user: {str(e)}")


@app.get("/api/admin/chat-history")
async def get_chat_history():
    """
    Get chat history - simulated implementation
    Note: In a real application, chat history should be loaded from database or file system
    """
    return None


@app.get("/api/admin/all-users")
async def get_all_users():
    """
    Get all user list (including password hash) - real implementation
    """
    # Load all user credentials
    all_users = load_user_credentials()
    users_list = []
    admin_usernames = {"admin", "administrator"}

    for username, user_data in all_users.items():
        role = "admin" if username.lower() in admin_usernames else "user"
        users_list.append({
            "username": username,
            "password_hash": user_data['password'],
            "role": role,
            "is_online": user_data['is_online']
        })

    return {
        "users": users_list,
        "note": "Passwords are stored as bcrypt hashes and cannot be recovered. For security reasons, please do not disclose this information to unauthorized personnel."
    }


@app.post("/api/feedback/submit")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """
    提交用户反馈
    """
    # 获取当前用户
    username = request.state.user
    if not username:
        raise HTTPException(status_code=401, detail="未登录")

    # 创建反馈对象
    feedback_data = {
        "id": str(time.time()),  # 使用时间戳作为唯一ID
        "user": username,
        "content": feedback.content,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending",
        "reply": ""
    }

    # 保存反馈
    if save_feedback(feedback_data):
        return {
            "success": True,
            "message": "反馈提交成功",
            "feedback_id": feedback_data["id"]
        }
    else:
        raise HTTPException(status_code=500, detail="保存反馈失败")


@app.get("/api/feedback/my-feedback")
async def get_my_feedback(request: Request):
    """
    获取当前用户的反馈
    """
    # 获取当前用户
    username = request.state.user
    if not username:
        raise HTTPException(status_code=401, detail="未登录")

    # 加载所有反馈
    feedbacks = load_feedbacks()
    # 筛选当前用户的反馈
    user_feedbacks = [f for f in feedbacks if f["user"] == username]
    # 按时间倒序排列
    user_feedbacks.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "success": True,
        "feedbacks": user_feedbacks
    }


@app.get("/api/admin/feedbacks")
async def get_all_feedbacks(user_data: dict = Depends(admin_required)):
    """
    获取所有用户的反馈 - 管理员专用
    """
    # 加载所有反馈
    feedbacks = load_feedbacks()
    # 按时间倒序排列
    feedbacks.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "success": True,
        "feedbacks": feedbacks
    }


@app.post("/api/admin/feedback/reply")
async def reply_feedback(reply: FeedbackReplyRequest, user_data: dict = Depends(admin_required)):
    """
    回复用户反馈 - 管理员专用
    """
    # 更新反馈状态和回复
    if update_feedback_status(reply.feedback_id, reply.status, reply.reply):
        return {
            "success": True,
            "message": "反馈回复成功"
        }
    else:
        raise HTTPException(status_code=404, detail="未找到该反馈")


@app.get("/api/admin/system-status")
async def get_system_status():
    """
    Get system status - real implementation
    """
    # Get system information
    version = __main_version__

    # Calculate server uptime (from application startup)
    # noinspection PyGlobalUndefined
    global server_start_time
    try:
        uptime_seconds = time.time() - server_start_time
        uptime = str(datetime.timedelta(seconds=int(uptime_seconds)))
    except NameError:
        # If server start time is not defined, set to current time
        server_start_time = time.time()
        uptime = "Just started"

    # Get real online user count
    online_users = len(ws_manager.sessions)
    total_users = len(USER_CREDENTIALS)
    cpu_usage = f"{psutil.cpu_percent(interval=1)}%"
    memory_usage = f"{psutil.virtual_memory().percent}%"

    return {
        "version": version,
        "uptime": uptime,
        "online_users": online_users,
        "total_users": total_users,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "note": "To see real online users, please ensure both WebSocket server and web server are running"
    }


def run(api_port=SERVER_PORT + 1):
    """
    Run the FastAPI application with Uvicorn server.

    Args:
        api_port (int): Port for the web.
    """
    # noinspection PyShadowingNames
    try:
        uvicorn.run(app, port=api_port)
    except Exception as e:
        print(f"Error running web server: {e}")
