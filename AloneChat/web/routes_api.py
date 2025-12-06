# Standard library imports
from typing import List

# Third-party imports
import psutil
import websockets
from fastapi import Depends

# Local imports
from AloneChat import __version__ as __main_version__
from AloneChat.core.client.command import CommandSystem
from .routes_base import *
from ..core.message.protocol import Message, MessageType


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


# Get singleton instance of WebSocketManager (imported lazily to avoid circular import)
from AloneChat.core.server.manager import WebSocketManager

ws_manager = WebSocketManager.get_instance()


# noinspection PyUnresolvedReferences
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
        uptime_seconds = time.time() - server_start_time  # type: ignore
        uptime = str(datetime.timedelta(seconds=int(uptime_seconds)))
    except NameError:
        # If server start time is not defined, set to current time
        server_start_time = time.time()
        uptime = "Just started"

    # Get real online user count
    # noinspection PyUnresolvedReferences
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
