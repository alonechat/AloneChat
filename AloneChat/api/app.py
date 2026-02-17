"""
AloneChat API - HTTP/WebSocket interaction layer.

This module handles all transport concerns and delegates business logic
to the server layer services.
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Set

import jwt
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from AloneChat import __version__
from AloneChat.config import config
from AloneChat.core.message import Message, MessageType
from AloneChat.core.server import (
    get_auth_service,
    get_user_service,
    get_message_service,
    get_chat_service,
    get_friend_service,
    Status,
)

logger = logging.getLogger(__name__)

JWT_SECRET = config.JWT_SECRET
JWT_ALGORITHM = config.JWT_ALGORITHM


class TokenCache:
    """LRU cache for decoded JWT tokens."""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._max_size = max_size
        self._ttl = ttl
    
    def get(self, token: str) -> Optional[dict]:
        if token in self._cache:
            payload, expiry = self._cache[token]
            if time.time() < expiry:
                return payload
            del self._cache[token]
        return None
    
    def set(self, token: str, payload: dict) -> None:
        if len(self._cache) >= self._max_size:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
        self._cache[token] = (payload, time.time() + self._ttl)
    
    def invalidate(self, token: str) -> None:
        self._cache.pop(token, None)


_token_cache = TokenCache()


def decode_token(token: str) -> Optional[dict]:
    cached = _token_cache.get(token)
    if cached:
        if cached.get("exp", 0) > time.time():
            return cached
        _token_cache.invalidate(token)
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        _token_cache.set(token, payload)
        return payload
    except jwt.PyJWTError:
        return None


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None


class FeedbackRequest(BaseModel):
    content: str


class PrivateMessageRequest(BaseModel):
    recipient: str
    content: str


class UserStatusRequest(BaseModel):
    status: str


class FriendRequestModel(BaseModel):
    to_user: str
    message: str = ""


class FriendActionRequest(BaseModel):
    request_id: str


class SetRemarkRequest(BaseModel):
    friend_id: str
    remark: str


class SearchUserRequest(BaseModel):
    query: str


_active_websockets: Dict[str, Set[WebSocket]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AloneChat API starting up")
    yield
    logger.info("AloneChat API shutting down")


app = FastAPI(
    title="AloneChat API",
    version=__version__,
    description="AloneChat API Server",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        whitelist = [
            "/api/login", "/api/register", "/api/get_default_server",
            "/static/", "/login.html", "/events", "/recv", "/recv/batch"
        ]
        
        if any(request.url.path.startswith(p) for p in whitelist):
            return await call_next(request)
        
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        
        if not token:
            token = request.cookies.get("authToken")
        
        if not token:
            return Response(status_code=307, headers={"Location": "/login.html"})
        
        payload = decode_token(token)
        if not payload or payload.get("exp", 0) < time.time():
            _token_cache.invalidate(token)
            return Response(status_code=307, headers={"Location": "/login.html"})
        
        request.state.user = payload.get("sub")
        return await call_next(request)


app.add_middleware(AuthMiddleware)


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _get_token_user(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    payload = decode_token(token)
    return payload.get("sub") if payload else None


@app.post("/api/register", response_model=TokenResponse)
async def register(credentials: RegisterRequest):
    result = get_auth_service().register(credentials.username, credentials.password)
    if not result.success:
        return TokenResponse(success=False, message=result.error)
    return TokenResponse(success=True, message="Registration successful")


@app.post("/api/login", response_model=TokenResponse)
async def login(credentials: LoginRequest):
    result = get_auth_service().authenticate(credentials.username, credentials.password)
    if not result.success:
        return TokenResponse(success=False, message=result.error)
    
    get_user_service().set_online(result.user_id)
    return TokenResponse(success=True, token=result.token, message="Login successful")


@app.post("/api/logout")
async def logout(request: Request):
    username = _get_user(request)
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        _token_cache.invalidate(auth.split(" ", 1)[1])
    
    get_user_service().set_offline(username)
    return {"success": True, "message": "Logout successful"}


@app.get("/api/get_default_server")
async def get_default_server():
    return {"success": True, "default_server_address": config.DEFAULT_SERVER_ADDRESS}


@app.get("/api/user/status/{user_id}")
async def get_user_status(user_id: str, request: Request):
    _get_user(request)
    
    user_service = get_user_service()
    info = user_service.get_user_info(user_id)
    
    if not info:
        return {"success": False, "user_id": user_id, "status": "unknown"}
    
    return {
        "success": True,
        "user_id": user_id,
        "status": info.status.name.lower(),
        "is_online": info.status != Status.OFFLINE
    }


@app.post("/api/user/status")
async def set_user_status(status_req: UserStatusRequest, request: Request):
    username = _get_user(request)
    
    status_map = {"online": Status.ONLINE, "away": Status.AWAY, 
                  "busy": Status.BUSY, "offline": Status.OFFLINE}
    
    status_str = status_req.status.lower()
    if status_str not in status_map:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    get_user_service().set_status(username, status_map[status_str])
    return {"success": True, "user_id": username, "status": status_str}


@app.get("/api/users/online")
async def get_online_users(request: Request):
    _get_user(request)
    users = get_user_service().get_online_users()
    return {"success": True, "users": users, "count": len(users)}


@app.get("/api/users/all")
async def get_all_users(request: Request):
    _get_user(request)
    users = get_user_service().get_all_users()
    return {"success": True, "users": users, "count": len(users)}


@app.post("/api/chat/private")
async def send_private_message(msg_req: PrivateMessageRequest, request: Request):
    sender = _get_user(request)
    
    if not msg_req.content or not msg_req.content.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if sender == msg_req.recipient:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    
    user_service = get_user_service()
    chat_service = get_chat_service()
    message_service = get_message_service()
    
    is_online = user_service.is_online(msg_req.recipient)
    
    chat_service.record_message(sender, msg_req.recipient, msg_req.content, is_online)
    
    message = Message(MessageType.TEXT, sender, msg_req.content, target=msg_req.recipient)
    
    await message_service.send_to_user(msg_req.recipient, message)
    await message_service.send_to_user(sender, message)
    
    return {"success": True, "message": "Message sent"}


@app.get("/api/chat/history/{other_user}")
async def get_chat_history(other_user: str, request: Request, limit: int = 50):
    current_user = _get_user(request)
    
    history = get_chat_service().get_history(current_user, other_user, limit)
    return {"success": True, "messages": history, "count": len(history)}


@app.get("/api/chat/recent")
async def get_recent_chats(request: Request, limit: int = 10):
    current_user = _get_user(request)
    
    chats = get_chat_service().get_recent_chats(current_user, limit)
    return {"success": True, "chats": chats, "count": len(chats)}


@app.get("/api/chat/pending")
async def get_pending_messages(request: Request):
    current_user = _get_user(request)
    
    pending = get_chat_service().get_pending(current_user)
    messages = [
        {"sender": p.sender, "content": p.message, "timestamp": p.timestamp}
        for p in pending
    ]
    return {"success": True, "messages": messages, "count": len(messages)}


@app.post("/api/chat/pending/clear")
async def clear_pending_messages(request: Request):
    current_user = _get_user(request)
    
    count = get_chat_service().clear_pending(current_user)
    return {"success": True, "cleared_count": count}


@app.get("/api/stats")
async def get_stats(request: Request):
    _get_user(request)
    
    user_service = get_user_service()
    chat_service = get_chat_service()
    
    return {
        "success": True,
        "stats": {
            "users": {
                "online": len(user_service.get_online_users()),
            },
            "chats": {
                "sessions": chat_service.get_session_count(),
                "messages": chat_service.get_total_message_count()
            }
        }
    }


@app.get("/api/friends")
async def get_friends(request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    friends = friend_service.get_friends(current_user)
    
    return {
        "success": True,
        "friends": [f.to_dict() for f in friends],
        "count": len(friends)
    }


@app.post("/api/friends/request")
async def send_friend_request(req: FriendRequestModel, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    result = friend_service.send_friend_request(current_user, req.to_user, req.message)
    
    if result.get('success'):
        message_service = get_message_service()
        notification = Message(
            MessageType.TEXT,
            "SYSTEM",
            json.dumps({
                "type": "friend_request",
                "from": current_user,
                "message": req.message
            }),
            target=req.to_user
        )
        await message_service.send_to_user(req.to_user, notification)
    
    return result


@app.post("/api/friends/accept")
async def accept_friend_request(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    result = friend_service.accept_friend_request(req.request_id, current_user)
    
    if result.get('success'):
        friend_request = friend_service._db.get_friend_request(req.request_id)
        if friend_request:
            from_user = friend_request.get('from_user')
            if from_user:
                message_service = get_message_service()
                notification = Message(
                    MessageType.TEXT,
                    "SYSTEM",
                    json.dumps({
                        "type": "friend_request_accepted",
                        "by": current_user
                    }),
                    target=from_user
                )
                await message_service.send_to_user(from_user, notification)
    
    return result


@app.post("/api/friends/reject")
async def reject_friend_request(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    result = friend_service.reject_friend_request(req.request_id, current_user)
    
    return result


@app.post("/api/friends/remove")
async def remove_friend(req: FriendActionRequest, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    result = friend_service.remove_friend(current_user, req.request_id)
    
    return result


@app.post("/api/friends/remark")
async def set_friend_remark(req: SetRemarkRequest, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    result = friend_service.set_remark(current_user, req.friend_id, req.remark)
    
    return result


@app.get("/api/friends/requests/pending")
async def get_pending_friend_requests(request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    requests = friend_service.get_pending_requests(current_user)
    
    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests)
    }


@app.get("/api/friends/requests/sent")
async def get_sent_friend_requests(request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    requests = friend_service.get_sent_requests(current_user)
    
    return {
        "success": True,
        "requests": [r.to_dict() for r in requests],
        "count": len(requests)
    }


@app.get("/api/friends/search")
async def search_users(request: Request, query: str, limit: int = 20):
    current_user = _get_user(request)
    
    if not query or len(query) < 1:
        return {"success": True, "users": [], "count": 0}
    
    friend_service = get_friend_service()
    users = friend_service.search_users(query, current_user, limit)
    
    return {
        "success": True,
        "users": users,
        "count": len(users)
    }


@app.get("/api/friends/check/{user_id}")
async def check_friendship(user_id: str, request: Request):
    current_user = _get_user(request)
    
    friend_service = get_friend_service()
    is_friend = friend_service.is_friend(current_user, user_id)
    
    return {
        "success": True,
        "is_friend": is_friend,
        "user_id": user_id
    }


@app.post("/send")
async def send_message(request: Request):
    username = _get_token_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        message = body.get("message")
        target = body.get("target")
    else:
        params = request.query_params
        message = params.get("message")
        target = params.get("target")
    
    if not message:
        raise HTTPException(status_code=400, detail="Missing message")
    
    msg = Message(MessageType.TEXT, username, message, target=target)
    message_service = get_message_service()
    
    if target:
        await message_service.send_to_user(target, msg)
    else:
        await message_service.broadcast(msg, exclude={username})
    
    return {"success": True}


@app.get("/recv")
async def recv_message(request: Request):
    username = _get_token_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    queue = get_message_service().get_queue(username)
    msg_data = await queue.get(timeout=30.0)
    
    if msg_data:
        msg = Message.deserialize(msg_data)
        return {
            "success": True,
            "sender": msg.sender,
            "content": msg.content,
            "type": msg.type.value
        }
    
    return {"success": False, "error": "Timeout"}


@app.get("/recv/batch")
async def recv_messages_batch(request: Request, max_messages: int = 10, timeout: float = 5.0):
    username = _get_token_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    queue = get_message_service().get_queue(username)
    messages = []
    
    first = await queue.get(timeout=timeout)
    if first:
        try:
            msg = Message.deserialize(first)
            messages.append({"sender": msg.sender, "content": msg.content, "type": msg.type.value})
        except Exception:
            pass
    
        while len(messages) < max_messages:
            msg_data = queue.get_nowait()
            if not msg_data:
                break
            try:
                msg = Message.deserialize(msg_data)
                messages.append({"sender": msg.sender, "content": msg.content, "type": msg.type.value})
            except Exception:
                pass
    
    return {"success": True, "messages": messages, "count": len(messages)}


@app.get("/events")
async def message_events(request: Request):
    username = _get_token_user(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    message_service = get_message_service()
    message_service.register_sse_client(username)
    queue = message_service.get_queue(username)
    
    async def event_generator():
        yield ": connected\n\n"
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                msg_data = await queue.get(timeout=30.0)
                if msg_data:
                    try:
                        msg = Message.deserialize(msg_data)
                        data = json.dumps({
                            "sender": msg.sender,
                            "content": msg.content,
                            "type": msg.type.value
                        })
                        yield f"data: {data}\n\n"
                    except Exception:
                        yield ": heartbeat\n\n"
                else:
                    yield ": heartbeat\n\n"
        finally:
            message_service.unregister_sse_client(username)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    token = None
    
    auth_header = websocket.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    
    if not token:
        token = websocket.query_params.get("token")
    
    if not token:
        await websocket.close(code=1008, reason="No token")
        return
    
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    username = payload.get("sub")
    if not username:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    user_service = get_user_service()
    message_service = get_message_service()
    
    user_service.set_online(username)
    
    if username not in _active_websockets:
        _active_websockets[username] = set()
    _active_websockets[username].add(websocket)
    
    async def send_func(data: str):
        try:
            await websocket.send_text(data)
        except Exception:
            pass
    
    message_service.register_connection(username, send_func)
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                msg = Message.deserialize(data)
                
                if msg.type == MessageType.HEARTBEAT:
                    pong = Message(MessageType.HEARTBEAT, "SERVER", "pong")
                    await websocket.send_text(pong.serialize())
                    continue
                
                if msg.target:
                    await message_service.send_to_user(msg.target, msg)
                    await message_service.send_to_user(username, msg)
                    get_chat_service().record_message(username, msg.target, msg.content)
                else:
                    await message_service.broadcast(msg, exclude={username})
            
            except Exception as e:
                logger.warning("WebSocket message error: %s", e)
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
    finally:
        _active_websockets[username].discard(websocket)
        if not _active_websockets[username]:
            del _active_websockets[username]
        
        message_service.unregister_connection(username)
        user_service.set_offline(username)
        
        logger.info("WebSocket disconnected: %s", username)


FEEDBACK_FILE = "feedback.json"


@app.post("/api/feedback/submit")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    username = _get_user(request)
    
    import os
    import datetime
    
    feedback_data = {
        "id": str(time.time()),
        "user": username,
        "content": feedback.content,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending"
    }
    
    feedbacks = []
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                feedbacks = data.get('feedbacks', [])
        except Exception:
            pass
    
    feedbacks.append(feedback_data)
    
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump({'feedbacks': feedbacks}, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "Feedback submitted"}
    except Exception as e:
        logger.error("Failed to save feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@app.get("/api/feedback/my-feedback")
async def get_my_feedback(request: Request):
    username = _get_user(request)
    
    import os
    
    if not os.path.exists(FEEDBACK_FILE):
        return {"success": True, "feedbacks": []}
    
    try:
        with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            feedbacks = [fb for fb in data.get('feedbacks', []) if fb.get("user") == username]
            feedbacks.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return {"success": True, "feedbacks": feedbacks}
    except Exception:
        return {"success": True, "feedbacks": []}
