"""
Message routes for AloneChat API.
"""

import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from AloneChat.core.message import Message, MessageType
from AloneChat.core.server import (
    get_message_service,
    get_chat_service,
    get_user_service,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["messages"])


_active_websockets: Dict[str, Set[WebSocket]] = {}


def _get_token_user(request: Request):
    from AloneChat.api.middleware import decode_token

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    payload = decode_token(token)
    return payload.get("sub") if payload else None


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/send")
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


@router.get("/recv")
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


@router.get("/recv/batch")
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


@router.get("/events")
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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    from AloneChat.api.middleware import decode_token

    await websocket.accept()

    username = None
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
        if username:
            _active_websockets[username].discard(websocket)
            if not _active_websockets[username]:
                del _active_websockets[username]

            message_service.unregister_connection(username)
            user_service.set_offline(username)

            logger.info("WebSocket disconnected: %s", username)
