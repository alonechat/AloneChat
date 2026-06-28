"""
WebSocket handler for AloneChat API.

Handles WS connect, authenticate, message relay via
container.message_service.set_send_callback(), and disconnect.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from AloneChat.di import container
from AloneChat.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

_active_connections: dict[str, set[WebSocket]] = {}


@router.websocket("")
async def ws_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint: authenticate, relay messages, handle disconnect."""
    await websocket.accept()

    # --- Authenticate ---
    token = None
    auth_header = websocket.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="No token")
        return

    username = await container.auth_service.validate_token(token)
    if not username:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # --- Register connection ---
    await container.user_service.set_online(username)
    if username not in _active_connections:
        _active_connections[username] = set()
    _active_connections[username].add(websocket)

    async def _send(data: str) -> None:
        try:
            await websocket.send_text(data)
        except Exception:
            pass

    container.message_service.set_send_callback(username, _send)

    # --- Message loop ---
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = Message.deserialize(raw)
            except Exception as exc:
                logger.warning("Deserialization error: %s", exc)
                continue

            if msg.type == MessageType.HEARTBEAT:
                pong = Message(MessageType.HEARTBEAT, "SERVER", "pong")
                await websocket.send_text(pong.serialize())
                continue

            if msg.target:
                await container.message_service.send_message(
                    sender=username,
                    recipient=msg.target,
                    content=msg.content,
                    msg_type=msg.type,
                )
                await websocket.send_text(msg.serialize())
                await container.chat_service.record_message(
                    username, msg.target, msg.content,
                )
            else:
                all_users = container.user_service.get_all_users()
                recipients = [
                    u["user_id"] for u in all_users if u["user_id"] != username
                ]
                if recipients:
                    await container.message_service.broadcast_message(
                        sender=username,
                        content=msg.content,
                        recipients=recipients,
                        msg_type=msg.type,
                    )
                await container.chat_service.record_message(
                    username, "*", msg.content,
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket error for %s: %s", username, exc)
    finally:
        if username:
            _active_connections[username].discard(websocket)
            if not _active_connections[username]:
                del _active_connections[username]
            container.message_service.set_send_callback(username, None)
            await container.user_service.set_offline(username)
            logger.info("WebSocket disconnected: %s", username)
