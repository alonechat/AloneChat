# Standard library imports

import asyncio
from typing import Any, Optional, List
from urllib.parse import quote_plus

# Third-party imports
import psutil
import websockets
from fastapi import Depends, HTTPException
from pydantic import BaseModel

# Local imports
from AloneChat import __version__ as __main_version__
from .routes_base import *
from ..core.message.protocol import Message, MessageType


def get_current_user(request: Request) -> str:
    """Extract and validate current user from Authorization bearer token."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token provided")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(username)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


class FriendRequestCreate(BaseModel):
    to_username: str
    message: str | None = ""


class ConversationSettingUpdate(BaseModel):
    pinned: bool | None = None
    muted: bool | None = None



@app.post("/api/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    username = credentials.username.strip()

    # Check if username already exists (SQLite first, then legacy JSON)
    if STORE.user_exists(username) or username in USER_CREDENTIALS:
        return TokenResponse(success=False, message="Username already exists")

    # Check password length
    if len(credentials.password) < 6:
        return TokenResponse(success=False, message="Password must be at least 6 characters")

    # Check username length
    if len(username) < 3 or len(username) > 20:
        return TokenResponse(success=False, message="Username must be between 3-20 characters")

    # Hash password and save
    password_hash = hash_password(credentials.password)

    # Persist in SQLite
    created = STORE.create_user(username, password_hash)
    if not created:
        return TokenResponse(success=False, message="Username already exists")

    # Legacy JSON store (kept for backward compatibility)
    USER_CREDENTIALS[username] = {
        "password": hash_password(credentials.password),
        "is_online": False
    }
    # Persist to file
    save_user_credentials(USER_CREDENTIALS)

    return TokenResponse(success=True, message="Registration successful")


@app.post("/api/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    username = credentials.username.strip()
    print(f"Attempting login: username={username}")

    # Prefer SQLite store
    stored_hash = STORE.get_password_hash(username)
    if stored_hash is not None:
        if not verify_password(credentials.password, stored_hash):
            print(f"Login failed: Password mismatch for user {username}")
            return TokenResponse(success=False, message="Incorrect username or password")
    else:
        # Fallback to legacy JSON store
        if username not in USER_CREDENTIALS:
            print(f"Login failed: User {username} does not exist")
            return TokenResponse(success=False, message="Incorrect username or password")
        if not verify_password(credentials.password, USER_CREDENTIALS[username]['password']):
            print(f"Login failed: Password mismatch for user {username}")
            return TokenResponse(success=False, message="Incorrect username or password")

        # If login succeeds from legacy store, migrate to SQLite.
        try:
            STORE.create_user(username, USER_CREDENTIALS[username]['password'])
        except Exception:
            pass

    print(f"Login successful: User {username}")

    # Determine user role - supports multiple admin usernames
    admin_usernames = {"admin", "administrator"}
    role = "admin" if username.lower() in admin_usernames else "user"

    # Generate JWT token
    expiration = time.time() + JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": role},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    # Update user online status
    try:
        STORE.set_user_online(username, True)
    except Exception:
        pass
    update_user_online_status(username, True)

    # Return different messages based on role
    if role == "admin":
        return TokenResponse(success=True, token=token, message="Admin login successful")
    else:
        return TokenResponse(success=True, token=token, message="Login successful")


@app.post("/api/logout")
async def logout(request: Request):
    """
    Logout endpoint
    - Extracts token from Authorization header
    - Updates user online status
    - Notifies WebSocket server of user logout
    - Closes user's WebSocket connection if exists
    """
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No valid authentication token provided")

    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if username:
        try:
            update_user_online_status(username, False)
        except Exception:
            pass
        try:
            STORE.set_user_online(username, False)
        except Exception:
            pass

    try:
        if token:
            sep = "&" if "?" in SERVER else "?"
            ws_url = f"{SERVER}{sep}token={quote_plus(token)}"
            try:
                async with websockets.connect(ws_url) as websocket:
                    leave_msg = Message(MessageType.LEAVE, username or "", "").serialize()
                    await websocket.send(leave_msg)
                    try:
                        await websocket.close(code=1000, reason="User logged out via API")
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    try:
        # noinspection ExceptionTooBroad
        if username and username in ws_manager.sessions:
            # noinspection PyUnresolvedReferences
            websocket = ws_manager.sessions.get(username)
            try:
                notice = Message(MessageType.TEXT, "SERVER", "You have been logged out by API").serialize()
                await websocket.send(notice)
                await websocket.close(code=1000, reason="User logged out via API")
                del ws_manager.sessions[username]
                ws_manager.clients.discard(websocket)
            except Exception:
                pass
    except Exception:
        pass

    return {"success": True, "message": "Logout successful"}


SERVER_ADDR = "localhost"

@app.post("/send")
async def send_message(request: Request):
    """
    Send a message to the connected WebSocket.
    Accept JSON body or query params，request Authorization token
    As URL parameter `token` give back to WebSocket server.
    """
    try:
        sender = None
        message = None
        target = None

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            sender = body.get("sender")
            message = body.get("message")
            target = body.get("target")
        else:
            params = request.query_params
            sender = params.get("sender")
            message = params.get("message")
            target = params.get("target")

        if not message:
            raise HTTPException(status_code=400, detail="Missing message")

        # From Authorization extract token
        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]

        if not token:
            raise HTTPException(status_code=401, detail="No valid authentication token provided")

        # Verify token and get username
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Create message
        msg = Message(MessageType.TEXT, sender or username, message, target)

        # Private message routing
        if target:
            # Enforce friendship approval for DMs
            if not STORE.are_friends(username, target):
                raise HTTPException(status_code=403, detail="You can only DM approved friends")
            # Store history
            try:
                STORE.add_message(username, target, message)
            except PermissionError:
                raise HTTPException(status_code=403, detail="You can only DM approved friends")
            except Exception as e:
                print(f"Warning: failed to persist message: {e}")
            await ws_manager._send_to_target(msg)
        else:
            await ws_manager.broadcast(msg)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/users")
async def list_users(request: Request, q: str = "", limit: int = 50):
    _ = get_current_user(request)
    return {"success": True, "users": STORE.list_users(q=q, limit=limit)}


@app.get("/api/friends")
async def list_friends(request: Request):
    username = get_current_user(request)
    friends = STORE.list_friends(username)
    return {"success": True, "friends": friends}


@app.post("/api/friends/request")
async def create_friend_request(request: Request, payload: FriendRequestCreate):
    username = get_current_user(request)
    ok, msg = STORE.create_friend_request(username, payload.to_username.strip(), payload.message or "")
    return {"success": ok, "message": msg}


@app.get("/api/friends/requests/incoming")
async def incoming_friend_requests(request: Request):
    username = get_current_user(request)
    reqs = STORE.list_incoming_requests(username)
    return {
        "success": True,
        "requests": [
            {
                "id": r.id,
                "from_user": r.from_user,
                "to_user": r.to_user,
                "message": r.message,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in reqs
        ],
    }


@app.get("/api/friends/requests/outgoing")
async def outgoing_friend_requests(request: Request):
    username = get_current_user(request)
    reqs = STORE.list_outgoing_requests(username)
    return {
        "success": True,
        "requests": [
            {
                "id": r.id,
                "from_user": r.from_user,
                "to_user": r.to_user,
                "message": r.message,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in reqs
        ],
    }


@app.post("/api/friends/requests/{request_id}/accept")
async def accept_friend_request(request_id: int, request: Request):
    username = get_current_user(request)
    # Read request row first so we can notify both parties if accepted.
    fr = STORE.get_friend_request(int(request_id))
    ok, msg = STORE.accept_friend_request(request_id, username)

    # Notify both users (especially the requester) to refresh conversations.
    # This prevents the requester from waiting until the first DM arrives.
    try:
        if ok and fr is not None:
            from_user = str(fr.from_user)
            to_user = str(fr.to_user)
            # System event message; GUI client treats it as a signal, not a chat message.
            evt_to_requester = Message(
                MessageType.TEXT,
                "SERVER",
                f"[[EVENT friend_accepted other={to_user}]]",
            )
            evt_to_acceptor = Message(
                MessageType.TEXT,
                "SERVER",
                f"[[EVENT friend_accepted other={from_user}]]",
            )

            for u, evt in ((from_user, evt_to_requester), (to_user, evt_to_acceptor)):
                try:
                    ws_manager._ensure_queue(u)  # type: ignore[attr-defined]
                    ws_manager.message_queues[u].put_nowait(evt.serialize())
                except Exception:
                    # Best-effort notification
                    pass
    except Exception:
        pass

    return {"success": ok, "message": msg}


@app.post("/api/friends/requests/{request_id}/reject")
async def reject_friend_request(request_id: int, request: Request):
    username = get_current_user(request)
    ok, msg = STORE.reject_friend_request(request_id, username)
    return {"success": ok, "message": msg}


@app.get("/api/conversations")
async def list_conversations(request: Request, limit: int = 50):
    username = get_current_user(request)
    return {"success": True, "conversations": STORE.list_conversations(username, limit=limit)}


@app.post("/api/conversations/{with_user}/settings")
async def update_conversation_settings(with_user: str, payload: ConversationSettingUpdate, request: Request):
    """Update per-user settings for a DM conversation (pin/mute)."""
    username = get_current_user(request)
    other = (with_user or "").strip()
    if not other or other.lower() == "global":
        raise HTTPException(status_code=400, detail="Invalid conversation")

    msg_parts: list[str] = []
    ok_any = False
    if payload.pinned is not None:
        ok, msg = STORE.set_conversation_pinned(username, other, bool(payload.pinned))
        ok_any = ok_any or ok
        msg_parts.append(msg)
        if not ok:
            return {"success": False, "message": msg}
    if payload.muted is not None:
        ok, msg = STORE.set_conversation_muted(username, other, bool(payload.muted))
        ok_any = ok_any or ok
        msg_parts.append(msg)
        if not ok:
            return {"success": False, "message": msg}

    if not ok_any:
        return {"success": False, "message": "No changes"}
    return {"success": True, "message": "; ".join([p for p in msg_parts if p])}


@app.get("/api/messages/history")
async def get_history(request: Request, with_user: str, limit: int = 50):
    username = get_current_user(request)
    other = with_user.strip()
    history = STORE.get_history(username, other, limit=limit)
    return {"success": True, "with": other, "messages": history}


@app.get("/recv")
async def recv_messages(request: Request):
    """
    Poll WebSocket server to receive one message and send back to HTTP client。
    Put Authorization token as a URL parameter `token` give back to WS。
    """
    try:
        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]

        if not token:
            raise HTTPException(status_code=401, detail="No valid authentication token provided")

        # Verify token and get username
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Ensure bounded message queue exists for user
        try:
            ws_manager._ensure_queue(username)  # type: ignore[attr-defined]
        except Exception:
            if username not in ws_manager.message_queues:
                ws_manager.message_queues[username] = asyncio.Queue()

        # Wait for a message from the queue
        try:
            # Wait for message with a timeout
            msg_data = await asyncio.wait_for(
                ws_manager.message_queues[username].get(),
                timeout=30.0
            )
            # Deserialize the message
            try:
                msg = Message.deserialize(msg_data)
                # Return formatted message as JSON
                return {
                    "success": True,
                    "sender": msg.sender,
                    "content": msg.content,
                    "type": msg.type.value
                }
            except Exception as e:
                # Log internal error details but return a generic message to the client
                print(f"Error deserializing message: {e}")
                return {"success": False, "error": "Failed to deserialize message"}
        except asyncio.TimeoutError:
            # Return empty response on timeout
            return {"success": False, "error": "Timeout waiting for message"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Get default server address
@app.get("/api/get_default_server")
async def get_default_server():
    """Get default WebSocket server address from configuration."""
    return {
        "success": True,
        "default_server_address": config.DEFAULT_SERVER_ADDRESS
    }


# Set default server address - Removed: Server address is now managed via config.py
# This endpoint is no longer available as server configuration is centralized in config.py


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


# Get singleton instance of UnifiedWebSocketManager (modern replacement for legacy WebSocketManager)
from AloneChat.core.server.websocket_manager import UnifiedWebSocketManager

# Create a global instance for API routes to use
_ws_manager_instance: Optional[UnifiedWebSocketManager] = None

def get_ws_manager() -> UnifiedWebSocketManager:
    """Get or create the global WebSocket manager instance."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = UnifiedWebSocketManager()
    return _ws_manager_instance

# Legacy compatibility: ws_manager attribute access
class _WSManagerProxy:
    """Proxy class to provide legacy-style attribute access to UnifiedWebSocketManager."""
    
    def __getattr__(self, name: str) -> Any:
        manager = get_ws_manager()
        return getattr(manager, name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        manager = get_ws_manager()
        setattr(manager, name, value)

ws_manager = _WSManagerProxy()


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
        "note": (
            "Passwords are stored as bcrypt hashes and cannot be recovered. "
            "For security reasons, please do not disclose this information to unauthorized personnel."
        )
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
        "note": "To see real online users, please ensure both WebSocket server and api server are running"
    }
