# Standard library imports
import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote_plus

# Third-party imports
import websockets
from fastapi import HTTPException

# Local imports
from AloneChat import __version__ as __main_version__
from .routes_base import *
from ..core.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


@app.post("/api/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    logger.debug("Attempting register: username=%s", credentials.username)
    if credentials.username in USER_CREDENTIALS:
        logger.debug("Register failed: User %s already exists", credentials.username)
        return TokenResponse(success=False, message="Username already exists")

    if len(credentials.password) < 6:
        return TokenResponse(success=False, message="Password must be at least 6 characters")

    if len(credentials.username) < 3 or len(credentials.username) > 20:
        return TokenResponse(success=False, message="Username must be between 3-20 characters")

    logger.info("Register successful: User %s", credentials.username)

    USER_CREDENTIALS[credentials.username] = {
        "password": hash_password(credentials.password),
        "is_online": False
    }
    save_user_credentials(USER_CREDENTIALS)

    return TokenResponse(success=True, message="Registration successful")


@app.post("/api/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    logger.debug("Attempting login: username=%s", credentials.username)
    if credentials.username not in USER_CREDENTIALS:
        logger.debug("Login failed: User %s does not exist", credentials.username)
        return TokenResponse(success=False, message="Incorrect username or password")

    if not verify_password(credentials.password, USER_CREDENTIALS[credentials.username]['password']):
        logger.debug("Login failed: Password mismatch for user %s", credentials.username)
        return TokenResponse(success=False, message="Incorrect username or password")

    logger.info("Login successful: User %s", credentials.username)

    expiration = time.time() + JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": credentials.username, "exp": expiration},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    update_user_online_status(credentials.username, True)

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
        if username and username in ws_manager.sessions:
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

        auth = request.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]

        if not token:
            raise HTTPException(status_code=401, detail="No valid authentication token provided")

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        msg = Message(MessageType.TEXT, sender or username, message, target)

        if target:
            await ws_manager._send_to_target(msg)
        else:
            await ws_manager.broadcast(msg)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error sending message: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


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

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            username = payload.get("sub")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        try:
            ws_manager._ensure_queue(username)
        except Exception:
            if username not in ws_manager.message_queues:
                ws_manager.message_queues[username] = asyncio.Queue()

        try:
            msg_data = await asyncio.wait_for(
                ws_manager.message_queues[username].get(),
                timeout=30.0
            )
            try:
                msg = Message.deserialize(msg_data)
                return {
                    "success": True,
                    "sender": msg.sender,
                    "content": msg.content,
                    "type": msg.type.value
                }
            except Exception as e:
                logger.exception("Error deserializing message: %s", e)
                return {"success": False, "error": "Failed to deserialize message"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout waiting for message"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error listing messages: %s", e)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/get_default_server")
async def get_default_server():
    """Get default WebSocket server address from configuration."""
    return {
        "success": True,
        "default_server_address": config.DEFAULT_SERVER_ADDRESS
    }


from AloneChat.core.server.websocket_manager import UnifiedWebSocketManager

_ws_manager_instance: Optional[UnifiedWebSocketManager] = None


def get_ws_manager() -> UnifiedWebSocketManager:
    """Get or create the global WebSocket manager instance."""
    global _ws_manager_instance
    if _ws_manager_instance is None:
        _ws_manager_instance = UnifiedWebSocketManager()
    return _ws_manager_instance


class _WSManagerProxy:
    """Proxy class to provide legacy-style attribute access to UnifiedWebSocketManager."""
    
    def __getattr__(self, name: str) -> Any:
        manager = get_ws_manager()
        return getattr(manager, name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        manager = get_ws_manager()
        setattr(manager, name, value)


ws_manager = _WSManagerProxy()


@app.post("/api/feedback/submit")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """
    提交用户反馈
    """
    username = request.state.user
    if not username:
        raise HTTPException(status_code=401, detail="未登录")

    feedback_data = {
        "id": str(time.time()),
        "user": username,
        "content": feedback.content,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending",
        "reply": ""
    }

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
    username = request.state.user
    if not username:
        raise HTTPException(status_code=401, detail="未登录")

    feedbacks = load_feedbacks()
    user_feedbacks = [f for f in feedbacks if f["user"] == username]
    user_feedbacks.sort(key=lambda x: x["timestamp"], reverse=True)

    return {
        "success": True,
        "feedbacks": user_feedbacks
    }
